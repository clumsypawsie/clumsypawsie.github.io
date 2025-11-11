from flask import Flask, render_template_string, request, redirect, url_for, session
from collections import deque
from itertools import groupby
from datetime import datetime

app = Flask(__name__)
app.secret_key = "mask_math_so_secret"

# ---------- CONFIG ----------
# You can tweak add/sub and starting color in Settings
app.config.update({
    "START_RGB": (241, 219, 29),  # base pixel (used for the finder/visualizer)
    "ADD_VALUE": 32,              # + for the dyed channel
    "SUB_VALUE": 16,              # - for the other channels (and for black on all)
    "MAX_DEPTH": 48               # search depth for sequence finder
})

DYES = ["red", "green", "blue", "black"]

# ---------- MASK MATH ----------
def clamp255(x): return max(0, min(255, x))

def dye_vector(dye, add_val, sub_val):
    if dye == "red":   return ( add_val, -sub_val, -sub_val)
    if dye == "green": return (-sub_val,  add_val, -sub_val)
    if dye == "blue":  return (-sub_val, -sub_val,  add_val)
    if dye == "black": return (-32, -32, -32)
    raise ValueError("unknown dye")

def apply_dye_to_mask(mask, dye):
    add_val = app.config["ADD_VALUE"]
    sub_val = app.config["SUB_VALUE"]
    dv = dye_vector(dye, add_val, sub_val)
    m = (clamp255(mask[0] + dv[0]),
         clamp255(mask[1] + dv[1]),
         clamp255(mask[2] + dv[2]))
    return m

def apply_mask_to_color(base_rgb, mask):
    # channel-wise: round( base * mask / 255 )
    r = int(round(base_rgb[0] * mask[0] / 255.0))
    g = int(round(base_rgb[1] * mask[1] / 255.0))
    b = int(round(base_rgb[2] * mask[2] / 255.0))
    return (clamp255(r), clamp255(g), clamp255(b))

def manhattan(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1]) + abs(a[2]-b[2])

# ---------- USE LAST-SAVED START_RGB PER USER (SESSION) ----------
@app.before_request
def _sync_start_rgb_from_session():
    """Ensure the app uses the user's last-saved START_RGB for all routes."""
    s = session.get("start_rgb")
    if isinstance(s, (list, tuple)) and len(s) == 3:
        try:
            app.config["START_RGB"] = (int(s[0]), int(s[1]), int(s[2]))
        except Exception:
            pass

# ---------- SEARCH (BFS over MASK space) ----------
# State = current MASK; color is derived by applying mask to START_RGB
def find_sequence_to_target(target_rgb, max_depth=None):
    if max_depth is None:
        max_depth = app.config["MAX_DEPTH"]

    start_mask = (255, 255, 255)
    start_rgb = app.config["START_RGB"]
    start_color = apply_mask_to_color(start_rgb, start_mask)

    q = deque([(start_mask, [])])
    visited = {start_mask}

    best_mask, best_seq = start_mask, []
    best_color = start_color
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
            nxt_mask = apply_dye_to_mask(mask, dye)
            if nxt_mask not in visited:
                visited.add(nxt_mask)
                q.append((nxt_mask, seq + [dye]))

    return best_seq, best_mask, best_color, best_diff

# ---------- PRESENTATION ----------
def pretty_sequence(seq):
    if not seq:
        return "No dyes applied"
    colors = {
        "red":   "#ff4d4d",
        "green": "#4dff4d",
        "blue":  "#4da6ff",
        "black": "#ffffff"
    }
    parts = []
    for token, grp in groupby(seq):
        n = len(list(grp))
        hexcol = colors.get(token, "#fff")
        style = (
            f"color:{hexcol}; font-size:22px; margin-right:12px;"
            "text-shadow:-1px -1px 0 #000,1px -1px 0 #000,"
            "-1px 1px 0 #000,1px 1px 0 #000;"
        )
        parts.append(f'<span style="{style}">{n}x {token}</span>')
    return " ".join(parts)

# ---------- TEMPLATES ----------
BASE_CSS = """
  html,body{margin:0;padding:0}
  body{
    font-family:'Rubik', sans-serif;
    font-size:20px;
    margin:40px;
    color:#fff;
  }
  .card{
    background-color:rgba(0,0,0,.55);
    padding:20px;
    border-radius:12px;
    margin-top:20px;
    display:inline-block;
    border:1px solid rgba(255,255,255,.15);
    box-shadow:0 8px 30px rgba(0,0,0,.35);
  }
  label{display:inline-block;width:160px}
  input[type=number]{width:110px;font-size:20px}
  input[type=submit],button,select{
    font-size:22px;padding:10px 18px;cursor:pointer;border-radius:10px;
    background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.25);
    color:#fff;
  }
  input[type=submit]:hover,button:hover{ background:rgba(255,255,255,.18) }
  .sequence{font-size:24px;margin-top:10px}
  .swatch{display:inline-block;width:50px;height:50px;border:1px solid #fff;margin-left:8px;vertical-align:middle}
  .nav{margin-top:16px;font-size:22px}
  .row{margin-top:8px}
  a{color:#fff;text-decoration:underline}
"""

