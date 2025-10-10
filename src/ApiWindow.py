#Check

from tenacity import retry, wait_exponential, stop_after_attempt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QProgressBar, QLabel, QSpinBox, QInputDialog, QComboBox, QMessageBox)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QColor
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QThread, QTimer, Qt
from AppLogger import Logger
import json
from config_ import Config
import requests
import os, json
import sqlite3
from Tile_Downloader import download_panorama
from dotenv import load_dotenv
from utils import resolve_path
from pathlib import Path
from Metadata_scanner_grid_search import StreetViewDensityScanner

class CoordinateReceiver(QObject):
    # Emitted when JavaScript sends coordinates: list of [lat, lng] or list of lists
    coordinatesReceived = pyqtSignal(object)

    @pyqtSlot('QVariant')
    def receiveCoordinates(self, coords):
        # coords is expected as a JS array of lat/lng pairs
        self.coordinatesReceived.emit(coords)

class StreetViewDownloader(QThread):
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal()

    def __init__(self, output_dir, max_images, logger: Logger, config: Config, FOUND_COORDS: list[tuple[float,float]]):
        super().__init__()
        self.coords = FOUND_COORDS
        self.api_key = os.getenv("API_KEY") #api_key
        self.config = config
        self.region = self.config.get_general_data()["region"]
        self.output_dir = output_dir
        self.max_images = max_images
        self.logger = logger

    def run(self):
        try:
            total = len(self.coords)
            count = 0
            for i, (lat, lng, pan_id) in enumerate(self.coords, 1):
                if self.max_images and count >= self.max_images:
                    self.logger.log_status(f"Reached max_images limit: {self.max_images}")
                    break
                try:
                    self.logger.log_status(f"Requesting Street View for ({lat}, {lng})")
                    download_panorama(pano_id=pan_id, save_dir=self.output_dir, coords=(lat, lng))
                    count += 1
                    self.logger.log_status(f"Saved image {self.region}_{lat}_{lng}")
                except Exception as e:
                    self.logger.log_exception(f"Failed to download at ({lat},{lng}): {e}")
                self.progress.emit(i, total)
            self.logger.log_status("Street View download finished")
        except Exception as e:
            self.logger.log_exception(f"Downloader thread failed: {e}")
        finally:
            self.finished.emit()

