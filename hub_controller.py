from flask import Flask, request
import pychromecast
import time

app = Flask(__name__)
URL = "https://lawbrewing.github.io/LawBrewing/"

def cast_to_device(target_room):
    # Discovery
    chromecasts, browser = pychromecast.get_chromecasts()
    try:
        # Match "Bar", "Kitchen", or "Hub"
        cast = next(cc for cc in chromecasts if target_room.lower() in cc.name.lower())
        cast.wait()
        cast.start_app("5E6C9054") # DashCast Receiver ID
        time.sleep(3)
        cast.socket_client.send_message("urn:x-cast:com.target-media.dashcast", 
            {"type": "LOAD", "url": URL, "force": True})
        return f"Casted to {target_room}"
    except Exception as e:
        return f"Error: {str(e)}", 404

@app.route('/show-taps')
def handle():
    room = request.args.get('room', 'Bar')
    return cast_to_device(room)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005)
