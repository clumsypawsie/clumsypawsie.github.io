from flask import Flask, render_template_string, request, redirect, url_for, session
from collections import deque
from itertools import groupby
from datetime import datetime
import numpy as np # Import numpy for numerical operations

app = Flask(__name__)
app.secret_key = "mask_math_so_secret"

# ---------- CONFIG ----------
app.config.update({
    "START_RGB": (241, 219, 29),  # base pixel (used for the finder/visualizer)
    "ADD_VALUE": 32,              # + for the dyed channel
    "SUB_VALUE": 16,              # - for the other channels (and for black on all)
    "MAX_DEPTH": 48               # search depth for sequence finder
})

DYES = ["red", "green", "blue", "black"]

# ---------- MASK MATH ----------
def clamp255(x):
    return max(0, min(255, x))

def dye_vector(dye, add_val, sub_val):
    if dye == "red":
        return [add_val, -sub_val, -sub_val]
    elif dye == "green":
        return [-sub_val, add_val, -sub_val]
    elif dye == "blue":
        return [-sub_val, -sub_val, add_val]
    elif dye == "black":
        return [0, 0, 0]  # Consistent with other black implementations
    raise ValueError("unknown dye")

def apply_dye_to_mask(mask, dye):
    add_val = app.config["ADD_VALUE"]
    sub_val = app.config["SUB_VALUE"]
    dv = dye_vector(dye, add_val, sub_val)
    mask = tuple(clamp255(mask_val + dv_val) for mask_val, dv_val in zip(mask, dv))
    return mask

def apply_mask_to_color(base_rgb, mask):
    # Apply mask to base_rgb (which is a tuple/list of [R, G, B])
    r, g, b = base_rgb
    mr, mg, mb = [clamp255(int(m * 255)) for m in mask]
    return (clamp255(r * mr / 255), clamp255(g * mg / 255), clamp255(b * mb / 255))

def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])

# ---------- SAVE/LOAD RGB AND SEARCH (BFS over MASK space) ----------
def save_current_to_session(result):
    """Saves the current state (target, result, session RGB) to the user's session."""
    session["current"] = result
    session["start_rgb"] = result["final_mask"]  # Save the final mask as the new start RGB

def load_from_session():
    """Loads the 'current' and 'start_rgb' from the session, or defaults."""
    result = session.get("current")
    start_rgb = session.get("start_rgb", app.config["START_RGB"]) # Default to global config
    return result, start_rgb

def find_sequence_to_target(target_rgb, start_rgb, max_depth=app.config["MAX_DEPTH"]):
    """Searches for a sequence of dye applications to transform start_rgb to target_rgb."""
    # Convert tuples to numpy arrays for easier calculations
    start_rgb_np = np.array(start_rgb, dtype=np.uint8)
    target_rgb_np = np.array(target_rgb, dtype=np.uint8)
    mask_start = np.array([255, 255, 255], dtype=np.uint8)
    mask_target = np.array([0, 0, 0], dtype=np.uint8)  # Black as a target mask

    q = deque([(mask_start, [])])  # Queue of (current_mask, sequence)
    visited = {tuple(mask_start)}
    best_mask, best_seq = mask_start, []
    best_color = start_rgb
    best_diff = manhattan(best_color, target_rgb)

    while q:
        mask, seq = q.popleft()
        if len(seq) > max_depth:
            continue
        color = apply_mask_to_color(start_rgb, mask)
        diff = manhattan(color, target_rgb)
        if diff < best_diff:
            best_diff = diff
            best_mask = mask
            best_seq = seq
            best_color = color
            if best_diff == 0:
                break
        for dye in DYES:
            next_mask = apply_dye_to_mask(mask, dye)
            if tuple(next_mask) not in visited:
                visited.add(tuple(next_mask))
                q.append((next_mask, seq + [dye]))

    # Convert back to tuple for return
    best_mask = tuple(best_mask)
    best_color = tuple(best_color)

    return best_seq, best_mask, best_color, best_diff

# ---------- PRESET MANAGEMENT ----------
def get_presets():
    """Gets the list of saved base RGBs from the session."""
    return session.get("base_rgbs", [])

