"""
rapidscan/odm_tab.py  —  NodeODM / WebODM 3D Reconstruction Tab
================================================================
Connects to a running NodeODM instance (default: http://localhost:3000)
via its REST API. No pyodm dependency — uses only requests + PyQt5.

NodeODM setup (one-time, run in terminal):
    docker run -p 3000:3000 opendronemap/nodeodm

Workflow:
  1. Connect  → GET /info           verify node is alive
  2. Upload   → POST /task/new      multipart upload of all drone images
  3. Process  → poll GET /task/{id}/info  until status = completed/failed
  4. Download → GET /task/{id}/download/all.zip  → extract to output folder
  5. View     → open orthophoto / point cloud / 3D model in embedded viewer

Changes vs original:
  - Inline HTML generation for viewers (no external template files needed)
  - 3D viewer uses Three.js + GLTFLoader from CDN with graceful fallback
  - HTTP server has CORS headers so QtWebEngine & browsers can load assets
  - UploadWorker closes file handles reliably via finally block
  - PollingWorker has a configurable max-iteration safety guard
  - Refined UI: card-based stat strip, cleaner section headers, better spacing
  - "Open in Browser" button always enabled after a GLB is located
  - Results folder fallback chain is more robust
"""

import os
import json
import time
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import threading
import socket
import mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler, SimpleHTTPRequestHandler
from functools import partial

import requests

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QGroupBox, QTextEdit, QProgressBar,
    QFileDialog, QCheckBox, QScrollArea, QFrame,
    QSplitter, QListWidget, QListWidgetItem, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer, QUrl
from PyQt5.QtGui import QColor, QDesktopServices, QFont
from PyQt5.QtWebEngineWidgets import (
    QWebEngineView, QWebEngineSettings,
)
from PyQt5.QtWidgets import QApplication

from ._constants import (
    BG_DEEP, BG_PANEL, BG_CARD, BORDER,
    ACCENT, ACCENT_H, ACCENT2, ACCENT3,
    TXT_HI, TXT_MID, TXT_LOW, FONT_MONO,
)

# Ensure modern MIME types for web preview assets
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("application/octet-stream", ".laz")
mimetypes.add_type("application/octet-stream", ".las")

# Task status codes from NodeODM API
TASK_STATUS = {
    10: "Queued",
    20: "Running",
    30: "Failed",
    40: "Completed",
    50: "Cancelled",
}

TASK_STATUS_ICON = {
    10: "⏳",
    20: "⚙️",
    30: "✗",
    40: "✓",
    50: "■",
}

# Default ODM processing options (editable in UI)
DEFAULT_OPTIONS = [
    {"name": "dsm",               "value": True,    "label": "Generate DSM",           "type": "bool"},
    {"name": "dtm",               "value": True,    "label": "Generate DTM",           "type": "bool"},
    {"name": "orthophoto-resolution", "value": 5,   "label": "Orthophoto Res (cm/px)", "type": "int"},
    {"name": "mesh-size",         "value": 200000,  "label": "3D Mesh Size (faces)",   "type": "int"},
    {"name": "pc-quality",        "value": "medium","label": "Point Cloud Quality",    "type": "choice",
     "choices": ["lowest", "low", "medium", "high", "ultra"]},
    {"name": "3d-tiles",          "value": True,    "label": "Generate 3D Tiles",      "type": "bool"},
    {"name": "feature-quality",   "value": "high",  "label": "Feature Quality",        "type": "choice",
     "choices": ["lowest", "low", "medium", "high", "ultra"]},
    {"name": "min-num-features",  "value": 10000,   "label": "Min Features",           "type": "int"},
    {"name": "use-3dmesh",        "value": False,   "label": "Use 3D Mesh (not 2.5D)", "type": "bool"},
    {"name": "dem-resolution",    "value": 5.0,     "label": "DEM Resolution (cm/px)", "type": "float"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  CORS-aware HTTP handler for local file serving
# ─────────────────────────────────────────────────────────────────────────────
class _CORSHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with CORS headers and silent logging."""

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cross-Origin-Embedder-Policy", "unsafe-none")
        self.send_header("Cross-Origin-Opener-Policy", "unsafe-none")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        return  # suppress terminal noise

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Inline HTML generators (no external template files needed)
# ─────────────────────────────────────────────────────────────────────────────

def _build_orthophoto_html(img_url: str, accent: str, bg_deep: str, bg_panel: str,
                            txt_low: str, font_mono: str) -> str:
    """Return a self-contained pan/zoom orthophoto viewer."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background: {bg_deep};
    display: flex; flex-direction: column;
    height: 100vh; overflow: hidden;
    font-family: {font_mono};
  }}
  #toolbar {{
    background: {bg_panel};
    border-bottom: 1px solid rgba(255,255,255,.08);
    padding: 6px 10px;
    display: flex; gap: 8px; align-items: center;
    flex-shrink: 0;
  }}
  #toolbar span {{
    color: {txt_low};
    font-size: 10px;
    margin-left: auto;
  }}
  button {{
    background: rgba(255,255,255,.07);
    color: #e0eaf4;
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 11px;
    cursor: pointer;
    font-family: {font_mono};
    transition: background .15s;
  }}
  button:hover {{ background: {accent}; border-color: {accent}; color: #fff; }}
  #canvas-wrap {{
    flex: 1; overflow: hidden; position: relative; cursor: grab;
  }}
  #canvas-wrap:active {{ cursor: grabbing; }}
  canvas {{ position: absolute; top:0; left:0; }}
</style>
</head>
<body>
<div id="toolbar">
  <button onclick="zoom(1.25)">＋ Zoom</button>
  <button onclick="zoom(0.8)">－ Zoom</button>
  <button onclick="resetView()">⤢ Fit</button>
  <button onclick="saveImg()">💾 Save PNG</button>
  <span id="info">Loading…</span>
</div>
<div id="canvas-wrap">
  <canvas id="c"></canvas>
</div>
<script>
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const wrap = document.getElementById('canvas-wrap');
const info = document.getElementById('info');

let img = new Image();
let scale = 1, ox = 0, oy = 0;
let dragging = false, lastX, lastY;

img.crossOrigin = 'anonymous';
img.onload = () => {{
  info.textContent = img.naturalWidth + ' × ' + img.naturalHeight + ' px';
  resetView();
}};
img.onerror = () => {{
  info.textContent = 'Failed to load image';
  ctx.fillStyle='#ff4040'; ctx.font='14px monospace';
  ctx.fillText('Image load failed', 20, 40);
}};
img.src = '{img_url}';

function resize() {{
  canvas.width = wrap.clientWidth;
  canvas.height = wrap.clientHeight;
  draw();
}}
function resetView() {{
  const wr = wrap.clientWidth / img.naturalWidth;
  const hr = wrap.clientHeight / img.naturalHeight;
  scale = Math.min(wr, hr) * 0.95;
  ox = (wrap.clientWidth  - img.naturalWidth  * scale) / 2;
  oy = (wrap.clientHeight - img.naturalHeight * scale) / 2;
  draw();
}}
function draw() {{
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (img.complete && img.naturalWidth)
    ctx.drawImage(img, ox, oy, img.naturalWidth*scale, img.naturalHeight*scale);
}}
function zoom(f) {{
  scale *= f;
  ox = canvas.width/2  - (canvas.width/2  - ox) * f;
  oy = canvas.height/2 - (canvas.height/2 - oy) * f;
  draw();
}}
function saveImg() {{
  const a = document.createElement('a');
  a.download = 'orthophoto.png';
  a.href = canvas.toDataURL('image/png');
  a.click();
}}
wrap.addEventListener('mousedown', e => {{
  dragging=true; lastX=e.clientX; lastY=e.clientY;
}});
window.addEventListener('mouseup',   () => dragging=false);
window.addEventListener('mousemove', e => {{
  if (!dragging) return;
  ox += e.clientX-lastX; oy += e.clientY-lastY;
  lastX=e.clientX; lastY=e.clientY; draw();
}});
wrap.addEventListener('wheel', e => {{
  e.preventDefault();
  const f = e.deltaY < 0 ? 1.1 : 0.9;
  const mx = e.offsetX, my = e.offsetY;
  scale *= f;
  ox = mx - (mx-ox)*f;
  oy = my - (my-oy)*f;
  draw();
}}, {{passive:false}});
window.addEventListener('resize', resize);
resize();
</script>
</body>
</html>"""


def _build_3d_viewer_html(glb_url: str, accent: str, bg_deep: str, bg_panel: str,
                           txt_low: str, txt_mid: str, font_mono: str) -> str:
    """
    Return a self-contained Three.js GLB viewer.
    Uses Three.js r128 + GLTFLoader + DRACOLoader from cdnjs/jsdelivr.
    DRACOLoader is always provided so Draco-compressed GLBs (common in ODM)
    load without the "No DRACOLoader instance provided" error.
    Falls back gracefully when CDN is unreachable.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background:{bg_deep}; overflow:hidden;
    font-family:{font_mono}; color:{txt_mid};
  }}
  #overlay {{
    position:fixed; inset:0; background:{bg_deep};
    display:flex; flex-direction:column;
    align-items:center; justify-content:center;
    z-index:100; transition:opacity .5s;
  }}
  #overlay.hidden {{ opacity:0; pointer-events:none; }}
  .spinner {{
    width:38px; height:38px; border:3px solid rgba(255,255,255,.08);
    border-top-color:{accent};
    border-radius:50%; animation:spin .8s linear infinite; margin-bottom:14px;
  }}
  @keyframes spin {{ to{{ transform:rotate(360deg); }} }}
  #load-msg {{ font-size:11px; color:{txt_low}; letter-spacing:.5px; }}
  #load-bar-wrap {{
    width:220px; height:3px; background:rgba(255,255,255,.08);
    border-radius:2px; margin-top:10px; overflow:hidden;
  }}
  #load-bar {{
    height:100%; width:0%; background:{accent};
    border-radius:2px; transition:width .2s;
  }}
  #toolbar {{
    position:fixed; top:0; left:0; right:0;
    background:rgba(14,20,28,.82); backdrop-filter:blur(10px);
    border-bottom:1px solid rgba(255,255,255,.06);
    padding:5px 10px; display:flex; gap:5px; align-items:center;
    z-index:50; height:36px;
  }}
  .tbtn {{
    background:rgba(255,255,255,.06);
    color:#b8ccdc; border:1px solid rgba(255,255,255,.1);
    border-radius:5px; padding:3px 9px; font-size:10.5px;
    cursor:pointer; font-family:{font_mono}; transition:all .15s;
    white-space:nowrap;
  }}
  .tbtn:hover {{ background:{accent}; border-color:{accent}; color:#fff; }}
  .tbtn.active {{ background:{accent}22; border-color:{accent}88; color:{accent}; }}
  #hint {{
    margin-left:auto; font-size:10px; color:{txt_low};
    letter-spacing:.2px; white-space:nowrap;
  }}
  #errbox {{
    display:none; position:fixed; inset:0;
    background:{bg_deep}; align-items:center; justify-content:center;
    z-index:200; flex-direction:column; gap:14px; padding:30px;
  }}
  #errbox p {{
    color:{txt_low}; font-size:11px; text-align:center;
    max-width:360px; line-height:1.7;
  }}
  canvas {{ display:block; }}
