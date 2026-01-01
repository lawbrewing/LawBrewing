import socket
import json
import os
import time

# --- CONFIGURATION ---
# Ensure these paths match your Raspberry Pi setup
WEIGHTS_FILE = '/home/lawmj04/law-brewing/tap_weights.json'
PORT = 1234
# Calibration: (Raw Value - Offset) / Scale
# Adjust these numbers based on your specific scale calibration
calibration_factor = 1000 

current_weights = {
    "law_tap": 0,
    "guest_tap": 0,
    "last_updated": ""
}

def sync_to_github():
    """Forces a pull from GitHub before pushing to prevent sync errors"""
    try:
        # 1. Save the local JSON file
        current_weights["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(current_weights, f, indent=4)

        print(f"💾 Local weights saved. Syncing to GitHub...")

        # 2. The Self-Healing Git Command
        # We use 'master' because the logs showed the site tracks origin/master
        cmd = (
            "git add . && "
            "git commit -m 'Scale Update' && "
            "git pull origin master --rebase && "
            "git push origin master"
        )
        
        result = os.system(cmd)
        
        if result == 0:
            print("🌍 GitHub Sync Successful")
        else:
            print("⚠️ GitHub Sync encountered a warning (Check logs)")
            
    except Exception as e:
        print(f"❌ Error during sync: {e}")

def start_server():
    """Starts the socket server to listen for scale data"""
    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Allow immediate reuse of the port after a crash
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind(('0.0.0.0', PORT))
        sock.listen(5)
        print(f"🧠 Brain is online. Listening on Port {PORT}...")
    except OSError as e:
        print(f"❌ Could not bind to port {PORT}: {e}")
        return

    while True:
        client, address = sock.accept()
        try:
            data = client.recv(1024).decode('utf-8')
            if data:
                # Assuming data comes in as "ScaleID:Value"
                # Example: "LAW:23.4"
                print(f"📡 Raw Data Received: {data}")
                
                parts = data.split(':')
                if len(parts) == 2:
                    tap_id = parts[0].strip().lower()
                    weight_val = float(parts[1].strip())
                    
                    if tap_id == "law":
                        current_weights["law_tap"] = weight_val
                    elif tap_id == "guest":
                        current_weights["guest_tap"] = weight_val
                    
                    # Sync to website immediately upon receiving data
                    sync_to_github()
                    
        except Exception as e:
            print(f"⚠️ Error handling data: {e}")
        finally:
            client.close()

if __name__ == "__main__":
    start_server()
