import requests
import logging

# 常见的 Clash API 端口列表
POTENTIAL_PORTS = [9090, 9097, 9999, 7890, 7891, 10000]

def find_clash_api():
    print("🔍 正在为您全量探测 Clash API 端口，请稍候...")
    print("-" * 40)
    
    found = False
    for port in range(9000, 9100): # 扫描最常见的 9000-9100 段
        url = f"http://127.0.0.1:{port}"
        try:
            # 尝试访问 Clash 的版本接口，这是不需要 Secret 的
            resp = requests.get(f"{url}/version", timeout=0.2)
            if resp.status_code == 200:
                print(f"🎯 找到啦！您的 Clash API 运行在端口: {port}")
                print(f"建议：请将脚本中的 CLASH_API_URL 修改为 'http://127.0.0.1:{port}'")
                found = True
                break
        except:
            continue
            
    if not found:
        # 如果 9000 段没找到，尝试 7890 段
        for port in [7890, 7891, 7892]:
            url = f"http://127.0.0.1:{port}"
            try:
                resp = requests.get(f"{url}/version", timeout=0.2)
                if resp.status_code == 200:
                    print(f"🎯 找到啦！您的 Clash API 运行在端口: {port}")
                    found = True
                    break
            except:
                continue

    if not found:
        print("❌ 探测失败。可能原因：")
        print("1. Clash 禁用了外部控制（请检查 config.yaml 中的 external-controller）")
        print("2. 您设置了核心 Secret（请在脚本中填入 secret 后再运行探测）")
    
    print("-" * 40)

if __name__ == "__main__":
    find_clash_api()
