import socket
import json
import os
import re
import time

# --- CONFIGURATION ---
WEIGHTS_FILE = "/home/lawmj04/law-brewing/tap_weights.json"
PORT = 1234
PUSH_COOLDOWN = 15  # Seconds to wait between GitHub pushes

TAP_CONFIG = {
    '192.168.86.47':  {'name': 'Law Tap',   'empty': 4500, 'full': 23600},
    '192.168.86.116': {'name': 'Wisco Tap', 'empty': 4500, 'full': 23600},
    '192.168.86.45':  {'name': 'Nitro Tap', 'empty': 4500, 'full': 23600}
}

current_weights = {
    "Law Tap": 0, "Law Tap_updated": "Waiting...",
    "Wisco Tap": 0, "Wisco Tap_updated": "Waiting...",
    "Nitro Tap": 0, "Nitro Tap_updated": "Waiting...",
    "last_updated": ""
}

last_sync_time = 0

def calculate_percent(raw_val, tap_ip):
    conf = TAP_CONFIG.get(tap_ip, {'empty': 4500, 'full': 23600})
    pct = ((raw_val - conf['empty']) / (conf['full'] - conf['empty'])) * 100
    return max(0, min(100, round(pct)))

def sync_to_github():
    global last_sync_time
    
    # COOLDOWN CHECK
    if time.time() - last_sync_time < PUSH_COOLDOWN:
        return

    try:
        current_weights["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(current_weights, f, indent=4)
        
        # Git Sync Logic
        os.system("git config user.email 'bot@lawbrewing.com'")
        os.system("git config user.name 'BeerBot'")
        
        # Pull with rebase ensures we don't get 'rejected' errors
        cmd = (
            f"git add {WEIGHTS_FILE} && "
            "git commit -m 'Scale Update' && "
            "git pull origin master --rebase && "
            "git push origin master"
        )
        os.system(cmd)
        print("🌍 GitHub Sync Complete")
        
        last_sync_time = time.time()
        
    except Exception as e:
        print(f"⚠️ GitHub Sync Failed: {e}")

def start_server():
    print("🚀 Initializing Socket...")
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
        try:
            conn, addr = sock.accept()
            tap_ip = addr[0]
            # Increased timeout to 10s to prevent 'Connection timed out' errors
            conn.settimeout(10.0)

            while True:
                raw_data = conn.recv(1024).decode('utf-8', errors='ignore')
                if not raw_data: break 
                
                # Clean Data: Replace Nulls with SPACE
                clean_data = raw_data.replace('\x00', ' ').strip()
                
                # Extract number after "vw"
                weight_match = re.search(r"vw.*?(-?\d+\.?\d*)", clean_data)

                if weight_match and tap_ip in TAP_CONFIG:
                    try:
                        raw_weight = float(weight_match.group(1))
                        
                        # --- THE BOUNCER ---
                        # Allow 0 (removed scale) OR 3.5kg-30kg (active kegs)
                        if raw_weight != 0 and (raw_weight < 3500 or raw_weight > 30000):
                            continue
                        
                        tap_name = TAP_CONFIG[tap_ip]['name']
                        percent = calculate_percent(raw_weight, tap_ip)
                        
                        current_weights[f"{tap_name}_updated"] = time.strftime("%H:%M:%S")

                        if current_weights.get(tap_name) != percent:
                            current_weights[tap_name] = percent
                            print(f"🍺 {tap_name} Update: {raw_weight}g -> {percent}%")
                            sync_to_github()
                        
                        # Send acknowledgment back to scale
                        conn.sendall(b'\x00\x00\x01\x00\xc8')
                    except ValueError:
                        pass

                elif len(clean_data) > 5:
                    conn.sendall(b'\x00\x00\x01\x00\xc8')

        except Exception as e:
            # Only print error if it's not a standard silent timeout
            if "timed out" not in str(e):
                print(f"⚠️ Connection Error: {e}")
        finally:
            try: conn.close()
            except: pass

if __name__ == "__main__":
    start_server()
