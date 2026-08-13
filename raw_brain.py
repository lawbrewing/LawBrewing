import subprocess
import socket, json, os, re, time, struct, threading, csv, urllib.request, ssl, io, traceback, random
from collections import deque
from flask import Flask, render_template_string, jsonify, request
from datetime import datetime, timedelta

# Create a lock so only one Git operation happens at a time
git_lock = threading.Lock()

# ================= CONFIGURATION =================
BASE_DIR = "/home/lawmj04/law-brewing"
WEIGHTS_FILE = os.path.join(BASE_DIR, "tap_weights.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
SESSIONS_FILE = os.path.join(BASE_DIR, "keg_sessions.json")
AUDIT_FILE = os.path.join(BASE_DIR, "pour_audit.csv")
MAINTENANCE_FILE = os.path.join(BASE_DIR, "maintenance.json")
KEG_HISTORY_FILE = os.path.join(BASE_DIR, "keg_history.json") # <--- NEW: The Graveyard File

SHEET_URL = "https://docs.google.com/spreadsheets/d/1VbP3OVG7PcRKYKsltZkMHD_cpiNXMrpuaxxnrBmRRQg/export?format=csv"
WEBHOOK_URL = "https://discord.com/api/webhooks/1457116112201322772/8Kl-UmwdO0bUPN-51ZdjVMzxa7823TEd1znJNgRAL-eRHsA8UAwONornmo9OW4r1JmFN"
DISCORD_INVITE = "https://discord.gg/KkK6C9C4"

# ==== SAFETY ALERT CONFIGURATION ====
NITRO_IP_SUFFIX = "45"       # Nitro is .45
TEMP_LIMIT_NITRO = 56.0      # Alert if Nitro > 56F
TEMP_LIMIT_STD = 50.0        # Alert others > 50F
LEAK_FLOW_MAX_SEC = 60       # Time threshold to check for leaks
LEAK_VOL_TRIGGER_OZ = 80.0   # Only alert if > 80oz lost (Major leak)
ALERT_COOLDOWN = 3600        # Wait 7 days before repeating same safety alert
safety_cooldowns = {}        # Track last alert times
VOLUME_ALERT_COOLDOWN = 604800  # 7 Days (60s * 60m * 24h * 7d)
volume_alert_history = {}    # Tracks when we last screamed about a specific tap
tap_beer_abv = {}            # Stores ABV from Google Sheet

# CONSTANTS
TAPS = ['Law Tap', 'Wisco Tap', 'Nitro Tap']
TAP_CONFIG = {
    '192.168.86.47':  {'name': 'Law Tap',   'empty': 0, 'full': 19000},
    '192.168.86.116': {'name': 'Wisco Tap', 'empty': 0, 'full': 19000},
    '192.168.86.45':  {'name': 'Nitro Tap', 'empty': 0, 'full': 19000}
}
AUDIT_TRIGGER = 6.0; POUR_TRIGGER = 6.0; GIT_TRIGGER_PCT = 3.0; MOTION_SENSITIVITY = 15; MAX_POUR_OZ = 130;
MAX_FLOW_RATE = 2.5

# Alert Thresholds
BREW_PCT = 25.0  # Brewmaster Warning
LOW_PCT = 10.0   # Dangerously Low
DEAD_PCT = 8.0   # Death Imminent (~3 Pints)
CRIT_PCT = 0.5   # Empty / Eulogy

# STATE
current_weights = {};
last_recon_weights = {}
pour_start_weights = {}; pour_start_times = {}; is_pouring = {}
readings_history = {}; volume_states = {}; last_local_save = 0;
last_git_push = 0
last_zero_alert = {} # Debounce for empty
tap_beer_names = {}  # Cache for beer names
tap_beer_styles = {} # <--- Fixed: Now global
tap_beer_abv = {}    # <--- Fixed: Now global

# --- PHRASES (DISCORD PERSONALITY) ---
PHRASES = {
    "NEW": [
        "📯 **HEAR YE, HEAR YE!** By royal decree, a fresh cask of **{beer}** is now flowing on {tap}!",
        "🎺 **FANFARE!** The drought is ended! **{beer}** hath entered the realm!",
        "🏰 **PROCLAMATION:** The gates are open! Come forth and taste the new **{beer}**!",
        "🍻 **FRESH POTS!** **{beer}** has tapped in. Come get some!"
    ],
    "BREW": [
        "🍺 **Brewmaster Alert:** **{beer}** is down to 25%. Time to fire up the kettle?",
        "📉 **Inventory Note:** **{beer}** is at the quarter mark. Plan the next batch!",
        "📝 **Log Update:** **{beer}** hits 25% capacity."
    ],
    "LOW": [
        "⚠️ **Dangerously Low:** Only 10% of **{beer}** remains.",
        "🏃 **HURRY!** **{beer}** is fading fast (10% left)!",
        "🚨 **Low Fuel:** **{beer}** is entering the red zone."
    ],
    "DEAD": [
        "💀 **DEATH IMMINENT:** Less than 3 pints of **{beer}** remain! Claim the final pours!",
        "⏳ **The End is Nigh:** **{beer}** is taking its final breaths.",
        "🩸 **Last Drops:** **{beer}** is critically low (< 3 pints)!"
    ],
    "EMPTY": [
        "⚰️ **RIP:** **{beer}** has officially kicked. It was a good keg.",
        "👻 **GHOST TOWN:** {tap} runs dry. **{beer}** is no more.",
        "🔚 **That's a Wrap:** **{beer}** has left the building."
    ]
}

# --- HELPERS ---
def load_json(path, default):
    try:
        with open(path, 'r') as f: return json.load(f)
    except: return default

def save_json(path, data):
    try:
        with open(path, 'w') as f: json.dump(data, f, indent=4)
    except: pass

def log_event(name, val, evt):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(AUDIT_FILE, "a") as f: f.write(f"{ts},{name},{val},{evt}\n")
    except: pass

def send_discord(msg):
    if "https" not in WEBHOOK_URL: return
    try:
        req = urllib.request.Request(WEBHOOK_URL, json.dumps({"content": msg}).encode(), {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req)
    except: pass

def get_pour_name(oz):
    if oz < POUR_TRIGGER: return None
    if oz < 6.5: return "Taster"
    if oz < 11.0: return "Short Pour"
    if oz < 24.0: return "Pint"
    if oz < 45.0: return "Crowler"
    return "Growler"

# --- NEW: ARCHIVE FUNCTION FOR HISTORY ---
def archive_current_keg(tap, manual_name=None):
    try:
        global tap_beer_names, tap_beer_styles, tap_beer_abv # Ensure access
        sessions = load_json(SESSIONS_FILE, {})
        if tap not in sessions: return

        session_data = sessions[tap]
        
        # Pull from globals (populated by Google Sheet sync)
        beer_name = manual_name if manual_name else tap_beer_names.get(tap, "Unknown Beer")
        beer_style = tap_beer_styles.get(tap, "Unknown Style")
        beer_abv = tap_beer_abv.get(tap, "??%")

        sessions = load_json(SESSIONS_FILE, {})
        if tap not in sessions: return

        session_data = sessions[tap]
        
        # USE THE PASSED NAME IF AVAILABLE, OTHERWISE FALLBACK TO CACHE
        beer_name = manual_name if manual_name else tap_beer_names.get(tap, "Unknown Beer")
        beer_style = tap_beer_styles.get(tap, "Unknown Style")
        beer_abv = tap_beer_abv.get(tap, "??%")

        start_str = session_data.get('start_date', datetime.now().strftime('%Y-%m-%d'))
        start_pct = float(session_data.get('start_pct', 100))
        end_dt = datetime.now()
        end_str = end_dt.strftime('%Y-%m-%d')
        start_gallons = round((start_pct / 100.0) * 5.0, 2)

        # 2. CALCULATE POUR STATS (The "Spotify Wrapped" Logic)
        # We scan the audit log for pours on THIS tap between Start Date and NOW.
        stats = {"Taster": 0, "Short Pour": 0, "Pint": 0, "Crowler": 0, "Growler": 0, "Total_Oz": 0}
        
        if os.path.exists(AUDIT_FILE):
            try:
                s_date_obj = datetime.strptime(start_str, "%Y-%m-%d")
                with open(AUDIT_FILE, 'r') as f:
                    for line in f:
                        parts = line.split(',')
                        if len(parts) < 4: continue
                        
                        # Check Tap Name
                        if parts[1] != tap: continue
                        
                        # Check Date (Is this pour from this keg's life?)
                        log_date = datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
                        if log_date < s_date_obj: continue

                        # Check Event Type (Must be POUR)
                        if "POUR" not in parts[3]: continue

                        # Calculate Volume
                        try:
                            val_str = parts[2].replace('oz','').replace('pts','').strip()
                            oz = float(val_str)
                            if oz <= 0 or oz > MAX_POUR_OZ: continue
                            stats["Total_Oz"] += oz
                            
                            # Categorize
                            if oz < 6.5: stats["Taster"] += 1
                            elif oz < 11.0: stats["Short Pour"] += 1
                            elif oz < 24.0: stats["Pint"] += 1
                            elif oz < 45.0: stats["Crowler"] += 1
                            else: stats["Growler"] += 1
                        except: pass
            except Exception as e:
                print(f"Error calculating stats: {e}")

        # 3. Create Clean Record
        record = {
            "beer": beer_name,
            "style": beer_style,
            "abv": beer_abv,        # <--- Saved forever
            "tap": tap,
            "start_date": start_str,
            "end_date": end_str,
            "start_gallons": start_gallons,
            "pour_count": stats     # <--- Saved forever
        }

        # 4. Save to Graveyard
        history = load_json(KEG_HISTORY_FILE, [])
        history.insert(0, record)
        save_json(KEG_HISTORY_FILE, history)
        print(f"⚰️ Archived: {beer_name}")

    except Exception as e:
        print(f"Error archiving keg: {e}")

def update_beer_names():
    # Background fetcher to learn beer names from Google Sheet
    global tap_beer_names
    try:
        ctx = ssl.create_default_context();
        ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
        r = urllib.request.urlopen(SHEET_URL, context=ctx, timeout=5)
        reader = csv.reader(io.StringIO(r.read().decode('utf-8')))
        next(reader) # Skip header
        for row in reader:
            if len(row) > 6:
                rid = row[0].lower()
                t = None
                if "law" in rid or "1" in rid: t = "Law Tap"
                elif "wisco" in rid or "2" in rid: t = "Wisco Tap"
                elif "nitro" in rid or "3" in rid: t = "Nitro Tap"
                if t: 
                    tap_beer_names[t] = row[2] # Store Beer Name
                    tap_beer_styles[t] = row[6] 
                    tap_beer_abv[t] = row[3]
    except: pass

def sync_to_github(filename):
    """
    Handles git operations safely in a separate thread.
    Uses a lock to ensure only one git process runs at a time.
    """
    def _run_git():
        # Check if locked. If locked, we skip this cycle to prevent pile-up.
        if git_lock.acquire(blocking=False): 
            try:
                # 1. Add all files (captures pour_audit.csv, etc.)
                subprocess.run(["git", "add", "."], cwd=BASE_DIR, check=False)
                
                # 2. Commit with timestamp
                msg = f"Update {os.path.basename(filename)} - {datetime.now().strftime('%H:%M:%S')}"
                subprocess.run(["git", "commit", "-m", msg], cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # 3. Push safely
                result = subprocess.run(["git", "push", "origin", "master"], cwd=BASE_DIR, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"🚀 Pushed {os.path.basename(filename)} to GitHub")
                else:
                    print(f"⚠️ Git Push Warning: {result.stderr.strip()}")
            except Exception as e:
                print(f"❌ Git Sync Error: {e}")
            finally:
                git_lock.release()
        else:
            print(f"⏳ Git busy, skipping sync for {os.path.basename(filename)}")

    # Launch in background
    t = threading.Thread(target=_run_git)
    t.start()

def save_data(data, filename=WEIGHTS_FILE, force_git=False):
    """
    Saves the current data to JSON and pushes to GitHub.
    force_git=True : Bypasses any checks and forces a push (used by Heartbeat).
    """
    data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # 1. Save JSON to disk (always)
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        
        # 2. Sync to GitHub
        # We push if it's a forced heartbeat OR a regular update
        if force_git:
            # Add specific files to be safe
            subprocess.run(["git", "add", filename], check=False)
            subprocess.run(["git", "commit", "-m", f"💓 Heartbeat: {datetime.now().strftime('%H:%M')}"], check=False)
            subprocess.run(["git", "push", "-f"], check=False)
            print("🚀 Heartbeat Pushed to GitHub")
        else:
            # This is the standard "Data Changed" path
            subprocess.run(["git", "add", filename], check=False)
            subprocess.run(["git", "commit", "-m", f"🍺 Pour Update: {datetime.now().strftime('%H:%M')}"], check=False)
            # Use 'subprocess.Popen' for non-blocking push on pours, or 'run' if you want safety
            subprocess.run(["git", "push"], check=False)

    except Exception as e:
        print(f"❌ Save/Sync Failed: {e}")

# --- BACKGROUND THREADS ---

def history_loop():
    """
    Background thread that handles:
    1. Git Sync (Heartbeat) - Every 10 mins
    2. History Logging - Every 1 min
    3. Beer Name Updates - Every 10 mins
    4. Low Keg Notifications - Realtime checks
    """
    global last_git_push, last_recon_weights
    last_name_update = 0
    
    # Track which kegs we have already alerted about to avoid spamming
    notified_low = {"Law Tap": False, "Wisco Tap": False, "Nitro Tap": False}
    notified_empty = {"Law Tap": False, "Wisco Tap": False, "Nitro Tap": False}

    print("⏳ Background Thread Started (Heartbeat & History)")

    while True:
        try:
            # --- 1. HEARTBEAT (Git Sync) ---
            # Checks every minute if 10 minutes (600s) have passed since last push
            if (time.time() - last_git_push) > 600:
                last_git_push = time.time()  # Reset timer immediately
                
                # RECONCILIATION ENGINE: Catch missed pours
                for tap in TAPS:
                    if tap in current_weights and tap in last_recon_weights:
                        old_pct = last_recon_weights[tap]
                        new_pct = current_weights[tap]
                    
                        # Calculate drop in % and convert to oz (Assuming 5gal/640oz keg)
                        pct_drop = old_pct - new_pct
                        drop_oz = (pct_drop / 100.0) * 640.0
                    
                        # If drop > 6.0oz and no POUR was recently logged
                        if drop_oz > 6.0:
                            # Check if a pour was already logged in the last 10 mins
                            # to avoid double-counting
                            log_event(tap, f"{drop_oz:.1f} oz", "RECONCILED_POUR")
                            print(f"🕵️ Reconciliation: Caught missed {drop_oz:.1f}oz pour on {tap}")
            
                # Update baselines for the next 10-minute window
                last_recon_weights = current_weights.copy()

                print("💓 Heartbeat: Pushing to GitHub...")
                # We use the global current_weights dictionary
                sync_to_github(HISTORY_FILE)

            # --- 2. UPDATE BEER NAMES (Every 10 mins) ---
            if (time.time() - last_name_update) > 600:
                update_beer_names()
                last_name_update = time.time()

            # --- 3. SAVE HISTORY JSON (For Graphs) ---
            h = load_json(HISTORY_FILE, [])
            # Keep history manageable (last ~48 hours at 1-min intervals)
            if len(h) > 2880:
                h.pop(0)
            
            # Snapshot the current state
            h.append({
                "time": datetime.now().strftime('%H:%M:%S'),
                "data": current_weights.copy()
            })
            save_json(HISTORY_FILE, h)

            # --- 4. NOTIFICATIONS (Low Keg Alerts) ---
            for tap, weight in current_weights.items():
                # Skip metadata keys (temps, timestamps, etc.)
                if "_temp" in tap or "_updated" in tap or "last_" in tap or "_pour" in tap:
                    continue

                try:
                    w = float(weight)
                    
                    # ALERT: Keg Empty (< 10oz)
                    if w < 10:
                        if not notified_empty.get(tap, False):
                            send_discord(f"🚨 KEG KICKED: {tap} is empty!")
                            notified_empty[tap] = True
                    
                    # ALERT: Low Keg (< 100oz)
                    elif w < 100:
                        if not notified_low.get(tap, False):
                            send_discord(f"⚠️ LOW KEG: {tap} is below 100oz.")
                            notified_low[tap] = True
                    
                    # RESET: If weight goes up (keg swapped), reset alerts
                    if w > 100:
                        notified_low[tap] = False
                        notified_empty[tap] = False

                except ValueError:
                    continue # Skip if weight isn't a number

            # --- 5. SLEEP (Crucial for CPU) ---
            time.sleep(60)  # Run this loop once per minute

        except Exception as e:
            print(f"❌ Background Loop Error: {e}")
            time.sleep(60)  # Sleep even on error to prevent log spam

# --- FLASK WEB SERVER ---
app = Flask(__name__)

# --- HTML TEMPLATES (Embedded) ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Law Brewing | Local Command</title>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Roboto:wght@300;400&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { --accent: #ffb400; --temp: #03a9f4; --bg: #121212; --card: #1e1e1e; --text: #ffffff; }
        body { background: var(--bg); color: var(--text); font-family: 'Roboto', sans-serif; margin: 0; padding: 20px; }
        .header { display: flex; flex-direction: column; align-items: center; gap: 15px; margin-bottom: 30px; border-bottom: 1px solid #333; padding-bottom: 20px; }
        h1 { font-family: 'Oswald', sans-serif; color: var(--accent); letter-spacing: 2px; margin: 0; text-align: center; }
        .nav-group { display: flex; gap: 20px; justify-content: center; width: 100%; flex-wrap: wrap; }
        .btn { background: #222; color: #fff; text-decoration: none; padding: 12px 25px; border-radius: 8px; font-size: 1rem; border: 2px solid #555; font-weight: bold; }
        .btn:hover { background: var(--accent); border-color: var(--accent); color: #000; }
        .btn-maint { border-color: #03a9f4; color: #03a9f4; }
        .btn-discord { border-color: #5865F2; color: #fff; background: #5865F2; }
        .btn-discord:hover { background: #4752c4; border-color: #4752c4; color: #fff; }
        .tap-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; max-width: 1200px; margin: 0 auto; }
        .tap-card { background: var(--card); border-radius: 15px; padding: 25px; border: 1px solid #333; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        .tap-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px; }
        .beer-name { font-family: 'Oswald', sans-serif; font-size: 1.8rem; margin: 0; color: #fff; }
        .tap-id { font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 1px; }
        .stats-row { display: flex; justify-content: space-between; font-size: 0.9rem; color: #aaa; margin-bottom: 15px; align-items: center; }
        .temp-stat { color: var(--temp); font-weight: bold; }
        .date-btn { background: none; border: none; color: #666; cursor: pointer; font-size: 1rem; margin-left: 5px; }
        .volume-container { background: #000; height: 30px; border-radius: 15px; overflow: hidden; border: 2px solid #333; position: relative; }
        .volume-bar { height: 100%; background: linear-gradient(90deg, #b8860b, var(--accent)); transition: width 1s; width: 0%; }
        .volume-text { position: absolute; top: 5px; width: 100%; text-align: center; font-size: 0.85rem; font-weight: bold; text-shadow: 1px 1px 2px #000; z-index: 2; }
        .last-pour { margin-top: 15px; text-align: center; font-size: 1.1rem; color: #fff; font-weight: bold; min-height: 1.2em; text-transform: uppercase; animation: flash 1s; }
        @keyframes flash { 0% { color: var(--accent); } 100% { color: #fff; } }
        .chart-box { height: 150px; margin-top: 20px; border-top: 1px solid #333; padding-top: 10px; }
        .meta-info { margin-top: 10px; font-size: 0.8rem; color: #666; text-align: center; }
        .highlight { color: var(--accent); }
    </style>
</head>
<body>
    <div class="header">
        <h1>🍺 LOCAL COMMAND CENTER</h1>
        <div class="nav-group">
            <a href="/maintenance" class="btn btn-maint">🛠 MAINTENANCE</a>
            <a href="/stats" class="btn" style="border-color:#ffb400; color:#ffb400;">📊 STATS</a>
            <a href="/admin/audit" class="btn">📜 AUDIT LOG</a>
        </div>
    </div>
    <div id="tap-display" class="tap-grid">Loading...</div>
    <script>
        let charts = {};
        async function updateDate(tap) {
            const safeId = tap.replace(/ /g, '-');
            const card = document.getElementById(`card-${safeId}`);
            const currentDisplayedBeer = card ? card.querySelector('.beer-name').innerText : "Unknown Beer";
            
            // Step 1: Confirm the Beer Name for the Archive
            const archivedBeerName = prompt(`Confirm name of the KEG BEING REMOVED from ${tap}:`, currentDisplayedBeer);
            if (!archivedBeerName) return; // Cancel if they hit cancel

            // Step 2: Enter the new Start Date
            const newDate = prompt(`Enter Start Date for the NEW keg on ${tap} (YYYY-MM-DD):`, new Date().toISOString().split('T')[0]);
    
            if (newDate) {
                await fetch('/set_date', {
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'}, 
                    body: JSON.stringify({ 
                        tap: tap, 
                        date: newDate,
                        old_beer_name: archivedBeerName // Passing the confirmed name to the Pi
                    })
                });
                location.reload();
            }
}

        async function update() {
            try {
                const res = await fetch('/data');
                const data = await res.json();
                const historyRes = await fetch('/history'); const history = await historyRes.json();
                const container = document.getElementById('tap-display');
                if (container.innerText === 'Loading...') container.innerHTML = '';

                data.taps.forEach(tap => {
                    const safeId = tap.replace(/ /g, '-');
                    let card = document.getElementById(`card-${safeId}`);
                    const meta = data.meta[tap];
                    const weight = data.weights[tap] || 0;
                    const temp = data.weights[tap + '_temp'] || 0;
                    const pour = data.weights[tap + '_last_pour'] || "";

                    if (!card) {
                        card = document.createElement('div'); card.id = `card-${safeId}`; card.className = 'tap-card';
                        card.innerHTML = `<div class="tap-header"><div><div class="tap-id">${tap}</div><div class="beer-name"></div><div style="font-size:0.9em; color:#888; font-style:italic;" class="beer-style"></div></div></div><div class="stats-row"><span>⏳ <span class="days-val"></span> Days <button class="date-btn" onclick="updateDate('${tap}')">📅</button></span><span class="temp-stat"></span></div><div class="volume-container"><div class="volume-bar" id="bar-${safeId}"></div><div class="volume-text" id="text-${safeId}"></div></div><div class="last-pour" id="pour-${safeId}"></div><div class="meta-info"></div><div class="chart-box"><canvas id="chart-${safeId}"></canvas></div>`;
                        container.appendChild(card);
                        const ctx = document.getElementById(`chart-${safeId}`).getContext('2d');
                        charts[tap] = new Chart(ctx, { type: 'line', data: { labels: [], datasets: [{ label: 'Vol (%)', data: [], borderColor: '#ffb400', borderWidth: 2, pointRadius: 0, tension: 0.4, fill: true, backgroundColor: 'rgba(255,180,0,0.1)', yAxisID: 'y' }, { label: 'Temp', data: [], borderColor: '#03a9f4', borderDash: [5, 5], borderWidth: 2, pointRadius: 0, tension: 0.4, yAxisID: 'y1' }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false, min: 0, max: 100 }, y1: { display: false, min: 25, max: 65, position: 'right' } } } });
                    }
                    card.querySelector('.beer-name').innerText = meta.beer;
                    card.querySelector('.beer-style').innerText = meta.style;
                    card.querySelector('.days-val').innerText = meta.days_on_tap;
                    card.querySelector('.temp-stat').innerText = `🌡 ${temp}°F`;
                    card.querySelector('.meta-info').innerHTML = `Burn Rate: <span class="highlight">${meta.pints_per_day}</span> pts/day <br>Est. Kick: <span class="highlight">${meta.kick_date || '--'}</span>`;
                    document.getElementById(`bar-${safeId}`).style.width = weight + '%';
                    const pints = Math.round((weight / 100) * 40);
                    document.getElementById(`text-${safeId}`).innerText = `${weight}% (${pints} Pints)`;

                    const pourEl = document.getElementById(`pour-${safeId}`);
                    if (pourEl.innerText !== pour) { pourEl.innerText = pour; 
                    if(pour) { pourEl.style.animation = 'none'; pourEl.offsetHeight; pourEl.style.animation = 'flash 1s'; } }

                    if (charts[tap] && history.length > 0) {
                        charts[tap].data.labels = history.map(h => h.time);
                        charts[tap].data.datasets[0].data = history.map(h => h.data[tap] || 0);
                        charts[tap].data.datasets[1].data = history.map(h => h.data[tap + '_temp'] || 0);
                        charts[tap].update('none');
                    }
                });
            } catch (e) { console.error(e); }
        }
        setInterval(update, 5000);
        update();
    </script>
</body>
</html>
"""

MAINTENANCE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Maintenance | Law Brewing</title>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Roboto:wght@300;400&display=swap" rel="stylesheet">
    <style>
        body { background: #121212; color: #fff; font-family: 'Roboto', sans-serif; padding: 20px; text-align: center; }
        h1 { font-family: 'Oswald', sans-serif; color: #ffb400; }
        .container { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; margin-top: 30px; }
        .card { background: #1e1e1e; border: 1px solid #333; border-radius: 15px; padding: 20px; width: 300px; text-align: left; }
        .card h2 { margin-top: 0; color: #03a9f4; border-bottom: 1px solid #444; padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        .btn-edit-cap { background: none; border: 1px solid #444; color: #888; font-size: 0.7em; padding: 2px 6px; border-radius: 4px; cursor: pointer; }
        .btn-edit-cap:hover { color: #fff; border-color: #ffb400; }
        .stat { font-size: 1.1rem; margin: 10px 0; display: flex; justify-content: space-between; color: #ccc; }
        .burn-rate { font-size: 0.9rem; color: #888; font-style: italic; margin-bottom: 15px; display: block; }
        .bar-bg { background: #000; height: 10px; border-radius: 5px; overflow: hidden; margin-bottom: 20px; }
        .bar-fill { height: 100%; background: #03a9f4; width: 0%; transition: width 0.5s; }
        .btn-group { display: flex; gap: 10px; margin-top: 20px; }
        button { flex: 1; padding: 10px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; transition: 0.2s; }
        .btn-add { background: #2e7d32; color: white; }
        .btn-reset { background: #c62828; color: white; }
        button:hover { opacity: 0.8; }
        .back-link { display: block; margin-top: 40px; color: #666; text-decoration: none; padding: 10px; border: 1px solid #333; border-radius: 5px; width: 200px; margin-left: auto; margin-right: auto; }
        .back-link:hover { color: #ffb400; border-color: #ffb400; }
    </style>
</head>
<body>
    <h1>🛠 SYSTEM MAINTENANCE</h1>
    <div class="container" id="app">Loading...</div>
    <a href="/" class="back-link">← Back to Dashboard</a>
    <script>
        const CONFIG = {
            'water': { label: 'RO Water Filter', unit: 'Gal', input_unit: 'Gal', color: '#03a9f4', type: 'simple' },
            'propane': { label: 'Propane Tank', unit: 'Lbs', input_unit: 'Hrs', color: '#ffb400', type: 'smart' }
        };
        async function load() {
            try {
                const res = await fetch('/api/maintenance');
                const data = await res.json();
                const container = document.getElementById('app');
                container.innerHTML = '';
                Object.keys(data).forEach(key => {
                    const item = data[key];
                    const cfg = CONFIG[key];
                    if (!cfg) return;

                    let remaining, pct, extraHtml = '';

                    if (cfg.type === 'smart') {
                        remaining = item.capacity - (item.used_hours * item.burn_rate);
                        pct = Math.max(0, Math.min(100, (remaining / item.capacity) * 100));
                        extraHtml = `<span class="burn-rate">Burn Rate: ${item.burn_rate.toFixed(2)} lbs/hr <br> (Used: ${item.used_hours.toFixed(1)} Hrs)</span>`;
                    } else {
                        remaining = item.capacity - item.used;
                        pct = Math.max(0, Math.min(100, (remaining / item.capacity) * 100));
                    }

                    const div = document.createElement('div');
                    div.className = 'card';
                    div.innerHTML = `
                        <h2>${cfg.label} <button class="btn-edit-cap" onclick="editCap('${key}')">⚙️</button></h2>
                        <div class="stat"><span>Remaining:</span> <span>${remaining.toFixed(1)} ${cfg.unit}</span></div>
                        ${extraHtml}
                        <div class="bar-bg"><div class="bar-fill" style="width: ${pct}%; background: ${cfg.color}"></div></div>
                        <div class="btn-group">
                            <button class="btn-add" onclick="addUsage('${key}', '${cfg.input_unit}')">Add Usage</button>
                            <button class="btn-reset" onclick="reset('${key}')">Empty/Reset</button>
                        </div>
                    `;
                    container.appendChild(div);
                });
            } catch (e) { console.error(e); }
        }

        async function addUsage(target, unit) {
            const amt = prompt(`Enter ${unit} used today:`);
            if (amt) {
                await fetch('/api/maintenance', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ action: 'add_usage', target: target, amount: amt, date: new Date().toISOString().split('T')[0] })
                });
                load();
            }
        }

        async function reset(target) {
            let msg = `Reset ${CONFIG[target].label} to full capacity?`;
            if (CONFIG[target].type === 'smart') {
                msg = "⚠️ TANK EMPTY?\\n\\nThis will calculate your actual burn rate based on hours used and the tank size.\\n\\nClick OK if the tank is actually empty/swapped.";
            }
            if (confirm(msg)) {
                await fetch('/api/maintenance', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ action: 'reset', target: target, date: new Date().toISOString().split('T')[0] })
                });
                load();
            }
        }

        async function editCap(target) {
            const newCap = prompt(`Enter NEW Total Capacity for ${CONFIG[target].label} (${CONFIG[target].unit}):`);
            if (newCap) {
                await fetch('/api/maintenance', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ action: 'set_capacity', target: target, amount: newCap })
                });
                load();
            }
        }
        load();
    </script>
</body>
</html>
"""

AUDIT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Law Brewing | Audit Log</title>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Roboto:wght@300;400&display=swap" rel="stylesheet">
    <style>
        body { background: #121212; color: #fff; font-family: 'Roboto', sans-serif; padding: 20px; }
        h1 { font-family: 'Oswald', sans-serif; color: #ffb400; text-align: center; }
        .table-container { max-width: 1000px; margin: 0 auto; background: #1e1e1e; border-radius: 10px; overflow: hidden; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 15px; text-align: left; border-bottom: 1px solid #333; }
        th { background: #222; color: #ffb400; text-transform: uppercase; }
        tr:hover { background: #2a2a2a; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
        .badge-active { background: #2e7d32; color: #fff; }
        .badge-update { background: #1565c0; color: #fff; }
        .badge-ignore { background: #444; color: #888; }
        .filters { text-align: center; margin-bottom: 20px; }
        select { background: #333; color: #fff; border: 1px solid #555; padding: 8px; border-radius: 4px; }
        .back-link { display: block; text-align: center; margin-top: 20px; color: #666; text-decoration: none; }
        .back-link:hover { color: #ffb400; }
    </style>
</head>
<body>
    <h1>📜 POUR AUDIT LOG</h1>
    <div class="filters">
        <label>Filter by Tap: </label>
        <select id="tapFilter" onchange="filter()">
            <option value="ALL">All Taps</option>
            {% for u in unique %}<option value="{{ u }}">{{ u }}</option>{% endfor %}
        </select>
    </div>
    <div class="table-container">
        <table id="logTable">
            <thead><tr><th>Time</th><th>Tap</th><th>Value</th><th>Event Type</th><th>Status</th></tr></thead>
            <tbody>
                {% for log in logs %}
                <tr class="log-row" data-tap="{{ log.tap }}">
                    <td>{{ log.time }}</td>
                    <td>{{ log.tap }}</td>
                    <td>{{ log.value }}</td>
                    <td>{{ log.type }}</td>
                    <td>{{ log.status_html|safe }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <a href="/" class="back-link">← Back to Dashboard</a>
    <script>
        function filter() {
            const val = document.getElementById('tapFilter').value;
            document.querySelectorAll('.log-row').forEach(row => {
                row.style.display = (val === 'ALL' || row.dataset.tap === val) ? '' : 'none';
            });
        }
    </script>
</body>
</html>
"""

STATS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Law Brewing | Analytics</title>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Roboto:wght@300;400&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { --accent: #ffb400; --bg: #121212; --card: #1e1e1e; --text: #ffffff; }
        body { background: var(--bg); color: var(--text); font-family: 'Roboto', sans-serif; padding: 20px; }
        h1, h2 { font-family: 'Oswald', sans-serif; color: var(--accent); text-transform: uppercase; letter-spacing: 1px; }
        .container { max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: 1fr; gap: 30px; }
        .card { background: var(--card); border: 1px solid #333; border-radius: 15px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        .heatmap-grid { display: grid; grid-template-columns: 40px repeat(24, 1fr); gap: 2px; margin-top: 20px; overflow-x: auto; }
        .day-label { font-size: 0.8rem; color: #888; align-self: center; }
        .hour-label { font-size: 0.7rem; color: #666; text-align: center; margin-bottom: 5px; }
        .heat-cell { aspect-ratio: 1; border-radius: 2px; background: #333; transition: 0.2s; }
        .heat-cell:hover { transform: scale(1.5); border: 1px solid #fff; z-index: 10; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th { text-align: left; color: #888; border-bottom: 1px solid #444; padding: 10px; font-size: 0.9rem; }
        td { padding: 12px 10px; border-bottom: 1px solid #333; font-weight: bold; }
        tr:first-child td { color: var(--accent); font-size: 1.1rem; }
        .back-link { display: block; margin: 30px auto; text-align: center; color: #666; text-decoration: none; border: 1px solid #333; padding: 10px; width: 200px; border-radius: 5px; }
        .back-link:hover { color: var(--accent); border-color: var(--accent); }
    </style>
</head>
<body>
    <h1 style="text-align:center; font-size: 2.5rem;">📊 Taproom Analytics</h1>
    <div class="container">
        <div class="card">
            <h2>🔥 Thirsty Hours (Activity Heatmap)</h2>
            <div id="heatmap" class="heatmap-grid">Loading...</div>
        </div>
        <div class="card">
            <h2>🍺 Pour Distribution</h2>
            <div style="height: 300px;"><canvas id="distChart"></canvas></div>
            <div id="chart-err" style="display:none; text-align:center; color:#666; padding:20px;">Chart Offline</div>
        </div>
        <div class="card">
            <h2>⚰️ The Graveyard (Keg History)</h2>
            <table id="graveyard">
                <thead><tr><th>Beer</th><th>Dates</th><th>Total Vol</th><th>Efficiency</th></tr></thead>
                <tbody><tr><td colspan="4">Loading data...</td></tr></tbody>
            </table>
        </div>
    </div>
    <a href="/" class="back-link">← Back to Dashboard</a>
    <script>
        const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                
                // RENDER HEATMAP
                const hm = document.getElementById('heatmap');
                hm.innerHTML = '<div class="day-label"></div>';
                for(let i=0; i<24; i++) hm.innerHTML += `<div class="hour-label">${i}</div>`;
                data.heatmap.forEach((row, dayIdx) => {
                    hm.innerHTML += `<div class="day-label">${DAYS[dayIdx]}</div>`;
                    row.forEach(val => {
                        const alpha = val > 0 ? Math.min(1.0, 0.2 + (val / (data.max_hourly_pours||1))) : 0.05;
                        const color = val > 0 ? `rgba(255, 180, 0, ${alpha})` : '#222';
                        hm.innerHTML += `<div class="heat-cell" style="background:${color}" title="${DAYS[dayIdx]} @ ${val} pours"></div>`;
                    });
                });

                // RENDER DISTRIBUTION (With Safety Check)
                if (typeof Chart !== 'undefined') {
                    new Chart(document.getElementById('distChart'), {
                        type: 'bar',
                        data: {
                            labels: ['Taster', 'Short', 'Pint', 'Crowler', 'Growler'],
                            datasets: [{
                                label: 'Pours', data: data.distribution, backgroundColor: '#ffb400', borderRadius: 5
                            }]
                        },
                        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { grid: { color: '#333' } }, x: { grid: { display: false } } } }
                    });
                } else {
                    document.getElementById('distChart').style.display = 'none';
                    document.getElementById('chart-err').style.display = 'block';
                }

                // RENDER GRAVEYARD
                const gy = document.getElementById('graveyard').querySelector('tbody');
                gy.innerHTML = '';
                if(data.graveyard.length === 0) {
                    gy.innerHTML = '<tr><td colspan="4" style="text-align:center;">No kegs archived yet.</td></tr>';
                } else {
                    data.graveyard.forEach(k => {
                        gy.innerHTML += `
                            <tr>
                                <td>${k.beer}</td>
                                <td style="font-size:0.85rem; color:#888;">${k.start_date} → ${k.end_date}</td>
                                <td>${k.total_pints} pts</td>
                                <td>${k.pints_per_day} /day</td>
                            </tr>`;
                    });
                }
            } catch (e) { console.error(e); }
        }
        loadStats();
    </script>
</body>
</html>
"""

# Load initial weights
current_weights = load_json(WEIGHTS_FILE, {})

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/maintenance')
def maintenance():
    return render_template_string(MAINTENANCE_HTML)

@app.route('/api/maintenance', methods=['GET', 'POST'])
def api_maint():
    d = load_json(MAINTENANCE_FILE, {})
    if 'water' not in d: d['water'] = {"used":0, "capacity":5000, "logs":[]}
    if 'propane' not in d: d['propane'] = {"used_hours": 0, "capacity": 20, "burn_rate": 1.5, "logs": []}

    if request.method == 'POST':
        try:
            r = request.json
            act = r.get('action'); tgt = r.get('target')
            if act == 'add_usage':
                amt = float(r.get('amount'))
                if tgt == 'propane':
                    d[tgt]['used_hours'] = d[tgt].get('used_hours', 0) + amt
                    d[tgt]['logs'].insert(0, {"date": r.get('date'), "hours": amt, "type": "usage"})
                else:
                    d[tgt]['used'] += amt
                    d[tgt]['logs'].insert(0, {"date": r.get('date'), "amount": amt, "type": "usage"})
            elif act == 'reset':
                if tgt == 'propane':
                    total_hrs = d[tgt].get('used_hours', 1)
                    cap = d[tgt]['capacity']
                    if total_hrs > 0:
                        new_rate = cap / total_hrs
                        if 0.1 < new_rate < 5.0: d[tgt]['burn_rate'] = new_rate
                    d[tgt]['used_hours'] = 0
                    d[tgt]['logs'].insert(0, {"date": r.get('date'), "old_hours": total_hrs, "new_rate": d[tgt]['burn_rate'], "type": "reset"})
                else:
                    d[tgt]['used'] = 0
                    d[tgt]['logs'].insert(0, {"date": r.get('date'), "amount": 0, "type": "reset"})
            elif act == 'set_capacity':
                d[tgt]['capacity'] = float(r.get('amount'))
            save_json(MAINTENANCE_FILE, d)
        except: return jsonify({"status": "error"}), 400
        return jsonify({"status": "success"})
    return jsonify(d)

@app.route('/data')
def get_data():
    try:
        weights = load_json(WEIGHTS_FILE, {})
        gdata = {}
        # Fetch Beer Data on Demand for Website (Shared Logic)
        try:
            ctx = ssl.create_default_context();
            ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
            r = urllib.request.urlopen(SHEET_URL, context=ctx, timeout=2)
            reader = csv.reader(io.StringIO(r.read().decode('utf-8')))
            next(reader)
            for row in reader:
                if len(row) > 6:
                    t = None; rid = row[0].lower()
                    if "law" in rid or "1" in rid: t = "Law Tap"
                    elif "wisco" in rid or "2" in rid: t = "Wisco Tap"
                    elif "nitro" in rid or "3" in rid: t = "Nitro Tap"
                    if t: gdata[t] = {"beer": row[2], "style": row[6], "image": row[4]}
        except: pass

        s = load_json(SESSIONS_FILE, {t: {"start_date": datetime.now().strftime('%Y-%m-%d'), "start_pct": 100} for t in TAPS})
        meta = {}
        now = time.time()
        for tap in TAPS:
            p_msg = weights.get(f"{tap}_last_pour", "")
            try:
                # UPDATED: WIPE AFTER 6 HOURS (21600s)
                if (now - float(weights.get(f"{tap}_pour_ts", 0))) > 21600: p_msg = ""
            except: pass
            weights[f"{tap}_last_pour"] = p_msg
            ts = s.get(tap, {}); info = gdata.get(tap, {"beer": "Unknown", "style": "", "image": ""})
            raw_date = ts.get('start_date', datetime.now().strftime('%Y-%m-%d'))
            try: start_date = datetime.strptime(raw_date, '%Y-%m-%d')
            except: start_date = datetime.now()
            days = (datetime.now() - start_date).days
            try: w_pct = float(weights.get(tap, 0))
            except: w_pct = 0
            try: s_pct = float(ts.get('start_pct', 100))
            except: s_pct = 100
            used = (max(0, s_pct - w_pct) / 100.0) * 40.0
            rate = round(used / max(1, days), 1)
            kick = "TBD"
            if rate > 0.05:
                try: kick = (datetime.now() + timedelta(days=((w_pct/100.0)*40.0)/rate)).strftime("%a, %b %d")
                except: pass
            meta[tap] = {"beer": info.get('beer', 'Unknown'), "style": info.get('style', ''), "image": info.get('image', ''), "days_on_tap": days, "pints_per_day": rate, "kick_date": kick, "start_date": raw_date}

        response = jsonify({"taps": TAPS, "weights": weights, "meta": meta})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    except: return jsonify({"error": "Data Error"}), 500

@app.route('/history')
def get_history(): return jsonify(load_json(HISTORY_FILE, []))

# --- UPDATED SET DATE ROUTE ---
@app.route('/set_date', methods=['POST'])
def set_date():
    try:
        r = request.json
        tap_name = r.get('tap')
        new_date = r.get('date')
        old_beer_name = r.get('old_beer_name') # The name captured from the UI

        # 1. ARCHIVE THE OLD KEG WITH THE CONFIRMED NAME
        archive_current_keg(tap_name, manual_name=old_beer_name)

        # 2. START THE NEW SESSION
        s = load_json(SESSIONS_FILE, {})
        if tap_name not in s: s[tap_name] = {}
        s[tap_name]['start_date'] = new_date
        
        try:
            s[tap_name]['start_pct'] = float(current_weights.get(tap_name, 100))
        except:
            s[tap_name]['start_pct'] = 100

        save_json(SESSIONS_FILE, s)
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Set Date Error: {e}")
        return jsonify({"status": "error"}), 400

@app.route('/admin/audit')
def view_audit():
    logs = []
    try:
        if os.path.exists(AUDIT_FILE):
            with open(AUDIT_FILE, 'r') as f:
                lines = f.readlines(); raw = list(csv.reader(lines)); raw.reverse()
                for r in raw:
                    if len(r) < 3: continue
                    val = 0
                    try: val = float(r[2].replace('%','').replace(' pts',''))
                    except: val = 0
                    tag = '<span class="badge badge-ignore">SMALL</span>'
                    evt = r[3] if len(r)>3 else "POUR"
                    if "POUR" in evt and val >= 4.75: tag = '<span class="badge badge-active">POUR</span>'
                    elif "UPDATE" in evt: tag = '<span class="badge badge-update">UPDATE</span>'
                    logs.append({"time": r[0], "tap": r[1], "value": r[2], "type": evt, "status_html": tag})
    except: pass
    unique = sorted(list(set(l['tap'] for l in logs)))
    return render_template_string(AUDIT_HTML, logs=logs, unique=unique)

# ==========================================
#  ANALYTICS ENGINE (FINAL PRODUCTION)
# ==========================================
def calculate_analytics():
    import os, json, math
    from datetime import datetime

    # 1. Defaults (Safe Empty State)
    heatmap = [[0]*24 for _ in range(7)]
    dist = [0, 0, 0, 0, 0]
    graveyard = []
    max_hourly = 1
    
    # 2. Paths
    audit_path = "/home/lawmj04/law-brewing/pour_audit.csv"
    history_path = "/home/lawmj04/law-brewing/keg_history.json"

    # --- PART 1: AUDIT LOG ---
    if os.path.exists(audit_path):
        try:
            with open(audit_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    try:
                        # Manual Split (Safer than CSV reader)
                        parts = line.split(',')
                        
                        # Fix 1: Ensure line has enough columns
                        if len(parts) < 4: continue 
                        
                        # Fix 2: ONLY process 'POUR' events. Ignore 'UPDATE'.
                        # This skips the lines with "10.7%" entirely.
                        event_type = parts[3].strip()
                        if "POUR" not in event_type: continue 

                        # Fix 3: Clean the volume string aggressively
                        # Removes 'pts', 'oz', and '%' just in case
                        raw_vol = parts[2].lower().replace('pts','').replace('oz','').replace('%','').strip()
                        if not raw_vol: continue
                        oz = float(raw_vol)

                        # Fix 4: Filter Infinity/NaN/Negative
                        if math.isnan(oz) or math.isinf(oz) or oz < 0 or oz > 130: continue

                        if oz > 6.0:
                            # Parse Date
                            dt_str = parts[0].strip()
                            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                            
                            # Heatmap
                            heatmap[dt.weekday()][dt.hour] += 1
                            if heatmap[dt.weekday()][dt.hour] > max_hourly:
                                max_hourly = heatmap[dt.weekday()][dt.hour]
                            
                            # Distribution
                            if oz < 6.5: dist[0] += 1
                            elif oz < 11.0: dist[1] += 1
                            elif oz < 24.0: dist[2] += 1
                            elif oz < 45.0: dist[3] += 1
                            else: dist[4] += 1
                    except: continue 
        except Exception as e:
            print(f"Log Error: {e}")

    # --- PART 2: GRAVEYARD ---
    # Fix 5: STRICT check for file existence
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r') as f:
                raw_gy = json.load(f)
                if isinstance(raw_gy, list):
                    for k in raw_gy:
                        try:
                            # Safely parse dates
                            s_date = str(k.get('start_date', '-'))
                            e_date = str(k.get('end_date', '-'))
                            beer = str(k.get('beer', 'Unknown'))
                            
                            try:
                                s = datetime.strptime(s_date, '%Y-%m-%d')
                                e = datetime.strptime(e_date, '%Y-%m-%d')
                                days = max(1, (e - s).days)
                            except: days = 1
                            
                            try:
                                gals = float(k.get('start_gallons', 5))
                                total_pts = int(gals * 8)
                            except: total_pts = 0
                            
                            graveyard.append({
                                "beer": beer,
                                "start_date": s_date,
                                "end_date": e_date,
                                "total_pints": total_pts,
                                "pints_per_day": round(total_pts / days, 1)
                            })
                        except: pass
        except: pass

    return {
        "heatmap": heatmap,
        "distribution": dist,
        "max_hourly_pours": max_hourly,
        "graveyard": graveyard,
        "status": "ok"
    }

# --- ROUTES ---
@app.route('/stats')
def view_stats():
    return render_template_string(STATS_HTML)

@app.route('/api/stats')
def api_stats():
    import json
    try:
        data = calculate_analytics()
        # default=str handles any leftover Date objects that Flask can't handle
        json_str = json.dumps(data, default=str)
        return app.response_class(response=json_str, status=200, mimetype='application/json')
    except Exception as e:
        # If it crashes, return the error as text so we can see it
        return app.response_class(
            response=json.dumps({"status": "error", "message": str(e)}),
            status=200,
            mimetype='application/json'
        )

def run_flask(): app.run(host='0.0.0.0', port=80, debug=False, use_reloader=False)

def handle_scale_connection(conn, addr):
    ip = addr[0]
    conn.settimeout(35.0) 
    print(f"🔌 Scale Connected: {ip}")

    try:
        while True:
            header = conn.recv(5)
            if not header: 
                print(f"❌ Scale {ip} closed connection gracefully.")
                break

            cmd, msg_id, length = struct.unpack('!BHH', header)
            
            if length > 0:
                data = conn.recv(length).decode('utf-8', errors='ignore')
            else:
                data = ""

            # --- BLYNK PROTOCOL ROUTING ---
            if cmd == 2 or len(data) == 32:
                conn.sendall(struct.pack('!BHH', 0, msg_id, 200))
                continue
            
            if cmd == 6 or length == 0:
                conn.sendall(struct.pack('!BHH', 0, msg_id, 200))
                continue

            # Clean the string so we can actually search it properly!
            safe_print = data.replace('\x00', '.')
            if "vw.51" in safe_print or "vw.69" in safe_print:
                print(f"Scale Data | IP: {ip} | {safe_print}")

            if ip in TAP_CONFIG:
                name = TAP_CONFIG[ip]['name']; conf = TAP_CONFIG[ip]

                # --- WEIGHT LOGIC (VW.51) ---
                # FIX: Search safe_print instead of raw data
                match = re.search(r"vw\.51\.(\d+\.?\d*)", safe_print)
                if match:
                    try:
                        raw = float(match.group(1))
                        if 0.1 <= raw < 100: raw *= 1000
                        
                        if name not in readings_history:
                            readings_history[name] = deque(maxlen=10)
                        readings_history[name].append(raw)

                        val = sum(readings_history[name]) / len(readings_history[name])
                        pct = max(0, min(100, round(((val - conf['empty']) / (conf['full'] - conf['empty'])) * 100, 1)))
                        old_pct = float(current_weights.get(name, pct))

                        if old_pct != pct:
                            current_weights[name] = pct
                            current_weights[f"{name}_updated"] = time.strftime("%-I:%M %p")

                            if pct < old_pct:
                                log_event(name, f"{pct}%", "UPDATE")
                                if abs(old_pct - pct) >= GIT_TRIGGER_PCT:
                                    current_weights[name] = pct
                                    save_json(WEIGHTS_FILE, current_weights)
                            else:
                                log_event(name, f"{pct}%", "BASELINE_ADJUST")
                                if abs(pct - old_pct) >= GIT_TRIGGER_PCT:
                                    save_json(WEIGHTS_FILE, current_weights)

                        if name not in pour_start_weights:
                            pour_start_weights[name] = val
                            is_pouring[name] = False

                        if not is_pouring[name]:
                            if abs(pour_start_weights[name] - val) > MOTION_SENSITIVITY:
                                is_pouring[name] = True
                                pour_start_times[name] = time.time()
                            else:
                                pour_start_weights[name] = val
                        else:
                            current_pour_dur = time.time() - pour_start_times.get(name, time.time())
                            if current_pour_dur > LEAK_FLOW_MAX_SEC:
                                is_pouring[name] = False
                                pour_start_weights[name] = val
                            elif (max(readings_history[name]) - min(readings_history[name])) < MOTION_SENSITIVITY:
                                dur = max(1, time.time() - pour_start_times.get(name, time.time()))
                                oz = (pour_start_weights[name] - val) / 29.57

                                if dur > LEAK_FLOW_MAX_SEC and oz < 3.0:
                                    is_pouring[name] = False
                                    pour_start_weights[name] = val
                                elif abs(oz) < 1.0: 
                                    is_pouring[name] = False
                                    pour_start_weights[name] = val
                                elif (oz/dur) <= MAX_FLOW_RATE:
                                    if oz > AUDIT_TRIGGER: log_event(name, f"{oz:.2f} oz", "POUR")
                                    if oz > POUR_TRIGGER:
                                        p_name = get_pour_name(oz)
                                        if p_name:
                                            current_weights[f"{name}_last_pour"] = f"{p_name} ({oz:.1f}oz)"
                                            current_weights[f"{name}_pour_ts"] = time.time()
                                    
                                    is_pouring[name] = False
                                    pour_start_weights[name] = val
                                    current_weights["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
                                    save_json(WEIGHTS_FILE, current_weights)
                    except Exception as e:
                        # Unmasking errors so they don't hide anymore
                        print(f"⚠️ Weight Logic Error: {e}")

                # --- TEMP LOGIC (VW.69) ---
                # FIX: Search safe_print AND allow negative numbers (-?)
                match_t = re.search(r"vw\.69\.(-?\d+\.?\d*)", safe_print)
                if match_t:
                    try:
                        f = round((float(match_t.group(1)) * 1.8) + 32, 1)
                        try: old_t = float(current_weights.get(f"{name}_temp", 0))
                        except: old_t = 0
                        
                        if abs(f - old_t) > 0.5:
                            current_weights[f"{name}_temp"] = f
                            save_json(WEIGHTS_FILE, current_weights)
                            
                        limit = TEMP_LIMIT_NITRO if NITRO_IP_SUFFIX in ip else TEMP_LIMIT_STD
                        if f > limit:
                            a_key = f"temp_{ip}"
                            if (time.time() - safety_cooldowns.get(a_key, 0)) > ALERT_COOLDOWN:
                                send_discord(f"🔥 TEMP ALERT: {name} is {f}°F")
                                safety_cooldowns[a_key] = time.time()
                    except Exception as e:
                        print(f"⚠️ Temp Logic Error: {e}")

    except Exception as e:
        print(f"⚠️ Scale {ip} dropped: {e}")
    finally:
        try: conn.close()
        except: pass

def start_brain():
    # 1. SETUP SOCKET
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # 2. RETRY LOGIC
    bound = False
    for i in range(15):
        try:
            sock.bind(('0.0.0.0', 1234))
            bound = True
            break
        except OSError:
            print(f"⚠️ Port 1234 busy, waiting 2s...", flush=True)
            time.sleep(2)

    if not bound:
        print("❌ CRITICAL: Could not bind port 1234. Exiting.", flush=True)
        return

    sock.listen(10)
    print(f"🧠 Brain Online (Port 1234)", flush=True)

    # 3. MAIN LOOP - MULTITHREADED
    while True:
        try:
            conn, addr = sock.accept()
            # Spin up a dedicated background thread for every scale that connects
            threading.Thread(target=handle_scale_connection, args=(conn, addr), daemon=True).start()
        except Exception as e:
            time.sleep(1)

# ================= STARTUP =================
if __name__ == "__main__":
    current_weights.update(load_json(WEIGHTS_FILE, {}))
    
    # --- ADD THIS LINE BACK TO START THE HEARTBEAT ---
    threading.Thread(target=history_loop, daemon=True).start()
    
    brain_thread = threading.Thread(target=start_brain, daemon=True)
    brain_thread.start()
    print("🚀 Law Brewing Brain & Dashboard Starting...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
