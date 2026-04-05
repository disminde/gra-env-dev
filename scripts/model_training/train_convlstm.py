import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
import numpy as np
import os
import time
import logging
from sklearn.metrics import r2_score, mean_squared_error

# ================= 核心配置区 =================
TENSOR_PATH = 'data/processed/spatiotemporal_tensors/convlstm_tensors.npz'

# 引入实验版本控制：每次运行生成独立的文件夹，防止模型覆盖
EXPERIMENT_ID = time.strftime("%Y%m%d_%H%M%S")
SAVE_DIR = os.path.join('convlstm_results', f'exp_{EXPERIMENT_ID}')
os.makedirs(SAVE_DIR, exist_ok=True)

# 训练超参数
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
BATCH_SIZE = 16      # 使用较大的逻辑 Batch Size 
ACCUMULATION_STEPS = 2 # 梯度累加步数，实际显存占用相当于 BATCH_SIZE / ACCUMULATION_STEPS = 8
LEARNING_RATE = 2e-4 # 提高基础学习率以适应大 Batch Size (原为 1e-4)
WARMUP_EPOCHS = 5    # 学习率预热的 Epoch 数
WARMUP_START_LR = 1e-5 # 预热的初始学习率
EPOCHS = 100         # 正式训练
EARLY_STOP_PATIENCE = 10

# 模型超参数
HIDDEN_DIM = 64
KERNEL_SIZE = (3, 3)
NUM_LAYERS = 2
# ==========================================

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(SAVE_DIR, 'train.log')),
        logging.StreamHandler()
    ]
)

class DroughtDataset(Dataset):
    def __init__(self, x_tensor, y_tensor):
        self.x = np.nan_to_num(x_tensor)
        self.y = np.nan_to_num(y_tensor)
        
    def __len__(self):
        return len(self.x)
        
    def __getitem__(self, idx):
        return torch.from_numpy(self.x[idx]), torch.from_numpy(self.y[idx])

