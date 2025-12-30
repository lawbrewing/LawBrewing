import socket, json, os, re, subprocess

# --- CONFIGURATION ---
PORT = 1234
DATA_FILE = "/home/lawmj04/law-brewing/taps.json"

# [Divisor, Empty Keg Weight]
CONFIG = {
    "Nitro Tap": [20816.0, 9.9], 
    "Law Tap": [165.0, 9.9], 
    "Wisco Tap": [513000.0, 9.9]
}

IP_MAP = {
    "192.168.86.45": "Nitro Tap", 
    "192.168.86.47": "Law Tap", 
    "192.168.86.116": "Wisco Tap"
}

def sync_to_github():
    try:
        os.chdir("/home/lawmj04/law-brewing")
        # Stage the json file
        subprocess.run(["git", "add", "taps.json"], check=True)
        
        # Check if there are actual changes before committing
        status = subprocess.run(["git", "diff", "--cached", "--exit-code"], capture_output=True)
        if status.returncode != 0:
            subprocess.run(["git", "commit", "-m", "Auto-update weights"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("🚀 GitHub Updated")
    except Exception as e:
        print(f"❌ Git Sync Failed: {e}")

def start_hub():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', PORT))
        s.listen(10)
        print(f"🍺 LAW BREWING HUB ONLINE ON PORT {PORT}")
        
        while True:
            conn, addr = s.accept()
            with conn:
                try:
                    data = conn.recv(1024)
                    if not data: continue
                    
                    # Send Blynk Heartbeat
                    conn.sendall(b'\x00' + data[1:3] + b'\x00\xc8')
                    
                    # Extract the raw scale value
                    found_numbers = re.findall(r'\d+\.\d+|\d+', data.decode('latin-1', 'ignore'))
                    if found_numbers:
                        val = float(max(found_numbers, key=len))
                        name = IP_MAP.get(addr[0], "Unknown")
                        
                        if name != "Unknown":
                            divisor, empty_weight = CONFIG[name]
                            
                            # Calculate Weight and Percent
                            lbs = round(val / divisor, 2)
                            # Full keg ~48.1lbs, Empty ~9.9lbs
                            percent = max(0, min(100, int(((lbs - empty_weight) / (48.1 - empty_weight)) * 100)))
                            
                            # Load current data
                            if os.path.exists(DATA_FILE):
                                with open(DATA_FILE, 'r') as f:
                                    current_data = json.load(f)
                            else:
                                current_data = {}

                            # Update entry
                            current_data[name] = {
                                "weight_lbs": lbs,
                                "percent": percent,
                                "temp_f": 38.0
                            }

                            # Save to file
                            with open(DATA_FILE, 'w') as f:
                                json.dump(current_data, f, indent=4)
                            
                            print(f"✅ {name}: {lbs} lbs ({percent}%)")
                            sync_to_github()
                except Exception as e:
                    print(f"⚠️ Error processing packet: {e}")
                    continue

if __name__ == "__main__":
    start_hub()
