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
        subprocess.run(["git", "commit", "-m", "Manual Update"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
    except Exception as e: print(f"Git Error: {e}")

@app.route('/')
def admin_page():
    # This serves the admin interface directly from the Pi
    with open(os.path.join(BASE_DIR, 'admin.html'), 'r') as f:
        return render_template_string(f.read())

@app.route('/get_data')
def get_data():
    return jsonify(load_data())

@app.route('/save_to_library', methods=['POST'])
def save_to_library():
    data = request.json
    all_data = load_data()
    all_data['library'][data['beer_name']] = {
        "abv": data['abv'], "desc": data['desc'],
        "artwork": data['artwork'], "percent": int(data.get('percent', 100))
    }
    save_data(all_data)
    run_deploy()
    return jsonify({"status": "success"})

@app.route('/assign_tap', methods=['POST'])
def assign_tap():
    data = request.json
    all_data = load_data()
    all_data['active_taps'][data['tap']] = data['beer_name']
    save_data(all_data)
    run_deploy()
    return jsonify({"status": "success"})

@app.route('/update_weight', methods=['POST'])
def update_weight():
    data = request.json
    all_data = load_data()
    beer_name = all_data['active_taps'].get(data['tap'])
    if beer_name and beer_name in all_data['library']:
        all_data['library'][beer_name]['percent'] = data['percent']
        save_data(all_data)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
