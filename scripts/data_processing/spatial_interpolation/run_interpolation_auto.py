"""
空间插值自动化脚本 - 带断点续传和进度可视化
功能：
    1. 从数据库读取 QM 校正后的站点数据
    2. 使用插值方法（IDW/Kriging）扩展到整个研究区域
    3. 支持断点续传（按日期分批处理）
    4. 实时进度显示和性能统计
    5. 自动保存插值结果到数据库

技术细节：
    - 插值方法：反距离加权 (IDW) 或 克里金 (Kriging)
    - 网格分辨率：可配置（默认 0.1°×0.1°）
    - 研究区域：华北平原（可配置）
    - 分批策略：按日期分批，每批处理 N 天
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
import json
import numpy as np
import pandas as pd
from typing import Tuple, List, Dict, Optional
from tqdm import tqdm

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 插值方法（需要安装 scipy 和 scikit-learn）
try:
    from scipy.interpolate import griddata
    from sklearn.neighbors import KDTree
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("⚠ 警告：scipy 或 sklearn 未安装，插值功能将受限")
    print("请运行：pip install scipy scikit-learn")

try:
    from pykrige.ok import OrdinaryKriging
    PYKRIGE_AVAILABLE = True
except ImportError:
    PYKRIGE_AVAILABLE = False
    print("⚠ 警告：pykrige 未安装，克里金插值不可用")
    print("请运行：pip install pykrige")

# 数据库连接
from dotenv import load_dotenv
import psycopg2
import os

load_dotenv()

# ==================== 配置区域 ====================

CONFIG = {
    # 研究区域范围（华北平原）
    'region': {
        'lat_min': 34.0,
        'lat_max': 42.0,
        'lon_min': 113.0,
        'lon_max': 120.0
    },
    
    # 网格分辨率（度）
    'resolution': 0.1,  # 0.1° × 0.1° ≈ 10km × 10km
    
    # 插值方法：'idw' 或 'kriging'
    'interpolation_method': 'idw',
    
    # IDW 参数
    'idw': {
        'power': 2,  # 距离的幂次，越大越重视近点
        'max_neighbors': 10  # 最大邻居数
    },
    
    # 克里金参数
    'kriging': {
        'variogram_model': 'linear',  # 变异函数模型
        'nlags': 10  # 变异函数滞后数
    },
    
    # 分批处理配置
    'batch_size': 30,  # 每次处理 30 天
    
    # 时间范围
    'start_date': '1990-01-01',
    'end_date': '2023-12-31',
    
    # 数据库配置
    'database': {
        'source_table': 'qm_corrected_grid_data',
        'target_table': 'interpolated_grid_data',
        'batch_size': 10000  # 写入数据库的批量大小
    },
    
    # 输出配置
    'output_dir': 'data/processed/spatial_interpolation',
    'save_csv': False,  # 是否保存 CSV 备份
    'progress_file': 'progress.json'
}


# ==================== 进度管理 ====================

class ProgressManager:
    """进度管理器 - 支持断点续传"""
    
    def __init__(self, progress_file: Path):
        self.progress_file = progress_file
        self.progress = {
            'completed_dates': [],
            'failed_dates': [],
            'current_batch': None,
            'start_time': None,
            'end_time': None,
            'statistics': {
                'total_days': 0,
                'processed_days': 0,
                'failed_days': 0,
                'total_records': 0
            }
        }
        self.load_progress()
    
    def load_progress(self):
        """加载进度"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    saved_progress = json.load(f)
                    self.progress.update(saved_progress)
                    print(f"✓ 已加载进度记录：已完成 {len(self.progress['completed_dates'])} 天")
            except Exception as e:
                print(f"⚠ 加载进度失败：{e}，将从头开始")
    
    def save_progress(self):
        """保存进度"""
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, indent=2, ensure_ascii=False)
    
    def start_batch(self, batch_dates: List[datetime]):
        """开始批次"""
        self.progress['current_batch'] = {
            'batch_dates': [d.isoformat() for d in batch_dates],
            'start_time': datetime.now().isoformat()
        }
        self.save_progress()
    
    def complete_date(self, date: datetime, records_count: int):
        """完成日期"""
        self.progress['completed_dates'].append(date.isoformat())
        self.progress['statistics']['processed_days'] += 1
        self.progress['statistics']['total_records'] += records_count
        self.progress['current_batch'] = None
        self.save_progress()
    
    def fail_date(self, date: datetime, error: str):
        """失败日期"""
        self.progress['failed_dates'].append({
            'date': date.isoformat(),
            'error': error
        })
        self.progress['statistics']['failed_days'] += 1
        self.progress['current_batch'] = None
        self.save_progress()
    
    def is_date_completed(self, date: datetime) -> bool:
        """检查日期是否已完成"""
        return date.isoformat() in self.progress['completed_dates']
    
    def finish_all(self):
        """完成所有"""
        self.progress['end_time'] = datetime.now().isoformat()
        self.save_progress()


