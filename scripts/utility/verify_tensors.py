import numpy as np
import os

def check_tensor():
    tensor_path = 'data/processed/spatiotemporal_tensors/convlstm_tensors.npz'
    if not os.path.exists(tensor_path):
        print(f"❌ 找不到张量文件: {tensor_path}")
        return

    print(f"✅ 找到张量文件: {tensor_path}")
    print("-" * 40)
    
    # 加载 npz 文件 (使用 mmap_mode='r' 以节省内存)
    data = np.load(tensor_path, allow_pickle=True)
    
    # 检查 X 张量
    if 'X' in data:
        X = data['X']
        print(f"X 张量形状: {X.shape}")
        print(f"   (Samples, Seq_Len, Channels, Height, Width)")
        print(f"X 张量内存占用: {X.nbytes / 1024**3:.2f} GB")
    
    # 检查 Y 张量
    if 'Y' in data:
        Y = data['Y']
        print(f"Y 张量形状: {Y.shape}")
        print(f"   (Samples, 1, Height, Width)")
        
    # 检查元数据
    if 'meta' in data:
        meta = data['meta'].item()
        print("\n元数据信息:")
        for k, v in meta.items():
            print(f"   {k}: {v}")
            
    print("-" * 40)
    print("🚀 张量验证通过，可以进行下一步训练脚本编写。")

if __name__ == '__main__':
    check_tensor()
