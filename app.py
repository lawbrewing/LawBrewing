import os, json, requests
from flask import Flask, request

app = Flask(__name__)

# --- CONFIG ---
USER_ID = os.getenv("BREWFATHER_USER_ID")
API_KEY = os.getenv("BREWFATHER_API_KEY")

@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def catch_all(path):
    # This responds to EVERYTHING: /, /api/v1/keg, /plaato, etc.
    if request.method == 'GET':
        return "Brewery Brain is Active!", 200
    
    # This is where the scale data hits
    try:
        data = request.json
        print(f"--- DATA RECEIVED AT /{path} ---")
        print(json.dumps(data, indent=2))
        
        # This is where we will add the Brewfather/Github logic next
        return "OK", 200
    except Exception as e:
        print(f"Error: {e}")
        return "Error", 400

if __name__ == '__main__':
    # We use 1234 because we know it's open on your router
    app.run(host='0.0.0.0', port=1234)