# ==================== 数据管理器 ====================

class DataManager:
    """数据库数据管理类"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': os.getenv('POSTGRES_PORT', '5432'),
            'dbname': os.getenv('POSTGRES_DB', 'gra_env_db'),
            'user': os.getenv('POSTGRES_USER', 'admin'),
            'password': os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
        }
    
    def connect(self):
        """建立数据库连接"""
        return psycopg2.connect(**self.db_config)
    
    def get_qm_data_for_dates(
        self,
        dates: List[datetime],
        variables: List[str]
    ) -> pd.DataFrame:
        """
        获取指定日期的 QM 校正数据
        
        Returns:
            DataFrame: 包含站点坐标、日期、各变量的校正数据
        """
        conn = self.connect()
        
        # 构建日期列表（转换为 date 类型）
        date_strings = [d.strftime('%Y-%m-%d') for d in dates]
        date_placeholders = ', '.join([f"DATE(%s)" for _ in dates])
        
        # 查询 QM 校正数据
        query = f"""
            SELECT DISTINCT ON (latitude, longitude, DATE(timestamp))
                latitude,
                longitude,
                timestamp,
                {', '.join([f'{var}_corrected' for var in variables])}
            FROM {CONFIG['database']['source_table']}
            WHERE DATE(timestamp) IN ({date_placeholders})
            ORDER BY latitude, longitude, DATE(timestamp), id
        """
        
        # 构建参数列表（每个日期作为一个参数）
        params = date_strings
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        return df
    
    def create_target_table(self, variables: List[str]):
        """创建目标表"""
        conn = self.connect()
        cur = conn.cursor()
        
        # 构建变量列
        var_columns = ',\n'.join([
            f"        {var}_interpolated DECIMAL(8, 4)" for var in variables
        ])
        
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {CONFIG['database']['target_table']} (
                id BIGSERIAL PRIMARY KEY,
                latitude DECIMAL(10, 6) NOT NULL,
                longitude DECIMAL(10, 6) NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
{var_columns},
                interpolation_method VARCHAR(50) DEFAULT 'IDW',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_interpolated_lat_lon
            ON {CONFIG['database']['target_table']} (latitude, longitude);
            
            CREATE INDEX IF NOT EXISTS idx_interpolated_timestamp
            ON {CONFIG['database']['target_table']} (timestamp);
        """
        
        cur.execute(create_sql)
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✓ 目标表 {CONFIG['database']['target_table']} 已创建/验证")
    
    def write_interpolated_data(
        self,
        data: pd.DataFrame,
        variables: List[str],
        batch_size: int = 10000
    ):
        """写入插值结果到数据库"""
        conn = self.connect()
        cur = conn.cursor()
        
        # 构建插入 SQL
        var_columns = ', '.join([f'{var}_interpolated' for var in variables])
        var_values = ', '.join(['%s'] * len(variables))
        
        insert_sql = f"""
            INSERT INTO {CONFIG['database']['target_table']} (
                latitude, longitude, timestamp,
                {var_columns},
                interpolation_method
            ) VALUES (%s, %s, %s, {var_values}, %s)
        """
        
        # 批量插入
        batch_data = []
        total_records = 0
        
        for idx, row in data.iterrows():
            # 转换 numpy 类型为 Python 原生类型
            values = [
                float(row['latitude']),
                float(row['longitude']),
                row['timestamp'],
            ]
            
            # 添加变量值
            for var in variables:
                val = row.get(f'{var}_interpolated')
                values.append(float(val) if pd.notna(val) else None)
            
            # 插值方法
            values.append(CONFIG['interpolation_method'].upper())
            
            batch_data.append(tuple(values))
            
            # 达到批量大小时写入
            if len(batch_data) >= batch_size:
                cur.executemany(insert_sql, batch_data)
                total_records += len(batch_data)
                batch_data = []
        
        # 写入剩余数据
        if batch_data:
            cur.executemany(insert_sql, batch_data)
            total_records += len(batch_data)
        
        conn.commit()
        cur.close()
        conn.close()
        
        return total_records


