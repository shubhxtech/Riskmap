"""
rapidscan package — public API.
Import RapidScanWindow from here or from the top-level shim.
"""

from ._constants import (
    BG_DEEP, BG_PANEL, BG_CARD, BORDER,
    ACCENT, ACCENT2, ACCENT3,
    TXT_HI, TXT_MID, TXT_LOW, FONT_MONO,
    DS_COLORS, MPL_STYLE, CLASS_NAMES,
    DEFAULT_GPS_ORIGIN,
    building_coords, js_escape, open_video, calculate_iou,
)
from ._video_processor import VideoProcessor
from ._risk_panel import MplCanvas, RiskCalcThread, RiskAssessmentPanel
from ._window import RapidScanWindow

__all__ = [
    "RapidScanWindow",
    "VideoProcessor",
    "RiskAssessmentPanel",
    "MplCanvas",
    "RiskCalcThread",
    "CLASS_NAMES",
    "DEFAULT_GPS_ORIGIN",
]
