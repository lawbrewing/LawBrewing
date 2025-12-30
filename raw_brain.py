import socket
import requests
import json
import time

# Configuration
PORT = 1234
# Points to our Admin Hub
HUB_URL = "http://localhost:5000/update_weight"

# Map your Scale IPs to the Tap Names defined in your JSON
SCALES = {
    '192.168.86.47': 'Law Tap',
    '192.168.86.48': 'Wisco Tap',
    '192.168.86.49': 'Nitro Tap'
}

def start_hub():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Prevents the "Address already in use" error
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', PORT))
        s.listen(10)
        print(f"🍺 RAW BRAIN ONLINE - LISTENING FOR SCALES ON PORT {PORT}")

        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024)
                if data:
                    try:
                        # Expecting format: "Weight: 85"
                        raw_msg = data.decode('utf-8').strip()
                        weight_val = int(raw_msg.split(':')[1].strip())
                        
                        scale_ip = addr[0]
                        tap_name = SCALES.get(scale_ip, "Unknown Tap")

                        if tap_name != "Unknown Tap":
                            payload = {
                                "tap": tap_name,
                                "percent": weight_val
                            }
                            # Send to Admin Hub
                            response = requests.post(HUB_URL, json=payload)
                            print(f"✅ {tap_name} ({scale_ip}): {weight_val}% -> Hub Status: {response.status_code}")
                        else:
                            print(f"⚠️ Received data from unknown IP: {scale_ip}")

                    except Exception as e:
                        print(f"❌ Data Error: {e}")

if __name__ == "__main__":
    start_hub()
