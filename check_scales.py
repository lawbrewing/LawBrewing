import socket, struct, re

def start_diagnostic():
    # Setup socket exactly like raw_brain.py
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind(('0.0.0.0', 1234))
        sock.listen(10)
        print("🛠️ Diagnostic Brain Online (Listening on Port 1234)")
        print("Waiting for scales to transmit...")
    except OSError as e:
        print(f"❌ Port 1234 is still blocked. Did you stop the service? Error: {e}")
        return

    while True:
        try:
            conn, addr = sock.accept()
            ip = addr[0]
            print(f"\n🔌 Connection established from: {ip}")
            
            while True:
                header = conn.recv(5)
                if not header:
                    print(f"❌ Connection dropped by {ip}")
                    break
                
                cmd, msg_id, length = struct.unpack('!BHH', header)
                
                if length > 0:
                    data = conn.recv(length).decode('utf-8', errors='ignore')
                else:
                    data = ""

                # Blynk heartbeat bypass
                if cmd == 2 or cmd == 6 or len(data) == 32 or length == 0:
                    conn.sendall(struct.pack('!BHH', 0, msg_id, 200))
                    continue
                
                # Clean and print the data stream
                safe_print = data.replace('\x00', '.')
                
                if "vw.51" in safe_print:
                    match = re.search(r"vw\.51\.(\d+\.?\d*)", safe_print)
                    val = match.group(1) if match else "Parse Error"
                    print(f"[{ip}] ⚖️ RAW WEIGHT SIGNAL: {val}")
                elif "vw.69" in safe_print:
                    match_t = re.search(r"vw\.69\.(-?\d+\.?\d*)", safe_print)
                    val_t = match_t.group(1) if match_t else "Parse Error"
                    print(f"[{ip}] 🌡️ RAW TEMP SIGNAL: {val_t}")
                else:
                    print(f"[{ip}] ❓ UNKNOWN SIGNAL: {safe_print}")

        except KeyboardInterrupt:
            print("\nExiting diagnostic mode.")
            break
        except Exception as e:
            print(f"⚠️ Error with connection: {e}")
            
if __name__ == "__main__":
    start_diagnostic()
