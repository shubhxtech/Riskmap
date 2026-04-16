"""
RapidScanWindow.py — Real-time video building detection + seismic risk assessment.
Integrated into RiskMap as a PyQt5 tab widget.

Ported from PySide6 (RAPID_SCAN/main.py + risk_tab.py).
Key fixes vs original:
  • PyQt5 instead of PySide6 (pyqtSignal/pyqtSlot, Qt.Horizontal, etc.)
  • AVI / codec-agnostic video loading (tries multiple OpenCV backends)
  • risk_engine imported from same src/ directory
  • Theme: RiskMap brand blue (#1DA1F2) instead of cyan (#00d4aa)
"""

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
from PyQt5.QtGui import QImage, QPixmap, QColor, QFont

# WebEngine MUST be imported before QApplication / QtWidgets (sets OpenGL context flag)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEngineSettings

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
        boore_atkinson_2008_pga,
    )
    _RISK_OK = True
except Exception as _risk_err:
    _RISK_OK = False
    _RISK_ERR = str(_risk_err)

# ── Palette (matches RiskMap brand) ──────────────────────────────────────────
BG_DEEP   = "#0d1117"
BG_PANEL  = "#111827"
BG_CARD   = "#1f2937"
BORDER    = "#374151"
ACCENT    = "#1DA1F2"       # RiskMap brand blue
ACCENT_H  = "#1A91DA"       # hover
ACCENT2   = "#f78166"       # warning/stop  
ACCENT3   = "#43A047"       # success/green
TXT_HI    = "#f3f4f6"
TXT_MID   = "#9ca3af"
TXT_LOW   = "#6b7280"
FONT_MONO = "Menlo, Consolas, Courier New"

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


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: robust video open  (fixes AVI on macOS and Linux)
# ─────────────────────────────────────────────────────────────────────────────
def open_video(path: str) -> cv2.VideoCapture:
    """Try multiple OpenCV backends until one opens successfully."""
    backends = [
        cv2.CAP_ANY,      # let OpenCV decide
        cv2.CAP_FFMPEG,   # explicit FFMPEG
        cv2.CAP_AVFOUNDATION,  # macOS native
        cv2.CAP_GSTREAMER,     # Linux
        0,               # bare integer (no backend hint)
    ]
    for bk in backends:
        try:
            if bk == 0:
                cap = cv2.VideoCapture(path)
            else:
                cap = cv2.VideoCapture(path, bk)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    return cap
                cap.release()
        except Exception:
            continue
    # Last resort — return even if not opened, let caller handle error
    return cv2.VideoCapture(path)


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
    frame_ready      = pyqtSignal(np.ndarray)
    detection_made   = pyqtSignal(float, float, str)
    status_update    = pyqtSignal(str)
    progress_update  = pyqtSignal(int)
    finished         = pyqtSignal()

    def __init__(self, video_path, checkpoint_path, class_names, detection_fps=30):
        super().__init__()
        self.video_path      = video_path
        self.checkpoint_path = checkpoint_path
        self.class_names     = class_names
        self.detection_fps   = detection_fps
        self.running         = True
        self._active_trackers = []
        self._next_id        = 0
        self.output_folder   = None
        self.crops_dir       = None
        self.dup_dir         = None
        self.orig_dir        = None

    # ── Lazy load TF detector ──
    def _load_detector(self):
        self.status_update.emit("Loading Faster R-CNN detector (TF Hub)…")
        try:
            import tensorflow as tf
            import tensorflow_hub as hub
            self._tf = tf
            gpus = tf.config.list_physical_devices("GPU")
            device = "/GPU:0" if gpus else "/CPU:0"
            with tf.device(device):
                module = hub.load(
                    "https://tfhub.dev/google/faster_rcnn/openimages_v4/inception_resnet_v2/1"
                )
            self.detector = module.signatures["default"]
            self.status_update.emit(f"Detector loaded on {device}")
            self._gpus = gpus
        except Exception as e:
            self.status_update.emit(f"Detector load failed: {e}")
            self.detector = None
            self._gpus = []

    # ── Lazy load BEiT classifier ──
    def _load_classifier(self):
        self.status_update.emit("Loading BEiT classifier…")
        try:
            import torch
            from transformers import BeitForImageClassification, BeitImageProcessor
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
                ckpt = torch.load(self.checkpoint_path, map_location=device,
                                  weights_only=False)
                model.load_state_dict(ckpt.get("model_state_dict", ckpt), strict=False)
                self.status_update.emit(f"Custom checkpoint loaded from {self.checkpoint_path}")
            model.to(device).eval()
            self.classifier = model
            self._transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.5] * 3, [0.5] * 3),
            ])
            self._torch = torch
            self.status_update.emit(f"Classifier loaded on {device}")
        except Exception as e:
            self.status_update.emit(f"Classifier load failed: {e}")
            self.classifier = None

    def _classify_crop(self, crop_bgr):
        """Run BEiT on crop, return predicted class name."""
        try:
            pil_img = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
            tensor = self._transform(pil_img).unsqueeze(0).to(self._torch_device)
            with self._torch.no_grad():
                idx = self.classifier(tensor).logits.argmax(1).item()
            return self.class_names[idx]
        except Exception:
            return "Unknown"

    def _apply_dbscan(self):
        if not _SKLEARN_OK or not hasattr(self, "all_crops") or not self.all_crops:
            return
        try:
            coords = np.array([[c["lat"], c["lon"]] for c in self.all_crops])
            labels = DBSCAN(eps=0.0003, min_samples=2).fit(coords).labels_

            unique, duplicates = [], []
            seen_clusters = set()
            for i, label in enumerate(labels):
                crop = self.all_crops[i]
                if label == -1:
                    unique.append(crop)
                elif label not in seen_clusters:
                    seen_clusters.add(label)
                    crop["cluster"] = label
                    unique.append(crop)
                else:
                    duplicates.append(crop)

            n_dup, n_uniq = len(duplicates), len(unique)
            self.status_update.emit(
                f"DBSCAN: {n_uniq} unique, {n_dup} duplicates removed."
            )
            # Classify unique crops and emit
            for u in unique:
                pred_class = (
                    self._classify_crop(u["crop"]) if self.classifier else "Unknown"
                )
                self.detection_made.emit(u["lat"], u["lon"], pred_class)
        except Exception as e:
            self.status_update.emit(f"DBSCAN error: {e}")

    def run(self):
        try:
            self._load_detector()
            self._load_classifier()

            cap = open_video(self.video_path)
            if not cap.isOpened():
                self.status_update.emit(
                    f"ERROR: Cannot open video: {self.video_path}\n"
                    "Supported formats: MP4, AVI, MOV, MKV. "
                    "Make sure OpenCV is built with FFMPEG support."
                )
                self.finished.emit()
                return

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            det_interval = max(1, int(fps / self.detection_fps))

            self.status_update.emit(f"Processing: {w}×{h} @ {fps:.1f} fps")

            # Optional video output
            out = None
            if self.output_folder:
                try:
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    out_path = os.path.join(self.output_folder, "annotated_video.mp4")
                    out = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
                except Exception as e:
                    self.status_update.emit(f"VideoWriter error: {e}")

            self.all_crops = []
            frame_count = 0

            while self.running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    # Retry once for AVI end-of-stream quirk
                    time.sleep(0.05)
                    ret, frame = cap.read()
                    if not ret:
                        break

                if frame_count % det_interval == 0 and self.detector is not None:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    try:
                        t = self._tf.convert_to_tensor(rgb, dtype=self._tf.float32) / 255.0
                        result = self.detector(t[self._tf.newaxis, ...])
                        boxes  = np.array(result["detection_boxes"]).reshape(-1, 4)
                        scores = np.array(result["detection_scores"]).flatten()
                        raw_cls = np.array(result["detection_class_entities"]).flatten()

                        for i in range(len(scores)):
                            if scores[i] < 0.30:
                                continue
                            cname = (
                                raw_cls[i].decode("utf-8")
                                if isinstance(raw_cls[i], bytes)
                                else str(raw_cls[i])
                            )
                            if cname not in ["House", "Building", "Skyscraper", "Tower"]:
                                continue

                            box = boxes[i]
                            ymin, xmin, ymax, xmax = box
                            y1 = max(0, int(ymin * h))
                            x1 = max(0, int(xmin * w))
                            y2 = min(h, int(ymax * h))
                            x2 = min(w, int(xmax * w))
                            crop = rgb[y1:y2, x1:x2]
                            if crop.size > 0:
                                crop_bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
                                lat = 31.7085 + self._next_id * 0.0001
                                lon = 76.9320 + self._next_id * 0.0001
                                self.all_crops.append({
                                    "id": self._next_id,
                                    "crop": crop_bgr,
                                    "lat": lat, "lon": lon,
                                })
                                if self.crops_dir:
                                    cv2.imwrite(
                                        os.path.join(self.crops_dir, f"{self._next_id}.jpg"),
                                        crop_bgr,
                                    )
                                self._next_id += 1

                            # Draw box on frame
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (29, 161, 242), 2)
                            cv2.putText(
                                frame, "Building",
                                (x1, max(y1 - 8, 0)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (29, 161, 242), 2,
                            )
                    except Exception as e:
                        self.status_update.emit(f"Detection error frame {frame_count}: {e}")

                self.frame_ready.emit(frame)
                if out:
                    out.write(frame)
                frame_count += 1
                if total > 0:
                    self.progress_update.emit(int(frame_count / total * 100))

            cap.release()
            if out:
                out.release()
            self.status_update.emit("Running DBSCAN deduplication…")
            self._apply_dbscan()
        except Exception as e:
            self.status_update.emit(f"Fatal error: {e}")
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
    """Standalone risk panel embedded in RapidScanWindow."""

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
        left.setMaximumWidth(320)
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

        def row(label, widget, r):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
            eg2.addWidget(lbl, r, 0)
            eg2.addWidget(widget, r, 1)

        self.mw_spin = QDoubleSpinBox()
        self.mw_spin.setRange(4.0, 9.0); self.mw_spin.setValue(6.5)
        self.mw_spin.setSingleStep(0.1); self.mw_spin.setSuffix(" Mw")
        row("Magnitude:", self.mw_spin, 0)

        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(1.0, 300.0); self.depth_spin.setValue(10.0)
        self.depth_spin.setSuffix(" km")
        row("Depth:", self.depth_spin, 1)

        self.src_lat = QDoubleSpinBox()
        self.src_lat.setRange(-90, 90); self.src_lat.setValue(31.70)
        self.src_lat.setDecimals(4); self.src_lat.setSingleStep(0.01)
        row("Source Lat:", self.src_lat, 2)

        self.src_lon = QDoubleSpinBox()
        self.src_lon.setRange(-180, 180); self.src_lon.setValue(76.93)
        self.src_lon.setDecimals(4); self.src_lon.setSingleStep(0.01)
        row("Source Lon:", self.src_lon, 3)

        self.vs30_spin = QDoubleSpinBox()
        self.vs30_spin.setRange(100, 1500); self.vs30_spin.setValue(400)
        self.vs30_spin.setSuffix(" m/s")
        row("Vs30:", self.vs30_spin, 4)

        hint = QLabel("(180=soft · 400=stiff · 760=rock)")
        hint.setStyleSheet(f"color:{TXT_LOW}; font-size:9px;")
        eg2.addWidget(hint, 5, 0, 1, 2)

        self.fault_combo = QComboBox()
        self.fault_combo.addItems(["unspecified", "reverse", "normal", "strike-slip"])
        row("Fault type:", self.fault_combo, 6)

        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(100, 5000); self.samples_spin.setValue(500)
        self.samples_spin.setSuffix(" samples")
        row("MC samples:", self.samples_spin, 7)
        ll.addWidget(eq_grp)

        # Quick presets
        preset_grp = QGroupBox("QUICK SCENARIOS  (Mandi, HP)")
        pg = QVBoxLayout(preset_grp)
        presets = [
            ("Mw 5.5  Moderate (R=20 km)", 5.5, 10, 31.65, 76.99),
            ("Mw 6.5  Strong   (R=15 km)", 6.5, 12, 31.62, 76.95),
            ("Mw 7.0  Major    (R=10 km)", 7.0, 15, 31.68, 76.90),
            ("Mw 7.5  Severe   (R=8 km)",  7.5, 20, 31.72, 76.87),
        ]
        for name, mw, dep, slat, slon in presets:
            btn = QPushButton(name)
            btn.setStyleSheet(
                f"text-align:left; padding:4px 8px; font-size:10px;"
                f"background:{BG_CARD}; color:{TXT_MID}; border:1px solid {BORDER}; border-radius:4px;"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _, m=mw, d=dep, la=slat, lo=slon: self._apply_preset(m, d, la, lo)
            )
            pg.addWidget(btn)
        ll.addWidget(preset_grp)

        # Run / export
        self.btn_run = QPushButton("▶  RUN RISK ASSESSMENT")
        self.btn_run.setObjectName("run")
        self.btn_run.setEnabled(False)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setStyleSheet(
            f"background:{ACCENT}; color:#fff; font-weight:700; border:none;"
            f"border-radius:6px; padding:10px; font-size:13px;"
        )
        self.btn_run.clicked.connect(self.run_assessment)
        ll.addWidget(self.btn_run)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        ll.addWidget(self.progress_bar)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(110)
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
        self.kpi_widgets = {}
        for key, label in [
            ("n_buildings",      "Buildings"),
            ("pga_mean_g",       "Mean PGA (g)"),
            ("avg_loss_ratio",   "Avg Loss Ratio"),
            ("total_loss_units", "Total Loss Units"),
        ]:
            card = QWidget()
            card.setStyleSheet(
                f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:8px; padding:8px;"
            )
            cl = QVBoxLayout(card)
            cl.setSpacing(2)
            val_lbl = QLabel("—")
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
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_table_select)
        rl.addWidget(self.table, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 900])
        root.addWidget(splitter)

    # ── Exposure loading ──────────────────────────────────────────────────
    def load_from_detections(self, detections: list):
        if not _RISK_OK:
            return
        self.buildings = []
        for det in detections:
            self.buildings.append(BuildingRecord(
                id=det.get("id", len(self.buildings) + 1),
                lat=det.get("lat", 31.7085),
                lon=det.get("lon", 76.9320),
                beit_class=det.get("classification", "RCC_H1 flat roof"),
            ))
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
            if not required.issubset(set(df.columns)):
                self._log(f"CSV missing columns. Need: {required}")
                return
            self.buildings = [
                BuildingRecord(
                    id=int(r["id"]), lat=float(r["lat"]),
                    lon=float(r["lon"]), beit_class=str(r["classification"])
                )
                for _, r in df.iterrows()
            ]
            self._update_exposure_label()
            self._log(f"Loaded {len(self.buildings)} buildings from {os.path.basename(path)}")
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
            self._log("No buildings or risk engine unavailable.")
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
            f"({params.source_lat:.4f}, {params.source_lon:.4f})"
        )
        self.btn_run.setEnabled(False)
        self.progress_bar.setVisible(True)
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
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(True)
        self._update_kpis(summary)
        self._draw_ds_chart(summary)
        self._fill_table(results)
        self._log(
            f"✓ Complete — {summary.get('n_buildings', 0)} buildings. "
            f"Avg loss ratio: {summary.get('avg_loss_ratio', 0):.1%}"
        )

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        self._log(f"ERROR: {msg}")

    # ── KPI / charts ──────────────────────────────────────────────────────
    def _update_kpis(self, s):
        self.kpi_widgets["n_buildings"].setText(str(s.get("n_buildings", "—")))
        self.kpi_widgets["pga_mean_g"].setText(f"{s.get('pga_mean_g', 0):.4f}")
        self.kpi_widgets["avg_loss_ratio"].setText(f"{s.get('avg_loss_ratio', 0):.1%}")
        self.kpi_widgets["total_loss_units"].setText(f"{s.get('total_loss_units', 0):.1f}")

    def _draw_ds_chart(self, summary):
        ax = self.ds_canvas.ax
        ax.clear()
        ds_pct = summary.get("ds_pct", {})
        labels = ["None", "DS1", "DS2", "DS3", "DS4"]
        vals   = [ds_pct.get(k, 0) for k in labels]
        colors = [DS_COLORS[k] for k in labels]
        bars   = ax.bar(labels, vals, color=colors, edgecolor=BORDER, linewidth=0.7)
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
        if not _RISK_OK:
            return
        from risk_engine import FRAGILITY_LIB, fragility_prob
        ax = self.frag_canvas.ax
        ax.clear()
        params    = FRAGILITY_LIB.get(archetype, FRAGILITY_LIB.get("CR_LFINF_DUL_H1", {}))
        pga_range = np.linspace(0.01, 2.0, 300)
        ds_labels = {"DS1": "Slight", "DS2": "Moderate", "DS3": "Extensive", "DS4": "Complete"}
        ds_clrs   = {"DS1": "#facc15", "DS2": "#f97316", "DS3": "#ef4444", "DS4": "#7f1d1d"}
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
        ax.yaxis.grid(True, alpha=0.3); ax.set_axisbelow(True)
        self.frag_canvas.fig.tight_layout()
        self.frag_canvas.draw()

    def _fill_table(self, results):
        self.table.setRowCount(0)
        for r in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            row_color = QColor(DS_COLORS.get(r.mean_ds, BG_CARD))
            vals = [
                str(r.id), r.beit_class, r.archetype,
                f"{r.lat:.5f}", f"{r.lon:.5f}",
                f"{r.pga_median:.4f}",
                f"{r.ds_probs['DS1']:.3f}", f"{r.ds_probs['DS2']:.3f}",
                f"{r.ds_probs['DS3']:.3f}", f"{r.ds_probs['DS4']:.3f}",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(TXT_HI))
                if col == 0:
                    item.setBackground(row_color)
                self.table.setItem(row, col, item)

    def _on_table_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows or not self.results:
            return
        idx = rows[0].row()
        if idx < len(self.results):
            r = self.results[idx]
            self._draw_fragility(r.archetype, r.pga_median)

    def export_csv(self):
        if not _PANDAS_OK or self.df is None:
            self._log("pandas not available or no results.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Risk Results", "risk_results.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.df.to_csv(path, index=False)
            self._log(f"✓ Exported {len(self.df)} rows → {path}")

    def _log(self, msg):
        self.log.append(msg)
        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum()
        )


