import requests
import socket

def check_port(port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except:
        return False

def probe_clash_api(port):
    try:
        url = f"http://127.0.0.1:{port}/version"
        # Try without auth first
        resp = requests.get(url, timeout=1)
        print(f"Port {port}: Status {resp.status_code}, Body: {resp.text[:50]}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"Port {port}: Connection Refused (HTTP)")
    except Exception as e:
        print(f"Port {port}: Error {e}")
    return False

if __name__ == "__main__":
    # Candidate ports from netstat
    # PID 19936 (Clash Proxy 7890) has 10380
    
    candidates = [3936, 9090, 7342, 5492, 10380, 9080, 6821, 12280, 7890, 9097, 12531]
    
    print("Scanning candidate ports...")
    for port in candidates:
        if check_port(port):
            print(f"Port {port} is OPEN (TCP)")
            probe_clash_api(port)
        else:
            print(f"Port {port} is CLOSED")
