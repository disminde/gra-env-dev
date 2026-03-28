"""
全自动 QM 校正脚本 - 带进度显示和错误恢复
功能：
    1. 自动处理所有批次
    2. 实时进度显示
    3. 错误恢复（断点续传）
    4. 详细的执行报告
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
import json

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
    'output_dir': 'data/processed/qm_correction',
    
    # 数据库配置
    'database': {
        'enabled': True,
        'table_name': 'qm_corrected_grid_data',
        'batch_size': 5000,
        'backup_csv': True
    },
    
    'save_models': True,
    'generate_assessment': True
}

# 进度记录文件
PROGRESS_FILE = Path(__file__).parent / 'progress.json'


# ==================== 进度管理 ====================

class ProgressManager:
    """进度管理器 - 支持断点续传"""
    
    def __init__(self, progress_file):
        self.progress_file = progress_file
        self.progress = {
            'completed_batches': [],
            'failed_batches': [],
            'current_batch': None,
            'start_time': None,
            'end_time': None
        }
        self.load_progress()
    
    def load_progress(self):
        """加载进度"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    saved_progress = json.load(f)
                    self.progress.update(saved_progress)
                    print(f"✓ 已加载进度记录：已完成 {len(self.progress['completed_batches'])} 批")
            except Exception as e:
                print(f"⚠ 加载进度失败：{e}，将从头开始")
    
    def save_progress(self):
        """保存进度"""
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, indent=2, ensure_ascii=False)
    
    def start_batch(self, batch_num, start_year, end_year):
        """开始批次"""
        self.progress['current_batch'] = {
            'batch_num': batch_num,
            'start_year': start_year,
            'end_year': end_year,
            'start_time': datetime.now().isoformat()
        }
        self.save_progress()
    
    def complete_batch(self, batch_num):
        """完成批次"""
        if self.progress['current_batch']:
            self.progress['current_batch']['end_time'] = datetime.now().isoformat()
            self.progress['completed_batches'].append(self.progress['current_batch'])
            self.progress['current_batch'] = None
            self.save_progress()
    
    def fail_batch(self, batch_num, error):
        """失败批次"""
        if self.progress['current_batch']:
            self.progress['current_batch']['error'] = str(error)
            self.progress['current_batch']['end_time'] = datetime.now().isoformat()
            self.progress['failed_batches'].append(self.progress['current_batch'])
            self.progress['current_batch'] = None
            self.save_progress()
    
    def is_batch_completed(self, batch_num):
        """检查批次是否已完成"""
        return any(b['batch_num'] == batch_num for b in self.progress['completed_batches'])
    
    def finish_all(self):
        """完成所有"""
        self.progress['end_time'] = datetime.now().isoformat()
        self.save_progress()


# ==================== 主函数 ====================

def main():
    """主函数 - 全自动处理"""
    # 配置日志
    log_dir = Path(__file__).parent.parent.parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(
                log_dir / 'qm_full_auto.log',
                encoding='utf-8',
                mode='a'
            ),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    print("\n" + "="*80)
    print("  华北平原气象数据 QM 偏差校正系统 (全自动版)")
    print("="*80)
    
    # 显示配置
    print(f"\n【配置信息】")
    print(f"  校正变量：{', '.join(CONFIG['variables_to_correct'])}")
    print(f"  时间范围：{CONFIG['start_year']} - {CONFIG['end_year']}")
    print(f"  分批大小：{CONFIG['batch_years']} 年/批")
    
    # 计算批次
    total_years = CONFIG['end_year'] - CONFIG['start_year'] + 1
    total_batches = (total_years + CONFIG['batch_years'] - 1) // CONFIG['batch_years']
    print(f"  总批次数：{total_batches}")
    print(f"  预计处理数据量：~{total_years * 365 * 32:,} 条记录")
    
    # 进度管理器
    progress_mgr = ProgressManager(PROGRESS_FILE)
    progress_mgr.progress['start_time'] = datetime.now().isoformat()
    
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
        
        # 检查是否已完成
        if progress_mgr.is_batch_completed(batch_num):
            print(f"\n⏭ 批次 {batch_num} ({start_year}-{end_year}) 已完成，跳过")
            start_year = end_year + 1
            continue
        
        # 显示进度条
        print(f"\n{'='*80}")
        print(f"【批次 {batch_num}/{total_batches}】处理年份：{start_year} - {end_year}")
        print(f"进度：{'='*int((batch_num-1)/total_batches*50)}>{' '*(50-int((batch_num-1)/total_batches*50))} {((batch_num-1)/total_batches*100):.1f}%")
        print(f"{'='*80}")
        
        # 开始批次
        progress_mgr.start_batch(batch_num, start_year, end_year)
        
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
            
            # 标记完成
            progress_mgr.complete_batch(batch_num)
            
        except Exception as e:
            print(f"\n❌ 批次 {batch_num} 失败：{e}")
            logger.error(f"批次 {batch_num} 失败：{e}", exc_info=True)
            fail_count += 1
            
            # 标记失败
            progress_mgr.fail_batch(batch_num, e)
            
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
    
    # 完成所有
    progress_mgr.finish_all()
    
    # 生成最终报告
    print("\n" + "="*80)
    print("  🎉 校正流程完成！")
    print("="*80)
    print(f"\n【执行摘要】")
    print(f"  总批次数：{total_batches}")
    print(f"  成功：{success_count} 批")
    print(f"  失败：{fail_count} 批")
    print(f"  总耗时：{datetime.fromisoformat(progress_mgr.progress['end_time']) - datetime.fromisoformat(progress_mgr.progress['start_time'])}")
    
    if progress_mgr.progress['completed_batches']:
        print(f"\n【已完成的批次】")
        for batch in progress_mgr.progress['completed_batches']:
            print(f"  ✓ 批次 {batch['batch_num']}: {batch['start_year']}-{batch['end_year']}")
    
    if progress_mgr.progress['failed_batches']:
        print(f"\n【失败的批次】")
        for batch in progress_mgr.progress['failed_batches']:
            print(f"  ✗ 批次 {batch['batch_num']}: {batch['start_year']}-{batch['end_year']} - {batch.get('error', '未知错误')}")
    
    print(f"\n【输出目录】")
    print(f"  {Path(CONFIG['output_dir']).absolute()}")
    
    print(f"\n【进度记录】")
    print(f"  {PROGRESS_FILE.absolute()}")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
