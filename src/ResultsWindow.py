import os
import sys
import json
import tempfile
import base64
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QDialog, QScrollArea, QFrame,
    QSizePolicy, QCheckBox
)
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt, QUrl, pyqtSlot, QSize
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QObject
import qtawesome as qta

from config_ import Config
from AppLogger import Logger
from utils import resolve_path

# Category color palette (visually distinct, colorblind-friendly)
CATEGORY_COLORS = [
    '#1DA1F2',  # Blue
    '#E53935',  # Red
    '#43A047',  # Green
    '#FB8C00',  # Orange
    '#8E24AA',  # Purple
    '#00ACC1',  # Cyan
    '#D81B60',  # Pink
    '#6D4C41',  # Brown
    '#546E7A',  # Blue Grey
    '#FFB300',  # Amber
    '#00897B',  # Teal
    '#5C6BC0',  # Indigo
]


class ResultObject(QObject):
    """Bridge for JavaScript to Python communication"""
    def __init__(self, window):
        super().__init__()
        self.window = window

    @pyqtSlot(str)
    def marker_clicked(self, filename):
        self.window.show_image_details(filename)


class DetailsDialog(QDialog):
    def __init__(self, image_path, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Detection — {data.get('folder_class', 'Unknown')}")
        self.setMinimumSize(850, 650)

        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header with metadata chips
        header = QHBoxLayout()
        header.setSpacing(12)

        cat_label = QLabel(f"  {data.get('folder_class', 'N/A')}  ")
        cat_label.setStyleSheet("""
            background-color: #1DA1F2; color: white;
            border-radius: 12px; padding: 4px 14px;
            font-weight: 600; font-size: 13px;
        """)
        header.addWidget(cat_label)

        class_label = QLabel(f"  {data['class']}  ")
        class_label.setStyleSheet("""
            background-color: #f0f0f0; color: #333;
            border-radius: 12px; padding: 4px 14px;
            font-size: 13px;
        """)
        header.addWidget(class_label)

        score_val = float(data['score'])
        score_color = '#43A047' if score_val >= 0.7 else '#FB8C00' if score_val >= 0.4 else '#E53935'
        score_label = QLabel(f"  Score: {score_val:.2f}  ")
        score_label.setStyleSheet(f"""
            background-color: {score_color}; color: white;
            border-radius: 12px; padding: 4px 14px;
            font-weight: 600; font-size: 13px;
        """)
        header.addWidget(score_label)

        coord_label = QLabel(f"  📍 {data['lat']:.5f}, {data['lng']:.5f}  ")
        coord_label.setStyleSheet("""
            background-color: #f8f9fa; color: #555;
            border-radius: 12px; padding: 4px 14px;
            font-size: 12px;
        """)
        header.addWidget(coord_label)
        header.addStretch()
        layout.addLayout(header)

        # Image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #f5f5f5; border-radius: 8px; padding: 8px;")

        if os.path.exists(image_path):
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(1000, 550, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(pixmap)
            else:
                self.image_label.setText("Failed to load image.")
        else:
            self.image_label.setText("Image file not found.")

        layout.addWidget(self.image_label, 1)

        # Bottom bar
        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = QPushButton("  Close")
        close_btn.setIcon(qta.icon('fa5s.times', color='white'))
        close_btn.setMinimumHeight(38)
        close_btn.setMinimumWidth(120)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self.setLayout(layout)


class ResultsWindow(QWidget):
    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.config = config
        self.logger = logger
        self.folder_path = None
        self.items = []
        self.category_colors = {}
        self._temp_file = None

        self.init_ui()

        # Bridge setup
        self.channel = QWebChannel()
        self.bridge = ResultObject(self)
        self.channel.registerObject("backend", self.bridge)
        self.webview.page().setWebChannel(self.channel)

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top Toolbar ──
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 10, 16, 10)
        toolbar_layout.setSpacing(12)

        # Title
        title_icon = QLabel()
        title_icon.setPixmap(qta.icon('fa5s.map-marked-alt', color='#1DA1F2').pixmap(QSize(22, 22)))
        toolbar_layout.addWidget(title_icon)

        title = QLabel("Detection Results")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1e1e1e; background: transparent;")
        toolbar_layout.addWidget(title)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #e0e0e0;")
        toolbar_layout.addWidget(sep)

        # Path label
        self.label_path = QLabel("No folder selected")
        self.label_path.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label_path.setStyleSheet("color: #888; font-size: 12px; background: transparent;")
        toolbar_layout.addWidget(self.label_path, 1)

        # Stats label
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #1DA1F2; font-weight: 600; font-size: 13px; background: transparent;")
        toolbar_layout.addWidget(self.stats_label)

        # Buttons
        self.select_btn = QPushButton("  Browse Folder")
        self.select_btn.setIcon(qta.icon('fa5s.folder-open', color='white'))
        self.select_btn.setCursor(Qt.PointingHandCursor)
        self.select_btn.setMinimumHeight(34)
        self.select_btn.clicked.connect(self.choose_folder)
        toolbar_layout.addWidget(self.select_btn)

        self.refresh_btn = QPushButton("  Refresh")
        self.refresh_btn.setIcon(qta.icon('fa5s.sync-alt', color='white'))
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setMinimumHeight(34)
        self.refresh_btn.clicked.connect(self.process_folder)
        self.refresh_btn.setEnabled(False)
        toolbar_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(toolbar)

        # ── Category Filter Bar (hidden until data loaded) ──
        self.filter_bar = QFrame()
        self.filter_bar.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-bottom: 1px solid #e8e8e8;
            }
        """)
        self.filter_bar.setVisible(False)
        self.filter_layout = QHBoxLayout(self.filter_bar)
        self.filter_layout.setContentsMargins(16, 6, 16, 6)
        self.filter_layout.setSpacing(8)

        filter_label = QLabel("Categories:")
        filter_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #555; background: transparent;")
        self.filter_layout.addWidget(filter_label)
        self.filter_layout.addStretch()

        main_layout.addWidget(self.filter_bar)

        # ── Map View ──
        self.webview = QWebEngineView()
        self.webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.webview, 1)

        self.setLayout(main_layout)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Classified Results Folder")
        if folder:
            self.folder_path = Path(folder)
            self.label_path.setText(str(self.folder_path))
            self.refresh_btn.setEnabled(True)
            self.process_folder()

    def parse_filename(self, filename):
        """
        Parses: 0.57_Street View 360 58 31.06867951 77.17903748__(0, 0)-1.jpg
        Returns: {score, class, lat, lng, filename}
        """
        try:
            name = filename.rsplit('.', 1)[0]
            parts = name.split('__')[0]

            score_split = parts.split('_', 1)
            if len(score_split) < 2:
                return None

            score = float(score_split[0])
            rest = score_split[1]

            tokens = rest.rsplit(' ', 2)
            if len(tokens) < 3:
                return None

            lat = float(tokens[1])
            lng = float(tokens[2])
            class_name = tokens[0]

            return {
                'score': score,
                'class': class_name,
                'lat': lat,
                'lng': lng,
                'filename': filename
            }
        except Exception:
            return None

    def process_folder(self):
        if not self.folder_path or not self.folder_path.exists():
            return

        self.items = []
        valid_exts = {'.jpg', '.jpeg', '.png', '.bmp'}

        folder_counts = {}

        for file in self.folder_path.rglob('*'):
            if file.parent.name.lower() == 'uncertain':
                continue

            if file.suffix.lower() in valid_exts and file.is_file():
                data = self.parse_filename(file.name)
                if data:
                    data['path'] = str(file)
                    data['folder_class'] = file.parent.name
                    self.items.append(data)
                    folder_counts[file.parent.name] = folder_counts.get(file.parent.name, 0) + 1

        self.logger.log_status(f"Found {len(self.items)} total items.")
        for folder, count in folder_counts.items():
            self.logger.log_status(f"  - {folder}: {count} items")

        # Assign colors to categories
        categories = sorted(folder_counts.keys())
        self.category_colors = {}
        for i, cat in enumerate(categories):
            self.category_colors[cat] = CATEGORY_COLORS[i % len(CATEGORY_COLORS)]

        # Update stats
        self.stats_label.setText(f"{len(self.items)} detections · {len(categories)} categories")
        self.label_path.setText(str(self.folder_path))

        # Update filter bar
        self._build_filter_bar(folder_counts)

        # Generate & show map
        self.generate_map()

    def _build_filter_bar(self, folder_counts):
        """Build category filter chips"""
        # Clear existing widgets (except the label and stretch)
        while self.filter_layout.count() > 2:
            item = self.filter_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        # Re-add stretch at end
        for cat, count in sorted(folder_counts.items()):
            color = self.category_colors.get(cat, '#888')
            chip = QLabel(f"  ● {cat} ({count})  ")
            chip.setStyleSheet(f"""
                background-color: {color}22;
                color: {color};
                border: 1px solid {color}44;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            """)
            self.filter_layout.insertWidget(self.filter_layout.count() - 1, chip)

        self.filter_bar.setVisible(True)

    def generate_map(self):
        if not self.items:
            self.webview.setHtml("<h3 style='text-align:center; color:#888; padding:40px;'>No valid data found in folder or subfolders</h3>")
            return

        avg_lat = sum(i['lat'] for i in self.items) / len(self.items)
        avg_lng = sum(i['lng'] for i in self.items) / len(self.items)

        # Build GeoJSON features
        features = []
        for item in self.items:
            safe_name = item['filename'].replace("'", "\\'").replace('"', '\\"')
            folder_class = item.get('folder_class', 'Unknown')
            color = self.category_colors.get(folder_class, '#888')
            score = float(item['score'])

            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [item['lng'], item['lat']]
                },
                'properties': {
                    'filename': item['filename'],
                    'safe_name': safe_name,
                    'folder_class': folder_class,
                    'class_name': item['class'],
                    'score': score,
                    'color': color,
                    'path': item.get('path', '')
                }
            })

        geojson = json.dumps({
            'type': 'FeatureCollection',
            'features': features
        })

        # Category legend entries
        legend_items = ""
        for cat, color in sorted(self.category_colors.items()):
            count = sum(1 for i in self.items if i.get('folder_class') == cat)
            legend_items += f'<div class="legend-item"><span class="legend-dot" style="background:{color}"></span>{cat} <span class="legend-count">({count})</span></div>\n'

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Detection Results Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    html, body, #map {{ width:100%; height:100%; }}

    /* ── Custom Cluster Icons ── */
    .marker-cluster-small {{
        background-color: rgba(29,161,242,0.25) !important;
    }}
    .marker-cluster-small div {{
        background-color: rgba(29,161,242,0.7) !important;
        color: #fff !important;
        font-weight: 700;
    }}
    .marker-cluster-medium {{
        background-color: rgba(251,140,0,0.25) !important;
    }}
    .marker-cluster-medium div {{
        background-color: rgba(251,140,0,0.7) !important;
        color: #fff !important;
        font-weight: 700;
    }}
    .marker-cluster-large {{
        background-color: rgba(229,57,53,0.25) !important;
    }}
    .marker-cluster-large div {{
        background-color: rgba(229,57,53,0.7) !important;
        color: #fff !important;
        font-weight: 700;
    }}

    /* ── Custom Popup ── */
    .leaflet-popup-content-wrapper {{
        border-radius: 12px !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.18) !important;
        padding: 0 !important;
        overflow: hidden;
    }}
    .leaflet-popup-content {{
        margin: 0 !important;
        min-width: 240px;
    }}
    .leaflet-popup-tip {{
        box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
    }}
    .popup-card {{
        font-family: -apple-system, 'Helvetica Neue', 'Segoe UI', sans-serif;
    }}
    .popup-header {{
        padding: 12px 16px;
        color: #fff;
        font-weight: 700;
        font-size: 13px;
        letter-spacing: 0.3px;
    }}
    .popup-body {{
        padding: 12px 16px;
    }}
    .popup-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 4px 0;
        font-size: 12px;
        color: #555;
    }}
    .popup-row .label {{
        color: #999;
    }}
    .popup-row .value {{
        font-weight: 600;
        color: #333;
    }}
    .score-badge {{
        display: inline-block;
        padding: 2px 10px;
        border-radius: 10px;
        font-weight: 700;
        font-size: 12px;
        color: #fff;
    }}
    .popup-btn {{
        display: block;
        width: 100%;
        margin-top: 10px;
        padding: 8px 0;
        border: none;
        border-radius: 8px;
        background: #1DA1F2;
        color: #fff;
        font-weight: 600;
        font-size: 13px;
        cursor: pointer;
        transition: background 0.2s;
    }}
    .popup-btn:hover {{
        background: #1A91DA;
    }}

    /* ── Legend ── */
    .legend {{
        position: absolute;
        bottom: 24px;
        right: 12px;
        z-index: 1000;
        background: rgba(255,255,255,0.95);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.12);
        font-family: -apple-system, 'Helvetica Neue', 'Segoe UI', sans-serif;
        max-width: 220px;
    }}
    .legend-title {{
        font-weight: 700;
        font-size: 12px;
        color: #333;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    .legend-item {{
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 3px 0;
        font-size: 12px;
        color: #555;
    }}
    .legend-dot {{
        width: 10px;
        height: 10px;
        border-radius: 50%;
        flex-shrink: 0;
    }}
    .legend-count {{
        color: #aaa;
        font-size: 11px;
    }}

    /* ── Stats Overlay ── */
    .stats-overlay {{
        position: absolute;
        top: 12px;
        left: 12px;
        z-index: 1000;
        background: rgba(255,255,255,0.95);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 12px 18px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.12);
        font-family: -apple-system, 'Helvetica Neue', 'Segoe UI', sans-serif;
    }}
    .stats-number {{
        font-size: 22px;
        font-weight: 800;
        color: #1DA1F2;
        line-height: 1;
    }}
    .stats-label {{
        font-size: 11px;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* ── Custom Tooltip ── */
    .leaflet-tooltip {{
        border-radius: 8px !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.15) !important;
        font-size: 12px !important;
        padding: 6px 12px !important;
        border: none !important;
    }}
</style>
</head>
<body>
<div id="map"></div>

<!-- Stats Overlay -->
<div class="stats-overlay">
    <div class="stats-number">{len(self.items)}</div>
    <div class="stats-label">Detections Found</div>
</div>

<!-- Legend -->
<div class="legend">
    <div class="legend-title">Categories</div>
    {legend_items}
</div>

<script>
// ── Qt Bridge ──
var backend = null;
new QWebChannel(qt.webChannelTransport, function(channel) {{
    backend = channel.objects.backend;
}});

// ── Map Setup ──
var map = L.map('map', {{
    center: [{avg_lat}, {avg_lng}],
    zoom: 15,
    zoomControl: false
}});

// Zoom control bottom-left
L.control.zoom({{ position: 'bottomleft' }}).addTo(map);

// ── Tile Layer (CartoDB Positron — clean, light) ──
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}@2x.png', {{
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
}}).addTo(map);

// ── GeoJSON Data ──
var geojsonData = {geojson};

// ── Marker Cluster ──
var clusters = L.markerClusterGroup({{
    maxClusterRadius: 50,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
    zoomToBoundsOnClick: true,
    chunkedLoading: true
}});

// ── Add Markers ──
L.geoJSON(geojsonData, {{
    pointToLayer: function(feature, latlng) {{
        var props = feature.properties;
        var radius = 6 + (props.score * 6);  // Size by score

        return L.circleMarker(latlng, {{
            radius: radius,
            fillColor: props.color,
            color: '#fff',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.85
        }});
    }},
    onEachFeature: function(feature, layer) {{
        var p = feature.properties;
        var scoreColor = p.score >= 0.7 ? '#43A047' : (p.score >= 0.4 ? '#FB8C00' : '#E53935');

        var popupHtml = '<div class="popup-card">' +
            '<div class="popup-header" style="background:' + p.color + '">' +
                p.folder_class +
            '</div>' +
            '<div class="popup-body">' +
                '<div class="popup-row"><span class="label">Class</span><span class="value">' + p.class_name + '</span></div>' +
                '<div class="popup-row"><span class="label">Score</span><span class="score-badge" style="background:' + scoreColor + '">' + p.score.toFixed(2) + '</span></div>' +
                '<div class="popup-row"><span class="label">Location</span><span class="value">' +
                    feature.geometry.coordinates[1].toFixed(5) + ', ' +
                    feature.geometry.coordinates[0].toFixed(5) +
                '</span></div>' +
                '<button class="popup-btn" onclick="viewDetails(\\'' + p.safe_name.replace(/'/g, "\\\\'") + '\\')">View Full Image</button>' +
            '</div>' +
        '</div>';

        layer.bindPopup(popupHtml, {{ closeButton: true, minWidth: 240 }});

        // Tooltip on hover
        layer.bindTooltip(
            '<b>' + p.folder_class + '</b> — ' + p.score.toFixed(2),
            {{ direction: 'top', offset: [0, -8] }}
        );

        // Hover animation
        layer.on('mouseover', function(e) {{
            this.setStyle({{ weight: 3, fillOpacity: 1 }});
        }});
        layer.on('mouseout', function(e) {{
            this.setStyle({{ weight: 2, fillOpacity: 0.85 }});
        }});
    }}
}}).addTo(clusters);

map.addLayer(clusters);

// ── Fit bounds to data ──
if (geojsonData.features.length > 0) {{
    var group = L.featureGroup(clusters.getLayers());
    if (group.getLayers().length > 0) {{
        map.fitBounds(group.getBounds().pad(0.1));
    }}
}}

// ── View Details (calls Python backend) ──
function viewDetails(filename) {{
    if (backend) {{
        backend.marker_clicked(filename);
    }}
}}
</script>
</body>
</html>"""

        # Save to temp file and load via URL (fixes SSL/origin issues)
        try:
            if self._temp_file and os.path.exists(self._temp_file):
                os.unlink(self._temp_file)
        except Exception:
            pass

        temp_dir = os.path.join(tempfile.gettempdir(), 'riskmap_results')
        os.makedirs(temp_dir, exist_ok=True)
        self._temp_file = os.path.join(temp_dir, 'results_map.html')

        with open(self._temp_file, 'w', encoding='utf-8') as f:
            f.write(html)

        self.webview.setUrl(QUrl.fromLocalFile(self._temp_file))
        self.logger.log_status(f"Map saved to {self._temp_file}")

    def show_image_details(self, filename):
        item = next((i for i in self.items if i['filename'] == filename), None)
        if item:
            dlg = DetailsDialog(item['path'], item, self)
            dlg.exec_()