# ==================== 插值器 ====================

class SpatialInterpolator:
    """空间插值器"""
    
    def __init__(
        self,
        region: Dict,
        resolution: float,
        method: str = 'idw'
    ):
        """
        初始化插值器
        
        Args:
            region: 研究区域范围
            resolution: 网格分辨率
            method: 插值方法
        """
        self.region = region
        self.resolution = resolution
        self.method = method
        
        # 生成目标网格
        self.grid_lats, self.grid_lons = self._create_grid()
        
        # 创建 KD 树用于快速搜索
        self.kdtree = None
        self.station_coords = None
        
        print(f"✓ 插值器初始化完成")
        print(f"  研究区域：{region['lat_min']:.2f}°N - {region['lat_max']:.2f}°N, "
              f"{region['lon_min']:.2f}°E - {region['lon_max']:.2f}°E")
        print(f"  网格分辨率：{resolution}° × {resolution}°")
        print(f"  网格点数：{len(self.grid_lats)} × {len(self.grid_lons)} = "
              f"{len(self.grid_lats) * len(self.grid_lons):,}")
    
    def _create_grid(self) -> Tuple[np.ndarray, np.ndarray]:
        """创建规则网格"""
        lats = np.arange(
            self.region['lat_min'],
            self.region['lat_max'] + self.resolution / 2,
            self.resolution
        )
        lons = np.arange(
            self.region['lon_min'],
            self.region['lon_max'] + self.resolution / 2,
            self.resolution
        )
        return lats, lons
    
    def prepare_stations(
        self,
        station_data: pd.DataFrame,
        variable: str
    ):
        """
        准备站点数据
        
        Args:
            station_data: 站点数据（包含 lat, lon 和变量值）
            variable: 变量名
        """
        # 提取有效数据
        valid_mask = (
            station_data['latitude'].notna() &
            station_data['longitude'].notna() &
            station_data[f'{variable}_corrected'].notna()
        )
        
        valid_data = station_data[valid_mask]
        
        if len(valid_data) < 3:
            raise ValueError(f"有效站点数不足：{len(valid_data)}")
        
        # 存储站点坐标
        self.station_coords = valid_data[['latitude', 'longitude']].values
        self.kdtree = KDTree(self.station_coords)
        
        return valid_data
    
    def interpolate_idw(
        self,
        values: np.ndarray,
        power: int = 2,
        max_neighbors: int = 10
    ) -> np.ndarray:
        """
        反距离加权插值 (IDW)
        
        Args:
            values: 站点值
            power: 距离的幂次
            max_neighbors: 最大邻居数
        
        Returns:
            插值结果网格
        """
        if self.kdtree is None or self.station_coords is None:
            raise ValueError("请先调用 prepare_stations()")
        
        # 生成网格
        grid_lon, grid_lat = np.meshgrid(self.grid_lons, self.grid_lats)
        grid_points = np.column_stack([grid_lat.ravel(), grid_lon.ravel()])
        
        # 查找最近的邻居
        distances, indices = self.kdtree.query(grid_points, k=max_neighbors)
        
        # IDW 插值
        result = np.zeros(len(grid_points))
        
        for i in range(len(grid_points)):
            dist = distances[i]
            idx = indices[i]
            
            # 避免除零
            dist = np.maximum(dist, 1e-10)
            
            # 计算权重
            weights = 1.0 / (dist ** power)
            weights = weights / weights.sum()
            
            # 插值
            result[i] = np.sum(weights * values[idx])
        
        return result.reshape(len(self.grid_lats), len(self.grid_lons))
    
    def interpolate_kriging(
        self,
        values: np.ndarray,
        variogram_model: str = 'linear',
        nlags: int = 10
    ) -> np.ndarray:
        """
        普通克里金插值
        
        Args:
            values: 站点值
            variogram_model: 变异函数模型
            nlags: 变异函数滞后数
        
        Returns:
            插值结果网格
        """
        if not PYKRIGE_AVAILABLE:
            raise ImportError("pykrige 未安装")
        
        if self.kdtree is None or self.station_coords is None:
            raise ValueError("请先调用 prepare_stations()")
        
        # 克里金插值
        ok = OrdinaryKriging(
            self.station_coords[:, 1],  # lon
            self.station_coords[:, 0],  # lat
            values,
            variogram_model=variogram_model,
            nlags=nlags,
            verbose=False,
            enable_plotting=False
        )
        
        # 生成网格
        grid_lon, grid_lat = np.meshgrid(self.grid_lons, self.grid_lats)
        
        # 克里金预测
        z, ss = ok.execute('grid', self.grid_lons, self.grid_lats)
        
        return z
    
    def interpolate(
        self,
        station_data: pd.DataFrame,
        variable: str,
        **kwargs
    ) -> pd.DataFrame:
        """
        执行插值
        
        Args:
            station_data: 站点数据
            variable: 变量名
            **kwargs: 插值参数
        
        Returns:
            插值结果 DataFrame
        """
        # 准备站点数据
        valid_data = self.prepare_stations(station_data, variable)
        values = valid_data[f'{variable}_corrected'].values
        
        # 执行插值
        if self.method.lower() == 'idw':
            power = kwargs.get('power', CONFIG['idw']['power'])
            max_neighbors = kwargs.get('max_neighbors', CONFIG['idw']['max_neighbors'])
            z = self.interpolate_idw(values, power, max_neighbors)
        elif self.method.lower() == 'kriging':
            variogram_model = kwargs.get('variogram_model', CONFIG['kriging']['variogram_model'])
            nlags = kwargs.get('nlags', CONFIG['kriging']['nlags'])
            z = self.interpolate_kriging(values, variogram_model, nlags)
        else:
            raise ValueError(f"不支持的插值方法：{self.method}")
        
        # 转换为 DataFrame
        grid_lon, grid_lat = np.meshgrid(self.grid_lons, self.grid_lats)
        
        result = pd.DataFrame({
            'latitude': grid_lat.ravel(),
            'longitude': grid_lon.ravel(),
            f'{variable}_interpolated': z.ravel()
        })
        
        return result


