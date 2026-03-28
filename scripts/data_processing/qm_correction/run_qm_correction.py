"""
QM 偏差校正主运行脚本

功能:
    一键执行完整的 QM 校正流程
    
使用方法:
    python run_qm_correction.py

扩展说明:
    如果后续获取到中国气象数据网的 ET0 数据:
    1. 在 CONFIG 中添加 'et0_fao_evapotranspiration' 到 variables_to_correct
    2. 确保 ET0 数据已放置在 data/processed/cma_et0/ 目录
    3. 运行此脚本会自动包含 ET0 校正
"""

import sys
import logging
from pathlib import Path

# 添加当前目录到路径
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
        # 【重要预留】如果获取到 CMA ET0 数据，取消下面这行的注释
        # 'et0_fao_evapotranspiration'
    ],
    
    # 时间范围
    'start_year': 1990,
    'end_year': 2023,
    
    # QM 参数
    'qm_params': {
        'n_quantiles': 100,
        'distribution': 'empirical',  # 经验分布
        'monthly': True  # 月度校正
    },
    
    # 输出目录
    'output_dir': 'data/processed/qm_correction',
    
    # 是否保存模型
    'save_models': True,
    
    # 是否生成评估报告
    'generate_assessment': True
}

# ==================== 主函数 ====================

def main():
    """主函数"""
    # 配置日志
    log_dir = Path(__file__).parent.parent.parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(
                log_dir / 'qm_correction.log',
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    logger.info("="*80)
    logger.info("华北平原气象数据 QM 偏差校正系统")
    logger.info("="*80)
    
    # 显示配置
    logger.info("\n配置信息:")
    logger.info(f"  校正变量：{CONFIG['variables_to_correct']}")
    logger.info(f"  时间范围：{CONFIG['start_year']}-{CONFIG['end_year']}")
    logger.info(f"  分位数数量：{CONFIG['qm_params']['n_quantiles']}")
    logger.info(f"  分布类型：{CONFIG['qm_params']['distribution']}")
    logger.info(f"  月度校正：{CONFIG['qm_params']['monthly']}")
    
    # 【重要】检查是否有 ET0 校正
    if 'et0_fao_evapotranspiration' in CONFIG['variables_to_correct']:
        logger.info("\n" + "="*80)
        logger.info("【注意】检测到 ET0 校正请求")
        logger.info("="*80)
        logger.info("请确保:")
        logger.info("  1. 已获取中国气象数据网的 ET0 观测数据")
        logger.info("  2. 数据已放置在 data/processed/cma_et0/ 目录")
        logger.info("  3. 数据格式符合要求（参见 data_loader.py 的 load_cma_et0_data 方法）")
        logger.info("\n如果没有 CMA ET0 数据，请从 variables_to_correct 中移除 ET0 变量")
        logger.info("="*80)
    
    # 创建执行器
    logger.info("\n创建 QM 校正执行器...")
    executor = QMExecutor(
        output_dir=CONFIG['output_dir'],
        n_quantiles=CONFIG['qm_params']['n_quantiles'],
        distribution=CONFIG['qm_params']['distribution'],
        monthly=CONFIG['qm_params']['monthly']
    )
    
    # 执行校正
    executor.run_correction(
        variables=CONFIG['variables_to_correct'],
        start_year=CONFIG['start_year'],
        end_year=CONFIG['end_year'],
        save_models=CONFIG['save_models']
    )
    
    # 生成评估报告
    if CONFIG['generate_assessment']:
        logger.info("\n生成质量评估报告...")
        stats_df = executor.get_correction_statistics()
        
        # 保存统计
        stats_file = executor.output_dir / 'correction_statistics.csv'
        stats_df.to_csv(stats_file, index=False)
        logger.info(f"统计报告已保存：{stats_file}")
        
        # 创建评估器
        assessor = QualityAssessment()
        assessor.create_assessment_report(stats_df.to_dict('records'))
        
        # 绘制图表
        try:
            assessor.plot_results(stats_df.to_dict('records'))
            logger.info("评估图表已生成")
        except Exception as e:
            logger.warning(f"生成图表时出错：{e}")
    
    logger.info("\n" + "="*80)
    logger.info("QM 校正流程完成!")
    logger.info("="*80)
    logger.info(f"\n输出目录：{executor.output_dir}")
    logger.info("\n主要输出文件:")
    logger.info(f"  - 校正后数据：{CONFIG['output_dir']}/*_corrected.csv")
    logger.info(f"  - QM 模型：{CONFIG['output_dir']}/qm_models/")
    logger.info(f"  - 统计报告：{CONFIG['output_dir']}/correction_statistics.csv")
    logger.info(f"  - 评估图表：{CONFIG['output_dir']}/assessment/")
    
    # 【预留】ET0 扩展提示
    if 'et0_fao_evapotranspiration' not in CONFIG['variables_to_correct']:
        logger.info("\n" + "="*80)
        logger.info("【预留扩展】ET0 校正接口")
        logger.info("="*80)
        logger.info("如果后续获取到中国气象数据网的 ET0 数据:")
        logger.info("  1. 将 ET0 数据放置在：data/processed/cma_et0/{station_id}_et0_daily.csv")
        logger.info("  2. 在 CONFIG 中添加 'et0_fao_evapotranspiration' 到 variables_to_correct")
        logger.info("  3. 重新运行此脚本")
        logger.info("\n详细说明请查看：docs/qm_correction_extension_guide.md")
        logger.info("="*80)


if __name__ == "__main__":
    main()
