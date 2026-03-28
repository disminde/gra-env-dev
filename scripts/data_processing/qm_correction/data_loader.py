"""
数据加载与管理模块

功能:
    1. 从 PostgreSQL 数据库读取网格数据
    2. 从 CSV 文件读取 NOAA 站点日数据
    3. 时空匹配（站点与网格点对应）
    4. 数据质量检查

扩展性:
    - 预留 ET0 观测数据加载接口（中国气象数据网）
    - 支持多种数据源格式
"""

import pandas as pd
import numpy as np
import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class DataManager:
    """数据管理类 - 负责加载和管理所有气象数据"""
    
    def __init__(self, db_config: Optional[Dict] = None):
        """
        初始化数据管理器
        
        Args:
            db_config: 数据库配置字典，如果为 None 则从环境变量读取
        """
        # 加载环境变量
        load_dotenv()
        
        # 数据库配置
        if db_config is None:
            self.db_config = {
                'host': os.getenv('POSTGRES_HOST', 'localhost'),
                'port': os.getenv('POSTGRES_PORT', '5432'),
                'dbname': os.getenv('POSTGRES_DB', 'gra_env_db'),
                'user': os.getenv('POSTGRES_USER', 'admin'),
                'password': os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
            }
        else:
            self.db_config = db_config
        
        # 路径配置
        self.base_dir = Path(__file__).parent.parent.parent
        self.project_root = self.base_dir.parent  # 项目根目录
        self.noaa_daily_dir = self.project_root / 'data' / 'processed' / 'noaa_daily'
        
        # 【预留】中国气象数据网 ET0 数据目录
        self.cma_et0_dir = self.project_root / 'data' / 'processed' / 'cma_et0'
        
        # 站点 - 网格映射文件 (在项目根目录)
        self.station_grid_mapping_file = self.project_root / 'station_grid_mapping.csv'
        
        logger.info("数据管理器初始化完成")
        logger.info(f"NOAA 日数据目录：{self.noaa_daily_dir}")
        logger.info(f"【预留】CMA ET0 数据目录：{self.cma_et0_dir}")
    
    def connect_db(self):
        """建立数据库连接"""
        try:
            conn = psycopg2.connect(**self.db_config)
            logger.info("数据库连接成功")
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败：{e}")
            raise
    
    def _map_variable_name(self, var_name: str) -> str:
        """
        映射变量名到数据库实际字段名
        
        Args:
            var_name: 标准变量名
        
        Returns:
            str: 数据库字段名
        """
        var_mapping = {
            'temperature': 'temperature',
            'precipitation': 'precipitation',
            'wind_speed': 'wind_speed_10m',
            'relative_humidity': 'relative_humidity_2m',
            'et0_fao_evapotranspiration': 'et0_fao_evapotranspiration',
            'soil_moisture': 'soil_moisture_0_to_7cm',
            'shortwave_radiation': 'shortwave_radiation'
        }
        return var_mapping.get(var_name, var_name)
    
    def load_grid_data(
        self,
        variables: List[str],
        start_year: int = 1990,
        end_year: int = 2023,
        grid_points: Optional[List[Tuple[float, float]]] = None
    ) -> pd.DataFrame:
        """
        从数据库加载网格数据（使用聚合查询）
        
        Args:
            variables: 变量名列表 ['temperature', 'precipitation', ...]
            start_year: 起始年份
            end_year: 结束年份
            grid_points: 可选的网格点列表 [(lat, lon), ...]，如果为 None 则加载全部
        
        Returns:
            DataFrame: 包含所有网格点日数据的 DataFrame
        """
        conn = self.connect_db()
        
        # 映射变量名到数据库字段名和聚合函数
        var_aggregation = {
            'temperature': ('AVG(temperature)', 'temperature'),
            'precipitation': ('SUM(precipitation)', 'precipitation'),
            'wind_speed': ('AVG(wind_speed_10m)', 'wind_speed'),
            'relative_humidity': ('AVG(relative_humidity_2m)', 'relative_humidity'),
            'et0_fao_evapotranspiration': ('AVG(et0_fao_evapotranspiration)', 'et0')
        }
        
        # 构建 SELECT 子句
        select_parts = ['latitude', 'longitude', 'DATE(timestamp) AS date']
        for var in variables:
            if var in var_aggregation:
                select_parts.append(f"{var_aggregation[var][0]} AS {var_aggregation[var][1]}")
        
        select_clause = ', '.join(select_parts)
        
        # 构建 WHERE 条件
        where_conditions = ["EXTRACT(YEAR FROM timestamp) BETWEEN %s AND %s"]
        params = [start_year, end_year]
        
        # 网格点条件（如果指定）
        if grid_points:
            lat_lon_conditions = []
            for lat, lon in grid_points:
                lat_lon_conditions.append("(latitude = %s AND longitude = %s)")
                params.extend([lat, lon])
            if lat_lon_conditions:
                where_conditions.append("(" + " OR ".join(lat_lon_conditions) + ")")
        
        where_clause = " AND ".join(where_conditions)
        
        # 构建完整查询
        query = f"""
            SELECT {select_clause}
            FROM grid_weather_data
            WHERE {where_clause}
            GROUP BY latitude, longitude, DATE(timestamp)
            ORDER BY latitude, longitude, date
        """
        
        # 执行查询
        df = pd.read_sql_query(
            query,
            conn,
            params=params
        )
        
        conn.close()
        
        logger.info(f"成功加载 {len(df):,} 条记录 (聚合到日尺度)")
        
        return df
    
    def load_noaa_station_data(
        self,
        station_id: str,
        variables: List[str],
        start_year: int = 1990,
        end_year: int = 2023
    ) -> pd.DataFrame:
        """
        加载 NOAA 站点日数据
        
        Args:
            station_id: 站点 ID (格式：USAF-WBAN)
            variables: 变量名列表
            start_year: 起始年份
            end_year: 结束年份
        
        Returns:
            DataFrame: 站点日数据
        """
        # 查找站点文件
        station_file = self.noaa_daily_dir / f"{station_id}_daily_data.csv"
        
        if not station_file.exists():
            raise FileNotFoundError(f"站点数据文件不存在：{station_file}")
        
        # 读取数据
        df = pd.read_csv(station_file)
        
        # 转换日期列
        df['date'] = pd.to_datetime(df['date'])
        
        # 提取年份
        df['year'] = df['date'].dt.year
        
        # 时间范围过滤
        df = df[(df['year'] >= start_year) & (df['year'] <= end_year)]
        
        # 变量名映射（NOAA → 统一命名）
        var_mapping = {
            'temp_mean': 'temperature',
            'precip_daily': 'precipitation',
            'wind_speed_mean': 'wind_speed',
            'rh_mean': 'relative_humidity'
        }
        
        # 创建反向映射（统一命名 → NOAA）
        reverse_var_mapping = {v: k for k, v in var_mapping.items()}
        
        # 选择需要的变量：找到请求变量对应的 NOAA 列名
        noaa_vars = []
        for v in variables:
            if v in reverse_var_mapping:
                noaa_var = reverse_var_mapping[v]
                if noaa_var in df.columns:
                    noaa_vars.append(noaa_var)
        
        # available_vars 就是 noaa_vars（已经过滤过在 df.columns 中的）
        available_vars = noaa_vars
        
        logger.info(f"站点 {station_id}: 请求变量={variables}, NOAA 变量={noaa_vars}, 可用变量={available_vars}")
        
        if len(available_vars) == 0:
            logger.warning(f"站点 {station_id}: 没有找到任何可用变量！DataFrame 列：{df.columns.tolist()}")
        
        # 选择日期和可用变量列，并重命名为标准变量名
        df_result = df[['date'] + available_vars].copy()
        
        # 将 NOAA 列名重命名为标准变量名
        rename_dict = {noaa_col: std_col for noaa_col, std_col in var_mapping.items() if noaa_col in available_vars}
        df_result = df_result.rename(columns=rename_dict)
        
        logger.info(f"加载站点 {station_id} 数据：{len(df_result)} 天，列：{df_result.columns.tolist()}")
        
        return df_result
    
    def load_station_grid_mapping(self) -> pd.DataFrame:
        """
        加载站点 - 网格映射关系
        
        Returns:
            DataFrame: 包含站点与网格点对应关系
        """
        if not self.station_grid_mapping_file.exists():
            raise FileNotFoundError(f"站点 - 网格映射文件不存在：{self.station_grid_mapping_file}")
        
        mapping = pd.read_csv(self.station_grid_mapping_file)
        logger.info(f"加载站点 - 网格映射：{len(mapping)} 个站点")
        
        return mapping
    
    # ============================================
    # 【预留接口】中国气象数据网 ET0 数据加载方法
    # ============================================
    def load_cma_et0_data(
        self,
        station_id: str,
        start_year: int = 1990,
        end_year: int = 2023
    ) -> Optional[pd.DataFrame]:
        """
        【预留接口】加载中国气象数据网 (CMA) 的 ET0 观测数据
        
        注意：此方法目前返回 None，直到获取到 CMA 数据
        
        Args:
            station_id: 站点 ID
            start_year: 起始年份
            end_year: 结束年份
        
        Returns:
            DataFrame 或 None: 如果数据存在则返回 DataFrame，否则返回 None
        
        数据格式要求（获取数据后需要转换）:
            - 文件位置：data/processed/cma_et0/{station_id}_et0_daily.csv
            - 文件格式：
              date, et0_obs
              1990-01-01, 2.5
              1990-01-02, 2.3
              ...
        """
        # 检查 ET0 数据目录是否存在
        if not self.cma_et0_dir.exists():
            logger.info(f"CMA ET0 数据目录不存在：{self.cma_et0_dir}")
            logger.info("【提示】如果获取到中国气象数据网的 ET0 数据，请存放至此目录")
            return None
        
        # 查找 ET0 数据文件
        et0_file = self.cma_et0_dir / f"{station_id}_et0_daily.csv"
        
        if not et0_file.exists():
            logger.info(f"站点 {station_id} 的 ET0 数据不存在：{et0_file}")
            return None
        
        try:
            # 读取 ET0 数据
            df = pd.read_csv(et0_file)
            
            # 转换日期列
            df['date'] = pd.to_datetime(df['date'])
            
            # 提取年份
            df['year'] = df['date'].dt.year
            
            # 时间范围过滤
            df = df[(df['year'] >= start_year) & (df['year'] <= end_year)]
            
            # 重命名变量为标准格式
            if 'et0_obs' in df.columns:
                df['et0_fao_evapotranspiration'] = df['et0_obs']
            
            logger.info(f"加载站点 {station_id} 的 ET0 数据：{len(df)} 天")
            
            return df[['date', 'et0_fao_evapotranspiration']]
            
        except Exception as e:
            logger.error(f"加载 ET0 数据失败：{e}")
            return None
    
    def get_matched_pairs(
        self,
        variables: List[str],
        start_year: int = 1990,
        end_year: int = 2023
    ) -> Dict:
        """
        获取所有站点 - 网格点对的匹配数据
        
        Args:
            variables: 变量列表
            start_year: 起始年份
            end_year: 结束年份
        
        Returns:
            Dict: {
                'station_id': {
                    'station_data': DataFrame,  # 站点数据
                    'grid_data': DataFrame,     # 对应网格数据
                    'lat': float,               # 站点纬度
                    'lon': float                # 站点经度
                }
            }
        """
        # 加载站点 - 网格映射
        mapping = self.load_station_grid_mapping()
        
        # 获取唯一的网格点列表
        grid_points = list(set(zip(mapping['grid_lat'], mapping['grid_lon'])))
        
        logger.info(f"加载 {len(grid_points)} 个网格点的数据库数据...")
        
        # 从数据库加载所有网格点数据
        grid_data_all = self.load_grid_data(
            variables=variables,
            start_year=start_year,
            end_year=end_year,
            grid_points=grid_points
        )
        
        # 存储匹配结果
        matched_pairs = {}
        
        logger.info("开始站点 - 网格数据匹配...")
        
        for idx, row in mapping.iterrows():
            station_id = row['station_id']
            grid_lat = row['grid_lat']
            grid_lon = row['grid_lon']
            
            try:
                # 加载站点数据
                station_data = self.load_noaa_station_data(
                    station_id=station_id,
                    variables=variables,
                    start_year=start_year,
                    end_year=end_year
                )
                
                # 提取对应网格数据
                mask = (
                    (grid_data_all['latitude'] == grid_lat) &
                    (grid_data_all['longitude'] == grid_lon)
                )
                grid_data = grid_data_all[mask].copy()
                
                # 检查数据是否足够
                if len(station_data) < 100 or len(grid_data) < 100:
                    logger.warning(f"站点 {station_id} 数据量不足，跳过")
                    continue
                
                # 按日期对齐
                # 将日期列转换为日期对象（去掉时间部分）
                station_data['date'] = pd.to_datetime(station_data['date']).dt.date
                grid_data['date'] = pd.to_datetime(grid_data['date']).dt.date
                
                # 找到共同日期（使用日期对象直接比较）
                common_dates = set(station_data['date']).intersection(set(grid_data['date']))
                
                if len(common_dates) < 100:
                    logger.warning(f"站点 {station_id} 共同日期不足，跳过")
                    continue
                
                # 过滤共同日期
                station_data_aligned = station_data[station_data['date'].isin(common_dates)]
                grid_data_aligned = grid_data[grid_data['date'].isin(common_dates)]
                
                # 【预留】尝试加载 ET0 观测数据
                if 'et0_fao_evapotranspiration' in variables:
                    cma_et0 = self.load_cma_et0_data(station_id, start_year, end_year)
                    if cma_et0 is not None:
                        # 如果加载到 CMA ET0 数据，替换站点数据中的 ET0
                        cma_et0 = cma_et0.set_index('date')
                        cma_et0_aligned = cma_et0.loc[common_dates]
                        station_data_aligned['et0_fao_evapotranspiration'] = cma_et0_aligned['et0_fao_evapotranspiration']
                        logger.info(f"站点 {station_id}: 使用 CMA ET0 观测数据")
                    else:
                        logger.info(f"站点 {station_id}: 使用 ERA5 ET0 数据（无 CMA 观测）")
                
                # 存储匹配结果
                matched_pairs[station_id] = {
                    'station_data': station_data_aligned.reset_index(),
                    'grid_data': grid_data_aligned.reset_index(),
                    'lat': row['station_lat'],
                    'lon': row['station_lon'],
                    'grid_lat': grid_lat,
                    'grid_lon': grid_lon,
                    'common_days': len(common_dates)
                }
                
            except Exception as e:
                logger.error(f"处理站点 {station_id} 时出错：{e}")
                continue
        
        logger.info(f"成功匹配 {len(matched_pairs)} 个站点 - 网格点对")
        
        return matched_pairs