</style>
</head>
<body>
<div id="overlay">
  <div class="spinner"></div>
  <div id="load-msg">Initialising 3D viewer…</div>
  <div id="load-bar-wrap"><div id="load-bar"></div></div>
</div>
<div id="toolbar">
  <button class="tbtn" onclick="resetCamera()">⤢ Reset</button>
  <button class="tbtn" id="btnWire" onclick="toggleWireframe()">⬡ Wire</button>
  <button class="tbtn" id="btnAxes" onclick="toggleAxes()">✛ Axes</button>
  <button class="tbtn" id="btnShade" onclick="toggleShading()">◑ Shade</button>
  <button class="tbtn" id="animBtn" onclick="toggleAnim()" style="display:none">▶ Anim</button>
  <span id="hint">drag · scroll · right-drag</span>
</div>
<div id="errbox">
  <div class="spinner"></div>
  <p>3D viewer needs an internet connection to load Three.js.<br>
     Use <b>Open 3D in Browser</b> instead, or check your network.</p>
</div>

<!-- Three.js r128 (UMD build, no ES modules — works in QtWebEngine) -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
        crossorigin="anonymous"
        onerror="showErr();">
</script>
<!-- GLTFLoader for r128 -->
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"
        crossorigin="anonymous" onerror="showErr();">
</script>
<!-- DRACOLoader for r128 — MUST be present or Draco-compressed ODM GLBs fail -->
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/DRACOLoader.js"
        crossorigin="anonymous" onerror="showErr();">
</script>
<!-- OrbitControls for r128 -->
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"
        crossorigin="anonymous">
</script>

<script>
function showErr() {{
  document.getElementById('errbox').style.display = 'flex';
  document.getElementById('overlay').classList.add('hidden');
}}

// Guard: all required libs must be present
window.addEventListener('load', function() {{
  if (typeof THREE === 'undefined' || !THREE.GLTFLoader || !THREE.DRACOLoader) {{
    showErr(); return;
  }}
  initViewer();
}});

function initViewer() {{
// ── Renderer ───────────────────────────────────────────────────────────────
const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputEncoding = THREE.sRGBEncoding;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
document.body.appendChild(renderer.domElement);

// ── Scene ──────────────────────────────────────────────────────────────────
const scene = new THREE.Scene();
scene.background = new THREE.Color('{bg_deep}');
scene.fog = new THREE.FogExp2('{bg_deep}', 0.0015);

const gridHelper = new THREE.GridHelper(500, 50, 0x1e2a38, 0x161f2a);
scene.add(gridHelper);

const axesHelper = new THREE.AxesHelper(5);
axesHelper.visible = false;
scene.add(axesHelper);

// ── Lights ──────────────────────────────────────────────────────────────────
const ambient = new THREE.AmbientLight(0xffffff, 0.55);
scene.add(ambient);

const sun = new THREE.DirectionalLight(0xfff4e0, 1.6);
sun.position.set(8, 15, 10);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.far = 5000;
scene.add(sun);

const fill = new THREE.DirectionalLight(0x4a80c0, 0.35);
fill.position.set(-6, 4, -8);
scene.add(fill);

// ── Camera ─────────────────────────────────────────────────────────────────
const camera = new THREE.PerspectiveCamera(
  45, window.innerWidth / window.innerHeight, 0.001, 50000);
camera.position.set(0, 10, 20);

// ── Controls ───────────────────────────────────────────────────────────────
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping  = true;
controls.dampingFactor  = 0.07;
controls.screenSpacePanning = true;
controls.minDistance    = 0.01;
controls.maxDistance    = 20000;
controls.zoomSpeed      = 1.2;

// ── State ──────────────────────────────────────────────────────────────────
let model = null, mixer = null, clock = new THREE.Clock();
let wireMode = false, flatShade = false, animPaused = false;
let savedCamPos = null, savedTarget = null;

// ── DRACOLoader — pointed at jsDelivr-hosted decoder WASM ─────────────────
const dracoLoader = new THREE.DRACOLoader();
// Use the same version's decoder workers from jsDelivr
dracoLoader.setDecoderPath(
  'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/libs/draco/gltf/'
);
dracoLoader.setDecoderConfig({{ type: 'js' }});  // fallback to JS decoder (no WASM CORS issues)

// ── GLTFLoader ─────────────────────────────────────────────────────────────
const loader = new THREE.GLTFLoader();
loader.setDRACOLoader(dracoLoader);   // ← key: prevents "No DRACOLoader" error

loader.load(
  '{glb_url}',
  (gltf) => {{
    model = gltf.scene;
    model.traverse(child => {{
      if (child.isMesh) {{
        child.castShadow    = true;
        child.receiveShadow = true;
        if (child.material) child.material.side = THREE.DoubleSide;
      }}
    }});
    scene.add(model);

    // Fit camera
    const box    = new THREE.Box3().setFromObject(model);
    const size   = new THREE.Vector3();
    const center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov    = camera.fov * (Math.PI / 180);
    let dist     = (maxDim / 2) / Math.tan(fov / 2) * 1.6;

    camera.near = dist * 0.0005;
    camera.far  = dist * 200;
    camera.updateProjectionMatrix();
    camera.position.set(center.x + dist*.6, center.y + dist*.4, center.z + dist);

    controls.target.copy(center);
    controls.update();

    // Reposition grid floor
    gridHelper.position.y = box.min.y - 0.01;
    gridHelper.scale.setScalar(maxDim * 0.8);

    savedCamPos = camera.position.clone();
    savedTarget = controls.target.clone();

    if (gltf.animations && gltf.animations.length) {{
      mixer = new THREE.AnimationMixer(model);
      gltf.animations.forEach(clip => mixer.clipAction(clip).play());
      document.getElementById('animBtn').style.display = 'inline-block';
    }}

    dracoLoader.dispose();
    document.getElementById('overlay').classList.add('hidden');
  }},
  (xhr) => {{
    if (xhr.total > 0) {{
      const pct = Math.round(xhr.loaded / xhr.total * 100);
      document.getElementById('load-msg').textContent = 'Loading… ' + pct + '%';
      document.getElementById('load-bar').style.width = pct + '%';
    }}
  }},
  (err) => {{
    console.error('GLTFLoader error:', err);
    document.getElementById('load-msg').textContent = 'Load failed: ' + (err.message || err);
    setTimeout(showErr, 900);
  }}
);

// ── Toolbar actions ────────────────────────────────────────────────────────
function resetCamera() {{
  if (!savedCamPos) return;
  camera.position.copy(savedCamPos);
  controls.target.copy(savedTarget);
  controls.update();
}}

function toggleWireframe() {{
  wireMode = !wireMode;
  document.getElementById('btnWire').classList.toggle('active', wireMode);
  if (model) model.traverse(c => {{
    if (c.isMesh && c.material) c.material.wireframe = wireMode;
  }});
}}

function toggleAxes() {{
  axesHelper.visible = !axesHelper.visible;
  document.getElementById('btnAxes').classList.toggle('active', axesHelper.visible);
}}

function toggleShading() {{
  flatShade = !flatShade;
  document.getElementById('btnShade').classList.toggle('active', flatShade);
  if (model) model.traverse(c => {{
    if (c.isMesh && c.material) {{
      c.material.flatShading = flatShade;
      c.material.needsUpdate = true;
    }}
  }});
}}

function toggleAnim() {{
  animPaused = !animPaused;
  document.getElementById('animBtn').textContent = animPaused ? '▶ Play' : '⏸ Pause';
}}

// ── Render loop ────────────────────────────────────────────────────────────
(function animate() {{
  requestAnimationFrame(animate);
  const dt = clock.getDelta();
  if (mixer && !animPaused) mixer.update(dt);
  controls.update();
  renderer.render(scene, camera);
}})();

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});

}} // end initViewer

