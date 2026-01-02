import pychromecast
import time

print("Scanning for Google Hubs on your network...")
print("(This may take 5-10 seconds)")

# Discover all devices
chromecasts, browser = pychromecast.get_chromecasts()

print("\n--- FOUND DEVICES ---")
if not chromecasts:
    print("No devices found. Ensure Pi and Hubs are on the same Wi-Fi.")
else:
    for cc in chromecasts:
        print(f"Name: '{cc.name}'  |  Model: {cc.model_name}")
print("---------------------\n")
