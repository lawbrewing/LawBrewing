import pychromecast
from pychromecast.controllers.dashcast import DashCastController
import time
import sys

# --- CONFIGURATION ---
CAST_DEVICE_NAME = "Bar" 
SITE_URL = "https://lawbrewing.github.io/LawBrewing/"
# ---------------------

def cast_site():
    print(f"1. Searching for '{CAST_DEVICE_NAME}'...")
    chromecasts, browser = pychromecast.get_chromecasts()
    
    try:
        cast = next(cc for cc in chromecasts if CAST_DEVICE_NAME.lower() in cc.name.lower())
        cast.wait()
        print(f"2. Connected to {cast.name}")

        # FORCE QUIT any stuck apps first
        print("3. Killing current app...")
        cast.quit_app()
        time.sleep(5) # Critical wait to let the Hub go back to Home Screen

        # Initialize DashCast
        d = DashCastController()
        cast.register_handler(d)

        print("4. Launching DashCast...")
        cast.start_app("5E6C9054")
        
        # Longer wait for the "Dash" logo to appear and be ready
        print("5. Waiting 8 seconds for app to initialize...")
        time.sleep(8) 

        print(f"6. Sending URL: {SITE_URL}")
        d.load_url(SITE_URL, force=True)
        
        # Double-check pulse
        time.sleep(2)
        print("7. Sending reload signal to be sure...")
        d.load_url(SITE_URL, force=True)
        
        print("Success! Check the Hub.")

    except StopIteration:
        print(f"Error: Could not find '{CAST_DEVICE_NAME}'")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    cast_site()
