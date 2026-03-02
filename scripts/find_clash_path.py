import psutil
import os

def find_clash_paths():
    clash_exe = None
    clash_core = None
    
    # Method 1: Check running processes
    for proc in psutil.process_iter(['name', 'exe']):
        try:
            if proc.info['name'] == 'Clash for Windows.exe':
                clash_exe = proc.info['exe']
                print(f"Found running Clash GUI: {clash_exe}")
                # The core is usually in resources/static/files/win/x64/clash-win64.exe
                # relative to the install dir
                install_dir = os.path.dirname(clash_exe)
                potential_core = os.path.join(install_dir, 'resources', 'static', 'files', 'win', 'x64', 'clash-win64.exe')
                if os.path.exists(potential_core):
                    clash_core = potential_core
                    print(f"Found Clash Core via running process: {clash_core}")
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    # Method 2: Common paths if not found
    if not clash_core:
        user_home = os.path.expanduser("~")
        common_paths = [
            os.path.join(user_home, "AppData", "Local", "Programs", "Clash for Windows", "resources", "static", "files", "win", "x64", "clash-win64.exe"),
            r"C:\Program Files\Clash for Windows\resources\static\files\win\x64\clash-win64.exe"
        ]
        for path in common_paths:
            if os.path.exists(path):
                clash_core = path
                print(f"Found Clash Core in common path: {clash_core}")
                break

    return clash_core

if __name__ == "__main__":
    core_path = find_clash_paths()
    if core_path:
        print(f"FINAL_CORE_PATH: {core_path}")
    else:
        print("Clash Core not found.")