# ==================== 主执行器 ====================

class InterpolationExecutor:
    """插值执行器"""
    
    def __init__(self, config: Dict):
        """
        初始化执行器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.variables = ['temperature', 'precipitation', 'wind_speed', 'relative_humidity']
        
        # 创建输出目录
        self.output_dir = Path(config['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 进度管理器
        self.progress_mgr = ProgressManager(
            self.output_dir / config['progress_file']
        )
        
        # 数据管理器
        self.data_mgr = DataManager()
        
        # 创建插值器
        self.interpolator = SpatialInterpolator(
            region=config['region'],
            resolution=config['resolution'],
            method=config['interpolation_method']
        )
        
        # 创建目标表
        self.data_mgr.create_target_table(self.variables)
        
        print(f"✓ 插值执行器初始化完成")
        print(f"  插值方法：{config['interpolation_method'].upper()}")
        print(f"  输出目录：{self.output_dir}")
    
    def generate_date_batches(
        self,
        start_date: datetime,
        end_date: datetime,
        batch_size: int
    ) -> List[List[datetime]]:
        """生成日期批次"""
        batches = []
        current_date = start_date
        batch = []
        
        while current_date <= end_date:
            if not self.progress_mgr.is_date_completed(current_date):
                batch.append(current_date)
                
                if len(batch) >= batch_size:
                    batches.append(batch)
                    batch = []
            
            current_date += timedelta(days=1)
        
        # 添加剩余批次
        if batch:
            batches.append(batch)
        
        return batches
    
    def run(self):
        """执行插值"""
        print("\n" + "="*80)
        print("  空间插值自动化脚本")
        print("="*80)
        
        # 显示配置
        print(f"\n【配置信息】")
        print(f"  插值方法：{self.config['interpolation_method'].upper()}")
        print(f"  网格分辨率：{self.config['resolution']}°")
        print(f"  时间范围：{self.config['start_date']} 到 {self.config['end_date']}")
        print(f"  批次大小：{self.config['batch_size']} 天/批")
        
        # 计算总天数
        start_date = datetime.strptime(self.config['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(self.config['end_date'], '%Y-%m-%d')
        total_days = (end_date - start_date).days + 1
        
        self.progress_mgr.progress['statistics']['total_days'] = total_days
        self.progress_mgr.progress['start_time'] = datetime.now().isoformat()
        
        print(f"  总天数：{total_days:,} 天")
        print(f"  预计网格点数：{len(self.interpolator.grid_lats) * len(self.interpolator.grid_lons):,}")
        
        # 生成批次
        batches = self.generate_date_batches(
            start_date,
            end_date,
            self.config['batch_size']
        )
        
        print(f"  待处理批次：{len(batches)} 批")
        
        # 处理每个批次
        batch_num = 0
        success_count = 0
        fail_count = 0
        
        for batch_dates in batches:
            batch_num += 1
            
            # 显示进度条
            processed_days = self.progress_mgr.progress['statistics']['processed_days']
            progress_pct = (processed_days / total_days) * 100
            bar_filled = int(processed_days / total_days * 50)
            
            print(f"\n{'='*80}")
            print(f"【批次 {batch_num}/{len(batches)}】{batch_dates[0].strftime('%Y-%m-%d')} - {batch_dates[-1].strftime('%Y-%m-%d')}")
            print(f"进度：{'='*bar_filled}>{' '*(50-bar_filled)} {progress_pct:.1f}%")
            print(f"{'='*80}")
            
            # 开始批次
            self.progress_mgr.start_batch(batch_dates)
            
            try:
                # 从数据库获取 QM 校正数据
                qm_data = self.data_mgr.get_qm_data_for_dates(batch_dates, self.variables)
                
                if len(qm_data) == 0:
                    print(f"⚠ 该批次没有 QM 数据，跳过")
                    for date in batch_dates:
                        self.progress_mgr.complete_date(date, 0)
                    continue
                
                print(f"  获取到 {len(qm_data)} 条站点数据")
                
                # 按日期分组处理
                for date in batch_dates:
                    date_str = date.strftime('%Y-%m-%d')
                    date_data = qm_data[qm_data['timestamp'].dt.date == date.date()]
                    
                    if len(date_data) < 3:
                        print(f"  ⚠ {date_str}: 站点数据不足 ({len(date_data)} 个)，跳过")
                        self.progress_mgr.fail_date(date, "站点数据不足")
                        fail_count += 1
                        continue
                    
                    try:
                        # 对每个变量进行插值
                        interpolated_results = []
                        
                        for var in self.variables:
                            # 执行插值
                            result = self.interpolator.interpolate(
                                date_data,
                                var,
                                **self.config.get(self.config['interpolation_method'], {})
                            )
                            interpolated_results.append(
                                result[f'{var}_interpolated']
                            )
                            
                            # 显示插值统计
                            print(f"    {var}: "
                                  f"min={result[f'{var}_interpolated'].min():.2f}, "
                                  f"max={result[f'{var}_interpolated'].max():.2f}, "
                                  f"mean={result[f'{var}_interpolated'].mean():.2f}")
                        
                        # 合并结果
                        for i, var in enumerate(self.variables):
                            if i == 0:
                                final_result = pd.DataFrame({
                                    'latitude': result['latitude'],
                                    'longitude': result['longitude'],
                                    'timestamp': date,
                                    f'{var}_interpolated': interpolated_results[i]
                                })
                            else:
                                final_result[f'{var}_interpolated'] = interpolated_results[i]
                        
                        # 写入数据库
                        records_count = self.data_mgr.write_interpolated_data(
                            final_result,
                            self.variables,
                            self.config['database']['batch_size']
                        )
                        
                        print(f"  ✓ {date_str}: 插值完成，写入 {records_count:,} 条记录")
                        self.progress_mgr.complete_date(date, records_count)
                        success_count += 1
                        
                    except Exception as e:
                        print(f"  ❌ {date_str}: 插值失败 - {e}")
                        self.progress_mgr.fail_date(date, str(e))
                        fail_count += 1
                        continue
                
            except Exception as e:
                print(f"❌ 批次 {batch_num} 失败：{e}")
                import traceback
                traceback.print_exc()
                
                # 标记所有日期为失败
                for date in batch_dates:
                    self.progress_mgr.fail_date(date, str(e))
                    fail_count += 1
                
                # 询问是否继续
                if batch_num < len(batches):
                    print(f"\n⚠ 是否继续处理下一批次？(y/n)")
                    try:
                        choice = input().strip().lower()
                        if choice != 'y':
                            print("已停止处理。")
                            break
                    except:
                        print("无响应，继续处理...")
                else:
                    break
        
        # 完成所有
        self.progress_mgr.finish_all()
        
        # 生成最终报告
        print("\n" + "="*80)
        print("  🎉 空间插值流程完成！")
        print("="*80)
        print(f"\n【执行摘要】")
        print(f"  总天数：{total_days:,} 天")
        print(f"  成功：{success_count} 天")
        print(f"  失败：{fail_count} 天")
        print(f"  成功率：{(success_count/total_days)*100:.1f}%")
        print(f"  总记录数：{self.progress_mgr.progress['statistics']['total_records']:,} 条")
        print(f"  总耗时：{datetime.fromisoformat(self.progress_mgr.progress['end_time']) - datetime.fromisoformat(self.progress_mgr.progress['start_time'])}")
        
        if self.progress_mgr.progress['failed_dates']:
            print(f"\n【失败的日期】")
            for failed in self.progress_mgr.progress['failed_dates'][:10]:  # 只显示前 10 个
                print(f"  ✗ {failed['date']}: {failed['error']}")
            if len(self.progress_mgr.progress['failed_dates']) > 10:
                print(f"  ... 还有 {len(self.progress_mgr.progress['failed_dates']) - 10} 个")
        
        print(f"\n【输出目录】")
        print(f"  {self.output_dir.absolute()}")
        
        print(f"\n【进度记录】")
        print(f"  {self.progress_mgr.progress_file.absolute()}")
        
        print("\n" + "="*80)


# ==================== 主函数 ====================

def main():
    """主函数"""
    # 配置日志
    log_dir = Path(__file__).parent.parent.parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(
                log_dir / 'spatial_interpolation.log',
                encoding='utf-8',
                mode='a'
            ),
            logging.StreamHandler()
        ]
    )
    
    # 检查依赖
    if not SCIPY_AVAILABLE:
        print("\n❌ 缺少必要的依赖库")
        print("请运行：pip install scipy scikit-learn")
        return
    
    # 创建执行器并运行
    executor = InterpolationExecutor(CONFIG)
    executor.run()


if __name__ == "__main__":
    main()