</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  NodeODM REST client (pure requests, no pyodm)
# ─────────────────────────────────────────────────────────────────────────────
class NodeODMClient:
    def __init__(self, host="localhost", port=3000, token="", timeout=30):
        self.base    = f"http://{host}:{port}"
        self.token   = token
        self.timeout = timeout

    def _params(self, extra=None):
        p = {}
        if self.token:
            p["token"] = self.token
        if extra:
            p.update(extra)
        return p

    def info(self):
        r = requests.get(f"{self.base}/info",
                         params=self._params(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def options(self):
        r = requests.get(f"{self.base}/options",
                         params=self._params(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def create_task(self, image_paths, options, name="BuildScan Task",
                    webhook=None, progress_cb=None):
        """
        Upload images and create a task via POST /task/new (multipart).
        Returns task dict with 'uuid'.
        progress_cb(n, total) called after each image upload.
        """
        url       = f"{self.base}/task/new"
        opts_json = json.dumps([{"name": k, "value": v}
                                 for k, v in options.items()])
        file_handles = []
        files = []
        try:
            for i, path in enumerate(image_paths):
                fh = open(path, "rb")
                file_handles.append(fh)
                files.append(("images",
                              (os.path.basename(path), fh, "image/jpeg")))
                if progress_cb:
                    progress_cb(i + 1, len(image_paths))

            data = {"name": name, "options": opts_json}
            if webhook:
                data["webhook"] = webhook

            r = requests.post(url, params=self._params(), data=data,
                              files=files, timeout=self.timeout * 10)
            r.raise_for_status()
            return r.json()
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    def task_info(self, task_uuid):
        r = requests.get(f"{self.base}/task/{task_uuid}/info",
                         params=self._params(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def task_output(self, task_uuid, line=0):
        r = requests.get(f"{self.base}/task/{task_uuid}/output",
                         params=self._params({"line": line}),
                         timeout=self.timeout)
        r.raise_for_status()
        return r.json()  # list of strings

    def download_all(self, task_uuid, dest_path, progress_cb=None):
        url = f"{self.base}/task/{task_uuid}/download/all.zip"
        r   = requests.get(url, params=self._params(),
                           stream=True, timeout=600)
        r.raise_for_status()
        total      = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        progress_cb(int(downloaded / total * 100))
        return dest_path

    def cancel_task(self, task_uuid):
        r = requests.post(f"{self.base}/task/{task_uuid}/cancel",
                          params=self._params(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def delete_task(self, task_uuid):
        r = requests.post(f"{self.base}/task/{task_uuid}/remove",
                          params=self._params(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_tasks(self):
        r = requests.get(f"{self.base}/task/list",
                         params=self._params(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()


# ─────────────────────────────────────────────────────────────────────────────
#  Background workers (QThread)
# ─────────────────────────────────────────────────────────────────────────────
class UploadWorker(QThread):
    progress = pyqtSignal(int, int)   # (uploaded, total)
    log      = pyqtSignal(str)
    finished = pyqtSignal(str)        # task_uuid on success
    error    = pyqtSignal(str)

    def __init__(self, client, image_paths, options, task_name):
        super().__init__()
        self.client      = client
        self.image_paths = image_paths
        self.options     = options
        self.task_name   = task_name

    def run(self):
        try:
            self.log.emit(f"Uploading {len(self.image_paths)} images to NodeODM…")
            result = self.client.create_task(
                self.image_paths, self.options, self.task_name,
                progress_cb=lambda n, t: self.progress.emit(n, t)
            )
            uuid = result.get("uuid", "")
            if not uuid:
                self.error.emit(f"No UUID returned: {result}")
                return
            self.log.emit(f"Task created: {uuid}")
            self.finished.emit(uuid)
        except Exception as e:
            self.error.emit(str(e))


class PollingWorker(QThread):
    """Polls task status every N seconds until done/failed/cancelled."""
    status_update = pyqtSignal(dict)   # full task info dict
    log_lines     = pyqtSignal(list)   # new console lines
    finished      = pyqtSignal(dict)   # final task info
    error         = pyqtSignal(str)

    MAX_ITERATIONS = 2880  # 4 hours at 5-second intervals

    def __init__(self, client, task_uuid, poll_interval=5):
        super().__init__()
        self.client        = client
        self.task_uuid     = task_uuid
        self.poll_interval = poll_interval
        self.running       = True
        self._last_line    = 0

    def run(self):
        iterations = 0
        while self.running and iterations < self.MAX_ITERATIONS:
            try:
                info = self.client.task_info(self.task_uuid)
                self.status_update.emit(info)

                # Fetch new log lines
                try:
                    lines = self.client.task_output(self.task_uuid,
                                                    self._last_line)
                    if lines:
                        self.log_lines.emit(lines)
                        self._last_line += len(lines)
                except Exception:
                    pass

                code = info.get("status", {}).get("code", 0)
                if code in (30, 40, 50):   # failed, completed, cancelled
                    self.finished.emit(info)
                    return

            except Exception as e:
                self.error.emit(str(e))

            iterations += 1
            time.sleep(self.poll_interval)

        if iterations >= self.MAX_ITERATIONS:
            self.error.emit("Polling timeout: task exceeded maximum wait time.")

    def stop(self):
        self.running = False


class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    log      = pyqtSignal(str)
    finished = pyqtSignal(str)   # extracted output folder path
    error    = pyqtSignal(str)

    def __init__(self, client, task_uuid, output_dir):
        super().__init__()
        self.client     = client
        self.task_uuid  = task_uuid
        self.output_dir = output_dir

    def run(self):
        try:
            zip_path = os.path.join(self.output_dir, "all.zip")
            self.log.emit("Downloading results (all.zip)…")
            self.client.download_all(
                self.task_uuid, zip_path,
                progress_cb=lambda p: self.progress.emit(p)
            )
            self.log.emit("Download complete. Extracting…")
            extract_dir = os.path.join(self.output_dir, "odm_results")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            os.remove(zip_path)
            self.log.emit(f"Extracted to: {extract_dir}")
            self.finished.emit(extract_dir)
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  Main ODM Tab Widget
# ─────────────────────────────────────────────────────────────────────────────
class ODMTab(QWidget):
    """
    Embeddable PyQt5 widget for NodeODM/WebODM 3D reconstruction.
    Drop-in compatible with RiskMap's add_tab() — accepts config/logger kwargs.
    """

    def __init__(self, config=None, logger=None, parent=None):
        super().__init__(parent)
        self.config        = config
        self.logger        = logger
        self.client        = None
        self.current_uuid  = None
        self.image_paths   = []
        self.output_dir    = ""
        self._extract_dir  = ""
        self._results_dir  = ""
        self._httpd        = None
        self._http_thread  = None
        self._http_root    = ""
        self._http_port    = None
        self.upload_worker = None
        self.poll_worker   = None
        self.dl_worker     = None
        self._option_widgets = {}   # name → (widget, type)

        self._build_ui()
        self._apply_stylesheet()

        # Allow QWebEngineView to load local files and remote URLs
        try:
            s = QWebEngineSettings.globalSettings()
            s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            s.setAttribute(QWebEngineSettings.WebGLEnabled, True)
            s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            s.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        except Exception:
            pass

    # ── Stylesheet ─────────────────────────────────────────────────────────
    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
        QWidget {{
            font-family: 'Segoe UI', 'SF Pro Display', system-ui, sans-serif;
            font-size: 12px;
            color: {TXT_HI};
            background: {BG_DEEP};
        }}
        QSplitter::handle {{
            background: {BORDER};
            border-radius: 2px;
        }}
        QSplitter::handle:hover {{ background: {ACCENT}; }}

        /* ── GroupBox ── */
        QGroupBox {{
            border: 1px solid {BORDER};
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 10px;
            font-weight: 700;
            font-size: 10px;
            color: {ACCENT};
            background: {BG_PANEL};
            letter-spacing: 0.8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
        }}

        /* ── Buttons ── */
        QPushButton {{
            background: {BG_CARD};
            color: {TXT_HI};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 7px 12px;
            font-size: 11px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background: {ACCENT};
            color: #ffffff;
            border-color: {ACCENT};
        }}
        QPushButton:pressed {{
            background: {ACCENT_H};
            border-color: {ACCENT_H};
        }}
        QPushButton:disabled {{
            background: {BG_CARD};
            color: {TXT_LOW};
            border-color: {BORDER};
        }}
        QPushButton#go {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {ACCENT}, stop:1 {ACCENT_H});
            color: #ffffff;
            font-weight: 700;
            border: none;
            padding: 8px 14px;
            border-radius: 7px;
        }}
        QPushButton#go:hover {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {ACCENT_H}, stop:1 {ACCENT});
        }}
        QPushButton#go:disabled {{
            background: {BG_CARD};
            color: {TXT_LOW};
            border: 1px solid {BORDER};
        }}
        QPushButton#danger {{
            color: {ACCENT2};
            border-color: {ACCENT2};
            background: transparent;
        }}
        QPushButton#danger:hover {{
            background: {ACCENT2};
            color: #ffffff;
        }}
        QPushButton#secondary {{
            background: transparent;
            color: {ACCENT};
            border: 1px solid {ACCENT};
            border-radius: 6px;
        }}
        QPushButton#secondary:hover {{
            background: {ACCENT};
            color: #ffffff;
        }}

        /* ── Inputs ── */
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background: {BG_PANEL};
            color: {TXT_HI};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 6px 9px;
            font-size: 12px;
            min-height: 28px;
            selection-background-color: {ACCENT};
        }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {ACCENT};
            background: {BG_DEEP};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox::down-arrow {{
            width: 10px; height: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: {BG_PANEL};
            border: 1px solid {BORDER};
            selection-background-color: {ACCENT};
            color: {TXT_HI};
        }}

        /* ── TextEdit / Log ── */
        QTextEdit {{
            background: {BG_DEEP};
            color: {TXT_MID};
            border: 1px solid {BORDER};
            border-radius: 6px;
            font-family: {FONT_MONO};
            font-size: 11px;
            padding: 4px;
        }}

        /* ── List ── */
        QListWidget {{
            background: {BG_DEEP};
            color: {TXT_HI};
            border: 1px solid {BORDER};
            border-radius: 6px;
            font-size: 11px;
            padding: 2px;
        }}
        QListWidget::item {{
            padding: 3px 6px;
            border-radius: 4px;
        }}
        QListWidget::item:selected {{
            background: rgba(30,140,220,.2);
            color: {ACCENT};
        }}
        QListWidget::item:hover:!selected {{
            background: rgba(255,255,255,.04);
        }}

        /* ── Checkbox ── */
        QCheckBox {{
            color: {TXT_MID};
            spacing: 7px;
            font-size: 12px;
            padding: 2px 0;
        }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border: 1px solid {BORDER};
            border-radius: 4px;
            background: {BG_PANEL};
        }}
        QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
        QCheckBox::indicator:checked {{
            background: {ACCENT};
            border-color: {ACCENT};
            image: url(none);
        }}
        QCheckBox::indicator:checked:hover {{ background: {ACCENT_H}; }}
        QCheckBox::indicator:disabled {{
            background: {BG_CARD};
            border-color: {BORDER};
        }}

        /* ── Progress bars ── */
        QProgressBar {{
            background: {BG_DEEP};
            border: 1px solid {BORDER};
            border-radius: 5px;
            height: 7px;
            text-align: center;
            font-size: 9px;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {ACCENT}, stop:1 {ACCENT_H});
            border-radius: 5px;
        }}

        /* ── Labels ── */
        QLabel {{
            color: {TXT_MID};
            font-size: 11px;
            background: transparent;
        }}
        QLabel#title {{
            color: {ACCENT};
            font-size: 10px;
            font-weight: 700;
            font-family: {FONT_MONO};
            letter-spacing: 1.2px;
        }}
        QLabel#section_hint {{
            color: {TXT_LOW};
            font-size: 10px;
            font-family: {FONT_MONO};
        }}
        QLabel#status_ok  {{
            color: {ACCENT3};
            font-family: {FONT_MONO};
            font-size: 11px;
            font-weight: 700;
        }}
        QLabel#status_err {{
            color: {ACCENT2};
            font-family: {FONT_MONO};
            font-size: 11px;
        }}
        QLabel#card_val {{
            color: {ACCENT};
            font-size: 20px;
            font-weight: 700;
            font-family: {FONT_MONO};
        }}
        QLabel#card_name {{
            color: {TXT_LOW};
            font-size: 10px;
            letter-spacing: 0.3px;
        }}

        /* ── Table ── */
        QTableWidget {{
            background: {BG_PANEL};
            color: {TXT_HI};
            gridline-color: {BORDER};
            border: 1px solid {BORDER};
            border-radius: 7px;
            font-size: 11px;
            alternate-background-color: {BG_DEEP};
        }}
        QHeaderView::section {{
            background: {BG_DEEP};
            color: {TXT_LOW};
            border: none;
            border-bottom: 1px solid {BORDER};
            padding: 7px 8px;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QTableWidget::item:selected {{
            background: rgba(30,140,220,.15);
            color: {ACCENT};
        }}

        /* ── Scrollbars ── */
        QScrollBar:vertical {{
            background: transparent; width: 7px; margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {BORDER}; border-radius: 3px; min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent; height: 7px; margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {BORDER}; border-radius: 3px; min-width: 20px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        /* ── Tabs: clean white card with underline indicator ── */
        QTabWidget {{
            background: #ffffff;
        }}
        QTabWidget::pane {{
            border: none;
            border-top: 1px solid {BORDER};
            background: #ffffff;
            top: 0px;
            margin-top: 0px;
        }}
        QTabBar {{
            background: #ffffff;
        }}
        QTabBar::tab {{
            background: #ffffff;
            color: {TXT_MID};
            padding: 11px 20px;
            border: none;
            border-bottom: 2px solid transparent;
            font-weight: 500;
            font-size: 11px;
            min-width: 88px;
        }}
        QTabBar::tab:selected {{
            background: #ffffff;
            color: {ACCENT};
            font-weight: 700;
            border-bottom: 2px solid {ACCENT};
        }}
        QTabBar::tab:hover:!selected {{
            color: {TXT_HI};
            background: #f4f8fc;
        }}
        QTabBar::scroller {{
            background: #ffffff;
        }}
        """)

    # ── Build UI ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(3)

        # ── LEFT PANEL: white card ───────────────────────────────────────────
        left = QWidget()
        left.setObjectName("left_card")
        left.setMinimumWidth(290)
        left.setMaximumWidth(320)
        left.setStyleSheet(f"""
            QWidget#left_card {{
                background: #ffffff;
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        ll = QVBoxLayout(left)
        ll.setSpacing(0)
        ll.setContentsMargins(0, 0, 0, 0)

        # Scrollable inner content
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        left_inner = QWidget()
        left_inner.setStyleSheet("QWidget { background: #ffffff; }")
        li = QVBoxLayout(left_inner)
        li.setSpacing(0)
        li.setContentsMargins(0, 0, 0, 0)

        # ── Section helper for left panel ─────────────────────────────────────
        def _left_section(title):
            """Flat section header with top border."""
            hdr = QWidget()
            hdr.setFixedHeight(36)
            hdr.setStyleSheet(
                f"QWidget {{ background: #f8fafc; border-top: 1px solid {BORDER}; "
                f"border-bottom: 1px solid {BORDER}; }}"
            )
            hl = QHBoxLayout(hdr)
            hl.setContentsMargins(16, 0, 16, 0)
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"color: #64748b; font-size: 10px; font-weight: 700; "
                f"letter-spacing: 1px; font-family: {FONT_MONO}; "
                f"background: transparent; border: none;"
            )
            hl.addWidget(lbl)
            return hdr

        def _left_content():
            """White content area inside a section."""
            w = QWidget()
            w.setStyleSheet("QWidget { background: #ffffff; }")
            return w

        # ── Connection group ──
        conn_grp = QGroupBox("NODE ODM CONNECTION")
        cg = QGridLayout(conn_grp)
        cg.setSpacing(6)
        cg.setContentsMargins(10, 14, 10, 10)

        for row_i, (lbl_txt, attr, widget_factory) in enumerate([
            ("Host",  "host_edit",  lambda: _make_line_edit("localhost")),
            ("Port",  "port_spin",  lambda: _make_port_spin()),
            ("Token", "token_edit", lambda: _make_line_edit("", "optional")),
        ]):
            lbl = QLabel(lbl_txt)
            lbl.setStyleSheet(f"color:{TXT_LOW}; font-size:11px; font-weight:600;")
            cg.addWidget(lbl, row_i, 0)
            w = widget_factory()
            setattr(self, attr, w)
            cg.addWidget(w, row_i, 1)

        conn_row = QHBoxLayout()
        conn_row.setSpacing(8)
        self.btn_connect = QPushButton("⚡  Connect")
        self.btn_connect.setObjectName("go")
        self.btn_connect.setCursor(Qt.PointingHandCursor)
        self.btn_connect.setToolTip("Connect to NodeODM server")
        self.btn_connect.clicked.connect(self.do_connect)
        self.conn_status = QLabel("Not connected")
        self.conn_status.setObjectName("status_err")
        conn_row.addWidget(self.btn_connect)
        conn_row.addWidget(self.conn_status, 1)
        cg.addLayout(conn_row, 3, 0, 1, 2)

        self.node_info_lbl = QLabel("")
        self.node_info_lbl.setWordWrap(True)
        self.node_info_lbl.setStyleSheet(
            f"color:{TXT_LOW}; font-size:10px; font-family:{FONT_MONO};"
        )
        cg.addWidget(self.node_info_lbl, 4, 0, 1, 2)
        ll.addWidget(conn_grp)

        # Docker hint (collapsible-style)
        hint = QLabel(
            "💡  docker run -p 3000:3000 opendronemap/nodeodm"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{TXT_LOW}; font-size:10px; font-family:{FONT_MONO}; "
            f"background:{BG_DEEP}; border:1px solid {BORDER}; "
            f"border-radius:6px; padding:7px 9px;"
        )
        ll.addWidget(hint)

        # ── Drone images group ──
        img_grp = QGroupBox("DRONE IMAGES")
        ig = QVBoxLayout(img_grp)
        ig.setContentsMargins(10, 14, 10, 10)
        ig.setSpacing(6)

        img_btn_row = QHBoxLayout()
        img_btn_row.setSpacing(5)
        self.btn_add_imgs   = QPushButton("📷  Images")
        self.btn_add_folder = QPushButton("📁  Folder")
        self.btn_clear_imgs = QPushButton("✕")
        self.btn_clear_imgs.setObjectName("danger")
        self.btn_clear_imgs.setFixedWidth(34)
        for btn, tip, fn in [
            (self.btn_add_imgs,   "Select drone images",          self.add_images),
            (self.btn_add_folder, "Import all images from folder", self.add_folder),
            (self.btn_clear_imgs, "Clear image list",              self.clear_images),
        ]:
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tip)
            btn.clicked.connect(fn)
            img_btn_row.addWidget(btn)
        ig.addLayout(img_btn_row)

        self.img_list = QListWidget()
        self.img_list.setFixedHeight(90)
        ig.addWidget(self.img_list)

        self.img_count_lbl = QLabel("0 images selected")
        self.img_count_lbl.setStyleSheet(
            f"color:{ACCENT}; font-weight:600; font-size:11px;"
        )
        ig.addWidget(self.img_count_lbl)
        ll.addWidget(img_grp)

        # ── Output folder ──
        out_grp = QGroupBox("OUTPUT FOLDER")
        og = QHBoxLayout(out_grp)
        og.setContentsMargins(10, 14, 10, 10)
        og.setSpacing(6)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Select output folder…")
        self.btn_out = QPushButton("…")
        self.btn_out.setFixedWidth(34)
        self.btn_out.setCursor(Qt.PointingHandCursor)
        self.btn_out.setToolTip("Browse output folder")
        self.btn_out.clicked.connect(self.select_output)
        og.addWidget(self.out_edit)
        og.addWidget(self.btn_out)
        ll.addWidget(out_grp)

        # ── Task name ──
        name_grp = QGroupBox("TASK")
        ng = QHBoxLayout(name_grp)
        ng.setContentsMargins(10, 14, 10, 10)
        ng.setSpacing(6)
        ng.addWidget(QLabel("Name:"))
        self.task_name_edit = QLineEdit("BuildScan Reconstruction")
        ng.addWidget(self.task_name_edit, 1)
        ll.addWidget(name_grp)

        # ── Run / Cancel ──
        run_row = QHBoxLayout()
        run_row.setSpacing(6)
        self.btn_run = QPushButton("▶  Start Processing")
        self.btn_run.setObjectName("go")
        self.btn_run.setEnabled(False)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setToolTip("Upload images and start ODM processing")
        self.btn_run.clicked.connect(self.start_task)
        self.btn_cancel = QPushButton("■  Cancel")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setToolTip("Cancel the running task on server")
        self.btn_cancel.clicked.connect(self.cancel_task)
        run_row.addWidget(self.btn_run, 3)
        run_row.addWidget(self.btn_cancel, 1)
        ll.addLayout(run_row)

        # ── Upload progress ──
        self.upload_bar = QProgressBar()
        self.upload_bar.setVisible(False)
        self.upload_lbl = QLabel("")
        self.upload_lbl.setStyleSheet(
            f"color:{TXT_MID}; font-size:10px; font-family:{FONT_MONO};"
        )
        ll.addWidget(self.upload_bar)
        ll.addWidget(self.upload_lbl)
        ll.addStretch()

        # ── RIGHT PANEL: white card wrapper + QTabWidget ─────────────────────
        # Outer white card that contains the tab bar + content — no grey bleed
        right_card = QWidget()
        right_card.setObjectName("right_card")
        right_card.setStyleSheet(f"""
            QWidget#right_card {{
                background: #ffffff;
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        right_card_layout = QVBoxLayout(right_card)
        right_card_layout.setContentsMargins(0, 0, 0, 0)
        right_card_layout.setSpacing(0)

        right_tabs = QTabWidget()
        right_tabs.setDocumentMode(False)
        right_tabs.setMovable(False)
        right_tabs.setStyleSheet(f"""
            QTabWidget {{
                background: #ffffff;
            }}
            QTabWidget::pane {{
                border: none;
                border-top: 1px solid {BORDER};
                background: #ffffff;
                border-radius: 0px;
                top: 0px;
            }}
            QTabBar {{
                background: #ffffff;
                border-bottom: none;
            }}
            QTabBar::tab {{
                background: #ffffff;
                color: #6b7a8d;
                padding: 12px 20px;
                border: none;
                border-bottom: 2px solid transparent;
                font-weight: 500;
                font-size: 11px;
                min-width: 90px;
            }}
            QTabBar::tab:selected {{
                background: #ffffff;
                color: {ACCENT};
                font-weight: 700;
                border-bottom: 2px solid {ACCENT};
            }}
            QTabBar::tab:hover:!selected {{
                color: #2c3a4a;
                background: #f5f8fb;
            }}
            QTabBar::scroller {{
                background: #ffffff;
                border: none;
                width: 0px;
            }}
        """)
        right_card_layout.addWidget(right_tabs)

        # ── Helper: make a white tab content widget ──────────────────────────
        def _make_tab_widget():
            w = QWidget()
            w.setStyleSheet("QWidget { background: #ffffff; }")
            return w

        # ── Section header helper ─────────────────────────────────────────────
        def _section_label(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: #8a95a0; font-size: 10px; font-weight: 700; "
                f"letter-spacing: 1.2px; font-family: {FONT_MONO}; "
                f"background: transparent;"
            )
            return lbl

        # ── Divider helper ────────────────────────────────────────────────────
        def _divider():
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet(f"color: {BORDER}; background: {BORDER}; max-height: 1px;")
            return line

        # ── Tab 1: Processing Options ─────────────────────────────────────────
        opts_widget = _make_tab_widget()
        opts_layout = QVBoxLayout(opts_widget)
        opts_layout.setContentsMargins(20, 16, 20, 16)
        opts_layout.setSpacing(12)

        opts_layout.addWidget(_section_label("PROCESSING OPTIONS"))
        opts_layout.addWidget(_divider())

        opts_scroll = QScrollArea()
        opts_scroll.setWidgetResizable(True)
        opts_scroll.setFrameShape(QFrame.NoFrame)
        opts_scroll.setStyleSheet("QScrollArea { background: #ffffff; border: none; }")
        opts_inner = QWidget()
        opts_inner.setStyleSheet("QWidget { background: #ffffff; }")
        opts_grid  = QGridLayout(opts_inner)
        opts_grid.setSpacing(10)
        opts_grid.setColumnStretch(1, 1)
        opts_grid.setContentsMargins(0, 4, 0, 4)

        for row_idx, opt in enumerate(DEFAULT_OPTIONS):
            lbl = QLabel(opt["label"] + ":")
            lbl.setStyleSheet(f"color: #4a5568; font-size: 12px; background: transparent;")
            opts_grid.addWidget(lbl, row_idx, 0)

            if opt["type"] == "bool":
                w = QCheckBox()
                w.setChecked(opt["value"])
            elif opt["type"] == "int":
                w = QSpinBox()
                w.setRange(0, 10_000_000)
                w.setValue(opt["value"])
            elif opt["type"] == "float":
                w = QDoubleSpinBox()
                w.setRange(0.1, 1000.0)
                w.setValue(opt["value"])
                w.setSingleStep(0.5)
            elif opt["type"] == "choice":
                w = QComboBox()
                w.addItems(opt["choices"])
                w.setCurrentText(str(opt["value"]))
            else:
                w = QLineEdit(str(opt["value"]))

            opts_grid.addWidget(w, row_idx, 1)
            self._option_widgets[opt["name"]] = (w, opt["type"])

        opts_scroll.setWidget(opts_inner)
        opts_layout.addWidget(opts_scroll)
        right_tabs.addTab(opts_widget, "⚙️  Options")

        # ── Tab 2: Status & Log ───────────────────────────────────────────────
        status_widget = _make_tab_widget()
        sl = QVBoxLayout(status_widget)
        sl.setContentsMargins(20, 16, 20, 16)
        sl.setSpacing(12)

        sl.addWidget(_section_label("TASK STATUS"))
        sl.addWidget(_divider())

        # Stat strip — white cards with subtle border
        stat_strip = QHBoxLayout()
        stat_strip.setSpacing(10)
        self.status_cards = {}
        card_defs = [
            ("status",   "Status",   "—"),
            ("progress", "Progress", "0%"),
            ("images",   "Images",   "—"),
            ("elapsed",  "Elapsed",  "00:00"),
        ]
        for key, label, default in card_defs:
            card = QWidget()
            card.setStyleSheet(
                f"QWidget {{ background: #f8fafc; border: 1px solid #e2e8f0; "
                f"border-radius: 8px; }}"
            )
            cl = QVBoxLayout(card)
            cl.setSpacing(2)
            cl.setContentsMargins(10, 10, 10, 10)
            v = QLabel(default)
            v.setStyleSheet(
                f"color: {ACCENT}; font-size: 18px; font-weight: 700; "
                f"font-family: {FONT_MONO}; background: transparent; border: none;"
            )
            v.setAlignment(Qt.AlignCenter)
            n = QLabel(label.upper())
            n.setStyleSheet(
                f"color: #94a3b8; font-size: 9px; letter-spacing: 0.8px; "
                f"background: transparent; border: none;"
            )
            n.setAlignment(Qt.AlignCenter)
            cl.addWidget(v)
            cl.addWidget(n)
            stat_strip.addWidget(card)
            self.status_cards[key] = v
        sl.addLayout(stat_strip)

        # Progress bar row
        prog_row = QHBoxLayout()
        prog_row.setSpacing(10)
        self.proc_bar = QProgressBar()
        self.proc_bar.setRange(0, 100)
        self.proc_pct_lbl = QLabel("0%")
        self.proc_pct_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-weight: 700; "
            f"font-family: {FONT_MONO}; min-width: 34px; background: transparent;"
        )
        prog_row.addWidget(self.proc_bar, 1)
        prog_row.addWidget(self.proc_pct_lbl)
        sl.addLayout(prog_row)

        sl.addWidget(_section_label("CONSOLE OUTPUT"))
        sl.addWidget(_divider())

        self.odm_log = QTextEdit()
        self.odm_log.setReadOnly(True)
        self.odm_log.setStyleSheet(
            f"QTextEdit {{ background: #0d1117; color: #8fb0c8; "
            f"border: 1px solid #1e2a38; border-radius: 6px; "
            f"font-family: {FONT_MONO}; font-size: 11px; padding: 6px; }}"
        )
        sl.addWidget(self.odm_log, stretch=1)
        right_tabs.addTab(status_widget, "📊  Status")

        # ── Tab 3: Results ────────────────────────────────────────────────────
        results_widget = _make_tab_widget()
        rl = QVBoxLayout(results_widget)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(12)

        res_top = QHBoxLayout()
        res_top.addWidget(_section_label("OUTPUT FILES"))
        res_top.addStretch()
        self.btn_pick_results = QPushButton("…  Load Results")
        self.btn_pick_results.setObjectName("secondary")
        self.btn_pick_results.setCursor(Qt.PointingHandCursor)
        self.btn_pick_results.setToolTip("Load an existing NodeODM results folder")
        self.btn_pick_results.clicked.connect(self.pick_results_folder)
        res_top.addWidget(self.btn_pick_results)
        rl.addLayout(res_top)
        rl.addWidget(_divider())

        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["File", "Size", "Open"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setMaximumHeight(180)
        self.results_table.setStyleSheet(
            f"QTableWidget {{ background: #ffffff; border: 1px solid {BORDER}; "
            f"border-radius: 7px; alternate-background-color: #f8fafc; }}"
        )
        rl.addWidget(self.results_table)

        # Action buttons — horizontal toolbar strip
        btn_bar = QWidget()
        btn_bar.setStyleSheet(
            f"QWidget {{ background: #f8fafc; border: 1px solid {BORDER}; "
            f"border-radius: 7px; padding: 4px; }}"
        )
        btn_bar_layout = QHBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(6, 4, 6, 4)
        btn_bar_layout.setSpacing(6)

        self.btn_open_folder = QPushButton("📂  Folder")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_folder.clicked.connect(self.open_results_folder)

        self.btn_view_ortho = QPushButton("🗺️  Orthophoto")
        self.btn_view_ortho.setEnabled(False)
        self.btn_view_ortho.setCursor(Qt.PointingHandCursor)
        self.btn_view_ortho.clicked.connect(self.view_orthophoto)

        self.btn_view_3d = QPushButton("🏗️  3D Model")
        self.btn_view_3d.setEnabled(False)
        self.btn_view_3d.setCursor(Qt.PointingHandCursor)
        self.btn_view_3d.clicked.connect(self.view_3d_model)

        self.btn_open_3d_browser = QPushButton("🌐  In Browser")
        self.btn_open_3d_browser.setEnabled(False)
        self.btn_open_3d_browser.setCursor(Qt.PointingHandCursor)
        self.btn_open_3d_browser.setToolTip(
            "Open 3D viewer in your default browser (recommended for large models)")
        self.btn_open_3d_browser.clicked.connect(self.open_3d_in_browser)

        for btn in [self.btn_open_folder, self.btn_view_ortho,
                    self.btn_view_3d, self.btn_open_3d_browser]:
            btn_bar_layout.addWidget(btn)
        btn_bar_layout.addStretch()
        rl.addWidget(btn_bar)

        # Preview section
        viewer_hdr_row = QHBoxLayout()
        viewer_hdr_row.addWidget(_section_label("PREVIEW"))
        viewer_hdr_row.addStretch()
        self.viewer_label = QLabel("PREVIEW")
        self.viewer_label.setStyleSheet(
            f"color: #8a95a0; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1.2px; font-family: {FONT_MONO}; background: transparent;"
        )
        rl.addLayout(viewer_hdr_row)
        rl.addWidget(_divider())

        self.web_viewer = QWebEngineView()
        self.web_viewer.setMinimumHeight(280)
        self.web_viewer.setStyleSheet(
            "QWebEngineView { border-radius: 7px; border: 1px solid #e2e8f0; }"
        )
        try:
            ws = self.web_viewer.settings()
            ws.setAttribute(QWebEngineSettings.WebGLEnabled, True)
            ws.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
            ws.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            ws.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            ws.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            ws.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        except Exception:
            pass
        self.web_viewer.setHtml(self._viewer_placeholder())
        rl.addWidget(self.web_viewer, stretch=1)
        right_tabs.addTab(results_widget, "📁  Results")

        # ── Tab 4: Tasks List ─────────────────────────────────────────────────
        tasks_widget = _make_tab_widget()
        tl = QVBoxLayout(tasks_widget)
        tl.setContentsMargins(20, 16, 20, 16)
        tl.setSpacing(12)

        tasks_top = QHBoxLayout()
        tasks_top.addWidget(_section_label("SERVER TASKS"))
        tasks_top.addStretch()
        self.btn_refresh_tasks = QPushButton("↻  Refresh")
        self.btn_refresh_tasks.setObjectName("secondary")
        self.btn_refresh_tasks.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_tasks.clicked.connect(self.refresh_tasks)
        tasks_top.addWidget(self.btn_refresh_tasks)
        tl.addLayout(tasks_top)
        tl.addWidget(_divider())

        self.tasks_table = QTableWidget(0, 5)
        self.tasks_table.setHorizontalHeaderLabels(
            ["UUID", "Name", "Status", "Images", "Actions"])
        self.tasks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tasks_table.setAlternatingRowColors(True)
        self.tasks_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tasks_table.verticalHeader().setVisible(False)
        self.tasks_table.setStyleSheet(
            f"QTableWidget {{ background: #ffffff; border: 1px solid {BORDER}; "
            f"border-radius: 7px; alternate-background-color: #f8fafc; }}"
        )
        tl.addWidget(self.tasks_table)
        right_tabs.addTab(tasks_widget, "📋  Tasks")

        self.right_tabs = right_tabs
        splitter.addWidget(left)
        splitter.addWidget(right_card)
        splitter.setSizes([300, 900])
        root.addWidget(splitter)

    # ── Connect ───────────────────────────────────────────────────────────────
    def do_connect(self):
        host  = self.host_edit.text().strip() or "localhost"
        port  = self.port_spin.value()
        token = self.token_edit.text().strip()
        self.client = NodeODMClient(host, port, token)
        try:
            info    = self.client.info()
            version = info.get("version", "?")
            engine  = info.get("engine", "odm")
            max_img = info.get("maxImages") or "∞"
            self.conn_status.setText("● Connected")
            self.conn_status.setObjectName("status_ok")
            self.conn_status.setStyleSheet(
                f"color:{ACCENT3}; font-family:{FONT_MONO}; "
                f"font-size:11px; font-weight:700;"
            )
            self.node_info_lbl.setText(
                f"v{version}  ·  {engine}  ·  max {max_img} imgs"
            )
            self.btn_run.setEnabled(True)
            self._log(f"Connected to NodeODM v{version} at {host}:{port}")
            self.refresh_tasks()
        except Exception as e:
            self.conn_status.setText("✗  Failed")
            self.conn_status.setObjectName("status_err")
            self.conn_status.setStyleSheet(
                f"color:{ACCENT2}; font-family:{FONT_MONO}; font-size:11px;"
            )
            self.node_info_lbl.setText(str(e))
            self._log(f"Connection failed: {e}")
            self.btn_run.setEnabled(False)

    # ── Images ────────────────────────────────────────────────────────────────
    def add_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Drone Images", "",
            "Images (*.jpg *.jpeg *.png *.tif *.tiff);;All Files (*)"
        )
        if paths:
            self._add_paths(paths)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if folder:
            exts  = {".jpg", ".jpeg", ".png", ".tif", ".tiff",
                     ".JPG", ".JPEG", ".PNG", ".TIF", ".TIFF"}
            paths = sorted(
                str(p) for p in Path(folder).iterdir()
                if p.suffix in exts
            )
            self._add_paths(paths)

    def _add_paths(self, paths):
        existing = set(self.image_paths)
        added    = 0
        for p in paths:
            if p not in existing:
                self.image_paths.append(p)
                self.img_list.addItem(os.path.basename(p))
                added += 1
        self.img_count_lbl.setText(
            f"{len(self.image_paths)} image(s) selected")
        self._log(f"Added {added} images ({len(self.image_paths)} total)")

    def clear_images(self):
        self.image_paths.clear()
        self.img_list.clear()
        self.img_count_lbl.setText("0 images selected")

    # ── Output folder ─────────────────────────────────────────────────────────
    def select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_dir = folder
            self.out_edit.setText(folder)

    # ── Collect options ───────────────────────────────────────────────────────
    def _collect_options(self):
        opts = {}
        for opt in DEFAULT_OPTIONS:
            name   = opt["name"]
            w, typ = self._option_widgets[name]
            if typ == "bool":
                opts[name] = w.isChecked()
            elif typ == "int":
                opts[name] = w.value()
            elif typ == "float":
                opts[name] = w.value()
            elif typ == "choice":
                opts[name] = w.currentText()
            else:
                opts[name] = w.text()
        return opts

    # ── File / folder helpers ──────────────────────────────────────────────────
    def _first_existing(self, base_dir, candidates):
        for rel in candidates:
            full = os.path.join(base_dir, rel)
            if os.path.exists(full):
                return full
        return None

    def _find_under_results(self, suffix):
        if not getattr(self, "_results_dir", ""):
            return None
        for root_dir, _dirs, files in os.walk(self._results_dir):
            for fn in files:
                if fn.lower().endswith(suffix.lower()):
                    return os.path.join(root_dir, fn)
        return None

    # ── Local HTTP server for results ─────────────────────────────────────────
    def _ensure_results_http_server(self, root_dir: str) -> str:
        """
        Serve the results directory over http://127.0.0.1:<port>/.
        CORS headers are added so QWebEngineView and external browsers can
        fetch assets (GLB etc.) without security errors.
        """
        if not root_dir or not os.path.isdir(root_dir):
            raise RuntimeError(f"Invalid results directory: {root_dir}")

        if self._httpd and self._http_root == root_dir and self._http_port:
            return f"http://127.0.0.1:{self._http_port}"

        self._stop_results_http_server()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        _host, port = sock.getsockname()
        sock.close()

        handler = partial(_CORSHandler, directory=root_dir)
        httpd   = ThreadingHTTPServer(("127.0.0.1", port), handler)
        httpd.daemon_threads = True

        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()

        self._httpd      = httpd
        self._http_thread = t
        self._http_root  = root_dir
        self._http_port  = port
        self._log(f"Local HTTP server started on port {port}")
        return f"http://127.0.0.1:{port}"

    def _stop_results_http_server(self):
        try:
            if self._httpd:
                self._httpd.shutdown()
                self._httpd.server_close()
        except Exception:
            pass
        self._httpd       = None
        self._http_thread = None
        self._http_root   = ""
        self._http_port   = None

    def _resolve_results_root(self, extract_dir: str) -> str:
        """
        NodeODM all.zip contents vary by version/config.
        Returns the deepest folder that looks like an ODM results root.
        """
        if not extract_dir or not os.path.isdir(extract_dir):
            return extract_dir

        def looks_like_odm_root(d: str) -> bool:
            if not os.path.isdir(d):
                return False
            expected_dirs = [
                "odm_orthophoto", "odm_texturing", "odm_dem",
                "odm_georeferencing", "odm_report", "reconstruction",
                "opensfm", "submodels",
            ]
            if any(os.path.isdir(os.path.join(d, x)) for x in expected_dirs):
                return True
            try:
                for fn in os.listdir(d):
                    low = fn.lower()
                    if low.endswith((".glb", ".obj", ".laz", ".las",
                                     ".tif", ".tiff", ".pdf")):
                        return True
                    if low.startswith("odm_") and low.endswith(".json"):
                        return True
            except Exception:
                pass
            return False

        if looks_like_odm_root(extract_dir):
            return extract_dir

        nested = os.path.join(extract_dir, "odm_results")
        if looks_like_odm_root(nested):
            return nested

        try:
            children = [
                os.path.join(extract_dir, n)
                for n in os.listdir(extract_dir)
                if not n.startswith(".")
            ]
            subdirs = [c for c in children if os.path.isdir(c)]
            if len(subdirs) == 1:
                only = subdirs[0]
                if looks_like_odm_root(only):
                    return only
                nested2 = os.path.join(only, "odm_results")
                if looks_like_odm_root(nested2):
                    return nested2
        except Exception:
            pass

        try:
            for root_dir, dirs, _files in os.walk(extract_dir):
                depth = os.path.relpath(root_dir, extract_dir).count(os.sep)
                if depth > 3:
                    dirs[:] = []
                    continue
                if looks_like_odm_root(root_dir):
                    return root_dir
        except Exception:
            pass

        return extract_dir

    # ── Start task ────────────────────────────────────────────────────────────
    def start_task(self):
        if not self.client:
            self._log("Not connected to NodeODM"); return
        if not self.image_paths:
            self._log("No images selected"); return
        output = self.out_edit.text().strip()
        if not output:
            self._log("No output folder selected"); return
        self.output_dir = output
        os.makedirs(output, exist_ok=True)

        opts = self._collect_options()
        name = self.task_name_edit.text().strip() or "BuildScan Task"

        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.upload_bar.setVisible(True)
        self.upload_bar.setValue(0)
        self.right_tabs.setCurrentIndex(1)

        self.upload_worker = UploadWorker(
            self.client, self.image_paths, opts, name)
        self.upload_worker.progress.connect(self._on_upload_progress)
        self.upload_worker.log.connect(self._log)
        self.upload_worker.finished.connect(self._on_upload_done)
        self.upload_worker.error.connect(self._on_error)
        self.upload_worker.start()

    @pyqtSlot(int, int)
    def _on_upload_progress(self, n, total):
        pct = int(n / total * 100) if total > 0 else 0
        self.upload_bar.setValue(pct)
        self.upload_lbl.setText(f"Uploading {n}/{total}")

    @pyqtSlot(str)
    def _on_upload_done(self, uuid):
        self.current_uuid = uuid
        self.upload_bar.setVisible(False)
        self.upload_lbl.setText("")
        self._log(f"Processing started. Task UUID: {uuid}")
        self._update_status_cards({
            "status":         {"code": 20},
            "imagesCount":    len(self.image_paths),
            "processingTime": 0,
            "progress":       0,
        })
        self.poll_worker = PollingWorker(self.client, uuid, poll_interval=5)
        self.poll_worker.status_update.connect(self._on_status_update)
        self.poll_worker.log_lines.connect(self._on_log_lines)
        self.poll_worker.finished.connect(self._on_task_finished)
        self.poll_worker.error.connect(self._on_error)
        self.poll_worker.start()

    @pyqtSlot(dict)
    def _on_status_update(self, info):
        self._update_status_cards(info)

    @pyqtSlot(list)
    def _on_log_lines(self, lines):
        for line in lines:
            self.odm_log.append(line)
        self.odm_log.verticalScrollBar().setValue(
            self.odm_log.verticalScrollBar().maximum())

    @pyqtSlot(dict)
    def _on_task_finished(self, info):
        code = info.get("status", {}).get("code", 0)
        name = TASK_STATUS.get(code, "Unknown")
        self._update_status_cards(info)

        if code == 40:
            self._log("✓ Processing complete! Downloading results…")
            self.dl_worker = DownloadWorker(
                self.client, self.current_uuid, self.output_dir)
            self.dl_worker.progress.connect(self._on_dl_progress)
            self.dl_worker.log.connect(self._log)
            self.dl_worker.finished.connect(self._on_download_done)
            self.dl_worker.error.connect(self._on_error)
            self.dl_worker.start()
        else:
            self._log(f"Task ended with status: {name}")
            self._reset_run_buttons()

    @pyqtSlot(int)
    def _on_dl_progress(self, pct):
        self.proc_bar.setValue(pct)
        self.proc_pct_lbl.setText(f"{pct}%")

    @pyqtSlot(str)
    def _on_download_done(self, extract_dir):
        self._extract_dir = extract_dir
        root = self._resolve_results_root(extract_dir)
        self._results_dir = root
        if root != extract_dir:
            self._log(f"Results root resolved: {root}")
        else:
            self._log(f"Results ready at: {extract_dir}")
        self._reset_run_buttons()
        self.btn_open_folder.setEnabled(True)
        self._populate_results(root)
        self.right_tabs.setCurrentIndex(2)
        self.refresh_tasks()

    @pyqtSlot(str)
    def _on_error(self, msg):
        self._log(f"ERROR: {msg}")
        self._reset_run_buttons()

    # ── Cancel ────────────────────────────────────────────────────────────────
    def cancel_task(self):
        if self.poll_worker:
            self.poll_worker.stop()
        if self.current_uuid and self.client:
            try:
                self.client.cancel_task(self.current_uuid)
                self._log(f"Task {self.current_uuid} cancelled")
            except Exception as e:
                self._log(f"Cancel error: {e}")
        self._reset_run_buttons()

    def _reset_run_buttons(self):
        self.btn_run.setEnabled(bool(self.client))
        self.btn_cancel.setEnabled(False)
        self.upload_bar.setVisible(False)
        self.upload_lbl.setText("")

    # ── Status cards ──────────────────────────────────────────────────────────
    def _update_status_cards(self, info):
        code     = info.get("status", {}).get("code", 0)
        progress = info.get("progress", 0) or 0
        images   = info.get("imagesCount", "?")
        elapsed  = info.get("processingTime", 0) or 0

        icon   = TASK_STATUS_ICON.get(code, "")
        status = TASK_STATUS.get(code, "—")
        self.status_cards["status"].setText(f"{icon} {status}")
        self.status_cards["progress"].setText(f"{int(progress)}%")
        self.status_cards["images"].setText(str(images))

        mins, secs = divmod(int(elapsed / 1000), 60)
        hrs,  mins = divmod(mins, 60)
        self.status_cards["elapsed"].setText(
            f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs
            else f"{mins:02d}:{secs:02d}"
        )
        self.proc_bar.setValue(int(progress))
        self.proc_pct_lbl.setText(f"{int(progress)}%")

        # Colour status card by outcome
        colour = {40: ACCENT3, 30: ACCENT2, 50: TXT_LOW}.get(code, ACCENT)
        self.status_cards["status"].setStyleSheet(
            f"color:{colour}; font-size:14px; font-weight:700; "
            f"font-family:{FONT_MONO};"
        )

    # ── Results ───────────────────────────────────────────────────────────────
    def _populate_results(self, extract_dir):
        self.results_table.setRowCount(0)
        self._results_dir = extract_dir
        if not extract_dir or not os.path.isdir(extract_dir):
            self._log(f"Results directory not found: {extract_dir}")
            self.btn_open_folder.setEnabled(
                bool(self._extract_dir) or bool(self.output_dir))
            return

        interesting = [
            "odm_orthophoto/odm_orthophoto.tif",
            "odm_orthophoto/odm_orthophoto.png",
            "odm_dem/dsm.tif",
            "odm_dem/dtm.tif",
            "odm_texturing/odm_textured_model.obj",
            "odm_texturing/odm_textured_model.glb",
            "odm_georeferencing/odm_georeferenced_model.laz",
            "odm_georeferencing/odm_georeferenced_model.las",
            "odm_report/report.pdf",
        ]
        found = []
        for rel in interesting:
            full = os.path.join(extract_dir, rel)
            if os.path.exists(full):
                found.append((rel, full))

        for root_dir, dirs, files in os.walk(extract_dir):
            for fn in files:
                full = os.path.join(root_dir, fn)
                rel  = os.path.relpath(full, extract_dir)
                if (rel, full) not in found:
                    found.append((rel, full))
            if len(found) > 200:
                break

        for rel, full in found:
            row     = self.results_table.rowCount()
            self.results_table.insertRow(row)
            size_mb = os.path.getsize(full) / 1e6
            self.results_table.setItem(row, 0, QTableWidgetItem(rel))
            self.results_table.setItem(
                row, 1, QTableWidgetItem(f"{size_mb:.1f} MB"))
            btn = QPushButton("Open")
            btn.setStyleSheet(
                f"background:transparent; color:{ACCENT}; "
                f"border:1px solid {BORDER}; border-radius:4px; "
                f"padding:2px 8px; font-size:10px;"
            )
            btn.clicked.connect(
                lambda _, p=full: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(p)))
            self.results_table.setCellWidget(row, 2, btn)

        self.btn_open_folder.setEnabled(True)
        if not found:
            self._log("No output files found — check ZIP extraction.")

        ortho_png = self._first_existing(extract_dir, [
            "odm_orthophoto/odm_orthophoto.png",
            "orthophoto/odm_orthophoto.png",
            "odm_orthophoto.png",
        ])
        ortho_tif = self._first_existing(extract_dir, [
            "odm_orthophoto/odm_orthophoto.tif",
            "orthophoto/odm_orthophoto.tif",
            "odm_orthophoto.tif",
        ])
        glb_candidates = [
            "odm_texturing/odm_textured_model.glb",
            "odm_texturing_25d/odm_25dtextured_model.glb",
            "odm_texturing/odm_textured_model_geo.glb",
            "reconstruction/odm_textured_model.glb",
        ]
        glb_path = (self._first_existing(extract_dir, glb_candidates)
                    or self._find_under_results(".glb"))

        if (ortho_png and os.path.exists(ortho_png)) or \
           (ortho_tif and os.path.exists(ortho_tif)):
            self.btn_view_ortho.setEnabled(True)

        if glb_path:
            self.btn_view_3d.setEnabled(True)
            self.btn_open_3d_browser.setEnabled(True)
        else:
            self._log("GLB not found yet — 3D view enabled when available.")

        if ortho_png and os.path.exists(ortho_png):
            self.view_orthophoto()

    def open_results_folder(self):
        candidates = [
            getattr(self, "_results_dir", ""),
            getattr(self, "_extract_dir", ""),
            getattr(self, "output_dir", ""),
        ]
        path = next((p for p in candidates if p and os.path.exists(p)), "")
        if not path:
            self._log("No results folder available yet.")
            return
        url = QUrl.fromLocalFile(os.path.abspath(path))
        ok  = QDesktopServices.openUrl(url)
        if not ok:
            try:
                QApplication.clipboard().setText(os.path.abspath(path))
                self._log(f"Copied path to clipboard: {path}")
            except Exception:
                self._log(f"Could not open folder: {path}")

    def pick_results_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select NodeODM Results Folder")
        if not folder:
            return
        root = self._resolve_results_root(folder)
        self._extract_dir = folder
        self._results_dir = root
        self._log(f"Selected results folder: {root}")
        self.btn_open_folder.setEnabled(True)
        self._populate_results(root)
        self.right_tabs.setCurrentIndex(2)

    # ── Viewer: Orthophoto ─────────────────────────────────────────────────────
    def view_orthophoto(self):
        if not getattr(self, "_results_dir", ""):
            self._log("No results downloaded yet"); return

        ortho_png = self._first_existing(self._results_dir, [
            "odm_orthophoto/odm_orthophoto.png",
            "orthophoto/odm_orthophoto.png",
            "odm_orthophoto.png",
        ])
        if not ortho_png or not os.path.exists(ortho_png):
            ortho_tif = (
                self._first_existing(self._results_dir, [
                    "odm_orthophoto/odm_orthophoto.tif",
                    "orthophoto/odm_orthophoto.tif",
                    "odm_orthophoto.tif",
                ]) or self._find_under_results(".tif")
            )
            if ortho_tif:
                self._log("PNG not found — opening TIFF externally.")
                QDesktopServices.openUrl(QUrl.fromLocalFile(ortho_tif))
            else:
                self._log("Orthophoto not found in results")
            return

        base    = self._ensure_results_http_server(self._results_dir)
        rel_img = os.path.relpath(ortho_png, self._results_dir).replace(os.sep, "/")
        img_url = f"{base}/{quote(rel_img)}"

        html = _build_orthophoto_html(
            img_url, ACCENT, BG_DEEP, BG_PANEL, TXT_LOW, FONT_MONO)

        viewer_path = os.path.join(self._results_dir, "_ortho_viewer.html")
        with open(viewer_path, "w", encoding="utf-8") as f:
            f.write(html)

        self.web_viewer.setUrl(QUrl(f"{base}/_ortho_viewer.html"))
        self.viewer_label.setText("[ ORTHOPHOTO PREVIEW ]")
        self._log(f"Orthophoto loaded: {os.path.basename(ortho_png)}")

    # ── Viewer: 3D Model ──────────────────────────────────────────────────────
    def view_3d_model(self):
        """
        Load a GLB model using Three.js + GLTFLoader served from CDN.
        The viewer HTML is written to the results directory and served via
        local HTTP (avoids file:// security restrictions on all platforms).
        """
        if not getattr(self, "_results_dir", ""):
            self._log("No results downloaded yet"); return

        candidates = [
            "odm_texturing/odm_textured_model.glb",
            "odm_texturing_25d/odm_25dtextured_model.glb",
            "odm_texturing/odm_textured_model_geo.glb",
            "reconstruction/odm_textured_model.glb",
        ]
        glb = (self._first_existing(self._results_dir, candidates)
               or self._find_under_results(".glb"))

        if glb is None:
            tex_dir = os.path.join(self._results_dir, "odm_texturing")
            if os.path.isdir(tex_dir):
                self._log(f"GLB not found. Files in odm_texturing/: "
                          f"{os.listdir(tex_dir)}")
            else:
                self._log(f"odm_texturing/ not found in {self._results_dir}")
            return

        file_size_mb = os.path.getsize(glb) / 1e6
        self._log(f"Loading 3D model: {os.path.basename(glb)} "
                  f"({file_size_mb:.1f} MB)")

        base    = self._ensure_results_http_server(self._results_dir)
        rel_glb = os.path.relpath(glb, self._results_dir).replace(os.sep, "/")
        glb_url = f"{base}/{quote(rel_glb)}"

        html = _build_3d_viewer_html(
            glb_url, ACCENT, BG_DEEP, BG_PANEL, TXT_LOW, TXT_MID, FONT_MONO)

        viewer_path = os.path.join(self._results_dir, "_3d_viewer.html")
        with open(viewer_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Always enable browser fallback once we have the viewer file
        self.btn_open_3d_browser.setEnabled(True)

        try:
            self.web_viewer.loadFinished.disconnect()
        except Exception:
            pass
        self.web_viewer.loadFinished.connect(self._on_3d_load_finished)
        self.web_viewer.setUrl(QUrl(f"{base}/_3d_viewer.html"))
        self.viewer_label.setText(
            "[ 3D MODEL  ·  drag=rotate  ·  scroll=zoom  ·  right=pan ]"
        )

    @pyqtSlot(bool)
    def _on_3d_load_finished(self, ok):
        if not ok:
            self._log(
                "Web viewer failed to load 3D viewer HTML. "
                "Try 'Open 3D in Browser' — it may work better in your system browser."
            )
            return
        self._log("3D viewer loaded. If the model appears blank, ensure "
                  "internet access for Three.js CDN or use 'Open in Browser'.")

    def open_3d_in_browser(self):
        if not getattr(self, "_results_dir", ""):
            self._log("No results folder available yet."); return
        try:
            base = self._ensure_results_http_server(self._results_dir)
            ok   = QDesktopServices.openUrl(QUrl(f"{base}/_3d_viewer.html"))
            if not ok:
                self._log("Could not open browser automatically.")
        except Exception as e:
            self._log(f"Browser open error: {e}")

    # ── Tasks list ────────────────────────────────────────────────────────────
    def refresh_tasks(self):
        if not self.client:
            return
        try:
            tasks = self.client.list_tasks()
            self.tasks_table.setRowCount(0)
            for t in tasks:
                uuid   = t.get("uuid", "")
                name   = t.get("name", "")
                code   = t.get("status", {}).get("code", 0)
                icon   = TASK_STATUS_ICON.get(code, "")
                status = f"{icon} {TASK_STATUS.get(code, '?')}"
                images = str(t.get("imagesCount", "?"))

                row = self.tasks_table.rowCount()
                self.tasks_table.insertRow(row)
                self.tasks_table.setItem(row, 0, QTableWidgetItem(uuid[:12] + "…"))
                self.tasks_table.setItem(row, 1, QTableWidgetItem(name))

                status_item = QTableWidgetItem(status)
                colour = {40: ACCENT3, 30: ACCENT2, 20: ACCENT}.get(code, TXT_MID)
                status_item.setForeground(QColor(colour))
                self.tasks_table.setItem(row, 2, status_item)
                self.tasks_table.setItem(row, 3, QTableWidgetItem(images))

                del_btn = QPushButton("Delete")
                del_btn.setStyleSheet(
                    f"color:{ACCENT2}; border:1px solid {ACCENT2}; "
                    f"border-radius:4px; padding:2px 8px; font-size:10px; "
                    f"background:transparent;"
                )
                del_btn.setCursor(Qt.PointingHandCursor)
                del_btn.clicked.connect(lambda _, u=uuid: self._delete_task(u))
                self.tasks_table.setCellWidget(row, 4, del_btn)

        except Exception as e:
            self._log(f"Could not list tasks: {e}")

    def _delete_task(self, uuid):
        try:
            self.client.delete_task(uuid)
            self._log(f"Deleted task {uuid[:12]}…")
            self.refresh_tasks()
        except Exception as e:
            self._log(f"Delete error: {e}")

    # ── Viewer placeholder ────────────────────────────────────────────────────
    def _viewer_placeholder(self):
        return f"""<!DOCTYPE html>
<html><body style='margin:0; background:{BG_DEEP};
  display:flex; align-items:center; justify-content:center; height:100vh;'>
<div style='background:{BG_PANEL}; border:1px solid {BORDER};
  border-radius:12px; padding:20px 24px; color:{TXT_LOW};
  font-family:{FONT_MONO}; text-align:center; font-size:12px;
  max-width:440px; line-height:1.7;'>
  PREVIEW<br><br>
  Orthophoto and 3D model previews appear here<br>
  after processing + download complete.<br><br>
  <span style='color:{TXT_LOW}; font-size:10px;'>
  Use <b style='color:{ACCENT}'>🗺️ Orthophoto</b> or
  <b style='color:{ACCENT}'>🏗️ 3D Model</b> to load results.</span>
</div></body></html>"""

    # ── Utility ───────────────────────────────────────────────────────────────
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.odm_log.append(f"[{ts}] {msg}")
        self.odm_log.verticalScrollBar().setValue(
            self.odm_log.verticalScrollBar().maximum())
        if self.logger:
            try:
                self.logger.info(msg)
            except Exception:
                pass

    def closeEvent(self, event):
        for worker in (self.upload_worker, self.poll_worker, self.dl_worker):
            if worker and worker.isRunning():
                if hasattr(worker, "stop"):
                    worker.stop()
                worker.wait(2000)
        self._stop_results_http_server()
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
#  Helper factory functions (keep QWidget constructors clean)
# ─────────────────────────────────────────────────────────────────────────────
def _make_line_edit(text="", placeholder=""):
    w = QLineEdit(text)
    if placeholder:
        w.setPlaceholderText(placeholder)
    return w


def _make_port_spin():
    w = QSpinBox()
    w.setRange(1, 65535)
    w.setValue(3000)
    return w