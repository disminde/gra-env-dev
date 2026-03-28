"""
优化版 QM 校正 - 分批次处理，避免内存溢出

策略：
    1. 按年份分批加载数据
    2. 每年数据单独处理并写入数据库
    3. 降低内存占用
"""

import sys
import logging
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from qm_executor import QMExecutor
from quality_assessment import QualityAssessment

# ==================== 配置区域 ====================

CONFIG = {
    # 要校正的变量列表
    'variables_to_correct': [
        'temperature',
        'precipitation',
        'wind_speed',
        'relative_humidity'
    ],
    
    # 时间范围
    'start_year': 1990,
    'end_year': 2023,
    
    # 分批处理配置
    'batch_years': 5,  # 每次处理 5 年数据
    
    # QM 参数
    'qm_params': {
        'n_quantiles': 100,
        'distribution': 'empirical',
        'monthly': True
    },
    
    # 输出目录
    'output_dir': 'scripts/data/processed/qm_correction',
    
    # 数据库配置
    'database': {
        'enabled': True,
        'table_name': 'qm_corrected_grid_data',
        'batch_size': 5000,  # 减小批量大小
        'backup_csv': True
    },
    
    'save_models': True,
    'generate_assessment': True
}

# ==================== 主函数 ====================

def main():
    """主函数 - 分批次处理"""
    # 配置日志
    log_dir = Path(__file__).parent.parent.parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(
                log_dir / 'qm_correction_batch.log',
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    logger.info("="*80)
    logger.info("华北平原气象数据 QM 偏差校正系统 (优化分批版)")
    logger.info("="*80)
    
    # 显示配置
    logger.info(f"\n校正变量：{CONFIG['variables_to_correct']}")
    logger.info(f"时间范围：{CONFIG['start_year']}-{CONFIG['end_year']}")
    logger.info(f"分批大小：{CONFIG['batch_years']} 年/批")
    logger.info(f"总批次数：{(CONFIG['end_year'] - CONFIG['start_year'] + 1) // CONFIG['batch_years'] + 1}")
    
    # 创建执行器
    executor = QMExecutor(
        output_dir=CONFIG['output_dir'],
        n_quantiles=CONFIG['qm_params']['n_quantiles'],
        distribution=CONFIG['qm_params']['distribution'],
        monthly=CONFIG['qm_params']['monthly']
    )
    
    # 分批次处理
    start_year = CONFIG['start_year']
    batch_num = 0
    
    while start_year <= CONFIG['end_year']:
        end_year = min(start_year + CONFIG['batch_years'] - 1, CONFIG['end_year'])
        batch_num += 1
        
        logger.info("\n" + "="*80)
        logger.info(f"【批次 {batch_num}】处理年份：{start_year} - {end_year}")
        logger.info("="*80)
        
        try:
            # 执行当前批次的校正
            executor.run_correction(
                variables=CONFIG['variables_to_correct'],
                start_year=start_year,
                end_year=end_year,
                save_models=False,  # 只在最后一批保存模型
                write_to_db=CONFIG['database']['enabled'],
                db_table=CONFIG['database']['table_name'],
                batch_size=CONFIG['database']['batch_size']
            )
            
            logger.info(f"✓ 批次 {batch_num} 完成")
            
        except Exception as e:
            logger.error(f"❌ 批次 {batch_num} 失败：{e}")
            import traceback
            traceback.print_exc()
            break
        
        # 更新起始年份
        start_year = end_year + 1
    
    # 保存模型（最后统一保存）
    if CONFIG['save_models']:
        logger.info("\n保存 QM 模型...")
        executor._save_qm_models()
    
    logger.info("\n" + "="*80)
    logger.info("QM 校正流程完成!")
    logger.info("="*80)


if __name__ == "__main__":
    main()
