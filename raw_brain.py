import socket, json, os, re, subprocess

# --- CONFIGURATION ---
PORT = 1234
DATA_FILE = "/home/lawmj04/law-brewing/taps.json"

# [Divisor, Empty Keg Weight, Full Weight]
CONFIG = {
    "Law Tap": [165.0, 9.9, 48.1], 
    "Wisco Tap": [513000.0, 9.9, 48.1],
    "Nitro Tap": [20816.0, 9.9, 48.1]
}

IP_MAP = {
    "192.168.86.47": "Law Tap", 
    "192.168.86.116": "Wisco Tap",
    "192.168.86.45": "Nitro Tap"
}

def calculate_volumes(lbs, empty_weight):
    """Calculates liquid units based on net weight."""
    net_lbs = max(0, lbs - empty_weight)
    # 1 Pint of beer is approx 1.04 lbs
    pints = int(net_lbs / 1.04)
    # 1 Growler (64oz) is approx 4.17 lbs
    growlers = int(net_lbs / 4.17)
    return pints, growlers

def sync_to_github():
    try:
        os.chdir("/home/lawmj04/law-brewing")
        subprocess.run(["git", "add", "taps.json"], check=True)
        status = subprocess.run(["git", "diff", "--cached", "--exit-code"], capture_output=True)
        if status.returncode != 0:
            subprocess.run(["git", "commit", "-m", "Auto-update volumes"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("🚀 GitHub Updated with latest volumes")
    except Exception as e:
        print(f"❌ Git Sync Failed: {e}")

def start_hub():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', PORT))
        s.listen(10)
        print(f"🍺 LAW BREWING HUB ONLINE - PINTS & GROWLERS ACTIVE")
        
        while True:
            conn, addr = s.accept()
            with conn:
                try:
                    data = conn.recv(1024)
                    if not data: continue
                    
                    # Send Heartbeat back to scale
                    conn.sendall(b'\x00' + data[1:3] + b'\x00\xc8')
                    
                    found_numbers = re.findall(r'\d+\.\d+|\d+', data.decode('latin-1', 'ignore'))
                    if found_numbers:
                        val = float(max(found_numbers, key=len))
                        name = IP_MAP.get(addr[0], "Unknown")
                        
                        if name in CONFIG:
                            divisor, empty, full = CONFIG[name]
                            
                            # Calculate Weight
                            lbs = round(val / divisor, 2)
                            
                            # Calculate Percent & Units
                            percent = max(0, min(100, int(((lbs - empty) / (full - empty)) * 100)))
                            pints, growlers = calculate_volumes(lbs, empty)
                            
                            # Load current data to preserve existing ratings/names
                            if os.path.exists(DATA_FILE):
                                with open(DATA_FILE, 'r') as f:
                                    current_data = json.load(f)
                            else:
                                current_data = {}

                            # Update entry (preserving description/rating if we add it later)
                            existing = current_data.get(name, {})
                            current_data[name] = {
                                "weight_lbs": lbs,
                                "percent": percent,
                                "pints": pints,
                                "growlers": growlers,
                                "beer_name": existing.get("beer_name", name),
                                "rating": existing.get("rating", 5.0),
                                "temp_f": 38.0
                            }

                            with open(DATA_FILE, 'w') as f:
                                json.dump(current_data, f, indent=4)
                            
                            print(f"✅ {name}: {lbs} lbs | {pints} Pints | {growlers} Growlers")
                            sync_to_github()
                except Exception as e:
                    print(f"⚠️ Error: {e}")
                    continue

if __name__ == "__main__":
    start_hub()