# 测试代码
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 测试数据加载
    dm = DataManager()
    
    # 测试加载站点 - 网格映射
    mapping = dm.load_station_grid_mapping()
    print(f"\n站点 - 网格映射：{len(mapping)} 个站点")
    print(mapping.head())
    
    # 测试加载 NOAA 站点数据
    test_station = mapping.iloc[0]['station_id']
    station_data = dm.load_noaa_station_data(
        station_id=test_station,
        variables=['temperature', 'precipitation'],
        start_year=2020,
        end_year=2020
    )
    print(f"\n站点 {test_station} 数据：{len(station_data)} 天")
    print(station_data.head())
    
    # 测试加载网格数据
    grid_points = [(mapping.iloc[0]['grid_lat'], mapping.iloc[0]['grid_lon'])]
    grid_data = dm.load_grid_data(
        variables=['temperature', 'precipitation'],
        start_year=2020,
        end_year=2020,
        grid_points=grid_points
    )
    print(f"\n网格点数据：{len(grid_data)} 条记录")
    print(grid_data.head())
    
    # 测试匹配
    pairs = dm.get_matched_pairs(
        variables=['temperature', 'precipitation'],
        start_year=2020,
        end_year=2020
    )
    print(f"\n成功匹配 {len(pairs)} 个站点 - 网格点对")