def save_preset(name, r, g, b):
    """Saves a new base RGB preset to the session."""
    presets = session.get("base_rgbs", [])
    presets.append({"name": name, "rgb": (r, g, b)})
    session["base_rgbs"] = presets

def load_preset(name):
    """Loads a base RGB from the session, or None if not found."""
    presets = session.get("base_rgbs", [])
    for preset in presets:
        if preset["name"] == name:
            return preset["rgb"]
    return None

@app.before_request
def sync_start_rgb_from_session():
    """Ensures the app uses the user's last-saved START_RGB for all routes."""
    s = session.get("start_rgb")
    if isinstance(s, (list, tuple)) and len(s) == 3:
        try:
            app.config["START_RGB"] = (int(s[0]), int(s[1]), int(s[2]))
        except Exception:
            pass

@app.after_request
def add_header(response):
    """Adds the saved RGB to the header for the visualizer."""
    start_rgb = session.get("start_rgb", app.config["START_RGB"])
    response.headers['My-Color'] = f"rgb({start_rgb[0]},{start_rgb[1]},{start_rgb[2]})"
    return response

# ---------- TEMPLATES ----------
BASE_CSS = """
html, body{margin:0;padding:0}
body{
    font-family: 'Rubik', sans-serif;
    font-size: 20px;
    margin: 40px;
    color: #fff;
}
.card{
    background-color: rgba(0,0,0,.55);
    padding: 20px;
    border-radius: 12px;
    margin-top: 20px;
    border: 1px solid rgba(255,255,255,.15);
    box-shadow: 0 8px 30px rgba(0,0,0,.35);
}
label{display:inline-block;width:160px}
input[type=number]{width:110px;font-size:20px}
input[type=submit], button, select{
    font-size: 22px;
    padding: 10px 18px;
    cursor: pointer;
    border-radius: 10px;
    background: rgba(255,255,255,.1);
    border: 1px solid rgba(255,255,255,.25);
    color: #fff;
}
input[type=submit]:hover, button:hover{
    background: rgba(255,255,255,.18);
}
.sequence{font-size:24px;margin-top:10px}
.swatch{display:inline-block;width:50px;height:50px;border:1px solid #fff;margin-left:8px;vertical-align:middle}
.nav{margin-top:16px;font-size:22px}
.row{margin-top:8px}
a{color:#fff;text-decoration:underline}
"""

MAIN_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Dye Doxxer</title>
    <link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        {{ base_css }}
        html, body { height: 100%; }
        body {
            background-image: url('{{ url_for("static", filename="background.png") }}');
            background-repeat: no-repeat;
            background-position: center center;
            background-attachment: fixed;
            background-size: cover;
            text-shadow: 0 1px 1px rgba(0,0,0,.6);
        }
        h2, h3{letter-spacing:.5px}
        /* Optional: make the result canvas pop a bit */
        #visual{
            box-shadow: 0 6px 20px rgba(0,0,0,.35);
            border-radius: 10px;
        }
    </style>
    <link rel="icon" href="{{ url_for('static', filename='favicon.png') }}">
