"""
rapidscan/_constants.py
Shared constants: colour palette, CLASS_NAMES, GPS helpers, open_video().
"""

import cv2
import numpy as np

# ── Palette (RiskMap brand – light theme) ─────────────────────────────────────
BG_DEEP   = "#f0f2f5"
BG_PANEL  = "#ffffff"
BG_CARD   = "#f8f9fa"
BORDER    = "#e2e5ea"
ACCENT    = "#1DA1F2"
ACCENT_H  = "#1A91DA"
ACCENT2   = "#e53935"   # stop / danger
ACCENT3   = "#43A047"   # success / start
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

# Default GPS origin (Mandi, HP). Override via RapidScanWindow(gps_origin=…).
DEFAULT_GPS_ORIGIN = (31.7085, 76.9320)

# Approx metres per degree at ~32°N
_M_PER_DEG_LAT = 111_320.0
_M_PER_DEG_LON = 111_320.0 * 0.848   # cos(32°) ≈ 0.848


def building_coords(building_id: int, origin_lat: float, origin_lon: float,
                    grid_spacing_m: float = 10.0) -> tuple:
    """Map a sequential building ID to approximate GPS coords on a grid."""
    cols = 20
    row  = building_id // cols
    col  = building_id % cols
    dlat = (row * grid_spacing_m) / _M_PER_DEG_LAT
    dlon = (col * grid_spacing_m) / _M_PER_DEG_LON
    return (origin_lat + dlat, origin_lon + dlon)


def js_escape(s: str) -> str:
    """Escape a string for safe embedding inside a JS single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


def open_video(path: str) -> cv2.VideoCapture:
    """
    Try multiple OpenCV backends until one opens and reads successfully.
    Safely skips platform-specific backends that don't exist.
    """
    for name in ["CAP_ANY", "CAP_FFMPEG", "CAP_AVFOUNDATION", "CAP_GSTREAMER"]:
        bk = getattr(cv2, name, None)
        if bk is None:
            continue
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
    return cv2.VideoCapture(path)   # bare fallback


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