class ApiWindow(QWidget):   
    def __init__(self, logger: Logger, config: Config):
        super().__init__()
        self.logger = logger
        self.config = config
        self.secrets_path = Path(resolve_path(config.get_paths_data()["secrets_path"]))
        print("Reached before set api key")
        QTimer.singleShot(0, lambda: self.set_api_key(self.secrets_path))
        self.DB_PATH = self.config.get_database_path()
        self.FOUND_COORDS = []
        self.region = self.config.get_general_data()["region"]
        self.output_dir = self.config.get_dwnd_file_path()
        os.makedirs(self.output_dir, exist_ok=True)
        self.setup_ui()

    def set_api_key(self, path:Path):
        print("In set api key")
        if not path.exists():
            # Create the dialog manually
            dialog = QInputDialog(self)
            dialog.setWindowTitle("Enter API Key")
            dialog.setLabelText("Paste your API key:")
            dialog.resize(400, 100)

            # Find the top-level QMainWindow
            main_window = self.window()  # This resolves to the top-level QMainWindow

            # Center the dialog on the main window
            if main_window:
                parent_geometry = main_window.frameGeometry()
                dialog_geometry = dialog.frameGeometry()
                dialog.move(
                    parent_geometry.center() - dialog_geometry.center()
                )

            if dialog.exec_() == QInputDialog.Accepted:
                api_key = dialog.textValue().strip()
                if api_key:
                    with open(path, "w") as f:
                        f.write(f"API_KEY={api_key}\n")
                    print("Wrote API key to", path)

        load_dotenv(dotenv_path=Path(resolve_path(self.config.get_paths_data()["secrets_path"])))
        self.setup_map()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()

        self.city_dropdown = QComboBox()
        self.city_dropdown.setEditable(True)
        self.city_dropdown.setInsertPolicy(QComboBox.NoInsert)
        self.city_dropdown.setPlaceholderText("Select a city")
        self.city_dropdown.setMinimumWidth(200)
        top_layout.addWidget(QLabel("City:"))
        top_layout.addWidget(self.city_dropdown)

        self.rect_btn = QPushButton("Rectangle Select")
        self.clear_btn = QPushButton("Clear Selection")
        top_layout.addWidget(self.rect_btn)
        top_layout.addWidget(self.clear_btn)

        self.populate_city_dropdown()
        self.city_dropdown.currentIndexChanged.connect(self.on_city_selected)

        self.spin_label = QLabel("Max Images:")
        self.spin = QSpinBox()
        self.spin.setRange(0, 10000)
        self.spin.setValue(1)
        top_layout.addWidget(self.spin_label)
        top_layout.addWidget(self.spin)

        self.folder_btn = QPushButton("Select Output Folder")
        self.folder_label = QLabel(f"{self.output_dir}")
        top_layout.addWidget(self.folder_btn)
        top_layout.addWidget(self.folder_label)

        self.download_btn = QPushButton("Download Images")
        top_layout.addWidget(self.download_btn)

        self.layout.addLayout(top_layout)

        # Web view for map
        self.view = QWebEngineView(self)
        self.layout.addWidget(self.view)

        # Progress bar
        self.progress = QProgressBar(self)
        self.layout.addWidget(self.progress)


        # Connect signals
        self.rect_btn.clicked.connect(lambda: self.run_js('enableRectangle()'))
        # self.circle_btn.clicked.connect(lambda: self.run_js('enableCircle()'))
        # self.poly_btn.clicked.connect(lambda: self.run_js('enablePolygon()'))
        self.clear_btn.clicked.connect(lambda: self.run_js('clearSelection()'))
        self.folder_btn.clicked.connect(self.choose_folder)
        self.download_btn.clicked.connect(self.start_download)

    def populate_city_dropdown(self):
        self.city_dropdown.clear()
        self.city_color_map = {}

        with open(self.config.get_map_index_path(), 'r') as f:
            self.city_map_data = json.load(f)

        os.makedirs(resolve_path("Metadata_Maps"), exist_ok=True)
        available_maps = {
            f.split("_")[0].lower()
            for f in os.listdir(resolve_path("Metadata_Maps"))
            if f.endswith(".html")
        }

        with open(resolve_path("cities.txt"), "r", encoding="utf-8") as f:
            city_list = [line.strip() for line in f if line.strip()]

        for city in sorted(city_list):
            is_available = city.lower() in available_maps
            self.city_dropdown.addItem(city)
            index = self.city_dropdown.findText(city)
            color = QColor('green') if is_available else QColor('red')
            self.city_dropdown.setItemData(index, color, Qt.TextColorRole)
            self.city_color_map[city] = is_available

        default_region = self.region.lower()
        default_index = self.city_dropdown.findText(default_region, Qt.MatchFixedString)
        if default_index != -1:
            self.city_dropdown.setCurrentIndex(default_index)

    def on_city_selected(self):
        city = self.city_dropdown.currentText().strip().title()
        if not city:
            return

        print(self.city_color_map.get(city), ": ", city)

        if not self.city_color_map.get(city, False):
            reply = QMessageBox.question(
                self,
                "City metadata missing",
                f"Metadata not found for {city.title()}. Generate now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Try fetching bounds
                bounds = self.city_map_data.get(city)
                if not bounds:
                    self.logger.log_status(f"Fetching bounds for {city} via Nominatim...")
                    bounds = self.fetch_city_bounds(city)
                    if not bounds:
                        QMessageBox.critical(self, "Error", f"Could not fetch bounds for {city.title()}.")
                        return
                    self.update_map_index(city, bounds)
                    self.populate_city_dropdown()  # Refresh dropdown color
                    self.city_dropdown.setCurrentText(city)

                # Launch scanner
                scanner = StreetViewDensityScanner(city=city)
                scanner.api_key_input.setText(os.getenv("API_KEY", ""))
                scanner.edge_inputs["North (max lat)"].setText(str(bounds["north"]))
                scanner.edge_inputs["South (min lat)"].setText(str(bounds["south"]))
                scanner.edge_inputs["East (max lon)"].setText(str(bounds["east"]))
                scanner.edge_inputs["West (min lon)"].setText(str(bounds["west"]))
                db_path = os.path.join("Metadata_Maps", f"{city}.db")
                scanner.dbfile_input.setText(db_path)
                scanner.workers_input.setText("10")
                scanner.show()
                scanner.start_btn.click()
        self.region = city
        self.setup_map()

    def fetch_city_bounds(self, city: str):
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": f"{city}, India",
                "format": "json",
                "limit": 1,
                "addressdetails": 0,
                "polygon": 0,
            }
            headers = {
                "User-Agent": "ML Assist (21bce010@nith.ac.in)" 
            }
            @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
            def safe_get(url, **kwargs):
                kwargs.setdefault("timeout",10)
                return requests.get(url, **kwargs)
            response = safe_get(url, params=params, headers=headers)
            data = response.json()
            if not data:
                raise ValueError(f"No results found for {city}")

            bbox = data[0]["boundingbox"]  # [south, north, west, east]
            bounds = {
                "south": float(bbox[0]),
                "north": float(bbox[1]),
                "west": float(bbox[2]),
                "east": float(bbox[3]),
            }
            return bounds
        except Exception as e:
            self.logger.log_exception(f"Failed to fetch bounds for {city}: {e}")
            return None

    def update_map_index(self, city: str, bounds: dict):
        try:
            map_path = self.config.get_map_index_path()
            if os.path.exists(map_path):
                with open(map_path, 'r') as f:
                    city_map_data = json.load(f)
            else:
                city_map_data = {}

            city_map_data[city.lower()] = bounds
            with open(map_path, 'w') as f:
                json.dump(city_map_data, f, indent=2)

            self.logger.log_status(f"Updated map_index.json with {city}: {bounds}")
        except Exception as e:
            self.logger.log_exception(f"Failed to update map index: {e}")

    def query_results(self, db_path, north, south, east, west):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        query = """
            SELECT c.lat, c.lon, r.pano_id
            FROM coords c
            JOIN results r ON c.id = r.coord_id
            WHERE c.lat <= ? AND c.lat >= ? AND c.lon <= ? AND c.lon >= ?
        """
        cur.execute(query, (north, south, east, west))
        results = cur.fetchall()
        conn.close()
        self.logger.log_status(results)
        return results

    def setup_map(self):
        # Setup WebChannel communication
        self.api_key = os.getenv("API_KEY") #api_key
        self.channel = QWebChannel()
        self.coord_receiver = CoordinateReceiver()
        self.coord_receiver.coordinatesReceived.connect(self.on_coordinates)
        self.channel.registerObject('coordReceiver', self.coord_receiver)
        self.view.page().setWebChannel(self.channel)

        self.map_bounds = []
        with open(self.config.get_map_index_path(), 'r') as f:
            index = json.load(f)
            self.map_bounds = index[self.region.lower()]

        #old = {"lat": 23.73, "lng": 92.72}

        self.map_centre = {
            'lat': (self.map_bounds['north']+self.map_bounds['south'])/2+0.03,
            'lng': (self.map_bounds['east']+self.map_bounds['west'])/2,
        }
        
        print(f"Centre of map of {self.region}: {self.map_centre}")
        self.logger.log_status(f"Centre of map of {self.region}: {self.map_centre}")
        # Load Google Maps HTML with JS selection tools
        html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="initial-scale=1.0, user-scalable=yes" />
  <style>html, body, #map {{ height: 100%; margin: 0; padding: 0 }}</style>
  <script loading="async" src="https://maps.googleapis.com/maps/api/js?key={self.api_key}&libraries=drawing"></script>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <script>
    let map, drawingManager, shapes=[];
    function initMap() {{
        const aizawlBounds = {self.map_bounds};

        map = new google.maps.Map(document.getElementById('map'), {{
            center: {self.map_centre}, // near Aizawl center
            zoom: 11,
            minZoom: 9,
            maxZoom: 16
        }});

        drawingManager = new google.maps.drawing.DrawingManager({{
            drawingMode: null,
            drawingControl: false,
            drawingControlOptions: {{
                drawingModes: ['rectangle', 'circle', 'polygon']
            }}
        }});

        drawingManager.setMap(map);

        google.maps.event.addListener(drawingManager, 'overlaycomplete', function(e) {{
            shapes.push(e.overlay);
            let coords = [];
            if (e.type === 'circle') {{
            let center = e.overlay.getCenter(); coords.push([center.lat(), center.lng()]);
            }} else if (e.type === 'rectangle') {{
            let bounds = e.overlay.getBounds();
            let ne = bounds.getNorthEast(), sw = bounds.getSouthWest();
            coords = [[ne.lat(), ne.lng()], [sw.lat(), sw.lng()]];
            }} else if (e.type === 'polygon') {{
            e.overlay.getPath().forEach(pt => coords.push([pt.lat(), pt.lng()]));
            }}
            // send coords to Python
            new QWebChannel(qt.webChannelTransport, channel => {{
            channel.objects.coordReceiver.receiveCoordinates(coords);
        }});
      }});
    }}
    function enableRectangle() {{ drawingManager.setDrawingMode(google.maps.drawing.OverlayType.RECTANGLE); }}
    function enableCircle() {{ drawingManager.setDrawingMode(google.maps.drawing.OverlayType.CIRCLE); }}
    function enablePolygon() {{ drawingManager.setDrawingMode(google.maps.drawing.OverlayType.POLYGON); }}
    function clearSelection() {{ shapes.forEach(s=>s.setMap(null)); shapes=[]; }}
  </script>