</head>
<body>
    <div class="card">
        <h2>Dye Doxxer</h2>
        <div class="row">
            <img src="/static/dye_red.png" alt="Red" style="width:80px;height:80px;margin-right:8px">
            <img src="/static/dye_green.png" alt="Green" style="width:80px;height:80px;margin-right:8px">
            <img src="/static/dye_blue.png" alt="Blue" style="width:80px;height:80px;margin-right:8px">
            <img src="/static/dye_black.png" alt="Black" style="width:80px;height:80px;margin-right:8px">
        </div>
        <form method="post" class="card">
            <div class="row"><label>Target R (0–255):</label><input type="number" name="r" min="0" max="255" required></div>
            <div class="row"><label>Target G (0–255):</label><input type="number" name="g" min="0" max="255" required></div>
            <div class="row"><label>Target B (0–255):</label><input type="number" name="b" min="0" max="255" required></div>
            <div class="row">
                <input type="submit" name="action" value="Find Sequence">
                <input type="submit" name="action" value="Save">
            </div>
        </form>
        {% if result %}
        <div class="card">
            <h3>Result</h3>
            <p class="sequence"><strong>Sequence:</strong> {{ result.sequence|safe }}</p>
            <p><strong>Final Color:</strong> {{ result.final_color }}
                <span class="swatch" style="background:rgb({{ result.final_color[0] }},{{ result.final_color[1] }},{{ result.final_color[2] }});"></span>
            </p>
            <p><strong>Target:</strong> {{ result.target }}
                <span class="swatch" style="background:rgb({{ result.target[0] }},{{ result.target[1] }},{{ result.target[2] }});"></span>
            </p>
            <p><strong>Final Mask:</strong> {{ result.final_mask }}</p>
            <p><strong>Difference:</strong> {{ result.diff }}</p>
            <button id="play">Play Sequence</button>
            <canvas id="visual" width="300" height="100" style="border:2px solid #fff;margin-top:10px"></canvas>
        </div>
        <script>
            (function(){
                const playBtn = document.getElementById('play');
                if(!playBtn) return;
                const steps = {{ result.raw_steps|tojson }};
                const startRGB = [{{ start_rgb[0] }}, {{ start_rgb[1] }}, {{ start_rgb[2] }}];
                const addVal = {{ add_value }};
                const subVal = {{ sub_value }};
                function dv(name){
                    if(name==='red')   return [ addVal, -subVal, -subVal];
                    if(name==='green') return [-subVal,  addVal, -subVal];
                    if(name==='blue')  return [-subVal, -subVal,  addVal];
                    if(name==='black') return [-32, -32, -32]; // Match Python change
                    return [0,0,0];
                }
                function clamp255(x){ return Math.max(0, Math.min(255, x)); }
                function applyMaskToColor(rgb, mask){
                    return [
                        Math.round(clamp255(rgb[0] * mask[0] / 255)),
                        Math.round(clamp255(rgb[1] * mask[1] / 255)),
                        Math.round(clamp255(rgb[2] * mask[2] / 255)),
                    ];
                }
                const c = document.getElementById('visual');
                const ctx = c.getContext('2d');
                function paint(rgb){
                    ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
                    ctx.fillRect(0,0,c.width,c.height);
                }
                playBtn.addEventListener('click', ()=>{
                    let mask = [255,255,255];
                    let cur = applyMaskToColor(startRGB, mask);
                    paint(cur);
                    let i = 0;
                    const t = setInterval(()=>{
                        if(i>=steps.length){ clearInterval(t); return; }
                        const d = dv(steps[i++]);
                        mask = [clamp255(mask[0]+d[0]), clamp255(mask[1]+d[1]), clamp255(mask[2]+d[2])];
                        cur = applyMaskToColor(startRGB, mask);
                        paint(cur);
                    }, 420);
                });
            })();
        </script>
        {% endif %}
        <div class="nav">
            <a href="{{ url_for('saved') }}">Saved</a> |
            <a href="{{ url_for('history') }}">History</a> |
            <a href="{{ url_for('settings') }}">Settings</a>
        </div>
    </div>
</body>
</html>
"""

SAVED_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Dye Doxxer · Saved</title>
    <link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
    <style>{{ base_css }}</style>
    <style>
        html, body { height: 100%; }
        body{
            background-image: url('{{ url_for("static", filename="background.png") }}');
            background-repeat: no-repeat;
            background-position: center center;
            background-attachment: fixed;
            background-size: cover;
            text-shadow: 0 1px 1px rgba(0,0,0,.6);
        }
        h2{letter-spacing:.5px}
    </style>
</head>
<body>
    <div class="card">
        <h2>Saved</h2>
        {% if items %}
            {% for idx, it in items %}
                <div style="border-bottom:1px solid #fff;margin-bottom:14px;padding-bottom:10px">
                    <div class="sequence"><strong>Sequence:</strong> {{ it.sequence|safe }}</div>
                    <div><strong>Target:</strong> {{ it.target }}
                        <span class="swatch" style="background:rgb({{ it.target[0] }},{{ it.target[1] }},{{ it.target[2] }});"></span>
                    </div>
                    <div><strong>Final Color:</strong> {{ it.final_color }}
                        <span class="swatch" style="background:rgb({{ it.final_color[0] }},{{ it.final_color[1] }},{{ it.final_color[2] }});"></span>
                    </div>
                    <div><strong>Final Mask:</strong> {{ it.final_mask }}</div>
                    <div><strong>Diff:</strong> {{ it.diff }}</div>
                </div>
            {% endfor %}
        {% else %}
            <p style="opacity:.9;margin-top:8px">No saved items.</p>
        {% endif %}
        <div class="nav"><a href="{{ url_for('home') }}">Back</a></div>
    </div>
</body>
</html>
"""

