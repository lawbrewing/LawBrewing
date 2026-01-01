import socket
import json
import os
import re
import time

# --- CONFIGURATION ---
WEIGHTS_FILE = "/home/lawmj04/law-brewing/tap_weights.json"
PORT = 1234

# MAP IPs TO TAP NAMES
TAP_CONFIG = {
    '192.168.86.47':  {'name': 'Law Tap',   'empty': 480, 'full': 4150},
    '192.168.86.116': {'name': 'Wisco Tap', 'empty': 500, 'full': 4000},
    '192.168.86.45':  {'name': 'Nitro Tap', 'empty': 450, 'full': 4200}
}

# Initialize with timestamp slots so the website doesn't crash reading them
current_weights = {
    "Law Tap": 0, "Law Tap_updated": "Waiting...",
    "Wisco Tap": 0, "Wisco Tap_updated": "Waiting...",
    "Nitro Tap": 0, "Nitro Tap_updated": "Waiting...",
    "last_updated": ""
}

def calculate_percent(raw_val, tap_ip):
    conf = TAP_CONFIG.get(tap_ip, {'empty': 500, 'full': 4000})
    if raw_val > 10000 or raw_val < -500: return 0 
    pct = ((raw_val - conf['empty']) / (conf['full'] - conf['empty'])) * 100
    return max(0, min(100, round(pct)))

def sync_to_github():
    try:
        current_weights["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(current_weights, f, indent=4)

        # Pull first to prevent jams, then push
        cmd = (
            f"git add {WEIGHTS_FILE} && "
            "git commit -m 'Scale Update' && "
            "git pull origin master --rebase && "
            "git push origin master"
        )
        os.system(cmd)
        print("🌍 GitHub Sync Complete")
    except Exception as e:
        print(f"⚠️ GitHub Sync Failed: {e}")

def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind(('0.0.0.0', PORT))
        sock.listen(5)
        print(f"🧠 Brain Online. Listening for: {list(TAP_CONFIG.keys())}")
    except OSError as e:
        print(f"❌ Port Error: {e}")
        return

    while True:
        conn, addr = sock.accept()
        tap_ip = addr[0]
        
        try:
            conn.sendall(b'\x00\x00\x01\x00\xc8') 
            raw_data = conn.recv(1024).decode('utf-8', errors='ignore')
            if not raw_data: continue

            # DEBUG: Print everything so we see the heartbeat
            print(f"🔍 DEBUG: Received from {tap_ip}: {raw_data}")

            match = re.search(r"(\d{1,4})", raw_data)
            if match and tap_ip in TAP_CONFIG:
                raw_weight = float(match.group(1))
                tap_name = TAP_CONFIG[tap_ip]['name']
                percent = calculate_percent(raw_weight, tap_ip)
                
                # Update the timestamp for THIS specific tap
                current_weights[f"{tap_name}_updated"] = time.strftime("%H:%M:%S")

                # If weight changed, save the new percent too
                if current_weights.get(tap_name) != percent:
                    current_weights[tap_name] = percent
                    print(f"📡 {tap_name} Update: {percent}%")
                    sync_to_github()
                
                # OPTIONAL: Uncomment this if you want to sync timestamps even if weight doesn't change
                # sync_to_github() 

        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    start_server()
