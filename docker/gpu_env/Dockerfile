# Use NVIDIA's official CUDA image with runtime and cuDNN support for Ubuntu 22.04
# Updated to 12.4.1 to match RTX 5080 (sm_120) and modern PyTorch
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# Set environment variables to avoid user interaction during apt installations
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai
# Ensure Python output is not buffered
ENV PYTHONUNBUFFERED=1

# 移除或修复导致公钥错误的阿里云源替换，使用官方源或更稳健的清华源
# RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
#     sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 确保安装基础证书和工具，防止 PPA 添加失败
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    ca-certificates \
    curl \
    git \
    build-essential \
    libpq-dev \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Upgrade pip (配置 pip 为国内清华源，加速后续 Python 库下载)
RUN python -m pip install --no-cache-dir --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# Create a working directory
WORKDIR /app

# Install PyTorch with CUDA 12.6/12.8 support (Nightly build required for RTX 50 series / sm_120)
# RTX 5080 (Blackwell) requires PyTorch 2.6.0+ which is only available in the nightly/preview channel currently
RUN pip install --no-cache-dir --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu126

# Copy requirements and install other dependencies (同样使用清华源加速)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Default command (keeps container running, or you can run jupyter/bash)
CMD ["tail", "-f", "/dev/null"]