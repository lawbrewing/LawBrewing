import socket

PORT = 1234
print(f"📡 DEBUGGER ON. Waiting for ANY connection on port {PORT}...")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', PORT))
    s.listen(1)
    while True:
        conn, addr = s.accept()
        print(f"🔥 CONNECTION DETECTED from {addr}")
        with conn:
            # Send the handshake
            conn.sendall(b'\x00\x00\x01\x00\xc8')
            data = conn.recv(1024)
            print(f"📥 RAW DATA RECEIVED: {data}")
