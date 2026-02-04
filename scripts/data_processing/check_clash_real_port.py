import psutil
import socket

def find_clash_listening_ports():
    print("🔍 正在扫描系统进程，寻找 Clash 的真实端口...")
    print("-" * 50)
    
    clash_ports = []
    
    # 遍历所有进程
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # 匹配 Clash 的进程名（CFW 通常是 Clash for Windows.exe 或 clash-win64.exe）
            if 'clash' in proc.info['name'].lower():
                connections = proc.connections(kind='inet')
                for conn in connections:
                    if conn.status == 'LISTEN':
                        clash_ports.append((proc.info['name'], conn.laddr.port))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not clash_ports:
        print("❌ 未发现正在运行的 Clash 进程。请确保 Clash for Windows 已启动。")
    else:
        print(f"✅ 发现 Clash 相关进程正在监听以下端口:")
        # 去重显示
        seen = set()
        for name, port in clash_ports:
            if port not in seen:
                purpose = "可能是 API 端口" if port != 7890 else "代理端口 (Mixed Port)"
                print(f" - 进程: {name} | 端口: {port} ({purpose})")
                seen.add(port)
        
        print("\n💡 提示：")
        print("1. 如果列表里有 9090 以外的端口，请尝试修改脚本中的 CLASH_API_URL。")
        print("2. 如果列表里有 9090，但脚本依然失败，请务必将“设置”页面的【核心Secret】复制到脚本的 CLASH_SECRET 中。")

if __name__ == "__main__":
    try:
        import psutil
    except ImportError:
        print("正在为您安装必要的检测工具 psutil...")
        import subprocess
        subprocess.check_call(["pip", "install", "psutil"])
        import psutil
        
    find_clash_listening_ports()
