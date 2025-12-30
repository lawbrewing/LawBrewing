import os
import json
import subprocess
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS  # <--- NEW: Permits ratings from external sites

app = Flask(__name__)
CORS(app)  # <--- NEW: Enable the handshake

DATA_FILE = '/home/lawmj04/law-brewing/taps.json'
LIB_FILE = '/home/lawmj04/law-brewing/library.json'

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

def git_sync():
    try:
        subprocess.run(["git", "add", "."], cwd="/home/lawmj04/law-brewing")
        subprocess.run(["git", "commit", "-m", "Admin: Updated Tap Assignments"], cwd="/home/lawmj04/law-brewing")
        subprocess.run(["git", "push", "origin", "main", "--force"], cwd="/home/lawmj04/law-brewing")
        return True
    except Exception as e:
        print(f"Git Push Failed: {e}")
        return False

@app.route('/admin')
def admin_panel():
    taps = load_json(DATA_FILE)
    library = load_json(LIB_FILE)
    return render_template('admin.html', taps=taps, library=library)

@app.route('/update_taps', methods=['POST'])
def update_taps():
    taps = load_json(DATA_FILE)
    library = load_json(LIB_FILE)
    
    # Update each tap based on selection
    for tap_id in ["Law Tap", "Wisco Tap", "Nitro Tap"]:
        selected_beer_id = request.form.get(tap_id)
        if selected_beer_id in library:
            beer = library[selected_beer_id]
            taps[tap_id].update({
                "beer_id": selected_beer_id,
                "beer_name": beer['name'],
                "desc": beer['desc'],
                "img": beer['art'],
                "abv": beer['abv'],
                "rating": beer.get('rating', 5.0)
            })
    
    save_json(DATA_FILE, taps)
    git_sync()
    return "Taps Updated and Synced to Web!"

@app.route('/rate', methods=['POST'])
def handle_rating():
    data = request.json
    tap_id = data.get('tap')
    score = float(data.get('rating'))
    
    taps = load_json(DATA_FILE)
    library = load_json(LIB_FILE)
    
    if tap_id in taps:
        beer_id = taps[tap_id]['beer_id']
        # Update in Library
        if beer_id in library:
            current_rating = float(library[beer_id].get('rating', 5.0))
            new_rating = round((current_rating + score) / 2, 1)
            library[beer_id]['rating'] = new_rating
            taps[tap_id]['rating'] = new_rating # Sync to tap too
            
            save_json(LIB_FILE, library)
            save_json(DATA_FILE, taps)
            git_sync() # Push rating to the live site
            return jsonify({"status": "success", "new_rating": new_rating})
    
    return jsonify({"status": "error"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
