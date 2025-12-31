import os
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_JSON = os.path.join(BASE_DIR, 'library.json')
LIBRARY_FOLDER = os.path.join(BASE_DIR, 'static/images/library')

# Ensure folders exist
os.makedirs(LIBRARY_FOLDER, exist_ok=True)

# Global assignments: Tap Number -> Beer ID
tap_assignments = {'1': '5657071', '2': 'none', '3': 'none'}
tap_weights = {'1': 0, '2': 0, '3': 0}

def get_library():
    if not os.path.exists(LIBRARY_JSON):
        return {}
    with open(LIBRARY_JSON, 'r') as f:
        return json.load(f)

def get_beer_image(beer_id):
    """Finds the existing image file regardless of extension."""
    extensions = ['.jpeg', '.jpg', '.png', '.webp']
    for ext in extensions:
        if os.path.exists(os.path.join(LIBRARY_FOLDER, f"{beer_id}{ext}")):
            return f"{beer_id}{ext}"
    return "placeholder.png" # Make sure to put a default image in the folder!

# --- ROUTES ---

@app.route('/')
def index():
    library = get_library()
    taps_to_render = {}
    
    for tap_num, beer_id in tap_assignments.items():
        if beer_id in library:
            beer_info = library[beer_id].copy()
            beer_info['id'] = beer_id
            beer_info['image_file'] = get_beer_image(beer_id)
            beer_info['percent'] = tap_weights.get(tap_num, 0)
            taps_to_render[tap_num] = beer_info
        else:
            taps_to_render[tap_num] = {
                'name': 'Empty Tap', 
                'percent': 0, 
                'id': 'none', 
                'image_file': 'placeholder.png'
            }
            
    return render_template('index.html', taps=taps_to_render)

@app.route('/manage', methods=['GET', 'POST'])
def manage_taps():
    library = get_library()
    if request.method == 'POST':
        tap_assignments['1'] = request.form.get('tap_1')
        tap_assignments['2'] = request.form.get('tap_2')
        tap_assignments['3'] = request.form.get('tap_3')
        return redirect(url_for('index'))
    return render_template('manage.html', library=library, current_assignments=tap_assignments)

@app.route('/update_weight', methods=['POST'])
def update_weight():
    data = request.json
    name_map = {'Law Tap': '1', 'Wisco Tap': '2', 'Nitro Tap': '3'}
    tap_num = name_map.get(data.get('tap'))
    if tap_num:
        tap_weights[tap_num] = data.get('percent')
    return jsonify({"status": "success"})

@app.route('/library')
def library_page():
    library = get_library()
    # Prepare library with correct image paths
    for beer_id in library:
        library[beer_id]['image_file'] = get_beer_image(beer_id)
    return render_template('library.html', library=library)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
