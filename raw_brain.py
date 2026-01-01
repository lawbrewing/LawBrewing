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

current_weights = {
    "Law Tap": 0, "Law Tap_updated": "Waiting...",
    "Wisco Tap": 0, "Wisco Tap_updated": "Waiting...",
    "Nitro Tap": 0, "Nitro Tap_updated": "Waiting...",
    "last_updated": ""
}

def calculate_percent(raw_val, tap_ip):
    conf = TAP_CONFIG.get(tap_ip, {'empty': 500, 'full': 4000})
    # Filter insane values (e.g. if scale sends 999999)
    if raw_val > 20000 or raw_val < -500: return 0 
    
    pct = ((raw_val - conf['empty']) / (conf['full'] - conf['empty'])) * 100
    return max(0, min(100, round(pct)))

def sync_to_github():
    try:
        current_weights["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(current_weights, f, indent=4)
        
        # Configure Git Identity (Just in case)
        os.system("git config user.email 'bot@lawbrewing.com'")
        os.system("git config user.name 'BeerBot'")
        
        cmd = (
            f"git add {WEIGHTS_FILE} && "
            "git commit -m 'Scale Update' && "
            "git pull origin master --rebase && "
            "git push origin master &" # Run in background so we don't block the scale
        )
        os.system(cmd)
        print("🌍 GitHub Sync Initiated")
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
        try:
            conn, addr = sock.accept()
            tap_ip = addr[0]
            conn.settimeout(3.0) # Don't wait longer than 3s for data

            raw_data = conn.recv(1024).decode('utf-8', errors='ignore').strip()
            if not raw_data: 
                conn.close()
                continue

            # DEBUG: See exactly what we got
            print(f"🔍 {tap_ip} sent: {raw_data}")

            # --- PARSER LOGIC ---

            # 1. Look for the "vw" pattern (e.g., vw5529.00)
            # This ignores the "Token" and "Version" garbage automatically
            weight_match = re.search(r"vw(-?\d+(\.\d+)?)", raw_data)

            if weight_match and tap_ip in TAP_CONFIG:
                # We found a real number!
                raw_weight = float(weight_match.group(1))
                tap_name = TAP_CONFIG[tap_ip]['name']
                percent = calculate_percent(raw_weight, tap_ip)
                
                # Update Timestamp
                current_weights[f"{tap_name}_updated"] = time.strftime("%H:%M:%S")

                # Update Value & Sync if changed
                if current_weights.get(tap_name) != percent:
                    current_weights[tap_name] = percent
                    print(f"🍺 {tap_name} Update: {raw_weight}g -> {percent}%")
                    sync_to_github()
                
                # Send 'Ack' because we got what we wanted
                conn.sendall(b'\x00\x00\x01\x00\xc8')

            elif len(raw_data) > 20:
                # This is likely a Token or Version info.
                # Just say "OK" so the scale stays happy.
                print("   -> Handshake/Token. Sending ACK.")
                conn.sendall(b'\x00\x00\x01\x00\xc8')

        except Exception as e:
            # Scale disconnected or timed out, just ignore and wait for next
            pass
        finally:
            try: conn.close()
            except: pass

if __name__ == "__main__":
    start_server()
