import pychromecast
import time

# YOUR CONFIG
HUB_NAME = "Bar" # Or "Kitchen Display"
TAPROOM_URL = "https://lawbrewing.github.io/LawBrewing/"

def push_to_hub():
    print("Signal received! Pushing taproom to Hub...")
    chromecasts, browser = pychromecast.get_chromecasts()
    try:
        cast = next(cc for cc in chromecasts if HUB_NAME.lower() in cc.name.lower())
        cast.wait()
        # Launch DashCast (The browser for Hubs)
        cast.start_app("5E6C9054") 
        time.sleep(3)
        cast.socket_client.send_message("urn:x-cast:com.target-media.dashcast", 
            {"type": "LOAD", "url": TAPROOM_URL, "force": True})
        print("Success!")
    except:
        print("Could not find the Hub on the network.")

# This is a 'manual' trigger for now to test the connection
if __name__ == "__main__":
    push_to_hub()