# ─────────────────────────────────────────────────────────────────────────────
#  RapidScanWindow — main tab widget
# ─────────────────────────────────────────────────────────────────────────────
class RapidScanWindow(QWidget):
    """Embeddable PyQt5 widget for the RiskMap tab bar."""

    def __init__(self, config=None, logger=None):
        super().__init__()
        self.config     = config
        self.logger     = logger

        self.video_path      = None
        self.output_folder   = None
        self.detections      = []
        self.video_processor = None
        self.playback_cap    = None
        self._temp_map_file  = None

        # Resolve checkpoint path from config, fallback to project default
        self.checkpoint_path = self._resolve_checkpoint()

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._next_playback_frame)

        self._build_ui()
        self._write_map_html()

    def _resolve_checkpoint(self):
        """Try to locate the classifier checkpoint from config."""
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
        # Fallback: look relative to this file
        here = Path(__file__).parent.parent / "assets" / "models" / "classifier" / "best_model.pth"
        return str(here) if here.exists() else ""

    # ── Stylesheet ────────────────────────────────────────────────────────
    def _stylesheet(self):
        return f"""
        QWidget {{
            background: {BG_DEEP};
            color: {TXT_HI};
            font-family: -apple-system, 'Helvetica Neue', 'Segoe UI', sans-serif;
        }}
        QGroupBox {{
            border: 1px solid {BORDER};
            border-radius: 8px;
            margin-top: 10px;
            font-weight: bold;
            color: {ACCENT};
            background: {BG_PANEL};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }}
        QPushButton {{
            background: {BG_CARD};
            color: {TXT_HI};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            border-color: {ACCENT};
            color: {ACCENT};
        }}
        QPushButton:disabled {{
            color: {TXT_LOW};
            border-color: {BG_CARD};
        }}
        QProgressBar {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 4px;
            height: 8px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {ACCENT}, stop:1 {ACCENT_H});
            border-radius: 4px;
        }}
        QTableWidget {{
            background: {BG_PANEL};
            color: {TXT_HI};
            gridline-color: {BORDER};
            border: none;
            font-size: 11px;
            alternate-background-color: {BG_CARD};
        }}
        QHeaderView::section {{
            background: {BG_CARD};
            color: {ACCENT};
            border: none;
            border-bottom: 2px solid {ACCENT};
            padding: 6px;
            font-weight: bold;
        }}
        QTextEdit {{
            background: {BG_CARD};
            color: {TXT_MID};
            border: 1px solid {BORDER};
            border-radius: 6px;
            font-family: {FONT_MONO};
            font-size: 11px;
        }}
        QSpinBox, QDoubleSpinBox, QComboBox {{
            background: {BG_CARD};
            color: {TXT_HI};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QSlider::groove:horizontal {{
            background: {BORDER};
            height: 4px;
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
        QSplitter::handle {{
            background: {BORDER};
        }}
        QSplitter::handle:horizontal {{ width: 5px; }}
        QSplitter::handle:vertical   {{ height: 5px; }}
        QSplitter::handle:hover {{ background: {ACCENT}; }}
        QTabWidget::pane {{
            border: 1px solid {BORDER};
            background: {BG_PANEL};
        }}
        QTabBar::tab {{
            background: {BG_CARD};
            color: {TXT_MID};
            padding: 8px 18px;
            border: 1px solid {BORDER};
            border-bottom: none;
        }}
        QTabBar::tab:selected {{
            background: {BG_PANEL};
            color: {ACCENT};
            border-bottom: 2px solid {ACCENT};
        }}
        """

    # ── Build UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        self.setStyleSheet(self._stylesheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ────────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setStyleSheet(
            f"QFrame {{ background:{BG_PANEL}; border-bottom:1px solid {BORDER}; }}"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 10, 16, 10)
        tb_layout.setSpacing(12)

        title_icon = QLabel("⚡")
        title_icon.setStyleSheet(f"font-size:18px; background:transparent;")
        tb_layout.addWidget(title_icon)

        title = QLabel("RAPIDSCAN  ·  Real-time Building Detection & Risk")
        title.setStyleSheet(
            f"font-size:15px; font-weight:700; color:{ACCENT}; background:transparent; "
            f"letter-spacing:0.5px;"
        )
        tb_layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color:{BORDER};")
        tb_layout.addWidget(sep)

        self.status_lbl = QLabel("● SYSTEM READY")
        self.status_lbl.setStyleSheet(f"color:{ACCENT3}; font-size:12px; background:transparent;")
        tb_layout.addWidget(self.status_lbl, 1)

        root.addWidget(toolbar)

        # ── Main splitter: map (top) | content (bottom) ────────────────
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setChildrenCollapsible(False)

        # Map view
        map_widget = QWidget()
        map_widget.setMinimumHeight(60)
        ml = QVBoxLayout(map_widget)
        ml.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        try:
            settings = self.web_view.settings()
            settings.setAttribute(
                QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.LocalStorageEnabled, True
            )
        except Exception:
            pass
        ml.addWidget(self.web_view)
        main_splitter.addWidget(map_widget)

        # Bottom section with tabs
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        self.right_tabs = QTabWidget()
        self.right_tabs.tabBar().setExpanding(False)
        self.right_tabs.tabBar().setElideMode(Qt.ElideNone)

        # ── Detection tab ──────────────────────────────────────────────
        det_tab  = QWidget()
        det_layout = QVBoxLayout(det_tab)
        det_layout.setContentsMargins(10, 10, 10, 10)
        det_layout.setSpacing(10)

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setChildrenCollapsible(False)

        # Left control panel
        ctrl_panel = QWidget()
        ctrl_panel.setMaximumWidth(280)
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_layout.setSpacing(10)

        file_grp = QGroupBox("FILE SETTINGS")
        fg = QVBoxLayout(file_grp)
        self.btn_load_video = QPushButton("📁  Load Video")
        self.btn_load_video.setCursor(Qt.PointingHandCursor)
        self.btn_load_video.clicked.connect(self.load_video)
        self.btn_select_folder = QPushButton("📂  Select Output Folder")
        self.btn_select_folder.setCursor(Qt.PointingHandCursor)
        self.btn_select_folder.clicked.connect(self.select_output_folder)
        self.vid_info = QLabel("No video loaded")
        self.vid_info.setStyleSheet(f"color:{TXT_LOW}; font-size:10px;")
        fg.addWidget(self.btn_load_video)
        fg.addWidget(self.btn_select_folder)
        fg.addWidget(self.vid_info)
        ctrl_layout.addWidget(file_grp)

        det_grp = QGroupBox("DETECTION SETTINGS")
        dg = QVBoxLayout(det_grp)
        fps_row = QHBoxLayout()
        fps_lbl = QLabel("Detection Rate:")
        fps_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120); self.fps_spin.setValue(30)
        self.fps_spin.setSuffix(" FPS")
        fps_row.addWidget(fps_lbl); fps_row.addWidget(self.fps_spin)
        dg.addLayout(fps_row)
        self.native_fps_lbl = QLabel("Native FPS: —")
        self.native_fps_lbl.setStyleSheet(f"color:{ACCENT}; font-size:10px;")
        dg.addWidget(self.native_fps_lbl)

        chkpt_lbl = QLabel("Checkpoint:")
        chkpt_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
        self.chkpt_edit = QLineEdit(self.checkpoint_path)
        self.chkpt_edit.setPlaceholderText("Path to .pth file…")
        self.chkpt_edit.setStyleSheet(
            f"background:{BG_CARD}; color:{TXT_HI}; border:1px solid {BORDER};"
            f"border-radius:4px; padding:4px; font-size:10px;"
        )
        self.btn_browse_chkpt = QPushButton("Browse")
        self.btn_browse_chkpt.setCursor(Qt.PointingHandCursor)
        self.btn_browse_chkpt.setFixedWidth(70)
        self.btn_browse_chkpt.clicked.connect(self._browse_checkpoint)
        chkpt_row = QHBoxLayout()
        chkpt_row.addWidget(self.chkpt_edit)
        chkpt_row.addWidget(self.btn_browse_chkpt)
        dg.addWidget(chkpt_lbl)
        dg.addLayout(chkpt_row)
        ctrl_layout.addWidget(det_grp)

        action_grp = QGroupBox("CONTROLS")
        ag = QVBoxLayout(action_grp)
        self.btn_process = QPushButton("▶  START DETECTION")
        self.btn_process.setCursor(Qt.PointingHandCursor)
        self.btn_process.setEnabled(False)
        self.btn_process.setStyleSheet(
            f"background:{ACCENT3}; color:#fff; font-weight:700; "
            f"border:none; border-radius:6px; padding:10px;"
        )
        self.btn_process.clicked.connect(self.start_processing)
        self.btn_stop = QPushButton("■  STOP")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            f"background:{ACCENT2}; color:#fff; font-weight:700; "
            f"border:none; border-radius:6px; padding:10px;"
        )
        self.btn_stop.clicked.connect(self.stop_processing)
        ag.addWidget(self.btn_process)
        ag.addWidget(self.btn_stop)
        ctrl_layout.addWidget(action_grp)

        prog_grp = QGroupBox("PROGRESS")
        pg = QVBoxLayout(prog_grp)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        pg.addWidget(self.progress_bar)
        ctrl_layout.addWidget(prog_grp)
        ctrl_layout.addStretch()
        content_splitter.addWidget(ctrl_panel)

        # Right: video feed + log/table
        video_outer = QWidget()
        vo = QVBoxLayout(video_outer)
        vo.setContentsMargins(0, 0, 0, 0)
        vo.setSpacing(8)

        vid_grp = QGroupBox("🎥 VIDEO FEED")
        vg = QVBoxLayout(vid_grp)
        self.video_label = QLabel("No video loaded")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet(
            f"background:{BG_CARD}; border-radius:8px; color:{TXT_LOW};"
            f"font-size:13px;"
        )
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setMinimumHeight(200)
        vg.addWidget(self.video_label)

        # Playback controls
        self.playback_controls = QWidget()
        pc = QHBoxLayout(self.playback_controls)
        pc.setContentsMargins(0, 4, 0, 0)
        self.btn_play_pause = QPushButton("⏸  PAUSE")
        self.btn_play_pause.setFixedWidth(100)
        self.btn_play_pause.setCursor(Qt.PointingHandCursor)
        self.btn_play_pause.clicked.connect(self.toggle_playback)
        self.video_slider = QSlider(Qt.Horizontal)
        self.video_slider.sliderMoved.connect(self.seek_video)
        pc.addWidget(self.btn_play_pause)
        pc.addWidget(self.video_slider)
        vg.addWidget(self.playback_controls)
        self.playback_controls.setVisible(False)
        vo.addWidget(vid_grp, 3)

        # Detection log + table
        log_splitter = QSplitter(Qt.Horizontal)
        tbl_grp = QGroupBox("📊 DETECTION LOG")
        tg = QVBoxLayout(tbl_grp)
        self.det_table = QTableWidget(0, 4)
        self.det_table.setHorizontalHeaderLabels(["ID", "Latitude", "Longitude", "Classification"])
        self.det_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.det_table.verticalHeader().setVisible(False)
        self.det_count_lbl = QLabel("0 detections")
        self.det_count_lbl.setStyleSheet(f"color:{ACCENT}; font-size:11px; padding:4px;")
        tg.addWidget(self.det_table)
        tg.addWidget(self.det_count_lbl)
        log_splitter.addWidget(tbl_grp)

        log_grp = QGroupBox("📝 PROCESSING LOG")
        lg = QVBoxLayout(log_grp)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        lg.addWidget(self.log_text)
        log_splitter.addWidget(log_grp)
        log_splitter.setSizes([450, 300])
        vo.addWidget(log_splitter, 2)

        content_splitter.addWidget(video_outer)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 4)
        det_layout.addWidget(content_splitter)

        self.right_tabs.addTab(det_tab, "🎥  Detection")

        # ── Risk tab ───────────────────────────────────────────────────
        self.risk_panel = RiskAssessmentPanel()
        risk_tab = QWidget()
        rt = QVBoxLayout(risk_tab)
        rt.setContentsMargins(0, 0, 0, 0)
        rt.addWidget(self.risk_panel)
        self.right_tabs.addTab(risk_tab, "⚠️  Risk Assessment")

        bl.addWidget(self.right_tabs, 1)
        main_splitter.addWidget(bottom)
        main_splitter.setSizes([280, 700])
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 7)

        root.addWidget(main_splitter, 1)

    # ── Map HTML ──────────────────────────────────────────────────────────
    def _write_map_html(self):
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>RapidScan Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body, #map {{ width:100%; height:100%; background:{BG_DEEP}; }}
  .overlay-badge {{
    position:absolute; top:12px; right:12px; z-index:1000;
    background:rgba(17,24,39,0.92); backdrop-filter:blur(8px);
    border:1px solid {ACCENT}; border-radius:10px;
    padding:10px 16px; color:{TXT_HI}; font-family:monospace; font-size:12px;
  }}
  .overlay-badge span {{ color:{ACCENT}; font-weight:700; }}
  .marker-cluster-small {{ background-color:rgba(29,161,242,0.25)!important; }}
  .marker-cluster-small div {{ background-color:rgba(29,161,242,0.7)!important; color:#fff; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="overlay-badge">
  ⚡ RapidScan  &nbsp;|&nbsp; Detections: <span id="cnt">0</span>
</div>
<script>
var map = L.map('map', {{zoomControl:false}}).setView([31.7085, 76.9320], 13);
L.control.zoom({{position:'bottomleft'}}).addTo(map);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution:'&copy; CARTO', subdomains:'abcd', maxZoom:20
}}).addTo(map);

