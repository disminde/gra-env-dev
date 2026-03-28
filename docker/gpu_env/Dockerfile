# Use NVIDIA's official CUDA image with runtime and cuDNN support for Ubuntu 22.04
# We use 12.1.1 which is highly compatible with the latest PyTorch
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Set environment variables to avoid user interaction during apt installations
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai
# Ensure Python output is not buffered
ENV PYTHONUNBUFFERED=1

# 替换 Ubuntu 官方源为阿里云源 (加速国内 apt-get 下载)
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# Install system dependencies and Python 3.11
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    curl \
    git \
    build-essential \
    libpq-dev \
    && add-apt-repository ppa:deadsnakes/ppa \
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

# Install PyTorch with CUDA 12.1 support directly first
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Copy requirements and install other dependencies (同样使用清华源加速)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Default command (keeps container running, or you can run jupyter/bash)
CMD ["tail", "-f", "/dev/null"]