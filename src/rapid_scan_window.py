"""
RapidScanWindow.py — thin shim for backward compatibility.
All logic now lives in the rapidscan/ package.

File structure:
  rapidscan/_constants.py      — palette, CLASS_NAMES, GPS helpers, open_video
  rapidscan/_video_processor.py — VideoProcessor QThread
  rapidscan/_risk_panel.py     — MplCanvas, RiskCalcThread, RiskAssessmentPanel
  rapidscan/_window.py         — RapidScanWindow (UI + playback + map)
  rapidscan/__init__.py        — public re-exports
"""

# WebEngine must be imported before QApplication — keep this import first.
from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401

from rapidscan import RapidScanWindow  # noqa: F401 — re-exported for main.py