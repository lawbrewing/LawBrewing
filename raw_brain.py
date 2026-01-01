import socket
import json
import os
import re
import time

# --- CONFIGURATION ---
# The file that the website reads
WEIGHTS_FILE = "/home/lawmj04/law-brewing/tap_weights.json"
PORT = 1234

# MAP IPs TO TAP NAMES
# This is how we know which tap is which
TAP_CONFIG = {
    '192.168.86.47':  {'name': 'Law Tap',   'empty': 480, 'full': 4150},
    '192.168.86.116': {'name': 'Wisco Tap', 'empty': 500, 'full': 4000},
    '192.168.86.45':  {'name': 'Nitro Tap', 'empty': 450, 'full': 4200}
}

# Default State
current_weights = {"Law Tap": 0, "Wisco Tap": 0, "Nitro Tap": 0}

def calculate_percent(raw_val, tap_ip):
    conf = TAP_CONFIG.get(tap_ip, {'empty': 500, 'full': 4000})
    
    # Filter out garbage noise from scale
    if raw_val > 10000 or raw_val < -500: 
        return 0 
    
    pct = ((raw_val - conf['empty']) / (conf['full'] - conf['empty'])) * 100
    return max(0, min(100, round(pct)))

def sync_to_github():
    """Syncs with GitHub using the Master branch and Rebase to prevent jams"""
    try:
        # Save timestamp
        current_weights["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(current_weights, f, indent=4)

        # THE FIX: Pull first, then Push to MASTER
        cmd = (
            f"git add {WEIGHTS_FILE} && "
            "git commit -m 'Scale Update' && "
            "git pull origin master --rebase && "
            "git push origin master"
        )
        
        # Run it (blocking, not background, to ensure safety)
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
        print(f"🧠 Brain Online. Listening for Taps: {list(TAP_CONFIG.keys())}")
    except OSError as e:
        print(f"❌ Port Error: {e}")
        return

    while True:
        conn, addr = sock.accept()
        tap_ip = addr[0] # Get the IP address of the scale
        
        try:
            # 1. Send Handshake (Keep-Alive for scale)
            conn.sendall(b'\x00\x00\x01\x00\xc8') 

            # 2. Receive Data
            raw_data = conn.recv(1024).decode('utf-8', errors='ignore')
            if not raw_data: continue
# --- ADD THIS LINE HERE ---
            print(f"🔍 DEBUG: Received from {tap_ip}: {raw_data}") 
            # --------------------------
            # 3. Find the weight number in the string
            match = re.search(r"(\d{1,4})", raw_data)
            
            if match and tap_ip in TAP_CONFIG:
                raw_weight = float(match.group(1))
                tap_name = TAP_CONFIG[tap_ip]['name']
                
                # Calculate percent
                percent = calculate_percent(raw_weight, tap_ip)
                
                # Only update/sync if the weight changed
                if current_weights.get(tap_name) != percent:
                    current_weights[tap_name] = percent
                    print(f"📡 {tap_name} ({tap_ip}): {raw_weight}g -> {percent}%")
                    sync_to_github()
            elif tap_ip not in TAP_CONFIG:
                print(f"⚠️ Unknown Scale IP connected: {tap_ip}")

        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    start_server()
