from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json, os, subprocess

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.expanduser('~/law-brewing')
JSON_FILE = os.path.join(BASE_DIR, 'taps.json')

def load_data():
    with open(JSON_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(JSON_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def run_deploy():
    try:
        os.chdir(BASE_DIR)
        subprocess.run(["git", "add", "taps.json"], check=True)
        subprocess.run(["git", "commit", "-m", "Tap and Weight Sync"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("🚀 Git Push Success!")
    except Exception as e:
        print(f"❌ Git Error: {e}")

@app.route('/')
def admin_page():
    with open(os.path.join(BASE_DIR, 'admin.html'), 'r') as f:
        return render_template_string(f.read())

@app.route('/get_data')
def get_data():
    return jsonify(load_data())

@app.route('/update_weight', methods=['POST'])
def update_weight():
    data = request.json
    all_data = load_data()
    tap_id = data.get('tap')  # e.g., "Law Tap"
    new_pct = data.get('percent', 0)
    
    # 1. Update the weight in the Active Taps section (for index.html display)
    if 'taps' in all_data and tap_id in all_data['taps']:
        all_data['taps'][tap_id]['percent'] = new_pct
    
    # 2. Update the weight in the Library for the beer currently on that tap
    beer_name = all_data['active_taps'].get(tap_id)
    if beer_name and beer_name in all_data['library']:
        all_data['library'][beer_name]['percent'] = new_pct
        
    save_data(all_data)
    run_deploy()
    return jsonify({"status": "success", "tap": tap_id, "percent": new_pct})

@app.route('/assign_beer', methods=['POST'])
def assign_beer():
    data = request.json
    all_data = load_data()
    tap_id = data.get('tap')
    beer_name = data.get('beer_name')

    if beer_name in all_data['library']:
        beer_info = all_data['library'][beer_name]
        
        # Ensure artwork path is relative for GitHub
        filename = beer_info['artwork'].split('/')[-1]
        artwork_path = f"images/labels/{filename}"
        
        # Update the active tap info
        all_data['active_taps'][tap_id] = beer_name
        all_data['taps'][tap_id] = {
            "name": beer_name,
            "brewery": beer_info.get('brewery', 'Law Brewing'),
            "style": beer_info.get('style', 'Beer'),
            "abv": beer_info.get('abv', '0%'),
            "percent": beer_info.get('percent', 100),
            "artwork": artwork_path
        }
        
        save_data(all_data)
        run_deploy()
        return jsonify({"status": "success"})
    
    return jsonify({"status": "error", "message": "Beer not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
