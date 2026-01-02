from flask import Flask, request
import pychromecast
import time

app = Flask(__name__)
# Your Taproom URL
URL = "https://lawbrewing.github.io/LawBrewing/"

def cast_to_hub(device_name):
    # This searches your WiFi for Google Hubs
    chromecasts, browser = pychromecast.get_chromecasts()
    try:
        # Matches the name "Bar", "Kitchen Display", or "Hub"
        cast = next(cc for cc in chromecasts if device_name.lower() in cc.name.lower())
        cast.wait()
        
        # DashCast is the only reliable way to show websites on Hubs in 2026
        # Receiver ID: 5E6C9054
        cast.start_app("5E6C9054") 
        time.sleep(4) # Give it a second to wake up
        
        # Force the URL onto the screen
        cast.socket_client.send_message("urn:x-cast:com.target-media.dashcast", 
            {"type": "LOAD", "url": URL, "force": True})
        return f"SUCCESS: Pushed to {cast.name}"
    except Exception as e:
        return f"ERROR: {str(e)}", 404

@app.route('/trigger')
def trigger():
    room = request.args.get('room', 'Bar')
    return cast_to_hub(room)

if __name__ == '__main__':
    # Use Port 5005 so it doesn't fight with your Beer Scales
    app.run(host='0.0.0.0', port=5005)
