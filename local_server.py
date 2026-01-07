from flask import Flask, render_template, jsonify, request, Response
import json
import os
import time
import threading
import subprocess
import urllib.request
from functools import wraps
from datetime import datetime, timedelta

app = Flask(__name__)

# --- CONFIGURATION ---
DATA_FILE = "/home/lawmj04/law-brewing/tap_weights.json"
HISTORY_FILE = "/home/lawmj04/law-brewing/history.json"
SESSIONS_FILE = "/home/lawmj04/law-brewing/keg_sessions.json"
TAPS = ['Law Tap', 'Wisco Tap', 'Nitro Tap']

# --- ALERTS ---
WEBHOOK_URL = "https://discord.com/api/webhooks/1457116112201322772/8Kl-UmwdO0bUPN-51ZdjVMzxa7823TEd1znJNgRAL-eRHsA8UAwONornmo9OW4r1JmFN"
BREW_PCT = 25.0 
LOW_PCT = 12.5  
CRIT_PCT = 5.0  
HYSTERESIS = 3.0 # Buffer: Must rise 3% to clear an alert state

# --- SECURITY ---
ADMIN_USER = "admin"
ADMIN_PASS = "beer"

def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS

def authenticate():
    return Response('Login Required', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- DATA HELPERS ---
def load_sessions():
    if not os.path.exists(SESSIONS_FILE):
        init_data = {tap: {"beer": "Empty", "style": "None", "start_date": datetime.now().strftime('%Y-%m-%d'), "start_pct": 0, "active": True} for tap in TAPS}
        init_data['history'] = []
        init_data['lifetime_pints'] = 0
        with open(SESSIONS_FILE, 'w') as f:
            json.dump(init_data, f)
    with open(SESSIONS_FILE, 'r') as f:
        return json.load(f)

def save_sessions(data):
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def send_discord_alert(msg):
    if "https" not in WEBHOOK_URL: return
    try:
        data = {"content": msg}
        req = urllib.request.Request(WEBHOOK_URL, json.dumps(data).encode(), {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req)
    except: pass

# --- BACKGROUND MONITOR ---
volume_states = {} 
SEVERITY = {"normal": 0, "brew_warning": 1, "low": 2, "critical": 3}

def record_history():
    while True:
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    current = json.load(f)
                
                history = []
                if os.path.exists(HISTORY_FILE):
                    with open(HISTORY_FILE, 'r') as f:
                        history = json.load(f)
                if len(history) > 2016: history.pop(0)
                history.append({"time": datetime.now().strftime('%H:%M'), "data": current})
                with open(HISTORY_FILE, 'w') as f:
                    json.dump(history, f)

                # CHECK ALERTS WITH HYSTERESIS
                sessions = load_sessions()
                for tap in TAPS:
                    pct = current.get(tap, 0)
                    beer_name = sessions.get(tap, {}).get('beer', 'Unknown Beer')
                    
                    # 1. Determine "Raw" State (Strict Thresholds)
                    raw_state = "normal"
                    if pct < CRIT_PCT: raw_state = "critical"
                    elif pct < LOW_PCT: raw_state = "low"
                    elif pct < BREW_PCT: raw_state = "brew_warning"
                    
                    # 2. Apply Sticky Logic
                    last_state = volume_states.get(tap, "normal")
                    new_state = raw_state
                    
                    # If we are seemingly "improving" (e.g. Low -> Brew Warning), 
                    # verify we exceeded the buffer (Hysteresis) to avoid noise flips.
                    if SEVERITY[raw_state] < SEVERITY[last_state]:
                        if last_state == "critical" and pct < (CRIT_PCT + HYSTERESIS):
                            new_state = "critical" # Stick to Critical
                        elif last_state == "low" and pct < (LOW_PCT + HYSTERESIS):
                            new_state = "low" # Stick to Low
                        elif last_state == "brew_warning" and pct < (BREW_PCT + HYSTERESIS):
                            new_state = "brew_warning" # Stick to Warning

                    # 3. Handle Alerting
                    if new_state != last_state:
                        # Only alert if getting WORSE (increasing severity)
                        if SEVERITY[new_state] > SEVERITY[last_state]:
                            if new_state == "brew_warning":
                                send_discord_alert(f"🛠 **BREWER'S NOTICE** 🛠\n**{beer_name}** ({tap}) is down to 25% (10 Pints).\n*Time to brew the replacement!*")
                            elif new_state == "low":
                                send_discord_alert(f"⚠️ **GROWLER WARNING** ⚠️\n**{beer_name}** ({tap}) is running low!\n*Only ~5 pints remaining.*")
                            elif new_state == "critical":
                                send_discord_alert(f"🚨 **DEATH IMMINENT** 🚨\n**{beer_name}** ({tap}) is taking its final breaths.\n*Less than 2 pints left.*")
                        
                        # Update memory
                        volume_states[tap] = new_state
                        
        except: pass
        time.sleep(300)

recorder = threading.Thread(target=record_history)
recorder.daemon = True
recorder.start()

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    weights = {}
    try:
        with open(DATA_FILE, 'r') as f: weights = json.load(f)
    except: pass
    sessions = load_sessions()
    meta = {}
    for tap in TAPS:
        s = sessions.get(tap, {})
        start_date = datetime.strptime(s.get('start_date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d')
        days = (datetime.now() - start_date).days
        start_pct = s.get('start_pct', 100)
        current_pct = weights.get(tap, 0)
        consumed_pct = max(0, start_pct - current_pct)
        consumed_pints = (consumed_pct / 100) * 40
        rate = round(consumed_pints / max(1, days), 1)
        kick_date_str = None
        if rate > 0.2:
            current_pints = (current_pct / 100) * 40
            days_left = current_pints / rate
            kick_date = datetime.now() + timedelta(days=days_left)
            kick_date_str = kick_date.strftime("%a, %b %d")
        meta[tap] = { "beer": s.get('beer', 'Empty'), "style": s.get('style', ''), "days_on_tap": days, "pints_per_day": rate, "kick_date": kick_date_str }
    return jsonify({"taps": TAPS, "weights": weights, "meta": meta, "lifetime": sessions.get('lifetime_pints', 0)})

@app.route('/history')
def get_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f: return jsonify(json.load(f))
    except: pass
    return jsonify([])

@app.route('/stats')
def get_stats():
    sessions = load_sessions()
    history = sessions.get('history', [])
    valid_history = [h for h in history if h['beer'] != 'Empty' and h.get('pints_consumed', 0) > 5]
    sorted_stats = sorted(valid_history, key=lambda x: x.get('rate', 0), reverse=True)[:5]
    return jsonify(sorted_stats)

@app.route('/swap', methods=['POST'])
def swap_keg():
    data = request.json
    tap = data['tap']
    new_beer = data['beer']
    new_style = data['style']
    action_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    sessions = load_sessions()
    old_session = sessions[tap]
    
    if old_session['beer'] == new_beer:
         old_session['start_date'] = action_date
         old_session['style'] = new_style
         save_sessions(sessions)
         return jsonify({"status": "updated"})
    
    if old_session['beer'] != 'Empty':
        end_date = datetime.strptime(action_date, '%Y-%m-%d')
        start_date = datetime.strptime(old_session['start_date'], '%Y-%m-%d')
        days = (end_date - start_date).days
        try:
            with open(DATA_FILE, 'r') as f: weights = json.load(f)
            end_pct = weights.get(tap, 0)
        except: end_pct = 0
        start_pct = old_session.get('start_pct', 100)
        pints = ((start_pct - end_pct) / 100) * 40
        rate = round(pints / max(1, days), 1)
        sessions['history'].append({ "beer": old_session['beer'], "style": old_session['style'], "days": days, "pints_consumed": round(pints, 1), "rate": rate, "kicked_date": action_date })
        sessions['lifetime_pints'] = sessions.get('lifetime_pints', 0) + round(pints, 1)
        msg = f"🪦 **KEG DEPARTED** 🪦\nWe gather today to mourn the loss of **{old_session['beer']}**.\n\n📝 **Final Stats:**\n⏳ Lived: {days} Days\n🍺 Served: {round(pints, 1)} Pints\n🔥 Burn Rate: {rate} pts/day\n\n*Rest in Peace.*"
        send_discord_alert(msg)

    try:
        with open(DATA_FILE, 'r') as f: weights = json.load(f)
        current_weight = weights.get(tap, 100)
    except: current_weight = 100
    sessions[tap] = { "beer": new_beer, "style": new_style, "start_date": action_date, "start_pct": current_weight, "active": True }
    save_sessions(sessions)
    msg = f"🎺 **GRAND ANNOUNCEMENT** 🎺\nA new challenger has entered the arena!\n\n🍺 **{new_beer}**\n📝 *{new_style}*\n📍 {tap}\n\n*Pouring now!*"
    send_discord_alert(msg)
    return jsonify({"status": "ok"})

@app.route('/admin/logs')
@requires_auth
def view_logs():
    try: output = subprocess.check_output("journalctl -u raw-brain.service -n 300 --no-pager", shell=True).decode('utf-8')
    except Exception as e: output = str(e)
    return f"<html><head><title>Logs</title><style>body{{background:#121212;color:#00ff00;font-family:monospace;padding:20px;}}pre{{white-space:pre-wrap;}}</style></head><body><h2>🧠 BRAIN LOGS</h2><pre>{output}</pre></body></html>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
