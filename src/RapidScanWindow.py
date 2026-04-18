
import os
import sys
import cv2
import json
import csv
import queue
import tempfile
import threading
import time
from datetime import datetime
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

from PyQt5.QtCore import Qt, QUrl, QThread, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QImage, QPixmap, QColor, QFont, QPalette

# WebEngine MUST be imported before QApplication / QtWidgets
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPushButton,
    QLabel, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QFrame, QProgressBar, QSlider, QSpinBox, QCheckBox,
    QTextEdit, QComboBox, QGroupBox, QTabWidget, QDoubleSpinBox,
    QGridLayout, QScrollArea, QSizePolicy, QApplication,
)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

try:
    from sklearn.cluster import DBSCAN
    _SKLEARN_OK = True
except ImportError:
    _SKLEARN_OK = False

try:
    from risk_engine import (
        ScenarioParams, BuildingRecord, BuildingResult,
        run_scenario, portfolio_summary,
        CLASS_TO_ARCHETYPE, FRAGILITY_LIB, LOSS_RATIO,
        boore_atkinson_2008_pga, fragility_prob,
    )
    _RISK_OK = True
    _RISK_ERR = ""
except Exception as _risk_err:
    _RISK_OK = False
    _RISK_ERR = str(_risk_err)
    # Stub so references don't crash at parse time
    FRAGILITY_LIB = {}
    def fragility_prob(pga, median, beta): return 0.0

# ── Palette ───────────────────────────────────────────────────────────────────
BG_DEEP   = "#f0f2f5"
BG_PANEL  = "#ffffff"
BG_CARD   = "#f8f9fa"
BORDER    = "#e2e5ea"
ACCENT    = "#1DA1F2"
ACCENT_H  = "#1A91DA"
ACCENT2   = "#e53935"
ACCENT3   = "#43A047"
TXT_HI    = "#1a1a2e"
TXT_MID   = "#4a5568"
TXT_LOW   = "#a0aec0"
FONT_MONO = "Menlo, Consolas, 'Courier New'"

DS_COLORS = {
    "None": "#43A047",
    "DS1":  "#facc15",
    "DS2":  "#f97316",
    "DS3":  "#ef4444",
    "DS4":  "#7f1d1d",
}

MPL_STYLE = {
    "axes.facecolor":   BG_CARD,
    "figure.facecolor": BG_PANEL,
    "axes.edgecolor":   BORDER,
    "axes.labelcolor":  TXT_MID,
    "xtick.color":      TXT_LOW,
    "ytick.color":      TXT_LOW,
    "text.color":       TXT_HI,
    "grid.color":       BORDER,
    "grid.alpha":       0.5,
    "lines.linewidth":  1.8,
}

CLASS_NAMES = [
    "AD_H1", "AD_H2", "MR_H1 flat roof", "MR_H1 gable roof",
    "MR_H2 flat roof", "MR_H2 gable roof", "MR_H3", "Metal_H1",
    "Non_Building", "RCC_H1 flat roof", "RCC_H1 gable roof",
    "RCC_H2 flat roof", "RCC_H2 gable roof", "RCC_H3 flat roof",
    "RCC_H3 gable roof", "RCC_H4 flat roof", "RCC_H4 gable roof",
    "RCC_H5", "RCC_H6", "RCC_OS_H1", "RCC_OS_H2", "RCC_OS_H3",
    "RCC_OS_H4", "Timber",
]

# Default GPS origin (Mandi, HP). Override via RapidScanWindow(gps_origin=(lat, lon)).
DEFAULT_GPS_ORIGIN = (31.7085, 76.9320)

# Approx metres per degree at ~32°N latitude
_M_PER_DEG_LAT = 111_320.0
_M_PER_DEG_LON = 111_320.0 * 0.848   # cos(32°) ≈ 0.848


def building_coords(building_id: int, origin_lat: float, origin_lon: float,
                    grid_spacing_m: float = 10.0) -> tuple:
    """
    Convert a sequential building ID to approximate GPS coordinates by
    arranging buildings on a small grid around the origin.

    Arranges in a square spiral: row = id // cols, col = id % cols.
    spacing_m controls physical gap between adjacent detections.
    """
    cols = 20  # wrap after 20 columns (~200 m wide strip)
    row  = building_id // cols
    col  = building_id % cols
    dlat = (row * grid_spacing_m) / _M_PER_DEG_LAT
    dlon = (col * grid_spacing_m) / _M_PER_DEG_LON
    return (origin_lat + dlat, origin_lon + dlon)


