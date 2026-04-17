"""
rapidscan/_window.py
RapidScanWindow — the main embeddable PyQt5 tab widget.

Distortion fix
──────────────
The bottom panel (tabs) sits inside a QScrollArea whose scrollbars are hidden.
The inner QWidget has a fixed minimum height so Qt never squishes its children.
When you drag the main splitter downward the viewport simply clips the panel
(it slides off-screen) rather than compressing it.
"""

import os
import csv
import tempfile
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from PyQt5.QtCore import Qt, QUrl, QTimer, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap, QColor
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPushButton,
    QLabel, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QFrame, QProgressBar, QSlider, QSpinBox,
    QTextEdit, QGroupBox, QTabWidget, QDoubleSpinBox,
    QScrollArea, QSizePolicy,
)

from ._constants import (
    BG_DEEP, BG_PANEL, BG_CARD, BORDER,
    ACCENT, ACCENT2, ACCENT3,
    TXT_HI, TXT_MID, TXT_LOW, FONT_MONO,
    CLASS_NAMES, DEFAULT_GPS_ORIGIN,
    js_escape, open_video,
)
from ._video_processor import VideoProcessor
from ._risk_panel import RiskAssessmentPanel


class RapidScanWindow(QWidget):
    """Embeddable PyQt5 widget — drop into RiskMap's tab bar."""

    def __init__(self, config=None, logger=None,
                 gps_origin=DEFAULT_GPS_ORIGIN):
        super().__init__()
        self.config     = config
        self.logger     = logger
        self.gps_origin = gps_origin

        self.video_path        = None
        self.output_folder     = None
        self.detections        = []
        self.video_processor   = None
        self.playback_cap      = None
        self._temp_map_file    = None
        self._playback_playing = True

        self.checkpoint_path = self._resolve_checkpoint()

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._next_playback_frame)

        self._build_ui()
        self._apply_stylesheet()
        self._write_map_html()

    # ── Checkpoint resolution ─────────────────────────────────────────────────
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
            Path(__file__).parent.parent.parent
            / "assets" / "models" / "classifier" / "best_model.pth"
        )
        return str(here) if here.exists() else ""

    # ── Global stylesheet ─────────────────────────────────────────────────────
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
        QPushButton:disabled {{ color: {TXT_LOW}; background: {BG_DEEP}; }}
        QPushButton#ActionButton {{
            color: #ffffff; font-weight: 700; font-size: 12px;
            border: none; border-radius: 6px; padding: 8px 16px;
        }}
        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 0 8px 8px 8px;
            background: {BG_PANEL};
        }}
        QTabBar::tab {{
            background: {BG_DEEP}; color: {TXT_MID};
            border: 1px solid {BORDER}; border-bottom: none;
            border-radius: 6px 6px 0 0;
            padding: 7px 16px; margin-right: 2px; font-weight: 500;
        }}
        QTabBar::tab:selected {{ background: {BG_PANEL}; color: {ACCENT}; font-weight: 700; }}
        QTabBar::tab:hover:!selected {{ background: {BG_CARD}; color: {TXT_HI}; }}
        QTableWidget {{
            background: {BG_PANEL}; alternate-background-color: {BG_CARD};
            gridline-color: {BORDER}; border: 1px solid {BORDER};
            border-radius: 6px; selection-background-color: {ACCENT};
            selection-color: #ffffff;
        }}
        QHeaderView::section {{
            background: {BG_DEEP}; color: {TXT_MID};
            border: none; border-bottom: 1px solid {BORDER};
            padding: 5px 8px; font-weight: 700;
            font-size: 10px; letter-spacing: 0.5px;
        }}
        QTextEdit, QLineEdit {{
            background: {BG_CARD}; color: {TXT_HI};
            border: 1px solid {BORDER}; border-radius: 6px;
            padding: 5px; font-family: {FONT_MONO}; font-size: 11px;
        }}
        QSpinBox, QDoubleSpinBox, QComboBox {{
            background: {BG_CARD}; color: {TXT_HI};
            border: 1px solid {BORDER}; border-radius: 5px;
            padding: 3px 6px;
        }}
        QComboBox::drop-down {{ border: none; }}
        QProgressBar {{
            border: 1px solid {BORDER}; border-radius: 5px;
            background: {BG_CARD}; text-align: center;
            color: {TXT_MID}; height: 14px;
        }}
        QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
        QSplitter::handle {{ background: {BORDER}; }}
        QSplitter::handle:horizontal {{ width: 5px; }}
        QSplitter::handle:vertical   {{ height: 5px; }}
        QSplitter::handle:hover      {{ background: {ACCENT}; }}
        QSlider::groove:horizontal {{
            height: 4px; background: {BORDER}; border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {ACCENT}; border: none;
            width: 14px; height: 14px;
            margin: -5px 0; border-radius: 7px;
        }}
        QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
        """)

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        # ── Main vertical splitter ────────────────────────────────────────────
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setOpaqueResize(True)
        self.main_splitter.setHandleWidth(6)

        # Map pane (top)
        map_widget = QWidget()
        map_widget.setMinimumHeight(150)
        ml = QVBoxLayout(map_widget)
        ml.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        try:
            s = self.web_view.settings()
            s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            s.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        except Exception:
            pass
        ml.addWidget(self.web_view)
        self.main_splitter.addWidget(map_widget)

        # Bottom pane — clipping QScrollArea (no scrollbars) so sliding the
        # splitter pushes the panel off-screen WITHOUT squishing its children.
        self._bottom_widget = QWidget()
        self._bottom_widget.setMinimumHeight(380)   # inner content never squishes
        # No maximumHeight set — allow natural growth

        bl = QVBoxLayout(self._bottom_widget)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        self.right_tabs = QTabWidget()
        self.right_tabs.tabBar().setExpanding(False)
        self.right_tabs.tabBar().setElideMode(Qt.ElideNone)
        self.right_tabs.addTab(self._build_detection_tab(), "🎥  Detection")

        self.risk_panel = RiskAssessmentPanel()
        risk_tab = QWidget()
        rt = QVBoxLayout(risk_tab)
        rt.setContentsMargins(0, 0, 0, 0)
        rt.addWidget(self.risk_panel)
        self.right_tabs.addTab(risk_tab, "⚠️  Risk Assessment")
        bl.addWidget(self.right_tabs, 1)

        # Wire map-update signal from risk panel → update Leaflet map
        self.risk_panel.map_update_requested.connect(
            self.update_map_marker_color
        )

        # ── Clipping QScrollArea ──────────────────────────────────────────────
        self._clip = QScrollArea()
        self._clip.setWidget(self._bottom_widget)
        self._clip.setWidgetResizable(False)           # keep inner widget at its own size to avoid squishing
        self._clip.setFrameShape(QFrame.NoFrame)
        self._clip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._clip.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._clip.setMinimumHeight(0)               # splitter can crush viewport to 0

        self.main_splitter.addWidget(self._clip)
        self.main_splitter.setSizes([400, 500])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)

        root.addWidget(self.main_splitter, 1)

    def resizeEvent(self, event):
        """Keep the inner panel exactly as wide as the splitter (no right gap),
        but never taller than its minimumHeight — that is what makes it clip
        (slide off-screen) rather than squish when the splitter is dragged down."""
        super().resizeEvent(event)
        if hasattr(self, "_bottom_widget") and hasattr(self, "main_splitter"):
            self._bottom_widget.setFixedWidth(self.main_splitter.width())

    def _build_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setStyleSheet(
            f"QFrame {{ background:{BG_PANEL}; border-bottom:2px solid {ACCENT}; }}"
        )
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(18, 10, 18, 10)
        tb.setSpacing(14)

        # Push the GPS label to the right
        tb.addStretch()

        self.gps_lbl = QLabel(
            f"📍 Origin: {self.gps_origin[0]:.4f}, {self.gps_origin[1]:.4f}"
        )
        self.gps_lbl.setStyleSheet(
            f"font-size:10px; color:{TXT_LOW}; background:transparent; "
            f"font-family:{FONT_MONO};"
        )
        tb.addWidget(self.gps_lbl)
        return toolbar

    def _build_detection_tab(self) -> QWidget:
        det_tab = QWidget()
        det_layout = QVBoxLayout(det_tab)
        det_layout.setContentsMargins(10, 10, 10, 10)
        det_layout.setSpacing(8)

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setOpaqueResize(True)
        content_splitter.setHandleWidth(6)

        # ── Left controls ─────────────────────────────────────────────────────
        ctrl_panel = QWidget()
        ctrl_panel.setFixedWidth(260)
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_layout.setSpacing(8)
        ctrl_layout.setContentsMargins(0, 0, 4, 0)

        # File settings
        file_grp = QGroupBox("FILE SETTINGS")
        fg = QVBoxLayout(file_grp); fg.setSpacing(6)
        self.btn_load_video = QPushButton("📁  Load Video")
        self.btn_load_video.setCursor(Qt.PointingHandCursor)
        self.btn_load_video.clicked.connect(self.load_video)
        self.btn_select_folder = QPushButton("📂  Output Folder")
        self.btn_select_folder.setCursor(Qt.PointingHandCursor)
        self.btn_select_folder.clicked.connect(self.select_output_folder)
        self.vid_info = QLabel("No video loaded")
        self.vid_info.setStyleSheet(
            f"color:{TXT_LOW}; font-size:10px; font-family:{FONT_MONO}; padding:2px 0;"
        )
        self.vid_info.setWordWrap(True)
        fg.addWidget(self.btn_load_video)
        fg.addWidget(self.btn_select_folder)
        fg.addWidget(self.vid_info)
        ctrl_layout.addWidget(file_grp)

        # Detection settings
        det_grp = QGroupBox("DETECTION SETTINGS")
        dg = QVBoxLayout(det_grp); dg.setSpacing(6)

        fps_row = QHBoxLayout()
        fps_lbl = QLabel("Detection FPS:")
        fps_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120); self.fps_spin.setValue(30)
        self.fps_spin.setSuffix(" fps")
        fps_row.addWidget(fps_lbl); fps_row.addWidget(self.fps_spin)
        dg.addLayout(fps_row)

        self.native_fps_lbl = QLabel("Native FPS: —")
        self.native_fps_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:10px; font-family:{FONT_MONO};"
        )
        dg.addWidget(self.native_fps_lbl)

        gps_grp_lbl = QLabel("Scene GPS Origin:")
        gps_grp_lbl.setStyleSheet(
            f"color:{TXT_MID}; font-size:11px; margin-top:4px;"
        )
        dg.addWidget(gps_grp_lbl)

        gps_row = QHBoxLayout()
        self.origin_lat_spin = QDoubleSpinBox()
        self.origin_lat_spin.setRange(-90, 90)
        self.origin_lat_spin.setValue(self.gps_origin[0])
        self.origin_lat_spin.setDecimals(4); self.origin_lat_spin.setPrefix("Lat: ")
        self.origin_lon_spin = QDoubleSpinBox()
        self.origin_lon_spin.setRange(-180, 180)
        self.origin_lon_spin.setValue(self.gps_origin[1])
        self.origin_lon_spin.setDecimals(4); self.origin_lon_spin.setPrefix("Lon: ")
        self.origin_lat_spin.valueChanged.connect(self._on_origin_changed)
        self.origin_lon_spin.valueChanged.connect(self._on_origin_changed)
        gps_row.addWidget(self.origin_lat_spin); gps_row.addWidget(self.origin_lon_spin)
        dg.addLayout(gps_row)

        chkpt_lbl = QLabel("Classifier Checkpoint:")
        chkpt_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px; margin-top:4px;")
        self.chkpt_edit = QLineEdit(self.checkpoint_path)
        self.chkpt_edit.setPlaceholderText("Path to .pth file…")
        self.btn_browse_chkpt = QPushButton("Browse…")
        self.btn_browse_chkpt.setFixedWidth(76)
        self.btn_browse_chkpt.setCursor(Qt.PointingHandCursor)
        self.btn_browse_chkpt.clicked.connect(self._browse_checkpoint)
        chkpt_row = QHBoxLayout()
        chkpt_row.addWidget(self.chkpt_edit); chkpt_row.addWidget(self.btn_browse_chkpt)
        dg.addWidget(chkpt_lbl); dg.addLayout(chkpt_row)
        ctrl_layout.addWidget(det_grp)

        # Start / Stop
        action_grp = QGroupBox("CONTROLS")
        ag = QVBoxLayout(action_grp); ag.setSpacing(6)
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
        ag.addWidget(self.btn_process); ag.addWidget(self.btn_stop)
        ctrl_layout.addWidget(action_grp)

        # Progress
        prog_grp = QGroupBox("PROGRESS")
        pg = QVBoxLayout(prog_grp)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%  (%v / %m frames)")
        pg.addWidget(self.progress_bar)
        ctrl_layout.addWidget(prog_grp)
        ctrl_layout.addStretch()
        content_splitter.addWidget(ctrl_panel)

        # ── Right: video + log ────────────────────────────────────────────────
        video_outer = QWidget()
        vo = QVBoxLayout(video_outer)
        vo.setContentsMargins(0, 0, 0, 0); vo.setSpacing(6)

        vid_grp = QGroupBox("🎥  VIDEO FEED")
        vg = QVBoxLayout(vid_grp); vg.setSpacing(6)
        self.video_label = QLabel("Load a video file to begin")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet(
            f"background:{BG_DEEP}; border-radius:8px; color:{TXT_MID}; "
            f"font-size:13px; font-style:italic;"
        )
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setMinimumHeight(120)
        vg.addWidget(self.video_label)

        # Playback bar
        self.playback_controls = QWidget()
        pc = QHBoxLayout(self.playback_controls)
        pc.setContentsMargins(0, 2, 0, 0); pc.setSpacing(8)
        self.btn_play_pause = QPushButton("⏸")
        self.btn_play_pause.setFixedSize(36, 30)
        self.btn_play_pause.setToolTip("Play / Pause")
        self.btn_play_pause.setCursor(Qt.PointingHandCursor)
        self.btn_play_pause.clicked.connect(self.toggle_playback)
        self.frame_lbl = QLabel("0 / 0")
        self.frame_lbl.setStyleSheet(
            f"color:{TXT_LOW}; font-size:10px; font-family:{FONT_MONO}; min-width:80px;"
        )
        self.frame_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.video_slider = QSlider(Qt.Horizontal)
        self.video_slider.setTracking(False)
        self.video_slider.sliderMoved.connect(self.seek_video)
        self.video_slider.valueChanged.connect(self._on_slider_value_changed)
        pc.addWidget(self.btn_play_pause)
        pc.addWidget(self.video_slider, 1)
        pc.addWidget(self.frame_lbl)
        vg.addWidget(self.playback_controls)
        self.playback_controls.setVisible(False)
        vo.addWidget(vid_grp, 3)

        # Detection + Processing log
        log_splitter = QSplitter(Qt.Horizontal)
        log_splitter.setChildrenCollapsible(False)
        log_splitter.setHandleWidth(5)

        tbl_grp = QGroupBox("📊  DETECTION LOG")
        tg = QVBoxLayout(tbl_grp); tg.setSpacing(4)
        self.det_table = QTableWidget(0, 4)
        self.det_table.setHorizontalHeaderLabels(
            ["ID", "Latitude", "Longitude", "Classification"]
        )
        # All 4 columns stretch equally so resizing the splitter is even
        hdr = self.det_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
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
        content_splitter.setStretchFactor(0, 0)  # left panel: fixed width
        content_splitter.setStretchFactor(1, 1)  # right: fills remaining space
        det_layout.addWidget(content_splitter)
        return det_tab

    # ── Leaflet map HTML ──────────────────────────────────────────────────────
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
  background:rgba(255,255,255,0.95); backdrop-filter:blur(6px);
  border:1.5px solid {ACCENT}; border-radius:8px;
  padding:8px 14px; font-family:monospace; font-size:12px; color:{TXT_HI};
  box-shadow:0 2px 12px rgba(0,0,0,0.1);
}}
.overlay-badge .cnt {{ color:{ACCENT}; font-weight:700; font-size:15px; }}
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

var clsColors = {{
  'RCC':'#1DA1F2','MR':'#f97316','AD':'#a855f7',
  'Metal':'#64748b','Timber':'#84cc16','Non':'#ef4444'
}};
function clsColor(cls) {{
  var keys = Object.keys(clsColors);
  for(var i=0;i<keys.length;i++) {{
    if(cls.indexOf(keys[i])===0) return clsColors[keys[i]];
  }}
  return '{ACCENT}';
}}

function updateMap(lat,lon,cls,id,color) {{
  color = color || clsColor(cls);
  var iconHtml = '<div style="background:'+color+';width:13px;height:13px;'
    +'border-radius:50%;box-shadow:0 0 8px '+color+'55;border:2px solid #fff;"></div>';
  var icon = L.divIcon({{className:'',html:iconHtml,iconSize:[13,13],iconAnchor:[6,6]}});
  var popup='<div style="font-family:monospace;font-size:12px;padding:10px 14px;min-width:160px;">'
    +'<b style="color:'+color+'">🏢 Building #'+id+'</b><br>'
    +'<span style="color:#666">📍 '+lat.toFixed(6)+', '+lon.toFixed(6)+'</span><br>'
    +'<span style="color:'+color+'">🏷 '+cls+'</span></div>';
  if(markers[id]) {{
    markers[id].setIcon(icon);
    markers[id].setPopupContent(popup);
  }} else {{
    cnt++;
    document.getElementById('cnt').textContent = cnt;
    var m = L.marker([lat,lon],{{icon:icon}}).addTo(map).bindPopup(popup);
    markers[id] = m;
    if(cnt===1) map.flyTo([lat,lon],16,{{duration:1.2}});
  }}
}}

function clearMarkers() {{
  Object.values(markers).forEach(function(m){{ map.removeLayer(m); }});
  markers={{}};cnt=0;
  document.getElementById('cnt').textContent=0;
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
            self.web_view.setUrl(
                QUrl.fromLocalFile(self._temp_map_file)
            )
        except Exception as e:
            self.log_message(f"Map init error: {e}")

    # ── Origin change ─────────────────────────────────────────────────────────
    def _on_origin_changed(self):
        self.gps_origin = (
            self.origin_lat_spin.value(),
            self.origin_lon_spin.value(),
        )
        self.gps_lbl.setText(
            f"📍 Origin: {self.gps_origin[0]:.4f}, {self.gps_origin[1]:.4f}"
        )

    def update_map_marker_color(
        self, marker_id: int, color: str, classification: str,
        lat: float, lon: float
    ):
        """Update or add a Leaflet marker — called from risk panel after
        CSV load (colour=#00d4aa) and after risk results (DS colours)."""
        safe_cls = js_escape(classification)
        self.web_view.page().runJavaScript(
            f"if(typeof updateMap==='function') "
            f"updateMap({lat},{lon},'{safe_cls}',{marker_id},'{color}');"
        )

    # ── Video I/O ─────────────────────────────────────────────────────────────
    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v);;All Files (*)",
        )
        if not path:
            return
        self.video_path = path
        fname = os.path.basename(path)
        cap   = open_video(path)
        if cap.isOpened():
            fps   = cap.get(cv2.CAP_PROP_FPS) or 0.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            ret, frame = cap.read()
            cap.release()
            if fps > 0:
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
                "AVI/MKV files need OpenCV with FFMPEG. Try converting to MP4."
            )
        self.btn_process.setEnabled(True)

    def _browse_checkpoint(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Checkpoint", "",
            "PyTorch Weights (*.pth *.pt);;All Files (*)"
        )
        if path:
            self.chkpt_edit.setText(path)

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder = folder
            self.log_message(f"Output folder: {folder}")
            parts = Path(folder).parts
            short = os.sep.join(parts[-2:]) if len(parts) >= 2 else folder
            self.vid_info.setText(self.vid_info.text() + f"\n📁 …/{short}")

    # ── Processing ────────────────────────────────────────────────────────────
    def start_processing(self):
        if not self.video_path:
            self.log_message("Error: load a video first."); return
        if not self.output_folder:
            self.log_message("Error: select an output folder first."); return

        self.btn_process.setEnabled(False)
        self.btn_load_video.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.det_table.setRowCount(0)
        self.detections = []
        self.progress_bar.setValue(0)

        self.web_view.page().runJavaScript(
            "if(typeof clearMarkers==='function') clearMarkers();"
        )
        for sub in ("crops", "duplicates", "originals"):
            os.makedirs(os.path.join(self.output_folder, sub), exist_ok=True)

        chkpt  = self.chkpt_edit.text().strip() or self.checkpoint_path
        origin = (self.origin_lat_spin.value(), self.origin_lon_spin.value())

        self.video_processor = VideoProcessor(
            self.video_path, chkpt, CLASS_NAMES,
            detection_fps=self.fps_spin.value(),
            gps_origin=origin,
        )
        self.video_processor.output_folder = self.output_folder
        self.video_processor.crops_dir     = os.path.join(self.output_folder, "crops")
        self.video_processor.dup_dir       = os.path.join(self.output_folder, "duplicates")
        self.video_processor.orig_dir      = os.path.join(self.output_folder, "originals")

        self.video_label.setText("⚙️  Processing…  detection + classification running")
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
        if annotated and os.path.exists(annotated) and os.path.getsize(annotated) > 1024:
            self.log_message(
                f"Starting annotated playback: {os.path.basename(annotated)} "
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

    # ── Playback ──────────────────────────────────────────────────────────────
    def _start_playback(self, path: str) -> bool:
        if self.playback_cap:
            self.playback_cap.release()
        self.playback_cap = open_video(path)
        if not self.playback_cap.isOpened():
            sz = os.path.getsize(path) if os.path.exists(path) else 0
            self.log_message(
                f"Playback failed: {os.path.basename(path)} "
                f"(size={sz} B, {'exists' if os.path.exists(path) else 'MISSING'})"
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
        self.playback_timer.start(max(16, int(1000 / fps)))
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
        if not self.video_slider.isSliderDown():
            self.seek_video(position)

    def seek_video(self, position: int):
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

    # ── Frames / detections ───────────────────────────────────────────────────
    @pyqtSlot(np.ndarray)
    def _on_frame(self, frame: np.ndarray):
        self._display_frame(frame)

    def _display_frame(self, frame: np.ndarray):
        try:
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w  = rgb.shape[:2]
            q_img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
            lw    = self.video_label.width()
            lh    = self.video_label.height()
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
        row = self.det_table.rowCount()
        self.det_table.insertRow(row)
        for col, val in enumerate([
            str(det_id + 1), f"{lat:.6f}", f"{lon:.6f}", classification
        ]):
            item = QTableWidgetItem(val)
            if col == 3:
                item.setForeground(QColor(TXT_HI))
            self.det_table.setItem(row, col, item)
        self.det_table.scrollToBottom()

        self.detections.append({
            "id": det_id + 1, "lat": lat,
            "lon": lon, "classification": classification,
        })
        n = len(self.detections)
        self.det_count_lbl.setText(f"{n} detection{'s' if n != 1 else ''}")

        safe_cls = js_escape(classification)
        self.web_view.page().runJavaScript(
            f"if(typeof updateMap==='function') "
            f"updateMap({lat},{lon},'{safe_cls}',{det_id + 1},'#00d4aa');"
        )
        self.risk_panel.load_from_detections(self.detections)

    def _save_results(self):
        if not self.output_folder or not self.detections:
            return
        csv_path = os.path.join(self.output_folder, "detections.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Latitude", "Longitude", "Classification"])
            for d in self.detections:
                writer.writerow([d["id"], d["lat"], d["lon"], d["classification"]])
        self.log_message(f"Results saved: {csv_path}")

    def log_message(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(
            f"<span style='color:{TXT_LOW}'>[{ts}]</span> {msg}"
        )
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, event):
        if self.video_processor and self.video_processor.isRunning():
            self.video_processor.stop()
            self.video_processor.wait(3000)
        if self.playback_cap:
            self.playback_cap.release()
        self.playback_timer.stop()
        event.accept()