MAIN_HTML = """
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><title>Dye Doxxer</title>
<link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
<style>{{ base_css }}</style>
<style>
  html, body { height: 100%; }
  body{
    /* Use Jinja so the path resolves correctly */
    background-image: url('{{ url_for('static', filename='background.png') }}');
    background-repeat: no-repeat;
    background-position: center center;
    background-attachment: fixed;
    background-size: cover;
    text-shadow: 0 1px 1px rgba(0,0,0,.6);
  }
  h2, h3{letter-spacing:.5px}
  /* Optional: make the result canvas pop a bit */
  #visual{
    box-shadow:0 6px 20px rgba(0,0,0,.35);
    border-radius:10px;
  }
</style>
<link rel="icon" href="{{ url_for('static', filename='favicon.png') }}">
</head><body>
  <div class="card">
    <h2>Dye Doxxer</h2>
    <div class="row">
      <img src="/static/dye_red.png"   alt="Red"   style="width:80px;height:80px;margin-right:8px">
      <img src="/static/dye_green.png" alt="Green" style="width:80px;height:80px;margin-right:8px">
      <img src="/static/dye_blue.png"  alt="Blue"  style="width:80px;height:80px;margin-right:8px">
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
    if(name==='black') return [-32, -32, -32]; // match Python change
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
</body></html>
"""

SAVED_HTML = """
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><title>Dye Doxxer · Saved</title>
<link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
<style>{{ base_css }}</style>
<style>
  html, body { height: 100%; }
  body{
    background-image: url('{{ url_for('static', filename='background.png') }}');
    background-repeat: no-repeat;
    background-position: center center;
    background-attachment: fixed;
    background-size: cover;
    text-shadow: 0 1px 1px rgba(0,0,0,.6);
  }
  h2{letter-spacing:.5px}
</style>
</head><body>
  <div class="card">
    <h2>Saved</h2>
    {% if items %}
      {% for idx, it in items %}
        <div style="border-bottom:1px solid #fff;margin-bottom:14px;padding-bottom:10px">
          <div class="sequence"><strong>Sequence:</strong> {{ it.sequence|safe }}</div>
          <div><strong>Final Color:</strong> {{ it.final_color }}
               <span class="swatch" style="background:rgb({{ it.final_color[0] }},{{ it.final_color[1] }},{{ it.final_color[2] }});"></span>
          </div>
          <div><strong>Target:</strong> {{ it.target }}
               <span class="swatch" style="background:rgb({{ it.target[0] }},{{ it.target[1] }},{{ it.target[2] }});"></span>
          </div>
          <div><strong>Final Mask:</strong> {{ it.final_mask }}</div>
          <div><strong>Diff:</strong> {{ it.diff }}</div>
          <form method="post" action="{{ url_for('delete_saved', idx=idx) }}">
            <input type="submit" value="Delete">
          </form>
        </div>
      {% endfor %}
    {% else %}<p>No saved items.</p>{% endif %}
    <div class="nav"><a href="{{ url_for('home') }}">Back</a></div>
  </div>
</body></html>
"""

HISTORY_HTML = """
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><title>Dye Doxxer · History</title>
<link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
<style>{{ base_css }}</style>
<style>
  html, body { height: 100%; }
  body{
    background-image: url('{{ url_for('static', filename='background.png') }}');
    background-repeat: no-repeat;
    background-position: center center;
    background-attachment: fixed;
    background-size: cover;
    text-shadow: 0 1px 1px rgba(0,0,0,.6);
  }
  h2{letter-spacing:.5px}
</style>
</head><body>
  <div class="card">
    <h2>History (last 10)</h2>
    <form method="get" action="{{ url_for('history') }}">
      <label>Filter (e.g. 241,219,29):</label>
      <input type="text" name="q" style="font-size:18px" value="{{ request.args.get('q','') }}">
      <input type="submit" value="Apply">
    </form>
    <div style="margin-top:10px">
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
      {% else %}<p>No history yet.</p>{% endif %}
    </div>
    <div class="nav"><a href="{{ url_for('home') }}">Back</a></div>
  </div>
</body></html>
"""

