# -*- coding: utf-8 -*-
"""
GPU Environment Verification Script

This script tests if the Docker container has successfully mounted the host's GPU
and if the machine learning libraries (PyTorch, XGBoost) can access it.
"""

import sys
import os

def print_separator(title):
    print(f"\n{'='*20} {title} {'='*20}")

def test_pytorch_gpu():
    print_separator("PyTorch GPU Test")
    try:
        import torch
        print(f"PyTorch Version: {torch.__version__}")
        
        is_available = torch.cuda.is_available()
        print(f"CUDA Available: {is_available}")
        
        if is_available:
            device_count = torch.cuda.device_count()
            print(f"Number of GPUs detected: {device_count}")
            
            for i in range(device_count):
                props = torch.cuda.get_device_properties(i)
                print(f"\nGPU {i}:")
                print(f"  Name: {props.name}")
                print(f"  Total VRAM: {props.total_memory / 1024**3:.2f} GB")
                print(f"  Compute Capability: {props.major}.{props.minor}")
                
            # Perform a simple tensor operation on GPU
            print("\nExecuting simple tensor multiplication on GPU...")
            x = torch.rand(5000, 5000).cuda()
            y = torch.rand(5000, 5000).cuda()
            z = torch.matmul(x, y)
            print("  -> Success! Tensor computation completed on GPU.")
        else:
            print("  -> FAILED: PyTorch cannot detect the GPU.")
            
    except ImportError:
        print("  -> FAILED: PyTorch is not installed.")
    except Exception as e:
        print(f"  -> ERROR: {e}")

def test_xgboost_gpu():
    print_separator("XGBoost GPU Test")
    try:
        import xgboost as xgb
        import numpy as np
        print(f"XGBoost Version: {xgb.__version__}")
        
        # Create a small dummy dataset
        X = np.random.rand(1000, 10)
        y = np.random.randint(0, 2, 1000)
        dtrain = xgb.DMatrix(X, label=y)
        
        # Set parameters to strictly use GPU
        params = {
            'tree_method': 'hist',
            'device': 'cuda', # Modern way to specify GPU in XGBoost 2.x+
            'objective': 'binary:logistic'
        }
        
        print("Attempting to train a tiny XGBoost model on GPU...")
        bst = xgb.train(params, dtrain, num_boost_round=10)
        print("  -> Success! XGBoost trained successfully using 'cuda' device.")
        
    except ImportError:
        print("  -> FAILED: XGBoost is not installed.")
    except xgb.core.XGBoostError as e:
        print(f"  -> FAILED: XGBoost threw an error. This usually means GPU support is missing.\n  -> Details: {e}")
    except Exception as e:
        print(f"  -> ERROR: {e}")

if __name__ == "__main__":
    print("Starting GPU Environment Verification...")
    print(f"Python Version: {sys.version}")
    
    test_pytorch_gpu()
    test_xgboost_gpu()
    
    print_separator("Verification Complete")
