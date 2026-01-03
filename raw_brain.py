import socket, json, os, re, time, struct

# --- CONFIG ---
WEIGHTS_FILE = "/home/lawmj04/law-brewing/tap_weights.json"
TAP_CONFIG = {
    '192.168.86.47':  {'name': 'Law Tap',   'empty': 0, 'full': 19000},
    '192.168.86.116': {'name': 'Wisco Tap', 'empty': 0, 'full': 19000},
    '192.168.86.45':  {'name': 'Nitro Tap', 'empty': 0, 'full': 19000}
}

try:
    with open(WEIGHTS_FILE, 'r') as f:
        current_weights = json.load(f)
except:
    current_weights = {
        "Law Tap": 0, "Law Tap_temp": 0, "Law Tap_updated": "Waiting...", "Law Tap_last_pour": "",
        "Wisco Tap": 0, "Wisco Tap_temp": 0, "Wisco Tap_updated": "Waiting...", "Wisco Tap_last_pour": "",
        "Nitro Tap": 0, "Nitro Tap_temp": 0, "Nitro Tap_updated": "Waiting...", "Nitro Tap_last_pour": "",
        "last_updated": ""
    }

last_sync = 0
last_stable_weights = {} 

def get_pour_name(oz):
    if oz < 2.5: return None # Ignore foam/drips
    if oz < 6.5: return "Taster"
    if oz < 11.0: return "Short Pour"
    if oz < 24.0: return "Pint"
    if oz < 45.0: return "Crowler"
    return "Growler"

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
    print("🧠 Brain Online. Layman's Terms Active (Pints/Tasters).")

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
                        timestamp = time.strftime("%-I:%M %p")

                        # --- TRACK 1: BEER MASS (v51) ---
                        match_mass = re.search(r"vw.51.(\d+\.?\d*)", data)
                        if match_mass:
                            try:
                                val = float(match_mass.group(1))
                                if 0.1 <= val < 100: val *= 1000 
                                
                                # --- POUR LOGIC ---
                                if name in last_stable_weights:
                                    prev_weight = last_stable_weights[name]
                                    diff = prev_weight - val
                                    
                                    # Threshold > 60g (2oz)
                                    if diff > 60:
                                        ounces = diff / 29.57
                                        pour_name = get_pour_name(ounces)
                                        
                                        if pour_name:
                                            # We save: "PINT (16.2oz)" for clarity
                                            display_str = f"{pour_name} ({ounces:.1f}oz)"
                                            print(f"🍺 {name}: {display_str}")
                                            
                                            current_weights[f"{name}_last_pour"] = display_str
                                            last_stable_weights[name] = val 
                                            sync()
                                    
                                    elif diff < -100: # Keg Change / Cleaning
                                        last_stable_weights[name] = val
                                else:
                                    last_stable_weights[name] = val

                                # --- PERCENTAGE LOGIC ---
                                pct = max(0, min(100, round(((val - conf['empty']) / (conf['full'] - conf['empty'])) * 100)))
                                
                                if current_weights.get(name) != pct:
                                    current_weights[name] = pct
                                    current_weights[f"{name}_updated"] = timestamp
                                    last_stable_weights[name] = val 
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
