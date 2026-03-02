import requests
try:
    print("Trying 127.0.0.1...")
    resp = requests.get('http://127.0.0.1:8181', timeout=5)
    print(f"Status: {resp.status_code}")
except Exception as e:
    print(f"Error 127.0.0.1: {repr(e)}")

try:
    print("Trying localhost...")
    resp = requests.get('http://localhost:8181', timeout=5)
    print(f"Status: {resp.status_code}")
except Exception as e:
    print(f"Error localhost: {repr(e)}")
