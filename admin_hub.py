import json
import os
import subprocess
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# --- FILE PATHS ---
BASE_DIR = "/home/lawmj04/law-brewing"
LIB_FILE = os.path.join(BASE_DIR, "library.json")
TAP_FILE = os.path.join(BASE_DIR, "taps.json")
ADMIN_PASSWORD = "Lex!ngt0n0904"  # <-- CHANGE THIS

# --- HELPER: GITHUB SYNC ---
def sync_to_github(message):
    try:
        os.chdir(BASE_DIR)
        subprocess.run(["git", "add", "library.json", "taps.json"], check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        return True
    except Exception as e:
        print(f"Git Sync Error: {e}")
        return False

# --- HTML TEMPLATE ---
ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>LBC Management</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #121212; color: white; padding: 20px; }
        .container { max-width: 800px; margin: auto; }
        .card { border: 1px solid #444; padding: 20px; margin-bottom: 25px; border-radius: 12px; background: #1e1e1e; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        h2 { color: #ffb400; border-bottom: 1px solid #333; padding-bottom: 10px; }
        select, input, textarea { width: 100%; margin: 10px 0; padding: 12px; background: #2a2a2a; color: white; border: 1px solid #444; border-radius: 6px; box-sizing: border-box; }
        button { width: 100%; padding: 15px; background: #ffb400; border: none; cursor: pointer; font-weight: bold; border-radius: 6px; transition: 0.2s; }
        button:hover { background: #e6a800; }
        .lib-item { font-size: 0.9em; color: #aaa; margin-bottom: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🍺 Live Tap Assignments</h2>
        <p>Assign beers from your library to the hardware scales.</p>
        <form method="POST" action="/update_taps">
            <input type="password" name="pw" placeholder="Admin Password" required>
            {% for tap_id in ["Law Tap", "Wisco Tap", "Nitro Tap"] %}
            <div class="card">
                <strong style="font-size: 1.2em;">{{ tap_id }}</strong>
                <select name="{{ tap_id }}">
                    <option value="none">-- Off Tap / Empty --</option>
                    {% for beer_id, beer in library.items() %}
                    <option value="{{ beer_id }}" {% if current_taps[tap_id].beer_id == beer_id %}selected{% endif %}>
                        {{ beer.name }} ({{ beer.abv }})
                    </option>
                    {% endfor %}
                </select>
            </div>
            {% endfor %}
            <button type="submit">Update Dashboard & Sync</button>
        </form>

        <hr style="margin: 40px 0; border: 0; border-top: 1px dashed #444;">

        <h2>📚 Add to Beer Library</h2>
        <form method="POST" action="/add_beer">
            <input type="password" name="pw" placeholder="Admin Password" required>
            <div class="card">
                <input type="text" name="name" placeholder="Beer Name (e.g., Midnight Porter)" required>
                <input type="text" name="abv" placeholder="ABV (e.g., 5.8%)">
                <input type="text" name="art" placeholder="Image Path (e.g., assets/porter.png)">
                <textarea name="desc" rows="3" placeholder="Description / Tasting Notes"></textarea>
                <button type="submit" style="background: #27ae60;">Save to Library</button>
            </div>
        </form>
    </div>
</body>
</html>
"""

# --- ROUTES ---

@app.route('/admin')
def admin_view():
    with open(LIB_FILE, 'r') as f: lib = json.load(f)
    with open(TAP_FILE, 'r') as f: taps = json.load(f)
    return render_template_string(ADMIN_HTML, library=lib, current_taps=taps)

@app.route('/update_taps', methods=['POST'])
def update_taps():
    if request.form.get('pw') != ADMIN_PASSWORD: return "Unauthorized", 401
    
    with open(LIB_FILE, 'r') as f: lib = json.load(f)
    with open(TAP_FILE, 'r') as f: taps = json.load(f)

    for tap_id in ["Law Tap", "Wisco Tap", "Nitro Tap"]:
        beer_id = request.form.get(tap_id)
        if beer_id != "none":
            beer_data = lib[beer_id]
            taps[tap_id].update({
                "beer_id": beer_id,
                "beer_name": beer_data["name"],
                "desc": beer_data["desc"],
                "img": beer_data["art"],
                "abv": beer_data["abv"],
                "rating": beer_data.get("rating", 5.0)
            })
        else:
            taps[tap_id].update({"beer_id": "none", "beer_name": "Off Tap", "desc": "", "img": ""})

    with open(TAP_FILE, 'w') as f: json.dump(taps, f, indent=4)
    sync_to_github("Admin: Updated Tap Assignments")
    return "Taps Updated! <a href='/admin'>Return to Admin</a>"

@app.route('/add_beer', methods=['POST'])
def add_beer():
    if request.form.get('pw') != ADMIN_PASSWORD: return "Unauthorized", 401
    with open(LIB_FILE, 'r') as f: lib = json.load(f)
    
    name = request.form.get('name')
    beer_id = name.lower().replace(" ", "_")
    
    lib[beer_id] = {
        "name": name,
        "abv": request.form.get('abv'),
        "art": request.form.get('art'),
        "desc": request.form.get('desc'),
        "rating": 5.0,
        "votes": 0
    }
    
    with open(LIB_FILE, 'w') as f: json.dump(lib, f, indent=4)
    sync_to_github(f"Admin: Added {name} to Library")
    return "Beer Added! <a href='/admin'>Return to Admin</a>"

@app.route('/rate_library', methods=['POST'])
def rate_library():
    data = request.json
    beer_id = data.get('beer_id')
    new_rating = float(data.get('rating'))
    
    with open(LIB_FILE, 'r') as f: lib = json.load(f)
    
    if beer_id in lib:
        curr_avg = lib[beer_id].get('rating', 5.0)
        votes = lib[beer_id].get('votes', 0)
        lib[beer_id]['rating'] = round(((curr_avg * votes) + new_rating) / (votes + 1), 1)
        lib[beer_id]['votes'] = votes + 1
        with open(LIB_FILE, 'w') as f: json.dump(lib, f, indent=4)
        sync_to_github(f"Auto: New rating for {beer_id}")
        return jsonify({"status": "success"})
    
    return jsonify({"status": "error"}), 404

if __name__ == '__main__':
    # Runs on port 5000, accessible on local network
    app.run(host='0.0.0.0', port=5000)
