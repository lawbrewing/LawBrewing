import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- CONFIGURATION ---
# Path to your library images
LIBRARY_FOLDER = os.path.expanduser('~/law-brewing/static/images/library')
app.config['LIBRARY_FOLDER'] = LIBRARY_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB Upload Limit

# Global variable to store tap data (In a real app, you'd use a database)
taps_status = {
    'Law Tap': {'percent': 0, 'id': 'unknown'},
    'Wisco Tap': {'percent': 0, 'id': 'unknown'},
    'Nitro Tap': {'percent': 0, 'id': 'unknown'}
}

# Ensure the library directory exists
os.makedirs(LIBRARY_FOLDER, exist_ok=True)

# --- ROUTES ---

@app.route('/')
def index():
    """Main Dashboard showing live tap levels"""
    return render_template('index.html', taps=taps_status)

@app.route('/update_weight', methods=['POST'])
def update_weight():
    """Endpoint for raw_brain.py to send weight updates"""
    data = request.json
    tap_name = data.get('tap')
    percent = data.get('percent')
    if tap_name in taps_status:
        taps_status[tap_name]['percent'] = percent
    return jsonify({"status": "success"})

@app.route('/library')
def library():
    """The Archive Gallery using the Beer ID trick"""
    # Get all .png files and strip the extension to get the ID
    beer_ids = [f.split('.')[0] for f in os.listdir(app.config['LIBRARY_FOLDER']) 
                if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    return render_template('library.html', beer_ids=beer_ids)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Mobile-friendly upload page"""
    if request.method == 'POST':
        beer_id = request.form.get('beer_id')
        file = request.files.get('file')
        
        if file and beer_id:
            # Save as [ID].png regardless of original name
            filename = secure_filename(f"{beer_id}.png")
            file.save(os.path.join(app.config['LIBRARY_FOLDER'], filename))
            return redirect(url_for('library'))
            
    return render_template('upload.html')

@app.route('/delete/<beer_id>', methods=['POST'])
def delete_beer(beer_id):
    """Remove a beer from the library"""
    file_path = os.path.join(app.config['LIBRARY_FOLDER'], f"{beer_id}.png")
    if os.path.exists(file_path):
        os.remove(file_path)
    return redirect(url_for('library'))

if __name__ == '__main__':
    # Run on 0.0.0.0 so it's accessible on your network and through tunnels
    app.run(host='0.0.0.0', port=5000, debug=True)