var markers = {{}};
var cnt = 0;

function updateMap(lat, lon, cls, id, color) {{
  color = color || '{ACCENT}';
  var iconHtml = '<div style="background:' + color + ';width:14px;height:14px;border-radius:50%;'
    + 'box-shadow:0 0 10px ' + color + ';border:2px solid #fff;"></div>';
  var icon = L.divIcon({{className:'', html:iconHtml, iconSize:[14,14], iconAnchor:[7,7]}});
  var popup = '<div style="font-family:monospace;font-size:12px;color:' + color + ';background:{BG_CARD};padding:10px;border-radius:8px;">'
    + '<b>🏢 #' + id + '</b><br>'
    + '📍 ' + lat.toFixed(6) + ', ' + lon.toFixed(6) + '<br>'
    + '🏷️ ' + cls + '</div>';
  if (!markers[id]) {{
    cnt++;
    document.getElementById('cnt').textContent = cnt;
    var m = L.marker([lat, lon], {{icon:icon}}).addTo(map).bindPopup(popup);
    markers[id] = m;
    if (cnt === 1) map.setView([lat, lon], 16);
  }} else {{
    markers[id].setIcon(icon).setPopupContent(popup);
  }}
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

    # ── Video Controls ────────────────────────────────────────────────────
    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v);;All Files (*)",
        )
        if not path:
            return
        self.video_path = path
        fname = os.path.basename(path)
        self.vid_info.setText(fname)
        self.log_message(f"Loaded: {fname}")

        cap = open_video(path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            ret, frame = cap.read()
            cap.release()
            if fps and fps > 0:
                self.fps_spin.setValue(round(fps))
                self.native_fps_lbl.setText(f"Native FPS: {fps:.2f}  |  {total} frames  |  {w}×{h}")
            else:
                self.native_fps_lbl.setText("FPS: unknown — using 30 default")
            if ret:
                self._display_frame(frame)
        else:
            cap.release()
            self.log_message(
                f"⚠️ Could not open {fname}. "
                "AVI files require OpenCV built with FFMPEG. "
                "Try converting to MP4 if issues persist."
            )
        self.btn_process.setEnabled(True)

    def _browse_checkpoint(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Checkpoint", "", "PyTorch Weights (*.pth *.pt);;All Files (*)"
        )
        if path:
            self.chkpt_edit.setText(path)

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder = folder
            self.log_message(f"Output folder: {folder}")

    def start_processing(self):
        if not self.video_path:
            self.log_message("Error: Load a video first.")
            return
        if not self.output_folder:
            self.log_message("Error: Select an output folder first.")
            return

        self.btn_process.setEnabled(False)
        self.btn_load_video.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.det_table.setRowCount(0)
        self.detections = []
        self.progress_bar.setValue(0)

        # Setup output dirs
        for sub in ("crops", "duplicates", "originals"):
            os.makedirs(os.path.join(self.output_folder, sub), exist_ok=True)

        chkpt = self.chkpt_edit.text().strip() or self.checkpoint_path
        self.video_processor = VideoProcessor(
            self.video_path, chkpt, CLASS_NAMES, self.fps_spin.value()
        )
        self.video_processor.output_folder = self.output_folder
        self.video_processor.crops_dir = os.path.join(self.output_folder, "crops")
        self.video_processor.dup_dir   = os.path.join(self.output_folder, "duplicates")
        self.video_processor.orig_dir  = os.path.join(self.output_folder, "originals")

        self.video_label.setText(
            "⚙️  Processing video in background…\n"
            "Detection & classification running. This may take a while."
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
        self.video_processor.progress_update.connect(self.progress_bar.setValue)
        self.video_processor.finished.connect(self._on_processing_finished)
        self.video_processor.start()
        self.log_message(f"Started with {self.fps_spin.value()} detection FPS")

    def stop_processing(self):
        if self.video_processor and self.video_processor.isRunning():
            self.video_processor.stop()
            self.video_processor.wait(3000)
            self.log_message("Processing stopped by user.")
        self._reset_ui()

    def _on_processing_finished(self):
        self._reset_ui()
        self.log_message("✓ Processing complete.")
        self._save_results()
        out_path = os.path.join(self.output_folder or "", "annotated_video.mp4")
        if os.path.exists(out_path):
            self._start_playback(out_path)

    def _reset_ui(self):
        self.btn_process.setEnabled(True)
        self.btn_load_video.setEnabled(True)
        self.btn_stop.setEnabled(False)

    # ── Playback ──────────────────────────────────────────────────────────
    def _start_playback(self, path):
        if self.playback_cap:
            self.playback_cap.release()
        self.playback_cap = open_video(path)
        if not self.playback_cap.isOpened():
            self.log_message(f"Playback failed: {path}")
            return
        fps    = self.playback_cap.get(cv2.CAP_PROP_FPS) or 30
        total  = int(self.playback_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.video_slider.setRange(0, max(0, total - 1))
        self.video_slider.setValue(0)
        self.playback_controls.setVisible(True)
        self.btn_play_pause.setText("⏸  PAUSE")
        self.playback_timer.start(int(1000 / fps))

    def _next_playback_frame(self):
        if not self.playback_cap or not self.playback_cap.isOpened():
            return
        ret, frame = self.playback_cap.read()
        if ret:
            self._display_frame(frame)
            curr = int(self.playback_cap.get(cv2.CAP_PROP_POS_FRAMES))
            self.video_slider.blockSignals(True)
            self.video_slider.setValue(curr)
            self.video_slider.blockSignals(False)
        else:
            # Loop
            self.playback_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def toggle_playback(self):
        if self.playback_timer.isActive():
            self.playback_timer.stop()
            self.btn_play_pause.setText("▶  PLAY")
        else:
            if self.playback_cap:
                fps = self.playback_cap.get(cv2.CAP_PROP_FPS) or 30
                self.playback_timer.start(int(1000 / fps))
                self.btn_play_pause.setText("⏸  PAUSE")

    def seek_video(self, position):
        if self.playback_cap:
            self.playback_cap.set(cv2.CAP_PROP_POS_FRAMES, position)
            ret, frame = self.playback_cap.read()
            if ret:
                self._display_frame(frame)

    # ── Detections / Map ─────────────────────────────────────────────────
    @pyqtSlot(np.ndarray)
    def _on_frame(self, frame):
        self._display_frame(frame)

    def _display_frame(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            q_img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
            lw, lh = self.video_label.width(), self.video_label.height()
            if lw > 0 and lh > 0:
                pix = QPixmap.fromImage(q_img).scaled(
                    lw, lh, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.video_label.setPixmap(pix)
        except Exception:
            pass

    @pyqtSlot(float, float, str)
    def _add_detection(self, lat, lon, classification):
        row = self.det_table.rowCount()
        self.det_table.insertRow(row)
        det_id = row + 1
        for col, val in enumerate([str(det_id), f"{lat:.6f}", f"{lon:.6f}", classification]):
            self.det_table.setItem(row, col, QTableWidgetItem(val))
        self.det_table.scrollToBottom()
        self.detections.append({"id": det_id, "lat": lat, "lon": lon, "classification": classification})
        self.det_count_lbl.setText(f"{len(self.detections)} detections")
        js = f"if(typeof updateMap==='function') updateMap({lat},{lon},'{classification}',{det_id},'{ACCENT}');"
        self.web_view.page().runJavaScript(js)
        # Feed risk panel
        self.risk_panel.load_from_detections(self.detections)

    def _save_results(self):
        if not self.output_folder or not self.detections:
            return
        csv_path = os.path.join(self.output_folder, "detections.csv")
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Latitude", "Longitude", "Classification"])
            for d in self.detections:
                w.writerow([d["id"], d["lat"], d["lon"], d["classification"]])
        self.log_message(f"Results saved: {csv_path}")

    def log_message(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {msg}")
        self.status_lbl.setText(msg[:80])

    def closeEvent(self, event):
        if self.video_processor and self.video_processor.isRunning():
            self.video_processor.stop()
            self.video_processor.wait(3000)
        if self.playback_cap:
            self.playback_cap.release()
        event.accept()
