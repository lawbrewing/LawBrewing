import socket, struct, re

def start():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 1234))
    sock.listen(10)
    print("🕵️  Explorer Online. Waiting for secret data...")

    while True:
        try:
            conn, addr = sock.accept()
            print(f"🔌 Connected to {addr[0]}")
            
            while True:
                header = conn.recv(5)
                if not header: break
                cmd, msg_id, length = struct.unpack('!BHH', header)
                
                if length > 0:
                    payload = conn.recv(length)
                    data = payload.decode('utf-8', errors='ignore')
                    
                    # Find ANY virtual pin (vw) command
                    # Matches: vw [pin] [value]
                    matches = re.findall(r"vw.(\d+).(\S+)", data)
                    for pin, val in matches:
                        # Translate known pins
                        meaning = "Unknown"
                        if pin == "51": meaning = "🍺 Mass"
                        if pin == "48": meaning = "📊 Percent"
                        if pin == "74": meaning = "🌡️ Temp (Maybe?)"
                        if pin == "75": meaning = "🌡️ Temp (Maybe?)"
                        
                        print(f"[{addr[0]}] Pin v{pin}: {val}  ({meaning})")

                # Keep connection alive
                response = struct.pack('!BHH', 0, msg_id, 200)
                conn.sendall(response)
        except: pass
        finally:
            try: conn.close()
            except: pass

if __name__ == "__main__":
    start()
