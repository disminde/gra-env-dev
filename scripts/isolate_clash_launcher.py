import os
import subprocess
import yaml
import time
import requests
import sys
import shutil

# --- Configuration ---
CLASH_CORE_PATH = r"C:\Users\27148\Downloads\Clash.for.Windows-0.20.39-win\resources\static\files\win\x64\clash-win64.exe"
USER_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "clash")
ORIGINAL_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "config.yaml")
PROFILES_DIR = os.path.join(USER_CONFIG_DIR, "profiles")
LIST_PATH = os.path.join(PROFILES_DIR, "list.yml")
CRAWLER_CONFIG_PATH = os.path.join(os.getcwd(), "crawler_config.yaml")

# Isolated Ports
CRAWLER_HTTP_PORT = 17890
CRAWLER_API_PORT = 19090
CRAWLER_API_URL = f"http://127.0.0.1:{CRAWLER_API_PORT}"

def get_active_profile_path():
    """Find the currently active profile path from list.yml."""
    if not os.path.exists(LIST_PATH):
        print(f"Profiles list not found at {LIST_PATH}")
        return None
    
    try:
        with open(LIST_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            index = data.get('index', 0)
            files = data.get('files', [])
            if 0 <= index < len(files):
                filename = files[index]['time']
                return os.path.join(PROFILES_DIR, filename)
    except Exception as e:
        print(f"Error reading profiles list: {e}")
    return None

def setup_crawler_config():
    """Create a dedicated Clash config for the crawler."""
    profile_path = get_active_profile_path()
    if not profile_path or not os.path.exists(profile_path):
        print(f"Active profile not found: {profile_path}")
        # Fallback to config.yaml if profile fails, though unlikely to work well
        profile_path = ORIGINAL_CONFIG_PATH

    print(f"Using profile: {profile_path}")

    try:
        # Load the profile content
        with open(profile_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Load base config to get the secret if not in profile
        base_secret = ''
        if os.path.exists(ORIGINAL_CONFIG_PATH):
             with open(ORIGINAL_CONFIG_PATH, 'r', encoding='utf-8') as f:
                 base_config = yaml.safe_load(f)
                 base_secret = base_config.get('secret', '')

        # Modify ports to avoid conflict with main instance
        config['mixed-port'] = CRAWLER_HTTP_PORT
        config['port'] = CRAWLER_HTTP_PORT
        config['socks-port'] = CRAWLER_HTTP_PORT + 1
        config['external-controller'] = f"127.0.0.1:{CRAWLER_API_PORT}"
        
        # Ensure secret is consistent
        if 'secret' not in config and base_secret:
            config['secret'] = base_secret
        
        # Ensure allow-lan is off for security if running locally
        config['allow-lan'] = False
        
        # Save to project directory
        with open(CRAWLER_CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f)
            
        print(f"Created isolated config at {CRAWLER_CONFIG_PATH}")
        return config.get('secret', '')
    except Exception as e:
        print(f"Failed to setup config: {e}")
        return None

def start_clash_core():
    """Start the Clash Core with the isolated config."""
    if not os.path.exists(CLASH_CORE_PATH):
        print(f"Error: Clash Core not found at {CLASH_CORE_PATH}")
        return None

    # Working directory should be the user's config dir so it finds Country.mmdb
    cmd = [
        CLASH_CORE_PATH,
        '-f', CRAWLER_CONFIG_PATH,
        '-d', USER_CONFIG_DIR
    ]
    
    print(f"Starting isolated Clash Core on port {CRAWLER_HTTP_PORT} (API: {CRAWLER_API_PORT})...")
    # Redirect stdout/stderr to devnull to keep terminal clean, or log file
    with open("crawler_clash.log", "w") as log_file:
        process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
        
    return process

def wait_for_clash(secret):
    """Wait for Clash API to be responsive."""
    print("Waiting for Clash to initialize...")
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    for _ in range(10):
        try:
            resp = requests.get(f"{CRAWLER_API_URL}/version", headers=headers, timeout=1)
            if resp.status_code == 200:
                print("Clash is ready!")
                return True
        except:
            time.sleep(1)
    return False

def run_crawler_script(secret):
    """Run the batch fetch script with modified environment variables."""
    env = os.environ.copy()
    
    # Override environment variables for the fetcher script
    env["CLASH_API_URL"] = CRAWLER_API_URL
    env["HTTP_PROXY"] = f"http://127.0.0.1:{CRAWLER_HTTP_PORT}"
    env["HTTPS_PROXY"] = f"http://127.0.0.1:{CRAWLER_HTTP_PORT}"
    env["NO_PROXY"] = "localhost,127.0.0.1"
    if secret:
        env["CLASH_SECRET"] = secret

    # Also pass as args if the script supports it, but env vars are cleaner
    script_path = os.path.join("scripts", "data_processing", "batch_fetch_weather.py")
    
    print(f"Launching crawler script with proxy {env['HTTP_PROXY']}...")
    try:
        # Run and wait for it to finish (or until user interrupts)
        subprocess.run([sys.executable, script_path], env=env, check=True)
    except KeyboardInterrupt:
        print("\nCrawler interrupted by user.")
    except Exception as e:
        print(f"Crawler failed: {e}")

def main():
    secret = setup_crawler_config()
    if secret is None:
        return

    clash_process = start_clash_core()
    if not clash_process:
        return

    try:
        if wait_for_clash(secret):
            run_crawler_script(secret)
        else:
            print("Failed to start Clash within timeout.")
    finally:
        print("Shutting down isolated Clash Core...")
        clash_process.terminate()
        clash_process.wait()
        print("Done.")

if __name__ == "__main__":
    main()