SETTINGS_HTML = """
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><title>Dye Doxxer · Settings</title>
<link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
<style>{{ base_css }}</style>
<style>
  html, body { height: 100%; }
  body{
    background-image: url('{{ url_for('static', filename='background.png') }}');
    background-repeat: no-repeat;
    background-position: center center;
    background-attachment: fixed;
    background-size: cover;
    text-shadow: 0 1px 1px rgba(0,0,0,.6);
  }
  h2{letter-spacing:.5px}
  .preset-row{display:flex;gap:10px;align-items:center;margin:8px 0}
  .pill{display:inline-block;padding:6px 10px;border:1px solid rgba(255,255,255,.25);border-radius:9999px;background:rgba(255,255,255,.1)}
  .mini-btn{font-size:16px;padding:6px 10px;border-radius:8px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.25);color:#fff;cursor:pointer}
  .mini-btn:hover{background:rgba(255,255,255,.18)}
  .sw{display:inline-block;width:20px;height:20px;border:1px solid #fff;border-radius:4px;margin-right:8px;vertical-align:middle}
  .section-title{margin-top:18px;margin-bottom:6px;font-size:18px;opacity:.95}
</style>
</head><body>
  <div class="card">
    <h2>Settings</h2>
    <form method="post">
      <div class="row"><strong>Start (base pixel S):</strong></div>
      <div class="row"><label>Start R:</label><input type="number" name="sr" min="0" max="255" value="{{ start[0] }}" required></div>
      <div class="row"><label>Start G:</label><input type="number" name="sg" min="0" max="255" value="{{ start[1] }}" required></div>
      <div class="row"><label>Start B:</label><input type="number" name="sb" min="0" max="255" value="{{ start[2] }}" required></div>
      <hr style="margin:12px 0;border-color:#777">
      <div class="row"><strong>Dye step parameters</strong></div>
      <div class="row"><label>ADD_VALUE (+):</label><input type="number" name="add" value="{{ add }}" required></div>
      <div class="row"><label>SUB_VALUE (−):</label><input type="number" name="sub" value="{{ sub }}" required></div>
      <div class="row"><label>Search MAX_DEPTH:</label><input type="number" name="depth" value="{{ depth }}" required></div>
      <div class="row">
        <input type="submit" name="action" value="Save Settings">
      </div>
    </form>

    <!-- Base RGBs section -->
    <div class="section-title"><strong>Base RGBs</strong></div>
    <form method="post" style="margin-top:8px">
      <div class="row"><label>Name:</label><input type="text" name="preset_name" placeholder="e.g., Sunny Gold" required style="width:220px;font-size:18px"></div>
      <div class="row">
        <label>R,G,B:</label>
        <input type="number" name="preset_r" min="0" max="255" required style="width:90px;font-size:18px">
        <input type="number" name="preset_g" min="0" max="255" required style="width:90px;font-size:18px">
        <input type="number" name="preset_b" min="0" max="255" required style="width:90px;font-size:18px">
      </div>
      <div class="row">
        <input type="submit" class="mini-btn" name="action" value="Save Base RGB">
      </div>
    </form>

    {% if presets %}
      <div class="section-title"><strong>Saved Base RGBs</strong></div>
      {% for idx, p in presets %}
        <div class="preset-row">
          <span class="sw" style="background:rgb({{ p.rgb[0] }},{{ p.rgb[1] }},{{ p.rgb[2] }})"></span>
          <span class="pill">{{ p.name }}</span>
          <span class="pill">({{ p.rgb[0] }}, {{ p.rgb[1] }}, {{ p.rgb[2] }})</span>

          <form method="post" style="display:inline;margin-left:8px">
            <input type="hidden" name="preset_idx" value="{{ idx }}">
            <input type="submit" class="mini-btn" name="action" value="Use Preset">
          </form>

          <form method="post" style="display:inline">
            <input type="hidden" name="preset_idx" value="{{ idx }}">
            <input type="submit" class="mini-btn" name="action" value="Delete Preset">
          </form>
        </div>
      {% endfor %}
    {% else %}
      <p style="opacity:.9;margin-top:8px">No base RGBs saved yet.</p>
    {% endif %}

    <div class="nav"><a href="{{ url_for('home') }}">Back</a></div>
  </div>
</body></html>
"""

