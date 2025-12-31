import socket
import requests
import json
import re

PORT = 1234
HUB_URL = "http://127.0.0.1:5000/update_weight"

# --- CALIBRATION SETTINGS ---
# Using the weights we established this morning
TAP_CONFIG = {
    '192.168.86.47': {
        'name': 'Law Tap',
        'empty': 480,    # Tare weight
        'full': 4150     # Full weight
    },
    '192.168.86.116': {
        'name': 'Wisco Tap',
        'empty': 520,
        'full': 4200
    },
    '192.168.86.45': {
        'name': 'Nitro Tap',
        'empty': 500,
        'full': 4100
    }
}

def calculate_percent(raw_val, empty, full):
    # Standard formula to map raw weight to 0-100%
    if raw_val <= empty: return 0
    if raw_val >= full: return 100
    return int(((raw_val - empty) / (full - empty)) * 100)

def start_hub():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', PORT))
        s.listen(10)
        print(f"🍺 CALIBRATED BRAIN ONLINE - PORT {PORT}")

        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024)
                if data:
                    try:
                        raw_msg = data.decode('utf-8').strip()
                        scale_ip = addr[0]
                        
                        if scale_ip in TAP_CONFIG:
                            conf = TAP_CONFIG[scale_ip]
                            # Extracts just the numbers from the scale data
                            numbers = re.findall(r'\d+', raw_msg)
                            
                            if numbers:
                                raw_weight = int(numbers[0])
                                pct = calculate_percent(raw_weight, conf['empty'], conf['full'])
                                
                                payload = {"tap": conf['name'], "percent": pct}
                                r = requests.post(HUB_URL, json=payload)
                                print(f"✅ {conf['name']}: {raw_weight}g -> {pct}% | Hub: {r.status_code}")
                        else:
                            print(f"⚠️ Unknown IP: {scale_ip} sent {raw_msg}")
                    except Exception as e:
                        print(f"❌ Error: {e}")

if __name__ == "__main__":
    start_hub()