class ChannelAttention(nn.Module):
    def __init__(self, in_planes, ratio=16):
        super(ChannelAttention, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.max_pool = nn.AdaptiveMaxPool2d(1)
        
        self.fc1 = nn.Conv2d(in_planes, in_planes // ratio, 1, bias=False)
        self.relu1 = nn.ReLU()
        self.fc2 = nn.Conv2d(in_planes // ratio, in_planes, 1, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        avg_out = self.fc2(self.relu1(self.fc1(self.avg_pool(x))))
        max_out = self.fc2(self.relu1(self.fc1(self.max_pool(x))))
        out = avg_out + max_out
        return self.sigmoid(out)

class SpatialAttention(nn.Module):
    def __init__(self, kernel_size=7):
        super(SpatialAttention, self).__init__()
        assert kernel_size in (3, 7), 'kernel size must be 3 or 7'
        padding = 3 if kernel_size == 7 else 1
        
        self.conv1 = nn.Conv2d(2, 1, kernel_size, padding=padding, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        avg_out = torch.mean(x, dim=1, keepdim=True)
        max_out, _ = torch.max(x, dim=1, keepdim=True)
        x_cat = torch.cat([avg_out, max_out], dim=1)
        out = self.conv1(x_cat)
        return self.sigmoid(out)

class CBAM(nn.Module):
    def __init__(self, in_planes, ratio=16, kernel_size=7):
        super(CBAM, self).__init__()
        self.ca = ChannelAttention(in_planes, ratio)
        self.sa = SpatialAttention(kernel_size)

    def forward(self, x):
        out = x * self.ca(x)
        result = out * self.sa(out)
        return result

class ConvLSTMCell(nn.Module):
    def __init__(self, input_dim, hidden_dim, kernel_size, bias=True, dropout_p=0.2):
        super(ConvLSTMCell, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.kernel_size = kernel_size
        self.padding = kernel_size[0] // 2, kernel_size[1] // 2
        self.bias = bias
        
        self.conv = nn.Conv2d(
            in_channels=self.input_dim + self.hidden_dim,
            out_channels=4 * self.hidden_dim,
            kernel_size=self.kernel_size,
            padding=self.padding,
            bias=self.bias
        )
        
        # 引入 CBAM 注意力机制，提纯核心特征
        self.cbam = CBAM(in_planes=self.hidden_dim)
        
        # 引入 Spatial Dropout，随机丢弃整个通道，防止对局部空间特征过拟合
        self.spatial_dropout = nn.Dropout2d(p=dropout_p)

    def forward(self, input_tensor, cur_state):
        h_cur, c_cur = cur_state
        combined = torch.cat([input_tensor, h_cur], dim=1)
        
        combined_conv = self.conv(combined)
        cc_i, cc_f, cc_o, cc_g = torch.split(combined_conv, self.hidden_dim, dim=1)
        
        i = torch.sigmoid(cc_i)
        f = torch.sigmoid(cc_f)
        o = torch.sigmoid(cc_o)
        g = torch.tanh(cc_g)
        
        c_next = f * c_cur + i * g
        h_next = o * torch.tanh(c_next)
        
        # 先穿过 CBAM 提纯特征，再穿过 Spatial Dropout 进行正则化
        h_next = self.cbam(h_next)
        h_next = self.spatial_dropout(h_next)
        
        return h_next, c_next

class ConvLSTM(nn.Module):
    def __init__(self, input_dim, hidden_dim, kernel_size, num_layers, batch_first=True, bias=True):
        super(ConvLSTM, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.kernel_size = kernel_size
        self.num_layers = num_layers
        self.batch_first = batch_first
        self.bias = bias
        
        cell_list = []
        for i in range(0, self.num_layers):
            cur_input_dim = self.input_dim if i == 0 else self.hidden_dim
            cell_list.append(ConvLSTMCell(
                input_dim=cur_input_dim,
                hidden_dim=self.hidden_dim,
                kernel_size=self.kernel_size,
                bias=self.bias
            ))
        self.cell_list = nn.ModuleList(cell_list)
        
        self.final_conv = nn.Conv2d(
            in_channels=self.hidden_dim,
            out_channels=1,
            kernel_size=1,
            padding=0
        )

    def forward(self, input_tensor):
        if not self.batch_first:
            input_tensor = input_tensor.permute(1, 0, 2, 3, 4)
            
        b, t, c, h, w = input_tensor.size()
        hidden_state = self._init_hidden(batch_size=b, image_size=(h, w))
        
        layer_output_list = []
        last_state_list = []
        cur_layer_input = input_tensor
        
        for layer_idx in range(self.num_layers):
            h_state, c_state = hidden_state[layer_idx]
            output_inner = []
            for t_step in range(t):
                h_state, c_state = self.cell_list[layer_idx](input_tensor=cur_layer_input[:, t_step, :, :, :], cur_state=[h_state, c_state])
                output_inner.append(h_state)
            
            layer_output = torch.stack(output_inner, dim=1)
            cur_layer_input = layer_output
            
            layer_output_list.append(layer_output)
            last_state_list.append([h_state, c_state])
            
        last_time_step_output = layer_output_list[-1][:, -1, :, :, :]
        final_output = self.final_conv(last_time_step_output)
        
        return final_output

    def _init_hidden(self, batch_size, image_size):
        init_states = []
        for i in range(self.num_layers):
            init_states.append((
                torch.zeros(batch_size, self.hidden_dim, image_size[0], image_size[1], device=DEVICE),
                torch.zeros(batch_size, self.hidden_dim, image_size[0], image_size[1], device=DEVICE)
            ))
        return init_states

def train():
    logging.info(f">>> 正在加载张量数据: {TENSOR_PATH}")
    data = np.load(TENSOR_PATH, allow_pickle=True)
    
    # 恢复单流架构：只加载 X 和 Y，抛弃 X_macro
    X, Y = data['X'], data['Y']
    meta = data['meta'].item()
    
    # 修复时间穿越：保留最后 5 年(60个月)的数据作为验证集
    val_months = 60
    if len(X) <= val_months:
        raise ValueError("数据量太少，无法切分出足够大的验证集！")
        
    split_idx = len(X) - val_months
    
    train_x, val_x = X[:split_idx], X[split_idx:]
    train_y, val_y = Y[:split_idx], Y[split_idx:]
    
    train_dataset = DroughtDataset(train_x, train_y)
    val_dataset = DroughtDataset(val_x, val_y)
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)
    
    input_channels = len(meta['features'])
    
    model = ConvLSTM(
        input_dim=input_channels,
        hidden_dim=HIDDEN_DIM,
        kernel_size=KERNEL_SIZE,
        num_layers=NUM_LAYERS,
        batch_first=True
    ).to(DEVICE)
    
    optimizer = optim.Adam(model.parameters(), lr=WARMUP_START_LR, weight_decay=1e-5) # 初始使用 Warmup LR
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=5)
    
    # 将 MSELoss 替换为 HuberLoss，增强对极端值的鲁棒性
    # 降低 delta 值 (从 1.0 降至 0.5)，强迫网络对更小范围的偏差就转入线性敏感区，打破趋中效应
    criterion = nn.HuberLoss(delta=0.5)
    
    logging.info(f">>> 模型初始化完成，使用设备: {DEVICE}")
    logging.info(f">>> 开始训练，训练集大小: {len(train_dataset)}, 验证集大小: {len(val_dataset)}")
    
    best_val_loss = float('inf')
    patience_counter = 0
    
    for epoch in range(EPOCHS):
        # --- 学习率线性 Warmup 逻辑 ---
        if epoch < WARMUP_EPOCHS:
            # 线性插值计算当前 epoch 的学习率
            current_lr = WARMUP_START_LR + (LEARNING_RATE - WARMUP_START_LR) * (epoch / WARMUP_EPOCHS)
            for param_group in optimizer.param_groups:
                param_group['lr'] = current_lr
            logging.info(f"--- Warmup Epoch {epoch+1}/{WARMUP_EPOCHS} - 当前学习率调整为: {current_lr:.6f} ---")
        elif epoch == WARMUP_EPOCHS:
            # Warmup 结束，确保切换到基础学习率
            for param_group in optimizer.param_groups:
                param_group['lr'] = LEARNING_RATE
            logging.info(f"--- Warmup 结束，切换至基础学习率: {LEARNING_RATE:.6f}，并交由 ReduceLROnPlateau 接管 ---")
        # --------------------------------
        
        model.train()
        train_losses = []
        optimizer.zero_grad() # 梯度累加前先清零
        
        for i, (batch_x, batch_y) in enumerate(train_loader):
            batch_x, batch_y = batch_x.to(DEVICE), batch_y.to(DEVICE)
            
            output = model(batch_x)
            
            # Spatial Mask: 忽略海洋和无效背景区域（值为0的像素）
            mask = (batch_y != 0)
            if mask.sum() > 0:
                loss = criterion(output[mask], batch_y[mask])
                
                # 梯度累加：将 loss 除以累加步数
                loss = loss / ACCUMULATION_STEPS
                loss.backward()
                
                # 记录真实 loss 值用于日志打印
                train_losses.append(loss.item() * ACCUMULATION_STEPS)
            
            # 当达到累加步数或者是当前 epoch 的最后一个 batch 时，执行梯度更新
            if (i + 1) % ACCUMULATION_STEPS == 0 or (i + 1) == len(train_loader):
                optimizer.step()
                optimizer.zero_grad()
            
        model.eval()
        val_losses = []
        val_preds_list = []
        val_targets_list = []
        
        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                batch_x, batch_y = batch_x.to(DEVICE), batch_y.to(DEVICE)
                output = model(batch_x)
                
                mask = (batch_y != 0)
                if mask.sum() > 0:
                    val_loss = criterion(output[mask], batch_y[mask])
                    val_losses.append(val_loss.item())
                    
                    # 提取有效区域用于 R2 和 RMSE 计算
                    val_preds_list.append(output[mask].cpu().numpy())
                    val_targets_list.append(batch_y[mask].cpu().numpy())
        
        avg_train_loss = np.mean(train_losses) if train_losses else float('inf')
        avg_val_loss = np.mean(val_losses) if val_losses else float('inf')
        
        # 计算评估指标
        if val_preds_list and val_targets_list:
            all_preds = np.concatenate(val_preds_list)
            all_targets = np.concatenate(val_targets_list)
            val_rmse = np.sqrt(mean_squared_error(all_targets, all_preds))
            val_r2 = r2_score(all_targets, all_preds)
        else:
            val_rmse = float('inf')
            val_r2 = -float('inf')
        
        logging.info(f"Epoch [{epoch+1}/{EPOCHS}] - Train Loss: {avg_train_loss:.6f} | Val Loss: {avg_val_loss:.6f} | Val RMSE: {val_rmse:.4f} | Val R2: {val_r2:.4f}")
        
        # 更新学习率
        # 注意：在 Warmup 阶段不应调用 ReduceLROnPlateau，否则会打乱预热节奏
        if epoch >= WARMUP_EPOCHS:
            scheduler.step(avg_val_loss)
        
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            try:
                torch.save(model.state_dict(), os.path.join(SAVE_DIR, 'best_convlstm.pth'))
                logging.info(f"✅ 发现更优模型 (Val Loss: {best_val_loss:.6f})，已保存！")
            except Exception as e:
                logging.error(f"❌ 模型保存失败: {e}")
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= EARLY_STOP_PATIENCE:
                logging.info(f"🛑 早停机制触发，验证集Loss已连续 {EARLY_STOP_PATIENCE} 轮未下降。")
                break
                
    logging.info(">>> 训练流程全部结束。")

if __name__ == '__main__':
    train()