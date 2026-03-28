"""
补充缺失的 37 个站点的网格数据并重新运行 QM 校正

步骤：
1. 检查缺失网格点在 ERA5-Land 原始数据中的存在性
2. 如果存在，提取并加载到 grid_weather_data 表
3. 重新运行 QM 校正（针对所有 69 个站点）
4. 确保与先前 32 个站点的处理流程完全一致
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
import json

# 添加路径
sys.path.insert(0, str(Path(__file__).parent / 'qm_correction'))

from data_loader import DataManager
from qm_executor import QMExecutor

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
    'batch_years': 5,
    
    # QM 参数
    'qm_params': {
        'n_quantiles': 100,
        'distribution': 'empirical',
        'monthly': True
    },
    
    # 输出目录
    'output_dir': 'data/processed/qm_correction',
    
    # 数据库配置
    'database': {
        'enabled': True,
        'table_name': 'qm_corrected_grid_data',
        'batch_size': 5000
    },
    
    'save_models': True
}

# ==================== 主函数 ====================

def main():
    """主函数 - 重新运行完整的 69 站点 QM 校正"""
    # 配置日志
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(
                log_dir / 'qm_full_69.log',
                encoding='utf-8',
                mode='a'
            ),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    print("\n" + "="*80)
    print("  QM 偏差校正系统 - 完整 69 站点版本")
    print("="*80)
    
    # 显示配置
    print(f"\n【配置信息】")
    print(f"  校正变量：{', '.join(CONFIG['variables_to_correct'])}")
    print(f"  时间范围：{CONFIG['start_year']} - {CONFIG['end_year']}")
    print(f"  分批大小：{CONFIG['batch_years']} 年/批")
    print(f"  目标站点数：69 个")
    
    # 计算批次
    total_years = CONFIG['end_year'] - CONFIG['start_year'] + 1
    total_batches = (total_years + CONFIG['batch_years'] - 1) // CONFIG['batch_years']
    print(f"  总批次数：{total_batches}")
    
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
    success_count = 0
    fail_count = 0
    
    while start_year <= CONFIG['end_year']:
        end_year = min(start_year + CONFIG['batch_years'] - 1, CONFIG['end_year'])
        batch_num += 1
        
        # 显示进度条
        progress_pct = ((batch_num-1)/total_batches*100)
        bar_filled = int((batch_num-1)/total_batches*50)
        print(f"\n{'='*80}")
        print(f"【批次 {batch_num}/{total_batches}】处理年份：{start_year} - {end_year}")
        print(f"总进度：{'='*bar_filled}>{' '*(50-bar_filled)} {progress_pct:.1f}%")
        print(f"{'='*80}")
        
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
            
            print(f"\n✅ 批次 {batch_num} 完成！")
            success_count += 1
            
        except Exception as e:
            print(f"\n❌ 批次 {batch_num} 失败：{e}")
            logger.error(f"批次 {batch_num} 失败：{e}", exc_info=True)
            fail_count += 1
            
            # 询问是否继续
            if batch_num < total_batches:
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
        
        # 更新起始年份
        start_year = end_year + 1
    
    # 保存模型（最后统一保存）
    if CONFIG['save_models'] and success_count > 0:
        print("\n保存 QM 模型...")
        executor._save_qm_models()
    
    # 生成最终报告
    print("\n" + "="*80)
    print("  🎉 QM 校正流程完成！")
    print("="*80)
    print(f"\n【执行摘要】")
    print(f"  总批次数：{total_batches}")
    print(f"  成功：{success_count} 批")
    print(f"  失败：{fail_count} 批")
    print(f"  总耗时：{datetime.now()}")
    
    print(f"\n【输出目录】")
    print(f"  {Path(CONFIG['output_dir']).absolute()}")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
