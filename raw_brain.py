import socket, json, os, re, time, struct

# --- CONFIG ---
WEIGHTS_FILE = "/home/lawmj04/law-brewing/tap_weights.json"
TAP_CONFIG = {
    '192.168.86.47':  {'name': 'Law Tap',   'empty': 0, 'full': 19000},
    '192.168.86.116': {'name': 'Wisco Tap', 'empty': 0, 'full': 19000},
    '192.168.86.45':  {'name': 'Nitro Tap', 'empty': 0, 'full': 19000}
}

# Initialize data structure
current_weights = {
    "Law Tap": 0, "Law Tap_temp": 0, "Law Tap_updated": "Waiting...",
    "Wisco Tap": 0, "Wisco Tap_temp": 0, "Wisco Tap_updated": "Waiting...",
    "Nitro Tap": 0, "Nitro Tap_temp": 0, "Nitro Tap_updated": "Waiting...",
    "last_updated": ""
}
last_sync = 0

def sync():
    global last_sync
    if time.time() - last_sync < 15: return
    try:
        current_weights["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(WEIGHTS_FILE, 'w') as f: json.dump(current_weights, f, indent=4)
        
        os.system("git config user.email 'bot@lawbrewing.com'; git config user.name 'BeerBot'")
        cmd = f"git stash && git pull origin master --rebase && git stash pop || echo 'No stash' && git add {WEIGHTS_FILE} && git commit -m 'Scale Update' && git push origin master"
        os.system(cmd)
        print("🌍 GitHub Sync Complete")
        last_sync = time.time()
    except: pass

def start():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 1234))
    sock.listen(10)
    print("🧠 Brain Online. Tracking Mass, Temp & Individual Timestamps.")

    while True:
        try:
            conn, addr = sock.accept()
            ip = addr[0]
            conn.settimeout(10.0) 
            
            while True:
                header = conn.recv(5)
                if not header: break
                cmd, msg_id, length = struct.unpack('!BHH', header)
                
                if length > 0:
                    payload = conn.recv(length)
                    data = payload.decode('utf-8', errors='ignore')
                    
                    if ip in TAP_CONFIG:
                        name = TAP_CONFIG[ip]['name']
                        conf = TAP_CONFIG[ip]
                        timestamp = time.strftime("%-I:%M %p") # e.g. "9:45 AM"
                        
                        # --- TRACK 1: BEER MASS (v51) ---
                        match_mass = re.search(r"vw.51.(\d+\.?\d*)", data)
                        if match_mass:
                            try:
                                val = float(match_mass.group(1))
                                if 0.1 <= val < 100: val *= 1000 
                                pct = max(0, min(100, round(((val - conf['empty']) / (conf['full'] - conf['empty'])) * 100)))
                                
                                if current_weights.get(name) != pct:
                                    current_weights[name] = pct
                                    current_weights[f"{name}_updated"] = timestamp
                                    print(f"✅ {name}: {pct}% (Updated {timestamp})")
                                    sync()
                            except: pass

                        # --- TRACK 2: TEMPERATURE (v69) ---
                        match_temp = re.search(r"vw.69.(\d+\.?\d*)", data)
                        if match_temp:
                            try:
                                val_c = float(match_temp.group(1))
                                val_f = round((val_c * 1.8) + 32, 1)
                                temp_key = f"{name}_temp"
                                
                                old_temp = current_weights.get(temp_key, 0)
                                if abs(val_f - old_temp) > 0.5:
                                    current_weights[temp_key] = val_f
                                    current_weights[f"{name}_updated"] = timestamp
                                    print(f"🌡️ {name} Temp: {val_f}F (Updated {timestamp})")
                                    sync()
                            except: pass
                
                response = struct.pack('!BHH', 0, msg_id, 200)
                conn.sendall(response)

        except: pass
        finally:
            try: conn.close()
            except: pass

if __name__ == "__main__":
    start()
