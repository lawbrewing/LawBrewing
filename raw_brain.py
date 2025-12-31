import socket
import json
import requests
import re
import os

# --- CONFIGURATION ---
HUB_URL = "http://localhost:5000/update_weight"
# The file that gets pushed to GitHub
WEIGHTS_FILE = "tap_weights.json"

TAP_CONFIG = {
    '192.168.86.47':  {'name': 'Law Tap',   'empty': 480, 'full': 4150},
    '192.168.86.116': {'name': 'Wisco Tap', 'empty': 500, 'full': 4000},
    '192.168.86.45':  {'name': 'Nitro Tap', 'empty': 450, 'full': 4200}
}

# Current state to prevent constant re-syncing if weights haven't changed
current_weights = {"Law Tap": 0, "Wisco Tap": 0, "Nitro Tap": 0}

def calculate_percent(raw_val, tap_ip):
    conf = TAP_CONFIG.get(tap_ip, {'empty': 500, 'full': 4000})
    # If the scale sends absolute garbage (scientific notation), default to 0
    if raw_val > 10000 or raw_val < -500: 
        return 0 
    
    pct = ((raw_val - conf['empty']) / (conf['full'] - conf['empty'])) * 100
    return max(0, min(100, round(pct)))

def sync_to_github():
    """Writes weights to JSON and pushes to GitHub Pages"""
    try:
        # 1. Write the file
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(current_weights, f)

        # 2. Sync commands
        # We add 'git pull --rebase' to make sure the Pi catches up to website changes
        # We remove the '&' so we can actually see if it fails
        cmd = (
            f"git pull --rebase && "
            f"git add {WEIGHTS_FILE} && "
            f"git commit -m 'Scale Sync' && "
            f"git push"
        )
        
        os.system(cmd)
        print("🌍 GitHub Sync Complete")
    except Exception as e:
        print(f"⚠️ GitHub Sync Failed: {e}")
def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 1234))
    sock.listen(5)
    print("🚀 3-Tap Brain (Fixed Parser + Sync) Live...")

    while True:
        conn, addr = sock.accept()
        try:
            # 1. Send the 5-byte "Success" handshake to keep scale online
            conn.sendall(b'\x00\x00\x01\x00\xc8') 

            # 2. Receive the raw message
            raw_data = conn.recv(1024).decode('utf-8', errors='ignore')
            if not raw_data: continue

            # 3. FIX: Only grab the first 1-4 digits found (the weight)
            # This ignores the long serial/ID numbers that caused the 8.7M error
            match = re.search(r"(\d{1,4})", raw_data)
            
            if match:
                raw_weight = float(match.group(1))
                tap_ip = addr[0]
                
                if tap_ip in TAP_CONFIG:
                    tap_name = TAP_CONFIG[tap_ip]['name']
                    percent = calculate_percent(raw_weight, tap_ip)

                    # Only update if the percentage has changed
                    if current_weights[tap_name] != percent:
                        current_weights[tap_name] = percent
                        print(f"📡 {tap_name} ({tap_ip}): {raw_weight}g -> {percent}%")
                        
                        # Update Local Hub
                        try:
                            requests.post(HUB_URL, json={'tap': tap_name, 'percent': percent}, timeout=1)
                        except:
                            print("⚠️ Local Hub unreachable (Port 5000)")

                        # Update Public GitHub
                        sync_to_github()

        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    start_server()
