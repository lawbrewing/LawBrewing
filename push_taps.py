import pychromecast
import time
import sys

# Change this to the exact name of your Hub (e.g., "Bar Hub")
TARGET_HUB = "'Hub'" 
URL = "https://lawbrewing.github.io/LawBrewing/"

def push():
    # 1. Find the Hub
    chromecasts, browser = pychromecast.get_chromecasts()
    try:
        cast = next(cc for cc in chromecasts if TARGET_HUB.lower() in cc.name.lower())
        cast.wait()
        
        # 2. Launch DashCast (The universal browser for Nest Hubs)
        # ID: 5E6C9054 is the official DashCast receiver
        cast.start_app("5E6C9054") 
        time.sleep(3) # Let it load
        
        # 3. Send your URL
        cast.socket_client.send_message("urn:x-cast:com.target-media.dashcast", 
            {"type": "LOAD", "url": URL, "force": True})
        print(f"Taps pushed to {cast.name}!")
    except StopIteration:
        print(f"Could not find a Hub named {TARGET_HUB}")

if __name__ == "__main__":
    push()
