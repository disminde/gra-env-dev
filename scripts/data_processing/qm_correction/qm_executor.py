"""
QM 校正执行器 - 协调整个校正流程

功能:
    1. 协调数据加载、QM 拟合、校正应用
    2. 批量处理多个站点和变量
    3. 保存校正结果和中间产品
    4. 生成处理日志

扩展性:
    - 预留 ET0 校正支持
    - 支持并行处理（可选）
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
from datetime import datetime
from typing import Dict, List, Optional

try:
    from .data_loader import DataManager
    from .qm_core import QuantileMapper
except ImportError:
    from data_loader import DataManager
    from qm_core import QuantileMapper

logger = logging.getLogger(__name__)


class QMExecutor:
    """QM 校正执行器"""
    
    def __init__(
        self,
        output_dir: str = 'data/processed/qm_correction',
        n_quantiles: int = 100,
        distribution: str = 'empirical',
        monthly: bool = True
    ):
        """
        初始化 QM 校正执行器
        
        Args:
            output_dir: 输出目录
            n_quantiles: 分位数数量
            distribution: 分布类型
            monthly: 是否月度校正
        """
        self.base_dir = Path(__file__).parent.parent.parent
        self.output_dir = self.base_dir / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据管理器
        self.data_manager = DataManager()
        
        # QM 配置
        self.qm_config = {
            'n_quantiles': n_quantiles,
            'distribution': distribution,
            'monthly': monthly
        }
        
        # 存储校正结果
        self.correction_results = {}
        self.qm_models = {}
        
        logger.info("QM 校正执行器初始化完成")
        logger.info(f"输出目录：{self.output_dir}")
    
    def run_correction(
        self,
        variables: List[str],
        start_year: int = 1990,
        end_year: int = 2023,
        save_models: bool = True,
        write_to_db: bool = False,
        db_table: str = 'qm_corrected_grid_data',
        batch_size: int = 10000
    ):
        """
        执行完整的 QM 校正流程
        
        Args:
            variables: 变量列表
            start_year: 起始年份
            end_year: 结束年份
            save_models: 是否保存 QM 模型
            write_to_db: 是否写入数据库
            db_table: 数据库表名
            batch_size: 批量写入大小
        """
        logger.info("="*60)
        logger.info("开始 QM 偏差校正流程")
        logger.info("="*60)
        logger.info(f"校正变量：{variables}")
        logger.info(f"时间范围：{start_year}-{end_year}")
        
        # 1. 加载匹配的站点 - 网格数据
        logger.info("\n【步骤 1/4】加载匹配的站点 - 网格数据...")
        matched_pairs = self.data_manager.get_matched_pairs(
            variables=variables,
            start_year=start_year,
            end_year=end_year
        )
        
        if len(matched_pairs) == 0:
            logger.error("没有成功匹配任何站点 - 网格点对")
            return
        
        logger.info(f"成功匹配 {len(matched_pairs)} 个站点")
        
        # 2. 对每个站点执行 QM 校正
        logger.info("\n【步骤 2/4】执行 QM 校正...")
        
        for station_id, pair_data in matched_pairs.items():
            logger.info(f"\n处理站点：{station_id}")
            
            # 将日期列转换回 datetime 类型，以便 QM 模型可以提取月份信息
            station_data = pair_data['station_data'].copy()
            grid_data = pair_data['grid_data'].copy()
            
            # 转换为 datetime 索引
            station_data['date'] = pd.to_datetime(station_data['date'])
            grid_data['date'] = pd.to_datetime(grid_data['date'])
            
            station_data = station_data.set_index('date')
            grid_data = grid_data.set_index('date')
            
            logger.info(f"  站点数据列：{station_data.columns.tolist()}")
            logger.info(f"  网格数据列：{grid_data.columns.tolist()}")
            logger.info(f"  站点数据记录数：{len(station_data)}")
            logger.info(f"  网格数据记录数：{len(grid_data)}")
            
            # 为每个变量创建 QM 模型
            self.qm_models[station_id] = {}
            
            for var in variables:
                # 检查变量是否在数据中存在
                station_var_exists = var in station_data.columns
                grid_var_exists = var in grid_data.columns
                
                logger.info(f"  检查变量 {var}: 站点数据={station_var_exists}, 网格数据={grid_var_exists}")
                
                if not station_var_exists or not grid_var_exists:
                    logger.warning(f"  变量 {var} 数据不完整，跳过")
                    continue
                
                logger.info(f"  校正变量：{var}")
                
                # 创建 QM 模型
                qm = QuantileMapper(
                    n_quantiles=self.qm_config['n_quantiles'],
                    distribution=self.qm_config['distribution'],
                    monthly=self.qm_config['monthly']
                )
                
                # 拟合模型（站点数据作为观测真值，网格数据作为模拟数据）
                qm.fit(
                    sim_data=grid_data[var],
                    obs_data=station_data[var],
                    variable_name=var
                )
                
                # 应用校正
                corrected_var = qm.transform(grid_data[var], var)
                
                # 存储结果
                grid_data[f'{var}_corrected'] = corrected_var
                
                # 保存 QM 模型
                self.qm_models[station_id][var] = qm
                
                # 计算校正统计
                bias_before = grid_data[var].mean() - station_data[var].mean()
                bias_after = corrected_var.mean() - station_data[var].mean()
                
                logger.info(f"    校正前偏差：{bias_before:.4f}")
                logger.info(f"    校正后偏差：{bias_after:.4f}")
                logger.info(f"    偏差减少：{(1 - abs(bias_after)/abs(bias_before))*100:.1f}%")
            
            # 保存该站点的校正结果
            self.correction_results[station_id] = grid_data.reset_index()
        
        # 3. 保存校正结果
        logger.info("\n【步骤 3/4】保存校正结果...")
        
        # 写入数据库（如果启用）
        if write_to_db:
            logger.info("\n写入数据库表...")
            self._write_to_database(
                table_name=db_table,
                batch_size=batch_size
            )
        
        # 保存 CSV 备份
        self._save_correction_results()
        
        # 4. 保存 QM 模型
        if save_models:
            logger.info("\n【步骤 4/4】保存 QM 模型...")
            self._save_qm_models()
        
        logger.info("\n" + "="*60)
        logger.info("QM 校正流程完成!")
        logger.info("="*60)
    
    def _save_correction_results(self):
        """保存校正结果到 CSV"""
        # 按站点保存
        for station_id, corrected_data in self.correction_results.items():
            output_file = self.output_dir / f"{station_id}_corrected.csv"
            corrected_data.to_csv(output_file, index=False)
        
        logger.info(f"  已保存 {len(self.correction_results)} 个站点的校正结果")
        
        # 合并所有站点结果（按变量）
        for var in ['temperature', 'precipitation', 'wind_speed', 'relative_humidity']:
            # 收集所有站点的该变量校正结果
            all_data = []
            
            for station_id, corrected_data in self.correction_results.items():
                if f'{var}_corrected' in corrected_data.columns:
                    # 添加站点信息
                    temp = corrected_data[['date', var, f'{var}_corrected']].copy()
                    temp['station_id'] = station_id
                    all_data.append(temp)
            
            if len(all_data) > 0:
                merged = pd.concat(all_data, ignore_index=True)
                output_file = self.output_dir / f"{var}_all_stations_corrected.csv"
                merged.to_csv(output_file, index=False)
                logger.info(f"  已合并变量 {var} 的所有站点数据")
    
    def _write_to_database(
        self, 
        table_name: str = 'qm_corrected_grid_data',
        batch_size: int = 10000
    ):
        """
        将校正结果写入数据库
        
        Args:
            table_name: 数据库表名
            batch_size: 批量写入大小
        """
        from dotenv import load_dotenv
        import psycopg2
        import os
        
        load_dotenv()
        
        # 连接数据库
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            database=os.getenv('POSTGRES_DB', 'gra_env_db'),
            user=os.getenv('POSTGRES_USER', 'admin'),
            password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
        )
        
        cur = conn.cursor()
        
        logger.info(f"  准备写入 {len(self.correction_results)} 个站点的校正结果...")
        
        total_records = 0
        for station_id, corrected_data in self.correction_results.items():
            logger.info(f"    处理站点 {station_id}...")
            
            # 获取网格点坐标
            if len(corrected_data) > 0:
                # 准备插入数据
                insert_sql = f"""
                INSERT INTO {table_name} (
                    latitude, longitude, timestamp,
                    temperature_corrected, precipitation_corrected,
                    wind_speed_corrected, relative_humidity_corrected,
                    temperature_original, precipitation_original,
                    wind_speed_original, relative_humidity_original,
                    source_station_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                # 批量插入
                batch_data = []
                for idx, row in corrected_data.iterrows():
                    # 假设第一行的 lat/lon 代表该网格点
                    lat = corrected_data.iloc[0].get('latitude', 0.0)
                    lon = corrected_data.iloc[0].get('longitude', 0.0)
                    
                    # 转换 numpy 类型为 Python 原生类型
                    batch_data.append((
                        float(lat) if lat is not None else None,
                        float(lon) if lon is not None else None,
                        row['date'].to_pydatetime() if hasattr(row['date'], 'to_pydatetime') else row['date'],
                        float(row.get('temperature_corrected')) if pd.notna(row.get('temperature_corrected')) else None,
                        float(row.get('precipitation_corrected')) if pd.notna(row.get('precipitation_corrected')) else None,
                        float(row.get('wind_speed_corrected')) if pd.notna(row.get('wind_speed_corrected')) else None,
                        float(row.get('relative_humidity_corrected')) if pd.notna(row.get('relative_humidity_corrected')) else None,
                        float(row.get('temperature')) if pd.notna(row.get('temperature')) else None,
                        float(row.get('precipitation')) if pd.notna(row.get('precipitation')) else None,
                        float(row.get('wind_speed')) if pd.notna(row.get('wind_speed')) else None,
                        float(row.get('relative_humidity')) if pd.notna(row.get('relative_humidity')) else None,
                        station_id
                    ))
                    
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
        
        logger.info(f"  ✓ 成功写入 {total_records:,} 条记录到数据库表 {table_name}")
    
    def _save_qm_models(self):
        """保存 QM 模型"""
        model_dir = self.output_dir / 'qm_models'
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # 按站点保存
        for station_id, models in self.qm_models.items():
            station_model_dir = model_dir / station_id
            station_model_dir.mkdir(parents=True, exist_ok=True)
            
            for var, qm_model in models.items():
                model_file = station_model_dir / f"{var}_qm_model.pkl"
                qm_model.save(model_file)
        
        logger.info(f"  已保存 {sum(len(m) for m in self.qm_models.values())} 个 QM 模型")
        
        # 保存配置信息
        config_file = model_dir / 'qm_config.json'
        import json
        with open(config_file, 'w') as f:
            json.dump({
                'qm_config': self.qm_config,
                'n_stations': len(self.qm_models),
                'variables': list(set(
                    var for models in self.qm_models.values()
                    for var in models.keys()
                )),
                'processing_date': datetime.now().isoformat()
            }, f, indent=2)
    
    def get_correction_statistics(self) -> pd.DataFrame:
        """
        获取校正统计信息
        
        Returns:
            DataFrame: 包含各站点各变量的校正统计
        """
        stats_list = []
        
        for station_id, pair_data in self.data_manager.get_matched_pairs(
            variables=['temperature', 'precipitation', 'wind_speed', 'relative_humidity'],
            start_year=1990,
            end_year=2023
        ).items():
            
            station_data = pair_data['station_data'].set_index('date')
            grid_data = pair_data['grid_data'].set_index('date')
            
            for var in station_data.columns:
                if var not in grid_data.columns:
                    continue
                
                if f'{var}_corrected' not in grid_data.columns:
                    continue
                
                # 计算统计指标
                bias_before = grid_data[var].mean() - station_data[var].mean()
                bias_after = grid_data[f'{var}_corrected'].mean() - station_data[var].mean()
                
                mae_before = np.mean(np.abs(grid_data[var] - station_data[var]))
                mae_after = np.mean(np.abs(grid_data[f'{var}_corrected'] - station_data[var]))
                
                rmse_before = np.sqrt(np.mean((grid_data[var] - station_data[var])**2))
                rmse_after = np.sqrt(np.mean((grid_data[f'{var}_corrected'] - station_data[var])**2))
                
                stats_list.append({
                    'station_id': station_id,
                    'variable': var,
                    'bias_before': bias_before,
                    'bias_after': bias_after,
                    'bias_reduction': (1 - abs(bias_after)/abs(bias_before)) * 100 if abs(bias_before) > 0 else 0,
                    'mae_before': mae_before,
                    'mae_after': mae_after,
                    'mae_reduction': (1 - mae_after/mae_before) * 100 if mae_before > 0 else 0,
                    'rmse_before': rmse_before,
                    'rmse_after': rmse_after,
                    'rmse_reduction': (1 - rmse_after/rmse_before) * 100 if rmse_before > 0 else 0
                })
        
        return pd.DataFrame(stats_list)


# 主函数
def main():
    """QM 校正主函数"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(
                Path(__file__).parent.parent.parent / 'logs' / 'qm_correction.log',
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
    
    # 创建执行器
    executor = QMExecutor(
        output_dir='data/processed/qm_correction',
        n_quantiles=100,
        distribution='empirical',  # 经验分布，适用于所有变量
        monthly=True  # 月度校正，考虑季节性
    )
    
    # 定义要校正的变量
    variables_to_correct = [
        'temperature',
        'precipitation',
        'wind_speed',
        'relative_humidity'
        # 【预留】'et0_fao_evapotranspiration' - 待中国气象数据网数据
    ]
    
    # 执行校正
    executor.run_correction(
        variables=variables_to_correct,
        start_year=1990,
        end_year=2023,
        save_models=True
    )
    
    # 生成统计报告
    logger.info("\n生成校正统计报告...")
    stats_df = executor.get_correction_statistics()
    
    # 保存统计报告
    stats_file = executor.output_dir / 'correction_statistics.csv'
    stats_df.to_csv(stats_file, index=False)
    logger.info(f"统计报告已保存：{stats_file}")
    
    # 打印摘要
    print("\n" + "="*60)
    print("QM 校正统计摘要")
    print("="*60)
    
    for var in variables_to_correct:
        var_stats = stats_df[stats_df['variable'] == var]
        if len(var_stats) > 0:
            print(f"\n{var.upper()}:")
            print(f"  平均偏差减少：{var_stats['bias_reduction'].mean():.1f}%")
            print(f"  平均 MAE 减少：{var_stats['mae_reduction'].mean():.1f}%")
            print(f"  平均 RMSE 减少：{var_stats['rmse_reduction'].mean():.1f}%")


if __name__ == "__main__":
    main()
