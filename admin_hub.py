from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import subprocess

app = Flask(__name__)
# CORS allows your GitHub website to securely talk to your Raspberry Pi
CORS(app)

# Paths to your data files
BASE_DIR = os.path.expanduser('~/law-brewing')
JSON_FILE = os.path.join(BASE_DIR, 'taps.json')
ARCHIVE_FILE = os.path.join(BASE_DIR, 'archive.json')

def run_deploy():
    """Automatically runs your deploy shortcut to push changes to GitHub"""
    try:
        # This calls the 'deploy' alias/command you use in your terminal
        subprocess.run(["/bin/bash", "-c", "deploy"], check=True)
        print("Successfully deployed to GitHub!")
    except Exception as e:
        print(f"Deploy failed: {e}")

def load_data(file_path, default_structure):
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump(default_structure, f, indent=4)
    with open(file_path, 'r') as f:
        return json.load(f)

@app.route('/update', methods=['POST'])
def update_tap():
    try:
        new_data = request.json
        tap_id = new_data.get('tap')
        
        all_taps = load_data(JSON_FILE, {})
        
        if tap_id in all_taps:
            # Update data from Admin Page
            all_taps[tap_id]['beer_name'] = new_data.get('beer_name', all_taps[tap_id].get('beer_name', ''))
            all_taps[tap_id]['abv'] = new_data.get('abv', all_taps[tap_id].get('abv', ''))
            all_taps[tap_id]['desc'] = new_data.get('desc', all_taps[tap_id].get('desc', ''))
            all_taps[tap_id]['percent'] = int(new_data.get('percent', 0))
            
            with open(JSON_FILE, 'w') as f:
                json.dump(all_taps, f, indent=4)
            
            # Automatically push to GitHub
            run_deploy()
            
            return jsonify({"status": "success", "message": f"{tap_id} updated and deployed!"})
        
        return jsonify({"status": "error", "message": "Tap not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/archive', methods=['POST'])
def archive_beer():
    try:
        data = request.json
        tap_id = data.get('tap')
        
        all_taps = load_data(JSON_FILE, {})
        archive = load_data(ARCHIVE_FILE, [])

        if tap_id in all_taps:
            beer_to_archive = all_taps[tap_id].copy()
            beer_to_archive['tap_location'] = tap_id # Remember where it was
            
            # Add to archive list
            archive.append(beer_to_archive)
            
            # Reset the tap to "Off Tap"
            all_taps[tap_id] = {
                "beer_name": "Off Tap",
                "abv": "0.0%",
                "desc": "Fresh brew coming soon...",
                "percent": 0,
                "rating": 5.0
            }

            with open(JSON_FILE, 'w') as f:
                json.dump(all_taps, f, indent=4)
            with open(ARCHIVE_FILE, 'w') as f:
                json.dump(archive, f, indent=4)

            run_deploy()
            return jsonify({"status": "success", "message": "Beer moved to Vault and deployed!"})
            
        return jsonify({"status": "error", "message": "Tap not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/rate', methods=['POST'])
def rate_beer():
    try:
        data = request.json
        tap_id = data.get('tap')
        new_rating = float(data.get('rating', 5))
        
        all_taps = load_data(JSON_FILE, {})
        
        if tap_id in all_taps:
            # Math to calculate a rolling average
            current_rating = float(all_taps[tap_id].get('rating', 5.0))
            updated_rating = round((current_rating + new_rating) / 2, 1)
            all_taps[tap_id]['rating'] = updated_rating
            
            with open(JSON_FILE, 'w') as f:
                json.dump(all_taps, f, indent=4)
            
            # We DON'T auto-deploy for every single rating to avoid GitHub spamming,
            # but the rating is saved locally on the Pi.
            return jsonify({"status": "success", "new_rating": updated_rating})
            
        return jsonify({"status": "error", "message": "Tap not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
