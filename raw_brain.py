import socket
import json
import requests
import re

# --- CONFIGURATION ---
HUB_URL = "http://localhost:5000/update_weight"

# Add your Nitro info back here!
TAP_CONFIG = {
    '192.168.86.47':  {'name': 'Law Tap',   'empty': 480, 'full': 4150},
    '192.168.86.116': {'name': 'Wisco Tap', 'empty': 500, 'full': 4000},
    '192.168.86.45':  {'name': 'Nitro Tap', 'empty': 450, 'full': 4200}
}

def calculate_percent(raw_val, tap_ip):
    conf = TAP_CONFIG.get(tap_ip, {'empty': 500, 'full': 4000})
    # Filter out garbage scientific notation or the 8.7M error
    if raw_val > 1000000 or raw_val < -500: 
        return 0 
    
    pct = ((raw_val - conf['empty']) / (conf['full'] - conf['empty'])) * 100
    return max(0, min(100, round(pct)))

def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 1234))
    sock.listen(5)
    print("🚀 3-Tap Brain (Nitro Restored) + Handshake Live...")

    while True:
        conn, addr = sock.accept()
        try:
            # The scale waits for this 5-byte hex "Success" code
            # Without this, the scale resets to Setup Mode after 30 seconds
            conn.sendall(b'\x00\x00\x01\x00\xc8') 

            data = conn.recv(1024).decode('utf-8', errors='ignore')
            if not data: continue
            
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", data)
            if numbers:
                raw_weight = float(numbers[0])
                tap_ip = addr[0]
                tap_name = TAP_CONFIG.get(tap_ip, {}).get('name', 'Unknown')
                percent = calculate_percent(raw_weight, tap_ip)
                
                print(f"📡 {tap_name} ({tap_ip}): {raw_weight}g -> {percent}%")
                requests.post(HUB_URL, json={'tap': tap_name, 'percent': percent})
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    start_server()
