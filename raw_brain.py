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
    if raw_val > 20000 or raw_val < -500: return 0 
    pct = ((raw_val - conf['empty']) / (conf['full'] - conf['empty'])) * 100
    return max(0, min(100, round(pct)))

def sync_to_github():
    try:
        current_weights["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(current_weights, f, indent=4)
        
        # Git Sync
        os.system("git config user.email 'bot@lawbrewing.com'")
        os.system("git config user.name 'BeerBot'")
        
        cmd = (
            f"git add {WEIGHTS_FILE} && "
            "git commit -m 'Scale Update' && "
            "git pull origin master --rebase && "
            "git push origin master &"
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

    while True: # Main Server Loop (Accepts new calls)
        try:
            conn, addr = sock.accept()
            tap_ip = addr[0]
            conn.settimeout(10.0) # Give them 10 seconds to talk

            # --- INNER LOOP: Keep talking to THIS scale ---
            while True:
                raw_data = conn.recv(1024).decode('utf-8', errors='ignore')
                if not raw_data: break # Scale hung up
                
                clean_data = raw_data.strip()
                # Debug print to see the conversation
                print(f"🔍 {tap_ip} sent: {clean_data}")

                # 1. Check for "vw" (The Weight!)
                weight_match = re.search(r"vw(-?\d+(\.\d+)?)", clean_data)

                if weight_match and tap_ip in TAP_CONFIG:
                    # found the gold!
                    raw_weight = float(weight_match.group(1))
                    tap_name = TAP_CONFIG[tap_ip]['name']
                    percent = calculate_percent(raw_weight, tap_ip)
                    
                    current_weights[f"{tap_name}_updated"] = time.strftime("%H:%M:%S")

                    if current_weights.get(tap_name) != percent:
                        current_weights[tap_name] = percent
                        print(f"🍺 {tap_name} Update: {raw_weight}g -> {percent}%")
                        sync_to_github()
                    
                    # Send ACK and Keep Listening (Scale might send more)
                    conn.sendall(b'\x00\x00\x01\x00\xc8')

                elif len(clean_data) > 5:
                    # Likely a Token or Version info
                    # Just say "OK" and WAIT for the next message
                    print("   -> Handshake/Info. Sending ACK & Listening...")
                    conn.sendall(b'\x00\x00\x01\x00\xc8')

        except Exception as e:
            # print(f"⚠️ Session Ended: {e}")
            pass
        finally:
            try: conn.close()
            except: pass

if __name__ == "__main__":
    start_server()