HISTORY_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Dye Doxxer · History</title>
    <link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
    <style>{{ base_css }}</style>
    <style>
        html, body { height: 100%; }
        body{
            background-image: url('{{ url_for("static", filename="background.png") }}');
            background-repeat: no-repeat;
            background-position: center center;
            background-attachment: fixed;
            background-size: cover;
            text-shadow: 0 1px 1px rgba(0,0,0,.6);
        }
        h2{letter-spacing:.5px}
    </style>
</head>
<body>
    <div class="card">
        <h2>History (last 10)</h2>
        <form method="get" action="{{ url_for('history') }}">
            <label>Filter (e.g. 241,219,29):</label>
            <input type="text" name="q" style="font-size:18px" value="{{ request.args.get('q','') }}">
            <input type="submit" value="Apply">
        </form>
        {% if items %}
            {% for it in items %}
                <div style="border-bottom:1px solid #fff;margin-bottom:14px;padding-bottom:10px">
                    <div class="sequence"><strong>Sequence:</strong> {{ it.sequence|safe }}</div>
                    <div><strong>Target:</strong> {{ it.target }}
                        <span class="swatch" style="background:rgb({{ it.target[0] }},{{ it.target[1] }},{{ it.target[2] }});"></span>
                    </div>
                    <div><strong>Final Color:</strong> {{ it.final_color }}
                        <span class="swatch" style="background:rgb({{ it.final_color[0] }},{{ it.final_color[1] }},{{ it.final_color[2] }});"></span>
                    </div>
                    <div><strong>Final Mask:</strong> {{ it.final_mask }}</div>
                    <div><strong>Diff:</strong> {{ it.diff }}</div>
                </div>
            {% endfor %}
        {% else %}
            <p style="opacity:.9;margin-top:8px">No history yet.</p>
        {% endif %}
        <div class="nav"><a href="{{ url_for('home') }}">Back</a></div>
    </div>
</body>
</html>
"""

SETTINGS_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Dye Doxxer · Settings</title>
    <link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
    <style>{{ base_css }}</style>
    <style>
        html, body { height: 100%; }
        body{
            background-image: url('{{ url_for("static", filename="background.png") }}');
            background-repeat: no-repeat;
            background-position: center center;
            background-attachment: fixed;
            background-size: cover;
            text-shadow: 0 1px 1px rgba(0,0,0,.6);
        }
        h2{letter-spacing:.5px}
        .preset-row{display:flex;gap:10px;align-items:center;margin:8px 0}
        .pill{display:inline-block;padding:6px 10px;border:1px solid rgba(255,255,255,.25);border-radius:9999px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.25);color:#fff;cursor:pointer}
        .pill:hover{background:rgba(255,255,255,.18)}
        .sw{display:inline-block;width:20px;height:20px;border:1px solid #fff;border-radius:4px;margin-right:8px;vertical-align:middle}
    </style>
</head>
<body>
    <div class="card">
        <h2>Settings</h2>
        <form method="post">
            <div class="row"><strong>Start (base pixel S):</strong></div>
            <div class="row"><label>Start R:</label><input type="number" name="sr" min="0" max="255" value="{{ start[0] }}" required></div>
            <div class="row"><label>Start G:</label><input type="number" name="sg" min="0" max="255" value="{{ start[1] }}" required></div>
            <div class="row"><label>Start B:</label><input type="number" name="sb" min="0" max="255" value="{{ start[2] }}" required></div>
            <hr style="margin:12px 0;border-color:#777">
            <div class="row"><strong>Dye step