</head>
<body onload="initMap()">
  <div id="map"></div>
</body>
</html>"""
        self.view.setHtml(html)
        self.logger.log_status("Map initialized")

    def run_js(self, script):
        try:
            self.view.page().runJavaScript(script)
            self.logger.log_status(f"Executed JS: {script}")
        except Exception as e:
            self.logger.log_exception(f"JS execution failed: {e}")

    def choose_folder(self):
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
            if folder:
                self.output_dir = folder
                self.folder_label.setText(folder)
                self.logger.log_status(f"Output folder set to {folder}")
        except Exception as e:
            self.logger.log_exception(f"Folder selection failed: {e}")

    def on_coordinates(self, coords):
        # coords received from JS drawing
        self.logger.log_status(f"Coordinates received: {coords}")
        self.logger.log_status("Received coords:", coords)
        north = float(coords[0][0])
        south = float(coords[1][0])
        east = float(coords[0][1])
        west = float(coords[1][1])
        data = self.query_results(self.DB_PATH, north, south, east, west)
        for i in data:
            self.FOUND_COORDS.append(i)
        self.logger.log_status(f"found {len(data)} results in {coords}")
        print(f'found {len(self.FOUND_COORDS)} results in selected')
        self.current_shape_coords = coords

    def start_download(self):
        try:
            coords = self.current_shape_coords
            if not coords:
                self.logger.log_status("No shape selected")
                return
            max_images = self.spin.value() or None
            out = self.output_dir
            if not out:
                self.logger.log_status("No output folder selected")
                return
            self.downloader = StreetViewDownloader(
                out, max_images, self.logger, self.config, self.FOUND_COORDS
            )
            self.logger.log_status(self.FOUND_COORDS)
            self.downloader.progress.connect(self.update_progress)
            self.downloader.finished.connect(lambda: self.logger.log_status("Download thread finished"))
            self.progress.setMaximum(len(coords))
            self.downloader.start()
        except Exception as e:
            self.logger.log_exception(f"Failed to start download: {e}")

    def update_progress(self, current, total):
        self.progress.setValue(current)
        self.logger.log_status(f"Progress: {current}/{total}")