def js_escape(s: str) -> str:
    """Escape a string for safe embedding inside a JS single-quoted string."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


def open_video(path: str) -> cv2.VideoCapture:
    """
    Try multiple OpenCV backends until one opens and reads successfully.
    Safely skips platform-specific backends that don't exist.
    """
    backend_names = ["CAP_ANY", "CAP_FFMPEG", "CAP_AVFOUNDATION", "CAP_GSTREAMER"]
    backends = []
    for name in backend_names:
        val = getattr(cv2, name, None)
        if val is not None:
            backends.append(val)

    for bk in backends:
        try:
            cap = cv2.VideoCapture(path, bk)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    return cap
            cap.release()
        except Exception:
            continue

    # Bare fallback
    cap = cv2.VideoCapture(path)
    return cap


def calculate_iou(box1, box2):
    y1_1, x1_1, y2_1, x2_1 = box1
    y1_2, x1_2, y2_2, x2_2 = box2
    iy1, ix1 = max(y1_1, y1_2), max(x1_1, x1_2)
    iy2, ix2 = min(y2_1, y2_2), min(x2_1, x2_2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    a1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    a2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0


# ─────────────────────────────────────────────────────────────────────────────
#  VideoProcessor — background QThread
# ─────────────────────────────────────────────────────────────────────────────
class VideoProcessor(QThread):
    """
    Runs detection + classification in a background thread.

    Signal contract
    ───────────────
    frame_ready(ndarray)          — throttled preview frames (~15 fps)
    detection_made(float, float, str, int)
                                  — emitted ONCE per unique building after
                                    DBSCAN dedup + BEiT classification
                                    args: lat, lon, class_name, building_id
    status_update(str)            — log messages
    progress_update(int)          — 0-100 progress
    finished()                    — thread done
    """
    frame_ready     = pyqtSignal(np.ndarray)
    detection_made  = pyqtSignal(float, float, str, int)   # lat, lon, cls, id
    status_update   = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    finished        = pyqtSignal()

    def __init__(self, video_path, checkpoint_path, class_names,
                 detection_fps=30, gps_origin=DEFAULT_GPS_ORIGIN):
        super().__init__()
        self.video_path      = video_path
        self.checkpoint_path = checkpoint_path
        self.class_names     = class_names
        self.detection_fps   = detection_fps
        self.gps_origin      = gps_origin   # (lat, lon) of scene centre
        self.running         = True
        self._next_id        = 0
        self.output_folder   = None
        self.crops_dir       = None
        self.dup_dir         = None
        self.orig_dir        = None
        self.output_video_path = None

        # Frame throttle: only emit preview at ~15 fps
        self._preview_interval_s = 1.0 / 15.0
        self._last_preview_t     = 0.0

    # ── Lazy-load TF detector ─────────────────────────────────────────────
    def _load_detector(self):
        self.status_update.emit("Loading Faster R-CNN detector (TF Hub)…")
        self.detector = None
        self._tf      = None
        self._gpus    = []
        try:
            import tensorflow as tf
            import tensorflow_hub as hub
            self._tf = tf
            gpus = tf.config.list_physical_devices("GPU")
            device = "/GPU:0" if gpus else "/CPU:0"
            with tf.device(device):
                module = hub.load(
                    "https://tfhub.dev/google/faster_rcnn/openimages_v4/"
                    "inception_resnet_v2/1"
                )
            self.detector = module.signatures["default"]
            self._gpus    = gpus
            self.status_update.emit(f"Detector loaded on {device}")
        except Exception as e:
            self.status_update.emit(f"Detector load failed: {e}")

    # ── Lazy-load BEiT classifier ─────────────────────────────────────────
    def _load_classifier(self):
        self.status_update.emit("Loading BEiT classifier…")
        self.classifier     = None
        self._torch         = None
        self._torch_device  = None
        self._transform     = None
        try:
            import torch
            from transformers import BeitForImageClassification
            from torchvision import transforms

            if torch.cuda.is_available():
                device = torch.device("cuda")
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = torch.device("mps")
            else:
                device = torch.device("cpu")
            self._torch_device = device

            model = BeitForImageClassification.from_pretrained(
                "microsoft/beit-base-patch16-224-pt22k-ft22k",
                num_labels=len(self.class_names),
                ignore_mismatched_sizes=True,
                local_files_only=False,
            )
            if self.checkpoint_path and os.path.exists(self.checkpoint_path):
                ckpt = torch.load(
                    self.checkpoint_path, map_location=device, weights_only=False
                )
                state = ckpt.get("model_state_dict", ckpt)
                model.load_state_dict(state, strict=False)
                self.status_update.emit(
                    f"Custom checkpoint loaded: {self.checkpoint_path}"
                )
            model.to(device).eval()
            self.classifier  = model
            self._transform  = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.5] * 3, [0.5] * 3),
            ])
            self._torch = torch
            self.status_update.emit(f"Classifier loaded on {device}")
        except Exception as e:
            self.status_update.emit(f"Classifier load failed: {e}")

    def _classify_crop(self, crop_bgr) -> str:
        """Run BEiT on a BGR crop; return predicted class name."""
        if self.classifier is None or self._transform is None:
            return "Unknown"
        try:
            pil_img = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
            tensor  = self._transform(pil_img).unsqueeze(0).to(self._torch_device)
            with self._torch.no_grad():
                idx = self.classifier(tensor).logits.argmax(1).item()
            return self.class_names[idx]
        except Exception as e:
            self.status_update.emit(f"Classification error: {e}")
            return "Unknown"

    def _apply_dbscan_and_emit(self):
        """
        Deduplicate collected crops with DBSCAN, classify each unique crop,
        then emit detection_made for each unique building.

        This is the SINGLE place that emits detection_made — avoids double-
        counting between the detector loop and the classification stage.
        """
        if not hasattr(self, "all_crops") or not self.all_crops:
            self.status_update.emit("No crops collected — nothing to classify.")
            return

        crops = self.all_crops
        olat, olon = self.gps_origin

        if _SKLEARN_OK and len(crops) >= 2:
            coords = np.array([[c["lat"], c["lon"]] for c in crops])
            # eps ≈ 15 m in degrees
            eps_deg = 15.0 / _M_PER_DEG_LAT
            labels  = DBSCAN(eps=eps_deg, min_samples=1).fit(coords).labels_

            # Keep one representative per cluster (first occurrence)
            seen_clusters: dict = {}
            unique_crops   = []
            n_dup          = 0
            for i, label in enumerate(labels):
                if label == -1:
                    # Noise point — treat as its own unique building
                    unique_crops.append(crops[i])
                elif label not in seen_clusters:
                    seen_clusters[label] = i
                    unique_crops.append(crops[i])
                else:
                    n_dup += 1
            self.status_update.emit(
                f"DBSCAN: {len(unique_crops)} unique buildings, "
                f"{n_dup} duplicate crops removed."
            )
        else:
            unique_crops = crops
            self.status_update.emit(
                f"Skipping DBSCAN (sklearn unavailable or <2 crops). "
                f"{len(unique_crops)} buildings."
            )

        # Re-assign sequential IDs after dedup, then classify + emit
        self.status_update.emit("Classifying unique crops…")
        for seq_id, crop_rec in enumerate(unique_crops):
            if not self.running:
                break
            pred_class = self._classify_crop(crop_rec["crop"])
            lat, lon   = building_coords(seq_id, olat, olon)
            self.detection_made.emit(lat, lon, pred_class, seq_id)
            self.status_update.emit(
                f"  [{seq_id + 1}/{len(unique_crops)}] {pred_class}"
            )

    def run(self):
        try:
            self._load_detector()
            self._load_classifier()

            cap = open_video(self.video_path)
            if not cap.isOpened():
                self.status_update.emit(
                    f"ERROR: Cannot open video: {self.video_path}\n"
                    "Supported: MP4, AVI, MOV, MKV. "
                    "Ensure OpenCV is built with FFMPEG support."
                )
                self.finished.emit()
                return

            fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            det_interval = max(1, int(fps / max(1, self.detection_fps)))

            self.status_update.emit(
                f"Video: {w}×{h} @ {fps:.1f} fps  |  "
                f"{total} frames  |  detecting every {det_interval} frames"
            )

            # Optional annotated video output
            out, out_path = None, None
            if self.output_folder:
                try:
                    out_path = os.path.join(self.output_folder, "annotated_video.mp4")
                    for codec in ("avc1", "mp4v", "MJPG"):
                        fourcc = cv2.VideoWriter_fourcc(*codec)
                        out    = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
                        if out.isOpened():
                            self.status_update.emit(f"VideoWriter: {codec}")
                            break
                        out.release()
                        out = None
                except Exception as e:
                    self.status_update.emit(f"VideoWriter error: {e}")
                    out = None

            self.all_crops = []   # accumulate raw crops; classify after DBSCAN
            frame_count    = 0

            while self.running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    ret, frame = cap.read()
                    if not ret:
                        break

                # ── Detection pass ────────────────────────────────────────
                if frame_count % det_interval == 0 and self.detector is not None:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    try:
                        t = self._tf.convert_to_tensor(
                            rgb, dtype=self._tf.float32
                        ) / 255.0
                        result  = self.detector(t[self._tf.newaxis, ...])
                        boxes   = np.array(result["detection_boxes"]).reshape(-1, 4)
                        scores  = np.array(result["detection_scores"]).flatten()
                        raw_cls = np.array(result["detection_class_entities"]).flatten()

                        for i in range(len(scores)):
                            if scores[i] < 0.30:
                                continue
                            cname = (
                                raw_cls[i].decode("utf-8")
                                if isinstance(raw_cls[i], bytes)
                                else str(raw_cls[i])
                            )
                            if cname not in {
                                "House", "Building", "Skyscraper", "Tower"
                            }:
                                continue

                            ymin, xmin, ymax, xmax = boxes[i]
                            y1 = max(0, int(ymin * h))
                            x1 = max(0, int(xmin * w))
                            y2 = min(h, int(ymax * h))
                            x2 = min(w, int(xmax * w))
                            crop = rgb[y1:y2, x1:x2]
                            if crop.size == 0:
                                continue

                            crop_bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
                            # Placeholder coords — will be replaced after DBSCAN
                            # Use frame position as a rough spatial proxy
                            frac   = frame_count / max(total, 1)
                            p_lat  = self.gps_origin[0] + frac * 0.005
                            p_lon  = self.gps_origin[1] + (
                                (x1 + x2) / 2 / w - 0.5
                            ) * 0.005
                            rec_id = self._next_id
                            self._next_id += 1
                            self.all_crops.append({
                                "id":   rec_id,
                                "crop": crop_bgr,
                                "lat":  p_lat,
                                "lon":  p_lon,
                            })
                            if self.crops_dir:
                                cv2.imwrite(
                                    os.path.join(self.crops_dir, f"{rec_id}.jpg"),
                                    crop_bgr,
                                )

                            # Annotate frame (preview only — no emit yet)
                            cv2.rectangle(
                                frame, (x1, y1), (x2, y2), (29, 161, 242), 2
                            )
                            cv2.putText(
                                frame, f"Bldg #{rec_id}",
                                (x1, max(y1 - 8, 0)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                (29, 161, 242), 2,
                            )
                    except Exception as e:
                        self.status_update.emit(
                            f"Detection error frame {frame_count}: {e}"
                        )

                # ── Throttled preview emit ────────────────────────────────
                now = time.monotonic()
                if now - self._last_preview_t >= self._preview_interval_s:
                    self.frame_ready.emit(frame.copy())
                    self._last_preview_t = now

                if out:
                    out.write(frame)

                frame_count += 1
                if total > 0:
                    self.progress_update.emit(int(frame_count / total * 100))

            cap.release()
            if out:
                out.release()
            self.output_video_path = out_path

            # ── Post-processing: dedup + classify + emit detections ───────
            self.status_update.emit(
                f"Detection pass done — {len(self.all_crops)} raw crops collected. "
                "Running DBSCAN + BEiT classification…"
            )
            self._apply_dbscan_and_emit()

        except Exception as e:
            import traceback
            self.status_update.emit(
                f"Fatal VideoProcessor error: {e}\n{traceback.format_exc()}"
            )
        finally:
            self.finished.emit()

    def stop(self):
        self.running = False


# ─────────────────────────────────────────────────────────────────────────────
#  MplCanvas helper
# ─────────────────────────────────────────────────────────────────────────────
class MplCanvas(FigureCanvas):
    def __init__(self, figsize=(5, 3.5)):
        with plt.rc_context(MPL_STYLE):
            self.fig = Figure(figsize=figsize, tight_layout=True)
            self.ax  = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"background: {BG_PANEL};")


# ─────────────────────────────────────────────────────────────────────────────
#  RiskCalcThread
# ─────────────────────────────────────────────────────────────────────────────
class RiskCalcThread(QThread):
    finished = pyqtSignal(object, object, object)
    progress = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, buildings, params):
        super().__init__()
        self.buildings = buildings
        self.params    = params

    def run(self):
        if not _RISK_OK:
            self.error.emit(f"risk_engine not available: {_RISK_ERR}")
            return
        try:
            self.progress.emit("Computing ground-motion field (BA08 GMPE)…")
            results, df = run_scenario(self.buildings, self.params)
            self.progress.emit("Aggregating damage states…")
            summary = portfolio_summary(results)
            self.progress.emit("Done.")
            self.finished.emit(results, df, summary)
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")


# ─────────────────────────────────────────────────────────────────────────────
#  Risk Assessment Panel
# ─────────────────────────────────────────────────────────────────────────────
class RiskAssessmentPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buildings   = []
        self.results     = []
        self.df          = None
        self.summary     = {}
        self.calc_thread = None
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── LEFT: inputs ──────────────────────────────────────────────────
        left = QWidget()
        left.setMaximumWidth(330)
        ll = QVBoxLayout(left)
        ll.setSpacing(10)

        # Exposure
        exp_grp = QGroupBox("EXPOSURE")
        eg = QVBoxLayout(exp_grp)
        self.exposure_lbl = QLabel("No buildings loaded")
        self.exposure_lbl.setWordWrap(True)
        self.exposure_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
        self.btn_load_csv = QPushButton("📂  Load Exposure CSV")
        self.btn_load_csv.setCursor(Qt.PointingHandCursor)
        self.btn_load_csv.clicked.connect(self.load_exposure_csv)
        eg.addWidget(self.exposure_lbl)
        eg.addWidget(self.btn_load_csv)
        ll.addWidget(exp_grp)

        # Earthquake params
        eq_grp = QGroupBox("EARTHQUAKE SCENARIO")
        eg2 = QGridLayout(eq_grp)
        eg2.setSpacing(6)

        def lrow(label, widget, r, hint=None):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
            eg2.addWidget(lbl, r, 0)
            eg2.addWidget(widget, r, 1)
            if hint:
                h = QLabel(hint)
                h.setStyleSheet(f"color:{TXT_LOW}; font-size:9px;")
                eg2.addWidget(h, r + 1, 0, 1, 2)

        self.mw_spin = QDoubleSpinBox()
        self.mw_spin.setRange(4.0, 9.0); self.mw_spin.setValue(6.5)
        self.mw_spin.setSingleStep(0.1); self.mw_spin.setSuffix(" Mw")
        lrow("Magnitude:", self.mw_spin, 0)

        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(1.0, 300.0); self.depth_spin.setValue(10.0)
        self.depth_spin.setSuffix(" km")
        lrow("Depth:", self.depth_spin, 1)

        self.src_lat = QDoubleSpinBox()
        self.src_lat.setRange(-90, 90); self.src_lat.setValue(31.70)
        self.src_lat.setDecimals(4); self.src_lat.setSingleStep(0.01)
        lrow("Source Lat:", self.src_lat, 2)

        self.src_lon = QDoubleSpinBox()
        self.src_lon.setRange(-180, 180); self.src_lon.setValue(76.93)
        self.src_lon.setDecimals(4); self.src_lon.setSingleStep(0.01)
        lrow("Source Lon:", self.src_lon, 3)

        self.vs30_spin = QDoubleSpinBox()
        self.vs30_spin.setRange(100, 1500); self.vs30_spin.setValue(400)
        self.vs30_spin.setSuffix(" m/s")
        lrow("Vs30:", self.vs30_spin, 4,
             hint="180=soft soil · 400=stiff · 760=rock")

        self.fault_combo = QComboBox()
        self.fault_combo.addItems(["unspecified", "reverse", "normal", "strike-slip"])
        lrow("Fault type:", self.fault_combo, 6)

        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(100, 5000); self.samples_spin.setValue(500)
        self.samples_spin.setSuffix(" samples")
        lrow("MC samples:", self.samples_spin, 7)
        ll.addWidget(eq_grp)

        # Quick presets
        preset_grp = QGroupBox("QUICK SCENARIOS  (Mandi, HP)")
        pg = QVBoxLayout(preset_grp)
        presets = [
            ("Mw 5.5  Moderate (R≈20 km)", 5.5, 10, 31.65, 76.99),
            ("Mw 6.5  Strong   (R≈15 km)", 6.5, 12, 31.62, 76.95),
            ("Mw 7.0  Major    (R≈10 km)", 7.0, 15, 31.68, 76.90),
            ("Mw 7.5  Severe   (R≈8 km)",  7.5, 20, 31.72, 76.87),
        ]
        for name, mw, dep, slat, slon in presets:
            btn = QPushButton(name)
            btn.setStyleSheet(
                f"text-align:left; padding:5px 8px; font-size:10px; "
                f"background:{BG_CARD}; color:{TXT_MID}; "
                f"border:1px solid {BORDER}; border-radius:4px;"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _, m=mw, d=dep, la=slat, lo=slon:
                    self._apply_preset(m, d, la, lo)
            )
            pg.addWidget(btn)
        ll.addWidget(preset_grp)

        self.btn_run = QPushButton("▶  RUN RISK ASSESSMENT")
        self.btn_run.setEnabled(False)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setStyleSheet(
            f"background:{ACCENT}; color:#fff; font-weight:700; border:none; "
            f"border-radius:6px; padding:10px; font-size:13px;"
        )
        self.btn_run.clicked.connect(self.run_assessment)
        ll.addWidget(self.btn_run)

        self.risk_progress = QProgressBar()
        self.risk_progress.setRange(0, 0)
        self.risk_progress.setVisible(False)
        ll.addWidget(self.risk_progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        ll.addWidget(self.log)

        self.btn_export = QPushButton("💾  Export Results CSV")
        self.btn_export.setEnabled(False)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_csv)
        ll.addWidget(self.btn_export)
        ll.addStretch()

        # ── RIGHT: results ────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setSpacing(8)

        # KPI row
        kpi_row_w = QWidget()
        kpi_l = QHBoxLayout(kpi_row_w)
        kpi_l.setSpacing(8)
        kpi_l.setContentsMargins(0, 0, 0, 0)
        self.kpi_widgets = {}
        kpi_defs = [
            ("n_buildings",      "Buildings",       "—"),
            ("pga_mean_g",       "Mean PGA (g)",    "—"),
            ("avg_loss_ratio",   "Avg Loss Ratio",  "—"),
            ("total_loss_units", "Total Loss Units","—"),
        ]
        for key, label, default in kpi_defs:
            card = QWidget()
            card.setStyleSheet(
                f"background:{BG_CARD}; border:1px solid {BORDER}; "
                f"border-radius:8px; padding:8px;"
            )
            cl = QVBoxLayout(card)
            cl.setSpacing(2)
            val_lbl = QLabel(default)
            val_lbl.setStyleSheet(
                f"color:{ACCENT}; font-size:20px; font-weight:700;"
            )
            val_lbl.setAlignment(Qt.AlignCenter)
            name_lbl = QLabel(label)
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setStyleSheet(f"color:{TXT_LOW}; font-size:10px;")
            cl.addWidget(val_lbl)
            cl.addWidget(name_lbl)
            kpi_l.addWidget(card)
            self.kpi_widgets[key] = val_lbl
        rl.addWidget(kpi_row_w)

        # Charts
        chart_row = QHBoxLayout()
        self.ds_canvas   = MplCanvas(figsize=(5, 3))
        self.frag_canvas = MplCanvas(figsize=(4.5, 3))
        chart_row.addWidget(self.ds_canvas,   3)
        chart_row.addWidget(self.frag_canvas, 2)
        rl.addLayout(chart_row)

        # Detail table
        tbl_lbl = QLabel("BUILDING RESULTS")
        tbl_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:11px; font-weight:bold; "
            f"border-bottom:1px solid {BORDER}; padding-bottom:3px;"
        )
        rl.addWidget(tbl_lbl)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "ID", "Class", "Archetype", "Lat", "Lon",
            "PGA(g)", "P(DS1)", "P(DS2)", "P(DS3)", "P(DS4)",
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_table_select)
        rl.addWidget(self.table, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([310, 900])
        root.addWidget(splitter)

    # ── Exposure loading ──────────────────────────────────────────────────
    def load_from_detections(self, detections: list):
        """Called by RapidScanWindow whenever the detection list updates."""
        if not _RISK_OK:
            return
        self.buildings = []
        for det in detections:
            try:
                self.buildings.append(BuildingRecord(
                    id=int(det.get("id", len(self.buildings) + 1)),
                    lat=float(det.get("lat", DEFAULT_GPS_ORIGIN[0])),
                    lon=float(det.get("lon", DEFAULT_GPS_ORIGIN[1])),
                    beit_class=str(det.get("classification", "RCC_H1 flat roof")),
                ))
            except Exception:
                continue
        self._update_exposure_label()

    def load_exposure_csv(self):
        if not _RISK_OK or not _PANDAS_OK:
            self._log("risk_engine or pandas not available.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Exposure CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            df = pd.read_csv(path)
            required = {"id", "lat", "lon", "classification"}
            missing  = required - set(df.columns)
            if missing:
                self._log(f"CSV missing columns: {missing}")
                return
            self.buildings = [
                BuildingRecord(
                    id=int(r["id"]), lat=float(r["lat"]),
                    lon=float(r["lon"]),
                    beit_class=str(r["classification"]),
                )
                for _, r in df.iterrows()
            ]
            self._update_exposure_label()
            self._log(f"Loaded {len(self.buildings)} buildings from "
                      f"{os.path.basename(path)}")
        except Exception as e:
            self._log(f"CSV load error: {e}")

    def _update_exposure_label(self):
        n = len(self.buildings)
        self.exposure_lbl.setText(
            f"<b style='color:{ACCENT}'>{n}</b> buildings loaded"
        )
        self.btn_run.setEnabled(n > 0 and _RISK_OK)

    def _apply_preset(self, mw, dep, slat, slon):
        self.mw_spin.setValue(mw)
        self.depth_spin.setValue(dep)
        self.src_lat.setValue(slat)
        self.src_lon.setValue(slon)

    # ── Run assessment ────────────────────────────────────────────────────
    def run_assessment(self):
        if not self.buildings or not _RISK_OK:
            self._log("No buildings loaded or risk_engine unavailable.")
            return
        params = ScenarioParams(
            Mw=self.mw_spin.value(),
            depth_km=self.depth_spin.value(),
            source_lat=self.src_lat.value(),
            source_lon=self.src_lon.value(),
            Vs30=self.vs30_spin.value(),
            fault_type=self.fault_combo.currentText(),
            n_samples=self.samples_spin.value(),
        )
        self._log(
            f"[{datetime.now():%H:%M:%S}] Mw{params.Mw} scenario at "
            f"({params.source_lat:.4f}, {params.source_lon:.4f}) — "
            f"{len(self.buildings)} buildings"
        )
        self.btn_run.setEnabled(False)
        self.risk_progress.setVisible(True)
        self.calc_thread = RiskCalcThread(self.buildings, params)
        self.calc_thread.progress.connect(self._log)
        self.calc_thread.finished.connect(self._on_results)
        self.calc_thread.error.connect(self._on_error)
        self.calc_thread.start()

    @pyqtSlot(object, object, object)
    def _on_results(self, results, df, summary):
        self.results = results
        self.df      = df
        self.summary = summary
        self.risk_progress.setVisible(False)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(True)
        self._update_kpis(summary)
        self._draw_ds_chart(summary)
        self._fill_table(results)
        self._log(
            f"✓ Complete — {summary.get('n_buildings', 0)} buildings.  "
            f"Avg loss ratio: {summary.get('avg_loss_ratio', 0):.1%}"
        )

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.risk_progress.setVisible(False)
        self.btn_run.setEnabled(True)
        self._log(f"ERROR: {msg}")

    # ── KPI / charts ──────────────────────────────────────────────────────
    def _update_kpis(self, s: dict):
        self.kpi_widgets["n_buildings"].setText(
            str(s.get("n_buildings", "—"))
        )
        pga = s.get("pga_mean_g", None)
        self.kpi_widgets["pga_mean_g"].setText(
            f"{pga:.4f}" if pga is not None else "—"
        )
        alr = s.get("avg_loss_ratio", None)
        self.kpi_widgets["avg_loss_ratio"].setText(
            f"{alr:.1%}" if alr is not None else "—"
        )
        tlu = s.get("total_loss_units", s.get("total_loss", None))
        self.kpi_widgets["total_loss_units"].setText(
            f"{tlu:.1f}" if tlu is not None else "—"
        )

    def _draw_ds_chart(self, summary: dict):
        ax = self.ds_canvas.ax
        ax.clear()
        ds_pct = summary.get("ds_pct", {})
        labels = ["None", "DS1", "DS2", "DS3", "DS4"]
        vals   = [ds_pct.get(k, 0) for k in labels]
        colors = [DS_COLORS[k] for k in labels]
        bars   = ax.bar(labels, vals, color=colors,
                        edgecolor=BORDER, linewidth=0.7)
        for bar, val in zip(bars, vals):
            if val > 1:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.5,
                    f"{val:.1f}%",
                    ha="center", va="bottom", fontsize=9, color=TXT_HI,
                )
        ax.set_ylabel("% of buildings", color=TXT_MID)
        ax.set_title("Damage State Distribution", color=TXT_HI, fontsize=11)
        ax.set_ylim(0, max(vals or [1]) * 1.2 + 5)
        ax.yaxis.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        self.ds_canvas.fig.tight_layout()
        self.ds_canvas.draw()

    def _draw_fragility(self, archetype: str, pga_median: float = None):
        if not _RISK_OK or not FRAGILITY_LIB:
            return
        ax = self.frag_canvas.ax
        ax.clear()
        params    = FRAGILITY_LIB.get(
            archetype, FRAGILITY_LIB.get("CR_LFINF_DUL_H1", {})
        )
        if not params:
            ax.set_title("No fragility data", color=TXT_MID, fontsize=10)
            self.frag_canvas.draw()
            return

        pga_range = np.linspace(0.01, 2.0, 300)
        ds_labels = {
            "DS1": "Slight", "DS2": "Moderate",
            "DS3": "Extensive", "DS4": "Complete",
        }
        ds_clrs = {
            "DS1": "#facc15", "DS2": "#f97316",
            "DS3": "#ef4444", "DS4": "#7f1d1d",
        }
        for ds_key, ds_name in ds_labels.items():
            if ds_key not in params:
                continue
            med, beta = params[ds_key]
            if med >= 90:
                continue
            probs = [fragility_prob(p, med, beta) for p in pga_range]
            ax.plot(pga_range, probs, label=ds_name, color=ds_clrs[ds_key])

        if pga_median:
            ax.axvline(
                pga_median, color=ACCENT, linestyle="--", linewidth=1.2,
                label=f"Site PGA={pga_median:.3f}g",
            )
        ax.set_xlabel("PGA (g)", color=TXT_MID)
        ax.set_ylabel("P(DS ≥ ds)", color=TXT_MID)
        ax.set_title(f"Fragility: {archetype}", color=TXT_HI, fontsize=10)
        ax.legend(fontsize=8, framealpha=0.3)
        ax.set_xlim(0, 2.0); ax.set_ylim(0, 1.05)
        ax.yaxis.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        self.frag_canvas.fig.tight_layout()
        self.frag_canvas.draw()

    def _fill_table(self, results):
        self.table.setRowCount(0)
        for r in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            ds_color = QColor(DS_COLORS.get(r.mean_ds, BG_CARD))
            vals = [
                str(r.id),
                r.beit_class,
                r.archetype,
                f"{r.lat:.5f}",
                f"{r.lon:.5f}",
                f"{r.pga_median:.4f}",
                f"{r.ds_probs.get('DS1', 0):.3f}",
                f"{r.ds_probs.get('DS2', 0):.3f}",
                f"{r.ds_probs.get('DS3', 0):.3f}",
                f"{r.ds_probs.get('DS4', 0):.3f}",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(TXT_HI))
                if col == 0:
                    item.setBackground(ds_color)
                self.table.setItem(row, col, item)

    def _on_table_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows or not self.results:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self.results):
            r = self.results[idx]
            self._draw_fragility(r.archetype, r.pga_median)

    def export_csv(self):
        if not _PANDAS_OK or self.df is None:
            self._log("pandas not available or no results to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Risk Results", "risk_results.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.df.to_csv(path, index=False)
            self._log(f"✓ Exported {len(self.df)} rows → {path}")

    def _log(self, msg: str):
        self.log.append(msg)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())


# ─────────────────────────────────────────────────────────────────────────────
#  RapidScanWindow — main tab widget
# ─────────────────────────────────────────────────────────────────────────────
class RapidScanWindow(QWidget):
    """Embeddable PyQt5 widget — drop into RiskMap's tab bar."""

    def __init__(self, config=None, logger=None,
                 gps_origin=DEFAULT_GPS_ORIGIN):
        super().__init__()
        self.config      = config
        self.logger      = logger
        self.gps_origin  = gps_origin   # (lat, lon) scene centre

        self.video_path      = None
        self.output_folder   = None
        self.detections      = []          # list of dicts: id/lat/lon/classification
        self.video_processor = None
        self.playback_cap    = None
        self._temp_map_file  = None
        self._playback_playing = True

        self.checkpoint_path = self._resolve_checkpoint()

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._next_playback_frame)

        self._build_ui()
        self._apply_stylesheet()
        self._write_map_html()

    def _resolve_checkpoint(self) -> str:
        try:
            if self.config:
                params    = self.config.get_classification_data()
                model_dir = params.get("model_path", "")
                models    = params.get("available_models", "best_model")
                ext       = params.get("model_ext", ".pth")
                first     = models.split(",")[0].strip()
                return str(Path(model_dir) / (first + ext))
        except Exception:
            pass
        here = (
            Path(__file__).parent.parent
            / "assets" / "models" / "classifier" / "best_model.pth"
        )
        return str(here) if here.exists() else ""

    # ── Global stylesheet ─────────────────────────────────────────────────
    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
        QWidget {{
            font-family: 'Segoe UI', 'SF Pro Display', system-ui, sans-serif;
            font-size: 12px;
            color: {TXT_HI};
            background: {BG_DEEP};
        }}
        QGroupBox {{
            border: 1px solid {BORDER};
            border-radius: 8px;
            margin-top: 8px;
            padding-top: 4px;
            background: {BG_PANEL};
            font-size: 10px;
            font-weight: 700;
            color: {TXT_MID};
            letter-spacing: 0.8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            left: 10px;
        }}
        QPushButton {{
            background: {BG_CARD};
            color: {TXT_HI};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background: {ACCENT};
            color: #ffffff;
            border-color: {ACCENT};
        }}
        QPushButton:disabled {{
            color: {TXT_LOW};
            background: {BG_DEEP};
        }}
        QPushButton#ActionButton {{
            color: #ffffff;
            font-weight: 700;
            font-size: 12px;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
        }}
        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 0 8px 8px 8px;
            background: {BG_PANEL};
        }}
        QTabBar::tab {{
            background: {BG_DEEP};
            color: {TXT_MID};
            border: 1px solid {BORDER};
            border-bottom: none;
            border-radius: 6px 6px 0 0;
            padding: 7px 16px;
            margin-right: 2px;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background: {BG_PANEL};
            color: {ACCENT};
            font-weight: 700;
        }}
        QTabBar::tab:hover:!selected {{
            background: {BG_CARD};
            color: {TXT_HI};
        }}
        QTableWidget {{
            background: {BG_PANEL};
            alternate-background-color: {BG_CARD};
            gridline-color: {BORDER};
            border: 1px solid {BORDER};
            border-radius: 6px;
            selection-background-color: {ACCENT};
            selection-color: #ffffff;
        }}
        QHeaderView::section {{
            background: {BG_DEEP};
            color: {TXT_MID};
            border: none;
            border-bottom: 1px solid {BORDER};
            padding: 5px 8px;
            font-weight: 700;
            font-size: 10px;
            letter-spacing: 0.5px;
        }}
        QTextEdit, QLineEdit {{
            background: {BG_CARD};
            color: {TXT_HI};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 5px;
            font-family: {FONT_MONO};
            font-size: 11px;
        }}
        QSpinBox, QDoubleSpinBox, QComboBox {{
            background: {BG_CARD};
            color: {TXT_HI};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 3px 6px;
        }}
        QComboBox::drop-down {{
            border: none;
        }}
        QProgressBar {{
            border: 1px solid {BORDER};
            border-radius: 5px;
            background: {BG_CARD};
            text-align: center;
            color: {TXT_MID};
            height: 14px;
        }}
        QProgressBar::chunk {{
            background: {ACCENT};
            border-radius: 4px;
        }}
        QSplitter::handle {{
            background: {BORDER};
        }}
        QSplitter::handle:horizontal {{
            width: 5px;
        }}
        QSplitter::handle:vertical {{
            height: 5px;
        }}
        QSplitter::handle:hover {{
            background: {ACCENT};
        }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: {BORDER};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {ACCENT};
            border: none;
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }}
        QSlider::sub-page:horizontal {{
            background: {ACCENT};
            border-radius: 2px;
        }}
        """)

    # ── Build UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setStyleSheet(
            f"QFrame {{ background:{BG_PANEL}; "
            f"border-bottom:2px solid {ACCENT}; }}"
        )
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(18, 10, 18, 10)
        tb.setSpacing(14)

        icon_lbl = QLabel("⚡")
        icon_lbl.setStyleSheet(
            f"font-size:20px; background:transparent; color:{ACCENT};"
        )
        tb.addWidget(icon_lbl)

        title_lbl = QLabel("RAPIDSCAN")
        title_lbl.setStyleSheet(
            f"font-size:16px; font-weight:900; color:{ACCENT}; "
            f"background:transparent; letter-spacing:2px;"
        )
        tb.addWidget(title_lbl)

        sub_lbl = QLabel("Real-time Building Detection & Seismic Risk")
        sub_lbl.setStyleSheet(
            f"font-size:11px; color:{TXT_MID}; background:transparent;"
        )
        tb.addWidget(sub_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color:{BORDER};")
        tb.addWidget(sep)

        self.status_lbl = QLabel("● SYSTEM READY")
        self.status_lbl.setStyleSheet(
            f"color:{ACCENT3}; font-size:11px; background:transparent; "
            f"font-weight:600;"
        )
        tb.addWidget(self.status_lbl, 1)

        # GPS origin display
        self.gps_lbl = QLabel(
            f"📍 Origin: {self.gps_origin[0]:.4f}, {self.gps_origin[1]:.4f}"
        )
        self.gps_lbl.setStyleSheet(
            f"font-size:10px; color:{TXT_LOW}; background:transparent; "
            f"font-family:{FONT_MONO};"
        )
        tb.addWidget(self.gps_lbl)

        root.addWidget(toolbar)

        # ── Main vertical splitter: map (top) | tabs (bottom) ────────
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setOpaqueResize(True)
        self.main_splitter.setHandleWidth(6)

        # Map pane
        map_widget = QWidget()
        map_widget.setMinimumHeight(150)
        ml = QVBoxLayout(map_widget)
        ml.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        try:
            s = self.web_view.settings()
            s.setAttribute(
                QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
            )
            s.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        except Exception:
            pass
        ml.addWidget(self.web_view)
        self.main_splitter.addWidget(map_widget)

        # Bottom: tabs (NO QScrollArea wrapper — was breaking splitter drag)
        bottom = QWidget()
        bottom.setMinimumHeight(120)
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        self.right_tabs = QTabWidget()
        self.right_tabs.tabBar().setExpanding(False)
        self.right_tabs.tabBar().setElideMode(Qt.ElideNone)

        # ── Detection tab ──────────────────────────────────────────
        det_tab = self._build_detection_tab()
        self.right_tabs.addTab(det_tab, "🎥  Detection")

        # ── Risk tab ────────────────────────────────────────────────
        self.risk_panel = RiskAssessmentPanel()
        risk_tab = QWidget()
        rt = QVBoxLayout(risk_tab)
        rt.setContentsMargins(0, 0, 0, 0)
        rt.addWidget(self.risk_panel)
        self.right_tabs.addTab(risk_tab, "⚠️  Risk Assessment")

        bl.addWidget(self.right_tabs, 1)
        self.main_splitter.addWidget(bottom)
        self.main_splitter.setSizes([420, 480])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)

        root.addWidget(self.main_splitter, 1)

    def _build_detection_tab(self) -> QWidget:
        det_tab = QWidget()
        det_layout = QVBoxLayout(det_tab)
        det_layout.setContentsMargins(10, 10, 10, 10)
        det_layout.setSpacing(8)

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setOpaqueResize(True)
        content_splitter.setHandleWidth(6)

        # ── Left: controls ────────────────────────────────────────
        ctrl_panel = QWidget()
        ctrl_panel.setFixedWidth(260)
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_layout.setSpacing(8)
        ctrl_layout.setContentsMargins(0, 0, 4, 0)

        # File group
        file_grp = QGroupBox("FILE SETTINGS")
        fg = QVBoxLayout(file_grp)
        fg.setSpacing(6)
        self.btn_load_video = QPushButton("📁  Load Video")
        self.btn_load_video.setCursor(Qt.PointingHandCursor)
        self.btn_load_video.clicked.connect(self.load_video)
        self.btn_select_folder = QPushButton("📂  Output Folder")
        self.btn_select_folder.setCursor(Qt.PointingHandCursor)
        self.btn_select_folder.clicked.connect(self.select_output_folder)
        self.vid_info = QLabel("No video loaded")
        self.vid_info.setStyleSheet(
            f"color:{TXT_LOW}; font-size:10px; "
            f"font-family:{FONT_MONO}; padding:2px 0;"
        )
        self.vid_info.setWordWrap(True)
        fg.addWidget(self.btn_load_video)
        fg.addWidget(self.btn_select_folder)
        fg.addWidget(self.vid_info)
        ctrl_layout.addWidget(file_grp)

        # Detection settings
        det_grp = QGroupBox("DETECTION SETTINGS")
        dg = QVBoxLayout(det_grp)
        dg.setSpacing(6)

        fps_row = QHBoxLayout()
        fps_lbl = QLabel("Detection FPS:")
        fps_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(30)
        self.fps_spin.setSuffix(" fps")
        fps_row.addWidget(fps_lbl)
        fps_row.addWidget(self.fps_spin)
        dg.addLayout(fps_row)

        self.native_fps_lbl = QLabel("Native FPS: —")
        self.native_fps_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:10px; font-family:{FONT_MONO};"
        )
        dg.addWidget(self.native_fps_lbl)

        # GPS origin controls
        gps_grp_lbl = QLabel("Scene GPS Origin:")
        gps_grp_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px; margin-top:4px;")
        dg.addWidget(gps_grp_lbl)

        gps_row = QHBoxLayout()
        self.origin_lat_spin = QDoubleSpinBox()
        self.origin_lat_spin.setRange(-90, 90)
        self.origin_lat_spin.setValue(self.gps_origin[0])
        self.origin_lat_spin.setDecimals(4)
        self.origin_lat_spin.setPrefix("Lat: ")
        self.origin_lon_spin = QDoubleSpinBox()
        self.origin_lon_spin.setRange(-180, 180)
        self.origin_lon_spin.setValue(self.gps_origin[1])
        self.origin_lon_spin.setDecimals(4)
        self.origin_lon_spin.setPrefix("Lon: ")
        self.origin_lat_spin.valueChanged.connect(self._on_origin_changed)
        self.origin_lon_spin.valueChanged.connect(self._on_origin_changed)
        gps_row.addWidget(self.origin_lat_spin)
        gps_row.addWidget(self.origin_lon_spin)
        dg.addLayout(gps_row)

        # Checkpoint
        chkpt_lbl = QLabel("Classifier Checkpoint:")
        chkpt_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px; margin-top:4px;")
        self.chkpt_edit = QLineEdit(self.checkpoint_path)
        self.chkpt_edit.setPlaceholderText("Path to .pth file…")
        self.btn_browse_chkpt = QPushButton("Browse…")
        self.btn_browse_chkpt.setFixedWidth(76)
        self.btn_browse_chkpt.setCursor(Qt.PointingHandCursor)
        self.btn_browse_chkpt.clicked.connect(self._browse_checkpoint)
        chkpt_row = QHBoxLayout()
        chkpt_row.addWidget(self.chkpt_edit)
        chkpt_row.addWidget(self.btn_browse_chkpt)
        dg.addWidget(chkpt_lbl)
        dg.addLayout(chkpt_row)
        ctrl_layout.addWidget(det_grp)

        # Start / Stop
        action_grp = QGroupBox("CONTROLS")
        ag = QVBoxLayout(action_grp)
        ag.setSpacing(6)
        self.btn_process = QPushButton("▶  START DETECTION")
        self.btn_process.setEnabled(False)
        self.btn_process.setCursor(Qt.PointingHandCursor)
        self.btn_process.setObjectName("ActionButton")
        self.btn_process.setStyleSheet(
            f"QPushButton#ActionButton {{ background: {ACCENT3}; }}"
            f"QPushButton#ActionButton:hover {{ background: #388E3C; }}"
        )
        self.btn_process.clicked.connect(self.start_processing)

        self.btn_stop = QPushButton("■  STOP")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setObjectName("ActionButton")
        self.btn_stop.setStyleSheet(
            f"QPushButton#ActionButton {{ background: {ACCENT2}; }}"
            f"QPushButton#ActionButton:hover {{ background: #c62828; }}"
        )
        self.btn_stop.clicked.connect(self.stop_processing)
        ag.addWidget(self.btn_process)
        ag.addWidget(self.btn_stop)
        ctrl_layout.addWidget(action_grp)

        # Progress
        prog_grp = QGroupBox("PROGRESS")
        pg = QVBoxLayout(prog_grp)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%  (%v / %m frames)")
        pg.addWidget(self.progress_bar)
        ctrl_layout.addWidget(prog_grp)
        ctrl_layout.addStretch()
        content_splitter.addWidget(ctrl_panel)

        # ── Right: video + log/table ──────────────────────────────
        video_outer = QWidget()
        vo = QVBoxLayout(video_outer)
        vo.setContentsMargins(0, 0, 0, 0)
        vo.setSpacing(6)

        vid_grp = QGroupBox("🎥  VIDEO FEED")
        vg = QVBoxLayout(vid_grp)
        vg.setSpacing(6)

        self.video_label = QLabel("Load a video file to begin")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet(
            f"background:{BG_DEEP}; border-radius:8px; color:{TXT_MID}; "
            f"font-size:13px; font-style:italic;"
        )
        self.video_label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.video_label.setMinimumHeight(120)
        vg.addWidget(self.video_label)

        # Playback controls — hidden until playback starts
        self.playback_controls = QWidget()
        pc = QHBoxLayout(self.playback_controls)
        pc.setContentsMargins(0, 2, 0, 0)
        pc.setSpacing(8)

        self.btn_play_pause = QPushButton("⏸")
        self.btn_play_pause.setFixedSize(36, 30)
        self.btn_play_pause.setToolTip("Play / Pause")
        self.btn_play_pause.setCursor(Qt.PointingHandCursor)
        self.btn_play_pause.clicked.connect(self.toggle_playback)

        self.frame_lbl = QLabel("0 / 0")
        self.frame_lbl.setStyleSheet(
            f"color:{TXT_LOW}; font-size:10px; font-family:{FONT_MONO}; "
            f"min-width:80px;"
        )
        self.frame_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.video_slider = QSlider(Qt.Horizontal)
        self.video_slider.setTracking(False)   # only seek on release
        # Both signals: sliderMoved for drag, valueChanged for key nav
        self.video_slider.sliderMoved.connect(self.seek_video)
        self.video_slider.valueChanged.connect(self._on_slider_value_changed)

        pc.addWidget(self.btn_play_pause)
        pc.addWidget(self.video_slider, 1)
        pc.addWidget(self.frame_lbl)
        vg.addWidget(self.playback_controls)
        self.playback_controls.setVisible(False)
        vo.addWidget(vid_grp, 3)

        # Detection log + processing log
        log_splitter = QSplitter(Qt.Horizontal)
        log_splitter.setChildrenCollapsible(False)
        log_splitter.setHandleWidth(5)

        tbl_grp = QGroupBox("📊  DETECTION LOG")
        tg = QVBoxLayout(tbl_grp)
        tg.setSpacing(4)
        self.det_table = QTableWidget(0, 4)
        self.det_table.setHorizontalHeaderLabels(
            ["ID", "Latitude", "Longitude", "Classification"]
        )
        self.det_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self.det_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.det_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.det_table.setSelectionMode(QTableWidget.SingleSelection)
        self.det_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.det_table.verticalHeader().setVisible(False)
        self.det_table.setAlternatingRowColors(True)
        self.det_count_lbl = QLabel("0 detections")
        self.det_count_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:11px; font-weight:600; padding:2px 0;"
        )
        tg.addWidget(self.det_table)
        tg.addWidget(self.det_count_lbl)
        log_splitter.addWidget(tbl_grp)

        log_grp = QGroupBox("📝  PROCESSING LOG")
        lg = QVBoxLayout(log_grp)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)
        lg.addWidget(self.log_text)
        log_splitter.addWidget(log_grp)
        log_splitter.setSizes([500, 300])
        vo.addWidget(log_splitter, 2)

        content_splitter.addWidget(video_outer)
        content_splitter.setStretchFactor(0, 0)
        content_splitter.setStretchFactor(1, 1)
        det_layout.addWidget(content_splitter)

        return det_tab

    # ── Map HTML ──────────────────────────────────────────────────────────
    def _write_map_html(self):
        olat, olon = self.gps_origin
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>RapidScan Map</title>
<link rel="stylesheet"
  href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html,body,#map {{ width:100%; height:100%; background:{BG_DEEP}; }}
.overlay-badge {{
  position:absolute; top:10px; right:10px; z-index:1000;
  background:rgba(255,255,255,0.95);
  backdrop-filter:blur(6px);
  border:1.5px solid {ACCENT};
  border-radius:8px; padding:8px 14px;
  font-family:monospace; font-size:12px; color:{TXT_HI};
  box-shadow: 0 2px 12px rgba(0,0,0,0.1);
}}
.overlay-badge .cnt {{
  color:{ACCENT}; font-weight:700; font-size:15px;
}}
</style>
</head>
<body>
<div id="map"></div>
<div class="overlay-badge">
  ⚡ RapidScan &nbsp;·&nbsp; Detections: <span class="cnt" id="cnt">0</span>
</div>
<script>
var map = L.map('map',{{zoomControl:false}}).setView([{olat},{olon}],14);
L.control.zoom({{position:'bottomleft'}}).addTo(map);
L.tileLayer(
  'https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',
  {{attribution:'&copy; CARTO',subdomains:'abcd',maxZoom:22}}
).addTo(map);

var markers = {{}};
var cnt = 0;

// Colour lookup for building classes
var clsColors = {{
  'RCC': '#1DA1F2', 'MR': '#f97316', 'AD': '#a855f7',
  'Metal': '#64748b', 'Timber': '#84cc16', 'Non': '#ef4444'
}};
function clsColor(cls) {{
  var keys = Object.keys(clsColors);
  for (var i=0; i<keys.length; i++) {{
    if (cls.indexOf(keys[i]) === 0) return clsColors[keys[i]];
  }}
  return '{ACCENT}';
}}

function updateMap(lat, lon, cls, id) {{
  var color = clsColor(cls);
  var iconHtml = '<div style="background:'+color+';width:13px;height:13px;'
    + 'border-radius:50%;box-shadow:0 0 8px '+color+'55;'
    + 'border:2px solid #fff;"></div>';
  var icon = L.divIcon({{
    className:'', html:iconHtml, iconSize:[13,13], iconAnchor:[6,6]
  }});
  var popup = '<div style="font-family:monospace;font-size:12px;'
    + 'padding:10px 14px;min-width:160px;">'
    + '<b style="color:'+color+'">🏢 Building #'+id+'</b><br>'
    + '<span style="color:#666">📍 '+lat.toFixed(6)+', '+lon.toFixed(6)+'</span><br>'
    + '<span style="color:'+color+'">🏷 '+cls+'</span>'
    + '</div>';
  cnt++;
  document.getElementById('cnt').textContent = cnt;
  var m = L.marker([lat,lon],{{icon:icon}}).addTo(map).bindPopup(popup);
  markers[id] = m;
  if (cnt === 1) map.flyTo([lat,lon], 16, {{duration:1.2}});
}}

function clearMarkers() {{
  Object.values(markers).forEach(function(m){{ map.removeLayer(m); }});
  markers = {{}};
  cnt = 0;
  document.getElementById('cnt').textContent = 0;
}}
</script>
</body>
</html>"""
        try:
            tmp_dir = os.path.join(tempfile.gettempdir(), "riskmap_rapidscan")
            os.makedirs(tmp_dir, exist_ok=True)
            self._temp_map_file = os.path.join(tmp_dir, "rapidscan_map.html")
            with open(self._temp_map_file, "w", encoding="utf-8") as f:
                f.write(html)
            self.web_view.setUrl(QUrl.fromLocalFile(self._temp_map_file))
        except Exception as e:
            self.log_message(f"Map init error: {e}")

    def _on_origin_changed(self):
        self.gps_origin = (
            self.origin_lat_spin.value(),
            self.origin_lon_spin.value(),
        )
        self.gps_lbl.setText(
            f"📍 Origin: {self.gps_origin[0]:.4f}, {self.gps_origin[1]:.4f}"
        )

    # ── Video load / controls ────────────────────────────────────────────
    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v);;All Files (*)",
        )
        if not path:
            return
        self.video_path = path
        fname = os.path.basename(path)

        cap = open_video(path)
        if cap.isOpened():
            fps   = cap.get(cv2.CAP_PROP_FPS) or 0.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            ret, frame = cap.read()
            cap.release()
            if fps and fps > 0:
                self.fps_spin.setValue(min(round(fps), 30))
                self.native_fps_lbl.setText(
                    f"FPS: {fps:.2f}  |  {total} frames  |  {w}×{h}"
                )
            else:
                self.native_fps_lbl.setText("FPS: unknown — defaulting to 30")
            self.vid_info.setText(fname)
            self.log_message(
                f"Loaded: {fname}  ({w}×{h}, {fps:.1f} fps, {total} frames)"
            )
            if ret:
                self._display_frame(frame)
        else:
            cap.release()
            self.vid_info.setText(f"⚠️ {fname}")
            self.log_message(
                f"⚠️  Could not open '{fname}'. "
                "AVI/MKV files need OpenCV with FFMPEG. "
                "Try converting to MP4."
            )
        self.btn_process.setEnabled(True)

    def _browse_checkpoint(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Checkpoint",
            "", "PyTorch Weights (*.pth *.pt);;All Files (*)"
        )
        if path:
            self.chkpt_edit.setText(path)

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder = folder
            self.log_message(f"Output folder: {folder}")
            # Show just the last two path components
            parts = Path(folder).parts
            short = os.sep.join(parts[-2:]) if len(parts) >= 2 else folder
            self.vid_info.setText(
                self.vid_info.text() + f"\n📁 …/{short}"
            )

    def start_processing(self):
        if not self.video_path:
            self.log_message("Error: load a video first.")
            return
        if not self.output_folder:
            self.log_message("Error: select an output folder first.")
            return

        self.btn_process.setEnabled(False)
        self.btn_load_video.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.det_table.setRowCount(0)
        self.detections = []
        self.progress_bar.setValue(0)

        # Clear map
        self.web_view.page().runJavaScript(
            "if(typeof clearMarkers==='function') clearMarkers();"
        )

        # Output subdirectories
        for sub in ("crops", "duplicates", "originals"):
            os.makedirs(os.path.join(self.output_folder, sub), exist_ok=True)

        chkpt = self.chkpt_edit.text().strip() or self.checkpoint_path
        origin = (self.origin_lat_spin.value(), self.origin_lon_spin.value())

        self.video_processor = VideoProcessor(
            self.video_path, chkpt, CLASS_NAMES,
            detection_fps=self.fps_spin.value(),
            gps_origin=origin,
        )
        self.video_processor.output_folder = self.output_folder
        self.video_processor.crops_dir = os.path.join(self.output_folder, "crops")
        self.video_processor.dup_dir   = os.path.join(self.output_folder, "duplicates")
        self.video_processor.orig_dir  = os.path.join(self.output_folder, "originals")

        self.video_label.setText(
            "⚙️  Processing…  detection + classification running"
        )
        self.video_label.setPixmap(QPixmap())
        self.playback_controls.setVisible(False)
        if self.playback_cap:
            self.playback_cap.release()
            self.playback_cap = None
        self.playback_timer.stop()

        self.video_processor.frame_ready.connect(self._on_frame)
        self.video_processor.detection_made.connect(self._add_detection)
        self.video_processor.status_update.connect(self.log_message)
        self.video_processor.progress_update.connect(self._on_progress)
        self.video_processor.finished.connect(self._on_processing_finished)
        self.video_processor.start()
        self.log_message(
            f"Started — detection at {self.fps_spin.value()} fps  |  "
            f"GPS origin: {origin[0]:.4f}, {origin[1]:.4f}"
        )

    def stop_processing(self):
        if self.video_processor and self.video_processor.isRunning():
            self.video_processor.stop()
            self.video_processor.wait(3000)
            self.log_message("Processing stopped by user.")
        self._reset_ui()

    @pyqtSlot(int)
    def _on_progress(self, val: int):
        self.progress_bar.setValue(val)
        if self.playback_cap:
            total = int(self.playback_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            curr  = int(self.playback_cap.get(cv2.CAP_PROP_POS_FRAMES))
            self.frame_lbl.setText(f"{curr} / {total}")

    def _on_processing_finished(self):
        self._reset_ui()
        self.log_message("✓ Processing complete.")
        self._save_results()

        annotated = (
            getattr(self.video_processor, "output_video_path", None)
            or os.path.join(self.output_folder or "", "annotated_video.mp4")
        )
        played = False
        if (annotated and os.path.exists(annotated)
                and os.path.getsize(annotated) > 1024):
            self.log_message(
                f"Starting annotated playback: "
                f"{os.path.basename(annotated)} "
                f"({os.path.getsize(annotated) // 1024} KB)"
            )
            played = self._start_playback(annotated)

        if not played and self.video_path and os.path.exists(self.video_path):
            self.log_message("Playing original source video.")
            self._start_playback(self.video_path)

    def _reset_ui(self):
        self.btn_process.setEnabled(True)
        self.btn_load_video.setEnabled(True)
        self.btn_stop.setEnabled(False)

    # ── Playback ──────────────────────────────────────────────────────────
    def _start_playback(self, path: str) -> bool:
        if self.playback_cap:
            self.playback_cap.release()
        self.playback_cap = open_video(path)
        if not self.playback_cap.isOpened():
            sz = os.path.getsize(path) if os.path.exists(path) else 0
            self.log_message(
                f"Playback failed: {os.path.basename(path)} "
                f"(size={sz} B, "
                f"{'exists' if os.path.exists(path) else 'MISSING'})"
            )
            return False

        fps   = self.playback_cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(self.playback_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.video_slider.blockSignals(True)
        self.video_slider.setRange(0, max(0, total - 1))
        self.video_slider.setValue(0)
        self.video_slider.blockSignals(False)
        self.frame_lbl.setText(f"0 / {total}")
        self.playback_controls.setVisible(True)
        self.btn_play_pause.setText("⏸")
        self._playback_playing = True
        interval = max(16, int(1000 / fps))
        self.playback_timer.start(interval)
        self.log_message(f"Playback: {total} frames @ {fps:.1f} fps")
        return True

    def _next_playback_frame(self):
        if not self.playback_cap or not self.playback_cap.isOpened():
            return
        ret, frame = self.playback_cap.read()
        if ret:
            self._display_frame(frame)
            curr  = int(self.playback_cap.get(cv2.CAP_PROP_POS_FRAMES))
            total = int(self.playback_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.video_slider.blockSignals(True)
            self.video_slider.setValue(curr)
            self.video_slider.blockSignals(False)
            self.frame_lbl.setText(f"{curr} / {total}")
        else:
            # Loop back to start
            self.playback_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def toggle_playback(self):
        if self.playback_timer.isActive():
            self.playback_timer.stop()
            self.btn_play_pause.setText("▶")
            self._playback_playing = False
        else:
            if self.playback_cap:
                fps = self.playback_cap.get(cv2.CAP_PROP_FPS) or 30.0
                self.playback_timer.start(max(16, int(1000 / fps)))
                self.btn_play_pause.setText("⏸")
                self._playback_playing = True

    def _on_slider_value_changed(self, position: int):
        """Handles keyboard arrow-key navigation on the slider."""
        if not self.video_slider.isSliderDown():
            # Only act if the slider isn't being dragged (that's handled by sliderMoved)
            self.seek_video(position)

    def seek_video(self, position: int):
        """Seek playback to the given frame position."""
        if not self.playback_cap:
            return
        was_playing = self.playback_timer.isActive()
        self.playback_timer.stop()
        self.playback_cap.set(cv2.CAP_PROP_POS_FRAMES, position)
        ret, frame = self.playback_cap.read()
        if ret:
            self._display_frame(frame)
            total = int(self.playback_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.frame_lbl.setText(f"{position} / {total}")
        if was_playing and self._playback_playing:
            fps = self.playback_cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.playback_timer.start(max(16, int(1000 / fps)))

    # ── Detections / Map ─────────────────────────────────────────────────
    @pyqtSlot(np.ndarray)
    def _on_frame(self, frame: np.ndarray):
        self._display_frame(frame)

    def _display_frame(self, frame: np.ndarray):
        try:
            rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            q_img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
            lw = self.video_label.width()
            lh = self.video_label.height()
            if lw > 10 and lh > 10:
                pix = QPixmap.fromImage(q_img).scaled(
                    lw, lh, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.video_label.setPixmap(pix)
        except Exception:
            pass

    @pyqtSlot(float, float, str, int)
    def _add_detection(self, lat: float, lon: float,
                       classification: str, det_id: int):
        """
        Receive a single unique classified building from VideoProcessor.
        det_id is the final sequential ID after DBSCAN dedup.
        """
        row = self.det_table.rowCount()
        self.det_table.insertRow(row)
        for col, val in enumerate([
            str(det_id + 1),          # 1-based display
            f"{lat:.6f}",
            f"{lon:.6f}",
            classification,
        ]):
            item = QTableWidgetItem(val)
            if col == 3:
                # Colour-code by structural type
                item.setForeground(QColor(TXT_HI))
            self.det_table.setItem(row, col, item)
        self.det_table.scrollToBottom()

        self.detections.append({
            "id":             det_id + 1,
            "lat":            lat,
            "lon":            lon,
            "classification": classification,
        })
        n = len(self.detections)
        self.det_count_lbl.setText(
            f"{n} detection{'s' if n != 1 else ''}"
        )

        # Update Leaflet map (JS-escape classification to handle apostrophes)
        safe_cls = js_escape(classification)
        js = (
            f"if(typeof updateMap==='function') "
            f"updateMap({lat},{lon},'{safe_cls}',{det_id + 1});"
        )
        self.web_view.page().runJavaScript(js)

        # Update risk panel exposure list
        self.risk_panel.load_from_detections(self.detections)

    def _save_results(self):
        if not self.output_folder or not self.detections:
            return
        csv_path = os.path.join(self.output_folder, "detections.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Latitude", "Longitude", "Classification"])
            for d in self.detections:
                writer.writerow(
                    [d["id"], d["lat"], d["lon"], d["classification"]]
                )
        self.log_message(f"Results saved: {csv_path}")

    def log_message(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"<span style='color:{TXT_LOW}'>[{ts}]</span> {msg}")
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())
        # Truncate status bar text
        self.status_lbl.setText(msg[:90] if len(msg) > 90 else msg)

    def closeEvent(self, event):
        if self.video_processor and self.video_processor.isRunning():
            self.video_processor.stop()
            self.video_processor.wait(3000)
        if self.playback_cap:
            self.playback_cap.release()
        self.playback_timer.stop()
        event.accept()