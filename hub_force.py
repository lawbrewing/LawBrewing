# Save this as ~/law-brewing/hub_force.py
from flask import Flask, request
import pychromecast
import time

app = Flask(__name__)
URL = "https://lawbrewing.github.io/LawBrewing/"

def push_to_hub(target_name):
    chromecasts, browser = pychromecast.get_chromecasts()
    try:
        # Finds your Hub (Bar, Kitchen Display, or Hub)
        cast = next(cc for cc in chromecasts if target_name.lower() in cc.name.lower())
        cast.wait()
        # Launch DashCast (The 'Secret' browser for Hubs)
        cast.start_app("5E6C9054") 
        time.sleep(2)
        cast.socket_client.send_message("urn:x-cast:com.target-media.dashcast", 
            {"type": "LOAD", "url": URL, "force": True})
        return f"Pushed to {target_name}"
    except:
        return "Device not found", 404

@app.route('/trigger')
def trigger():
    room = request.args.get('room', 'Bar')
    return push_to_hub(room)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005)
