from flask import Flask, render_template, request, flash, redirect, url_for
import requests
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "law_brewing_secure_key"

# CONFIGURATION
WEBHOOK_URL = "https://discord.com/api/webhooks/1457116112201322772/8Kl-UmwdO0bUPN-51ZdjVMzxa7823TEd1znJNgRAL-eRHsA8UAwONornmo9OW4r1JmFN"

def send_discord_update(title, message, update_type="Info"):
    colors = {"Info": 3447003, "Success": 5763719, "Alert": 15548997}
    data = {
        "username": "Law Brewing Admin",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": title, "description": message,
            "color": colors.get(update_type, 3447003),
            "footer": {"text": f"Sent via Dashboard • {datetime.now().strftime('%H:%M')}"}
        }]
    }
    try:
        requests.post(WEBHOOK_URL, json=data)
        return True
    except:
        return False

@app.route('/', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        update_type = request.form.get('type')
        if title and content:
            send_discord_update(title, content, update_type)
            flash("Update sent!", "success")
        else:
            flash("Missing info.", "error")
        return redirect(url_for('dashboard'))
    return render_template('index.html')

if __name__ == '__main__':
    # Running on port 5000 so it doesn't hit the main site
    app.run(host='0.0.0.0', port=5000)
