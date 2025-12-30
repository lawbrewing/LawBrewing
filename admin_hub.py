from flask import Flask, request, jsonify
from flask_cors import CORS
import json, os, subprocess, time

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
        subprocess.run(["git", "commit", "-m", "Data Update"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
    except Exception as e:
        print(f"Git Error: {e}")

@app.route('/save_to_library', methods=['POST'])
def save_to_library():
    data = request.json
    name = data.get('beer_name')
    all_data = load_data()
    all_data['library'][name] = {
        "abv": data.get('abv'),
        "desc": data.get('desc'),
        "artwork": data.get('artwork'),
        "percent": int(data.get('percent', 100))
    }
    save_data(all_data)
    run_deploy()
    return jsonify({"status": "success"})

@app.route('/assign_tap', methods=['POST'])
def assign_tap():
    data = request.json
    all_data = load_data()
    all_data['active_taps'][data.get('tap')] = data.get('beer_name')
    save_data(all_data)
    run_deploy()
    return jsonify({"status": "success"})

@app.route('/update_weight', methods=['POST'])
def update_weight():
    # This endpoint is called by raw_brain.py
    data = request.json
    tap_id = data.get('tap')
    all_data = load_data()
    
    # Update weight for the beer currently assigned to this tap
    active_beer_name = all_data['active_taps'].get(tap_id)
    if active_beer_name in all_data['library']:
        all_data['library'][active_beer_name]['percent'] = data.get('percent')
        save_data(all_data)
    return jsonify({"status": "success"})

@app.route('/get_data', methods=['GET'])
def get_data():
    return jsonify(load_data())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