# ---------- ROUTES ----------
@app.route("/", methods=["GET","POST"])
def home():
    result = None
    if request.method == "POST":
        try:
            target = (int(request.form["r"]), int(request.form["g"]), int(request.form["b"]))
        except Exception:
            target = (0,0,0)

        steps, final_mask, final_color, diff = find_sequence_to_target(target)

        result = {
            "sequence": pretty_sequence(steps),
            "raw_steps": steps,
            "final_mask": final_mask,
            "final_color": final_color,
            "target": target,
            "diff": diff
        }

        # history (limit 10)
        hist = session.get("history", [])
        hist.append({
            "sequence": result["sequence"],
            "final_mask": final_mask,
            "final_color": final_color,
            "target": target,
            "diff": diff,
            "ts": datetime.now().isoformat()
        })
        session["history"] = hist[-10:]
        session["current"] = result

        if request.form.get("action") == "Save":
            saved = session.get("saved", [])
            saved.append({
                "sequence": result["sequence"],
                "final_mask": final_mask,
                "final_color": final_color,
                "target": target,
                "diff": diff
            })
            session["saved"] = saved

    # Use session value for display if present (keeps the visualizer header in sync)
    effective_start = session.get("start_rgb", app.config["START_RGB"])
    ctx = {
        "base_css": BASE_CSS,
        "result": result if result else session.get("current"),
        "start_rgb": effective_start,
        "add_value": app.config["ADD_VALUE"],
        "sub_value": app.config["SUB_VALUE"]
    }
    return render_template_string(MAIN_HTML, **ctx)

@app.route("/saved", methods=["GET"])
def saved():
    items = list(enumerate(session.get("saved", [])))
    return render_template_string(SAVED_HTML, base_css=BASE_CSS, items=items)

@app.route("/delete/<int:idx>", methods=["POST"])
def delete_saved(idx):
    items = session.get("saved", [])
    if 0 <= idx < len(items):
        items.pop(idx)
    session["saved"] = items
    return redirect(url_for("saved"))

@app.route("/history", methods=["GET"])
def history():
    q = request.args.get("q","").strip()
    items = session.get("history", [])
    if q:
        items = [it for it in items if q in f"{it.get('target',(0,0,0))}"]
    items = items[::-1]  # newest first
    return render_template_string(HISTORY_HTML, base_css=BASE_CSS, items=items)

@app.route("/settings", methods=["GET","POST"])
def settings():
    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "Save Settings":
            try:
                sr = int(request.form["sr"])
                sg = int(request.form["sg"])
                sb = int(request.form["sb"])
                app.config["START_RGB"] = (sr, sg, sb)
                session["start_rgb"] = (sr, sg, sb)   # <-- persist per-user
                app.config["ADD_VALUE"] = int(request.form["add"])
                app.config["SUB_VALUE"] = int(request.form["sub"])
                app.config["MAX_DEPTH"] = int(request.form["depth"])
            except Exception:
                pass
            return redirect(url_for("home"))

        elif action == "Save Base RGB":
            # Add a named preset stored in session
            try:
                name = (request.form.get("preset_name") or "").strip()
                r = max(0, min(255, int(request.form.get("preset_r", 0))))
                g = max(0, min(255, int(request.form.get("preset_g", 0))))
                b = max(0, min(255, int(request.form.get("preset_b", 0))))
                if name:
                    presets = session.get("base_rgbs", [])
                    presets.append({"name": name, "rgb": (r, g, b)})
                    session["base_rgbs"] = presets
            except Exception:
                pass
            return redirect(url_for("settings"))

        elif action == "Use Preset":
            # Apply a preset to START_RGB
            try:
                idx = int(request.form.get("preset_idx", -1))
                presets = session.get("base_rgbs", [])
                if 0 <= idx < len(presets):
                    rgb = tuple(presets[idx]["rgb"])
                    app.config["START_RGB"] = rgb
                    session["start_rgb"] = rgb  # <-- persist selection
            except Exception:
                pass
            return redirect(url_for("settings"))

        elif action == "Delete Preset":
            # Remove a preset
            try:
                idx = int(request.form.get("preset_idx", -1))
                presets = session.get("base_rgbs", [])
                if 0 <= idx < len(presets):
                    presets.pop(idx)
                    session["base_rgbs"] = presets
            except Exception:
                pass
            return redirect(url_for("settings"))

        return redirect(url_for("settings"))

    # GET — read start from session if available so the inputs reflect last value
    effective_start = session.get("start_rgb", app.config["START_RGB"])
    presets = list(enumerate(session.get("base_rgbs", [])))
    ctx = {
        "base_css": BASE_CSS,
        "start": effective_start,
        "add": app.config["ADD_VALUE"],
        "sub": app.config["SUB_VALUE"],
        "depth": app.config["MAX_DEPTH"],
        "presets": presets
    }
    return render_template_string(SETTINGS_HTML, **ctx)

@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='favicon.png'))

if __name__ == "__main__":
    app.run(debug=True)
