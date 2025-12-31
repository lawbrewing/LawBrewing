import os
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# Paths
LIBRARY_JSON = os.path.expanduser('~/law-brewing/library.json')
LIBRARY_FOLDER = os.path.expanduser('~/law-brewing/static/images/library')

# This tracks which beer ID is on which tap (1, 2, or 3)
# You can change these IDs here to swap beers on the home page
tap_assignments = {
    '1': '5657071', 
    '2': 'none',
    '3': 'none'
}

# Live weights sent from your scale script
tap_weights = {'1': 0, '2': 0, '3': 0}

def get_library():
    with open(LIBRARY_JSON, 'r') as f:
        return json.load(f)

@app.route('/')
def index():
    library = get_library()
    taps_to_render = {}
    
    for tap_num, beer_id in tap_assignments.items():
        if beer_id in library:
            # Combine the library stats with the live weight
            beer_info = library[beer_id].copy()
            beer_info['id'] = beer_id
            beer_info['percent'] = tap_weights[tap_num]
            taps_to_render[tap_num] = beer_info
        else:
            taps_to_render[tap_num] = {'name': 'Empty Tap', 'percent': 0, 'id': 'none'}
            
    return render_template('index.html', taps=taps_to_render)

@app.route('/update_weight', methods=['POST'])
def update_weight():
    data = request.json
    # Map your tap names (Law/Wisco/Nitro) to 1, 2, 3
    name_map = {'Law Tap': '1', 'Wisco Tap': '2', 'Nitro Tap': '3'}
    tap_num = name_map.get(data.get('tap'))
    if tap_num:
        tap_weights[tap_num] = data.get('percent')
    return jsonify({"status": "success"})

@app.route('/library')
def library_page():
    return render_template('library.html', library=get_library())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
