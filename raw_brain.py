import socket
import json
import os

# --- CONFIG ---
PORT = 1234
DATA_FILE = "/home/lawmj04/law-brewing/taps.json"

SMOOTHING_FACTOR = 0.05  
KEG_FULL_LBS = 58.0   # Standard full 1/6 bbl is ~58-60 lbs
KEG_EMPTY_LBS = 9.0    # Empty steel corny keg is ~9-10 lbs

IP_MAP = {
    "192.168.86.45": "Nitro Tap",
    "192.168.86.47": "Law Tap",
    "192.168.86.116": "Wisco Tap"
}

tap_data = {k: {"weight_lbs": 0.0, "percent": 0, "temp_f": 38.0} for k in IP_MAP.values()}

def save_to_json():
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(tap_data, f, indent=4)
    except Exception: pass

def start_hub():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', PORT))
        s.listen(5)
        print("🍺 HUB STARTING (LBS/FAHRENHEIT MODE)")

        while True:
            conn, addr = s.accept()
            ip = addr[0]
            name = IP_MAP.get(ip)
            
            if name:
                with conn:
                    conn.sendall(b'\x00\x00\x01\x00\xc8')
                    try:
                        while True:
                            data = conn.recv(1024)
                            if not data: break
                            
                            # WEIGHT LOGIC (vw)
                            if b'vw' in data:
                                chunk = data.split(b'vw')[1][:10]
                                raw_str = "".join([chr(b) for b in chunk if chr(b) in "0123456789."])
                                if raw_str and "." in raw_str:
                                    val_kg = float(raw_str)
                                    if 0 < val_kg < 100:
                                        val_lbs = round(val_kg * 2.20462, 2)
                                        
                                        # Smoothing lbs
                                        prev = tap_data[name]["weight_lbs"]
                                        if prev == 0 or abs(val_lbs - prev) > 5:
                                            tap_data[name]["weight_lbs"] = val_lbs
                                        else:
                                            tap_data[name]["weight_lbs"] = round((val_lbs * 0.05) + (prev * 0.95), 2)
                                        
                                        # Percent Calculation
                                        rem = max(0, tap_data[name]["weight_lbs"] - KEG_EMPTY_LBS)
                                        tap_data[name]["percent"] = min(100, round((rem / (KEG_FULL_LBS - KEG_EMPTY_LBS)) * 100))
                                        save_to_json()
                                        print(f"📊 {name}: {tap_data[name]['weight_lbs']} lbs")

                            # TEMP LOGIC (vt) - Only if scale sends it
                            if b'vt' in data:
                                t_chunk = data.split(b'vt')[1][:10]
                                t_str = "".join([chr(b) for b in t_chunk if chr(b) in "0123456789."])
                                if t_str:
                                    temp_c = float(t_str)
                                    tap_data[name]["temp_f"] = round((temp_c * 9/5) + 32, 1)

                    except Exception: continue

if __name__ == "__main__":
    start_hub()
