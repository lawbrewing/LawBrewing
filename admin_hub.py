from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os

app = Flask(__name__)
# CORS allows your GitHub website to talk to your Raspberry Pi
CORS(app)

# Path to your data file
JSON_FILE = os.path.expanduser('~/law-brewing/taps.json')

def load_data():
    if not os.path.exists(JSON_FILE):
        # Create a blank slate if the file is missing
        initial_data = {
            "Law Tap": {"beer_name": "Off Tap", "abv": "0%", "desc": "Brewing...", "percent": 0, "rating": 5.0, "pints": 0, "growlers": 0},
            "Wisco Tap": {"beer_name": "Off Tap", "abv": "0%", "desc": "Brewing...", "percent": 0, "rating": 5.0, "pints": 0, "growlers": 0},
            "Nitro Tap": {"beer_name": "Off Tap", "abv": "0%", "desc": "Brewing...", "percent": 0, "rating": 5.0, "pints": 0, "growlers": 0}
        }
        with open(JSON_FILE, 'w') as f:
            json.dump(initial_data, f, indent=4)
    
    with open(JSON_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(JSON_FILE, 'w') as f:
        json.dump(data, f, indent=4)

@app.route('/update', methods=['POST'])
def update_tap():
    try:
        new_data = request.json
        tap_id = new_data.get('tap')
        
        all_taps = load_data()
        
        if tap_id in all_taps:
            # Update the fields provided by the admin page
            all_taps[tap_id]['beer_name'] = new_data.get('beer_name', all_taps[tap_id]['beer_name'])
            all_taps[tap_id]['abv'] = new_data.get('abv', all_taps[tap_id]['abv'])
            all_taps[tap_id]['desc'] = new_data.get('desc', all_taps[tap_id]['desc'])
            all_taps[tap_id]['percent'] = int(new_data.get('percent', all_taps[tap_id]['percent']))
            
            save_data(all_taps)
            return jsonify({"status": "success", "message": f"{tap_id} updated."})
        
        return jsonify({"status": "error", "message": "Tap not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/rate', methods=['POST'])
def rate_beer():
    try:
        data = request.json
        tap_id = data.get('tap')
        new_rating = float(data.get('rating', 5))
        
        all_taps = load_data()
        
        if tap_id in all_taps:
            current_rating = float(all_taps[tap_id].get('rating', 5.0))
            # Simple moving average for ratings
            updated_rating = round((current_rating + new_rating) / 2, 1)
            all_taps[tap_id]['rating'] = updated_rating
            
            save_data(all_taps)
            return jsonify({"status": "success", "new_rating": updated_rating})
            
        return jsonify({"status": "error", "message": "Tap not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Run on port 5000, accessible to the Cloudflare Tunnel
    app.run(host='0.0.0.0', port=5000, debug=True)
