#Check

from tenacity import retry, wait_exponential, stop_after_attempt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QProgressBar, QLabel, QSpinBox, QInputDialog, QComboBox, QMessageBox,
    QFrame, QGroupBox, QFormLayout, QSizePolicy, QScrollArea, QCheckBox, QButtonGroup, QLineEdit)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtGui import QColor
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QThread, QTimer, Qt, QSize
from AppLogger import Logger
import json
from config_ import Config
import requests
import os, json
import sqlite3
import math
from Tile_Downloader import download_panorama
from dotenv import load_dotenv
from utils import resolve_path
from pathlib import Path
from Metadata_scanner_grid_search import StreetViewDensityScanner
import qtawesome as qta
from SearchResultsWindow import SearchResultsWidget
from PyQt5.QtWidgets import QStackedWidget

class CoordinateReceiver(QObject):
    # Emitted when JavaScript sends coordinates: list of [lat, lng] or list of lists
    coordinatesReceived = pyqtSignal(object)

    @pyqtSlot('QVariant')
    def receiveCoordinates(self, coords):
        # coords is expected as a JS array of lat/lng pairs
        self.coordinatesReceived.emit(coords)

class PlaceReceiver(QObject):
    """Receiver for Google Places Autocomplete selections"""
    placeSelected = pyqtSignal(object)
    
    @pyqtSlot('QVariant')
    def receivePlaceData(self, place_data):
        # place_data contains: name, address, lat, lng, bounds
        self.placeSelected.emit(place_data)

class PanoramaFetcher(QThread):
    """Background thread for fetching panorama metadata from Google API"""
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(list)  # list of (lat, lon, pano_id) tuples
    error = pyqtSignal(str)

    def __init__(self, grid_points, api_key, logger: Logger):
        super().__init__()
        self.grid_points = grid_points
        self.api_key = api_key
        self.logger = logger

    def fetch_single_point(self, lat, lon):
        """Fetch metadata for a single point"""
        try:
            api_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
            params = {
                "location": f"{lat},{lon}",
                "key": self.api_key
            }
            
            response = requests.get(api_url, params=params, timeout=5)
            
            if response.status_code == 200:
                metadata = response.json()
                if metadata.get('status') == 'OK':
                    # Return full metadata for the UI
                    return {
                        'location': metadata['location'],
                        'panoId': metadata.get('pano_id', ''),
                        'date': metadata.get('date', ''),
                        'copyright': metadata.get('copyright', ''),
                        'status': metadata.get('status', '')
                    }
            return None
        except Exception as e:
            self.logger.log_exception(f"API request failed for ({lat}, {lon}): {e}")
            return None

    def run(self):
        try:
            results = []
            total = len(self.grid_points)
            completed = 0
            
            self.logger.log_status(f"Fetching panoramas from Google API for {total} points (parallel mode)...")
            
            # Use ThreadPoolExecutor for parallel requests (10 workers for good balance)
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                # Submit all tasks
                future_to_point = {
                    executor.submit(self.fetch_single_point, lat, lon): (lat, lon)
                    for lat, lon in self.grid_points
                }
                
                # Process completed tasks
                for future in as_completed(future_to_point):
                    result = future.result()
                    if result:
                        results.append(result)
                    
                    completed += 1
                    # Emit progress every 10 requests or on completion
                    if completed % 10 == 0 or completed == total:
                        self.progress.emit(completed, total)
            
            self.logger.log_status(f"Found {len(results)} panoramas from Google API")
            self.finished.emit(results)
            
        except Exception as e:
            self.logger.log_exception(f"Panorama fetcher thread failed: {e}")
            self.error.emit(str(e))

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

class CustomWebPage(QWebEnginePage):
    """Custom WebEnginePage to intercept and log JavaScript console messages"""
    def __init__(self, parent=None, logger=None):
        super().__init__(parent)
        self.logger = logger

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        try:
            # Map log levels to string prefixes
            levels = {
                QWebEnginePage.InfoMessageLevel: "INFO",
                QWebEnginePage.WarningMessageLevel: "WARN",
                QWebEnginePage.ErrorMessageLevel: "ERROR"
            }
            log_level = levels.get(level, "LOG")
            
            # Format message
            formatted_msg = f"[JS {log_level}] {message} (Line {lineNumber})"
            
            # Print to console for immediate feedback
            print(formatted_msg)
            
            # Log to application logger if available
            if self.logger:
                if level == QWebEnginePage.ErrorMessageLevel:
                    self.logger.log_exception(formatted_msg)
                else:
                    self.logger.log_status(formatted_msg)
        except:
            pass # Prevent recursion or errors in logging

class ApiWindow(QWidget):   
    def __init__(self, logger: Logger, config: Config):
        super().__init__()
        self.logger = logger
        self.config = config
        self.secrets_path = Path(resolve_path(config.get_paths_data()["secrets_path"]))
        print("Reached before set api key")
        QTimer.singleShot(0, lambda: self.set_api_key(self.secrets_path))
        self.FOUND_COORDS = []
        self.region = self.config.get_general_data()["region"]
        # Use region-specific database path instead of generic scan_data.db
        self.DB_PATH = self.get_region_db_path()
        self.output_dir = self.config.get_dwnd_file_path()
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Density settings (distance in meters)
        self.density_distances = {
            'low': 262,
            'medium': 113,
            'high': 53,
            'custom': 100  # default custom value
        }
        self.current_density = 'low'
        self.current_shape_coords = None  # Store selected area
        
        self.init_db()
        self.setup_ui()

    def init_db(self):
        """Initialize the database tables if they don't exist"""
        try:
            conn = sqlite3.connect(self.DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coords (
                    id INTEGER PRIMARY KEY,
                    lat REAL, lon REAL,
                    stage TEXT, scanned INTEGER DEFAULT 0
                )""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    coord_id INTEGER, pano_id TEXT,
                    FOREIGN KEY(coord_id) REFERENCES coords(id)
                )""")
            conn.commit()
            conn.close()
            self.logger.log_status(f"Database initialized at {self.DB_PATH}")
        except Exception as e:
            self.logger.log_exception(f"Failed to initialize database: {e}")
    
    def get_region_db_path(self) -> str:
        """
        Get the path to the region-specific metadata database.
        Returns path like: Metadata_Maps/{region}.db
        """
        metadata_folder = resolve_path("Metadata_Maps")
        os.makedirs(metadata_folder, exist_ok=True)
        db_filename = f"{self.region.lower()}.db"
        db_path = os.path.join(metadata_folder, db_filename)
        self.logger.log_status(f"Using database path: {db_path}")
        return db_path

    def set_api_key(self, path:Path):
        print("In set api key")
        if not path.exists():
            # Create the dialog with optimized settings
            dialog = QInputDialog(self)
            dialog.setWindowTitle("Enter API Key")
            dialog.setLabelText("Paste your Google Maps API key:")
            
            # Set fixed size instead of resize (more efficient)
            dialog.setFixedWidth(450)
            dialog.setMinimumHeight(100)

            # Pre-calculate center position to avoid lag
            main_window = self.window()
            if main_window:
                # Get geometries once
                parent_rect = main_window.frameGeometry()
                dialog_width = 450
                dialog_height = 150
                
                # Calculate center position
                x = parent_rect.x() + (parent_rect.width() - dialog_width) // 2
                y = parent_rect.y() + (parent_rect.height() - dialog_height) // 2
                
                dialog.move(x, y)

            # Show dialog (blocking but optimized)
            if dialog.exec_() == QInputDialog.Accepted:
                api_key = dialog.textValue().strip()
                if api_key:
                    with open(path, "w") as f:
                        f.write(f"API_KEY={api_key}\n")
                    print("Wrote API key to", path)

        load_dotenv(dotenv_path=Path(resolve_path(self.config.get_paths_data()["secrets_path"])))
        self.setup_map()

    def setup_ui(self):
        # 1. Main Layout (Vertical: Map Area + Bottom Panel)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 2. Map Container (Holds Map + Floating Widgets)
        self.map_container = QWidget()
        self.map_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Map View
        self.view = QWebEngineView(self.map_container)
        # Use custom page to capture JS logs
        self.page = CustomWebPage(self.view, self.logger)
        self.view.setPage(self.page)
        self.view.resize(self.map_container.size()) # Initial size
        
        # --- Floating Search Bar (Top Left) ---
        # Removed: Using native Google Maps search control instead
        
        # --- Floating Tool Bar (Top Center) ---
        
        # --- Floating Tool Bar (Top Center) ---
        self.tools_widget = QFrame(self.map_container)
        self.tools_widget.setObjectName("FloatingWidget")

        tools_layout = QHBoxLayout(self.tools_widget)
        tools_layout.setContentsMargins(5, 5, 5, 5)
        tools_layout.setSpacing(5)
        
        import qtawesome as qta
        
        self.hand_btn = QPushButton()
        self.hand_btn.setIcon(qta.icon('fa5s.hand-paper', color='#5f6368'))
        self.hand_btn.setIconSize(QSize(20, 20))
        self.hand_btn.setObjectName("ToolButton")
        self.hand_btn.setToolTip("Pan/Move Tool")
        self.hand_btn.setCheckable(True)
        
        self.rect_btn = QPushButton()
        self.rect_btn.setIcon(qta.icon('fa5s.square', color='#5f6368'))
        self.rect_btn.setIconSize(QSize(20, 20))
        self.rect_btn.setObjectName("ToolButton")
        self.rect_btn.setToolTip("Rectangle Selection")
        self.rect_btn.setCheckable(True)
        
        self.poly_btn = QPushButton()
        self.poly_btn.setIcon(qta.icon('fa5s.draw-polygon', color='#5f6368'))
        self.poly_btn.setIconSize(QSize(20, 20))
        self.poly_btn.setObjectName("ToolButton")
        self.poly_btn.setToolTip("Polygon Selection") 
        self.poly_btn.setCheckable(True)
        
        
        self.clear_btn = QPushButton()
        self.clear_btn.setIcon(qta.icon('fa5s.trash-alt', color='#5f6368'))
        self.clear_btn.setIconSize(QSize(20, 20))
        self.clear_btn.setObjectName("ToolButton")
        self.clear_btn.setToolTip("Clear Selection")
        
        self.map_type_btn = QPushButton()
        self.map_type_btn.setIcon(qta.icon('fa5s.layer-group', color='#5f6368'))
        self.map_type_btn.setIconSize(QSize(20, 20))
        self.map_type_btn.setObjectName("ToolButton")
        self.map_type_btn.setToolTip("Toggle Satellite/Roadmap")
        self.map_type_btn.setCheckable(True)
        self.map_type_btn.setChecked(True)  # Start with satellite
        
        tools_layout.addWidget(self.hand_btn)
        tools_layout.addWidget(self.rect_btn)
        tools_layout.addWidget(self.poly_btn)
        tools_layout.addWidget(self.clear_btn)
        tools_layout.addWidget(self.map_type_btn)

        # Add to Main Layout
        self.main_layout.addWidget(self.map_container, stretch=1)

        # 3. Bottom Panel (Stats + Actions) - Increased height
        self.bottom_panel = QFrame()
        self.bottom_panel.setObjectName("BottomPanel")
        self.bottom_panel.setMinimumHeight(300)  # Increased further for better UI
        
        bottom_layout = QHBoxLayout(self.bottom_panel)
        bottom_layout.setContentsMargins(40, 30, 40, 30)  # More breathing room
        bottom_layout.setSpacing(40)
        
        # Stats Section (Left) - Detailed Info
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(6)
        
        # Title
        stats_title = QLabel("Area selection validation")
        stats_title.setAlignment(Qt.AlignLeft)
        stats_title.setStyleSheet("font-weight: 600; font-size: 18px; color: #1e1e1e; margin-bottom: 8px;")
        stats_layout.addWidget(stats_title)
        
        # Area info
        area_layout = QHBoxLayout()
        area_layout.setSpacing(8)
        area_icon_label = QLabel()
        area_icon_label.setPixmap(qta.icon('fa5s.ruler-combined', color='#1DA1F2').pixmap(QSize(16, 16)))
        area_layout.addWidget(area_icon_label)
        self.area_label = QLabel("Area: 0.7 km² (0.3 sq mi)")
        self.area_label.setObjectName("StatValue")
        area_layout.addWidget(self.area_label)
        area_layout.addStretch()
        stats_layout.addLayout(area_layout)
        
        # Crawling distance
        crawl_layout = QHBoxLayout()
        crawl_layout.setSpacing(8)
        crawl_icon_label = QLabel()
        crawl_icon_label.setPixmap(qta.icon('fa5s.route', color='#1DA1F2').pixmap(QSize(16, 16)))
        crawl_layout.addWidget(crawl_icon_label)
        self.crawling_label = QLabel("Crawling distance: 283 m (928 ft)")
        self.crawling_label.setObjectName("StatValue")
        crawl_layout.addWidget(self.crawling_label)
        crawl_layout.addStretch()
        stats_layout.addLayout(crawl_layout)
        
        # Number of requests
        req_layout = QHBoxLayout()
        req_layout.setSpacing(8)
        req_icon_label = QLabel()
        req_icon_label.setPixmap(qta.icon('fa5s.exchange-alt', color='#1DA1F2').pixmap(QSize(16, 16)))
        req_layout.addWidget(req_icon_label)
        self.requests_label = QLabel("Number of requests: 16")
        self.requests_label.setObjectName("StatValue")
        req_layout.addWidget(self.requests_label)
        req_layout.addStretch()
        stats_layout.addLayout(req_layout)
        
        # Panoramas
        pano_layout = QHBoxLayout()
        pano_layout.setSpacing(8)
        pano_icon_label = QLabel()
        pano_icon_label.setPixmap(qta.icon('fa5s.camera', color='#1DA1F2').pixmap(QSize(16, 16)))
        pano_layout.addWidget(pano_icon_label)
        self.pano_label = QLabel("Estimated panoramas: < 2000") 
        self.pano_label.setObjectName("StatValue")
        pano_layout.addWidget(self.pano_label)
        pano_layout.addStretch()
        stats_layout.addLayout(pano_layout)
        
        stats_layout.addStretch()
        bottom_layout.addLayout(stats_layout)
        
        bottom_layout.addStretch()
        
        # Settings Section (Center)
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(10)
        
        
        # Search density section
        density_header_layout = QHBoxLayout()
        density_header_layout.setSpacing(8)
        
        density_title = QLabel("Search density")
        density_title.setAlignment(Qt.AlignLeft)
        density_title.setStyleSheet("font-weight: 600; font-size: 16px; color: #1e1e1e; margin-bottom: 4px;")
        density_header_layout.addWidget(density_title)
        
        self.info_btn = QPushButton()
        self.info_btn.setIcon(qta.icon('fa5s.info-circle', color='#1DA1F2'))
        self.info_btn.setIconSize(QSize(16, 16))
        self.info_btn.setFixedSize(24, 24)
        self.info_btn.setCursor(Qt.PointingHandCursor)
        self.info_btn.setToolTip("Determines the distance between search points.\nHigher density checks more points but consumes more API requests.")
        self.info_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #E6F4FA;
            }
        """)
        self.info_btn.clicked.connect(self.show_density_info)
        density_header_layout.addWidget(self.info_btn)
        
        density_header_layout.addStretch()
        settings_layout.addLayout(density_header_layout)
        
        density_buttons = QHBoxLayout()
        density_buttons.setSpacing(12) # Add more spacing between buttons
        
        self.density_group = QButtonGroup(self) # Exclusive selection
        
        # Define common button style
        btn_style = """
            QPushButton#DensityButton {
                border: 1px solid #dcdcdc;
                border-radius: 6px;
                background-color: #f8f9fa;
                color: #5f6368;
                font-weight: 500;
                padding: 5px 15px;
            }
            QPushButton#DensityButton:hover {
                background-color: #e8eaed;
                border-color: #dadce0;
            }
            QPushButton#DensityButton:checked {
                background-color: #E6F4FA;
                color: #1DA1F2;
                border: 2px solid #1DA1F2;
                font-weight: 600;
            }
        """
        
        self.low_btn = QPushButton("  Low")
        self.low_btn.setObjectName("DensityButton")
        self.low_btn.setCheckable(True)
        self.low_btn.setChecked(True)
        self.low_btn.setMinimumHeight(42)
        self.low_btn.setToolTip("Low Density (~260m spacing)\nFaster, fewer points")
        self.low_btn.setIcon(qta.icon('fa5s.th-large', color='#1DA1F2'))
        self.low_btn.setIconSize(QSize(16, 16))
        self.low_btn.setStyleSheet(btn_style)
        self.density_group.addButton(self.low_btn)
        
        self.medium_btn = QPushButton("  Medium")
        self.medium_btn.setObjectName("DensityButton")
        self.medium_btn.setCheckable(True)
        self.medium_btn.setMinimumHeight(42)
        self.medium_btn.setToolTip("Medium Density (~110m spacing)\nBalanced coverage")
        self.medium_btn.setIcon(qta.icon('fa5s.th', color='#5f6368'))
        self.medium_btn.setIconSize(QSize(16, 16))
        self.medium_btn.setStyleSheet(btn_style)
        self.density_group.addButton(self.medium_btn)
        
        self.high_btn = QPushButton("  High")
        self.high_btn.setObjectName("DensityButton")
        self.high_btn.setCheckable(True)
        self.high_btn.setMinimumHeight(42)
        self.high_btn.setToolTip("High Density (~50m spacing)\nDetailed, many requests")
        self.high_btn.setIcon(qta.icon('fa5s.th-list', color='#5f6368'))
        self.high_btn.setIconSize(QSize(16, 16))
        self.high_btn.setStyleSheet(btn_style)
        self.density_group.addButton(self.high_btn)
        
        self.custom_btn = QPushButton("  Custom")
        self.custom_btn.setObjectName("DensityButton")
        self.custom_btn.setCheckable(True)
        self.custom_btn.setMinimumHeight(42)
        self.custom_btn.setToolTip("Custom Spacing")
        self.custom_btn.setIcon(qta.icon('fa5s.sliders-h', color='#5f6368'))
        self.custom_btn.setIconSize(QSize(16, 16))
        self.custom_btn.setStyleSheet(btn_style)
        self.density_group.addButton(self.custom_btn)
        
        # Connect to update icons and stats when selection changes
        self.density_group.buttonClicked.connect(self.on_density_changed)
        
        density_buttons.addWidget(self.low_btn)
        density_buttons.addWidget(self.medium_btn)
        density_buttons.addWidget(self.high_btn)
        density_buttons.addWidget(self.custom_btn)
        settings_layout.addLayout(density_buttons)
        
        # Custom distance input (hidden by default)
        self.custom_distance_input = QLineEdit()
        self.custom_distance_input.setPlaceholderText("Enter distance in meters (e.g., 100)")
        self.custom_distance_input.setVisible(False)
        self.custom_distance_input.setMinimumHeight(36)
        self.custom_distance_input.textChanged.connect(self.on_custom_distance_changed)
        settings_layout.addWidget(self.custom_distance_input)
        
        # Restore last density setting from config
        try:
            config = self.config.read_config()
            if 'MAP_SETTINGS' in config.sections():
                last_density = config.get('MAP_SETTINGS', 'last_density', fallback='low')
                
                # Temporarily disconnect signal to avoid saving during restoration
                self.density_group.buttonClicked.disconnect(self.on_density_changed)
                
                if last_density == 'medium':
                    self.medium_btn.setChecked(True)
                    self.current_density = 'medium'
                elif last_density == 'high':
                    self.high_btn.setChecked(True)
                    self.current_density = 'high'
                elif last_density == 'custom':
                    self.custom_btn.setChecked(True)
                    self.current_density = 'custom'
                    custom_dist = config.get('MAP_SETTINGS', 'custom_distance', fallback='100')
                    self.custom_distance_input.setText(custom_dist)
                    self.custom_distance_input.setVisible(True)
                else:
                    self.low_btn.setChecked(True)
                    self.current_density = 'low'
                
                # Update icons for restored selection
                checked_btn = self.density_group.checkedButton()
                if checked_btn:
                    self.update_density_icons(checked_btn)
                
                # Reconnect signal
                self.density_group.buttonClicked.connect(self.on_density_changed)
                
                self.logger.log_status(f"Restored density setting: {self.current_density}")
        except Exception as e:
            self.logger.log_exception(f'Failed to restore density setting: {e}')
            # Fallback to low (already set as default)
            self.current_density = 'low'
        
        # Outdoor views checkbox
        self.outdoor_check = QCheckBox("✓ Outdoor Street Views by Google only")
        self.outdoor_check.setChecked(True)
        self.outdoor_check.setStyleSheet("font-size: 13px;")
        settings_layout.addWidget(self.outdoor_check)
        
        settings_layout.addStretch()
        bottom_layout.addLayout(settings_layout)
        
        bottom_layout.addStretch()

        # Action Section (Right)
        action_layout = QVBoxLayout()
        action_layout.setSpacing(10)
        
        self.download_btn = QPushButton("  Download Area")
        self.download_btn.setIcon(qta.icon('fa5s.download', color='white'))
        self.download_btn.setIconSize(QSize(18, 18))
        self.download_btn.setObjectName("ActionButton")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setMinimumHeight(45)
        self.download_btn.setMinimumWidth(180)
        action_layout.addWidget(self.download_btn)
        
        # Download Panoramas button (hidden by default, shown after fetch completes)
        self.download_panos_btn = QPushButton("  Download Panoramas")
        self.download_panos_btn.setIcon(qta.icon('fa5s.images', color='white'))
        self.download_panos_btn.setIconSize(QSize(18, 18))
        self.download_panos_btn.setObjectName("ActionButton")
        self.download_panos_btn.setCursor(Qt.PointingHandCursor)
        self.download_panos_btn.setMinimumHeight(45)
        self.download_panos_btn.setMinimumWidth(180)
        self.download_panos_btn.setVisible(False)  # Hidden by default
        action_layout.addWidget(self.download_panos_btn)
        
        # View Results Button (to navigate back to results list)
        self.view_results_btn = QPushButton("  View Results")
        self.view_results_btn.setIcon(qta.icon('fa5s.list-ul', color='#5f6368'))
        self.view_results_btn.setIconSize(QSize(16, 16))
        self.view_results_btn.setMinimumHeight(40)
        self.view_results_btn.setMinimumWidth(180)
        self.view_results_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f3f4;
                color: #3c4043;
                border: 1px solid #dadce0;
                border-radius: 4px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #e8eaed;
                border-color: #dadce0;
            }
        """)

        self.view_results_btn.setVisible(False)
        self.view_results_btn.clicked.connect(self.show_results_view)
        action_layout.addWidget(self.view_results_btn)
        
        self.settings_btn = QPushButton("  Settings")
        self.settings_btn.setIcon(qta.icon('fa5s.cog', color='#1DA1F2'))
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.setMinimumHeight(40)
        self.settings_btn.setMinimumWidth(180)
        action_layout.addWidget(self.settings_btn)
        
        action_layout.addStretch()
        action_layout.addStretch()
        bottom_layout.addLayout(action_layout)
        
        # --- Create Wrapper & Stack ---
        # 1. Container for the standard search controls we just built
        self.search_controls_widget = QWidget()
        self.search_controls_widget.setLayout(bottom_layout)
        
        # 2. Stacked Widget to swap between Controls and Results
        self.bottom_stack = QStackedWidget()
        self.bottom_stack.addWidget(self.search_controls_widget) # Index 0
        
        # Final Assembly into bottom_panel
        stack_layout = QVBoxLayout(self.bottom_panel)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.addWidget(self.bottom_stack)
        
        self.main_layout.addWidget(self.bottom_panel)

        # Progress Bar overlay or integrated
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.main_layout.addWidget(self.progress)


        # Logic Connections
        # Note: Search autocomplete is handled by JavaScript (Google Places Autocomplete)
        # Place selection events are received via PlaceReceiver
        
        # Toggle logic for tools
        self.hand_btn.clicked.connect(self.on_hand_clicked)
        self.rect_btn.clicked.connect(self.on_rect_clicked)
        self.poly_btn.clicked.connect(self.on_poly_clicked)
        self.clear_btn.clicked.connect(lambda: self.run_js('clearSelection()'))
        self.map_type_btn.clicked.connect(self.on_map_type_clicked)
        
        
        self.download_btn.clicked.connect(self.on_download_area_clicked)
        self.download_panos_btn.clicked.connect(self.start_download)
        
        # Set hand tool as default
        self.hand_btn.setChecked(True)
        
        # Handle Resize for Floating Widgets
        self.map_container.installEventFilter(self)

    def eventFilter(self, source, event):
        if source == self.map_container and event.type() == event.Resize:
            # Resize webview
            self.view.resize(source.size())
            
            # Position Tools (Top Center)
            tool_x = (source.width() - self.tools_widget.width()) // 2
            self.tools_widget.move(tool_x, 20)
            
        return super().eventFilter(source, event)

    def on_hand_clicked(self):
        self.rect_btn.setChecked(False)
        self.poly_btn.setChecked(False)
        self.hand_btn.setChecked(True)
        self.run_js('enableHand()')
    
    def on_rect_clicked(self):
        self.hand_btn.setChecked(False)
        self.poly_btn.setChecked(False)
        self.rect_btn.setChecked(True)
        self.run_js('enableRectangle()')

    def on_poly_clicked(self):
        self.hand_btn.setChecked(False)
        self.rect_btn.setChecked(False)
        self.poly_btn.setChecked(True)
        self.run_js('enablePolygon()')
    
    def on_map_type_clicked(self):
        self.run_js('toggleMapType()')
    
    def on_density_changed(self, button):
        """Handle density button selection changes"""
        # Update icons
        self.update_density_icons(button)
        
        # Update current density
        if self.low_btn.isChecked():
            self.current_density = 'low'
            self.custom_distance_input.setVisible(False)
        elif self.medium_btn.isChecked():
            self.current_density = 'medium'
            self.custom_distance_input.setVisible(False)
        elif self.high_btn.isChecked():
            self.current_density = 'high'
            self.custom_distance_input.setVisible(False)
        elif self.custom_btn.isChecked():
            self.current_density = 'custom'
            self.custom_distance_input.setVisible(True)
            self.custom_distance_input.setFocus()
        
        # Save density setting to config for persistence
        try:
            config = self.config.read_config()
            if 'MAP_SETTINGS' not in config.sections():
                config.add_section('MAP_SETTINGS')
            config['MAP_SETTINGS']['last_density'] = self.current_density
            if self.current_density == 'custom':
                config['MAP_SETTINGS']['custom_distance'] = self.custom_distance_input.text()
            
            with open(self.config.config_file, 'w') as f:
                config.write(f)
            self.logger.log_status(f"Saved density setting: {self.current_density}")
        except Exception as e:
            self.logger.log_exception(f'Failed to save density setting: {e}')
        
        # Update UI with new calculations
        self.update_stats_ui()
    
    def on_custom_distance_changed(self, text):
        """Handle custom distance input changes"""
        try:
            if text.strip():
                distance = int(text)
                if distance > 0:
                    self.density_distances['custom'] = distance
                    self.update_stats_ui()
        except ValueError:
            pass  # Invalid input, ignore
    
    def update_density_icons(self, button):
        """Update icons and styles when density selection changes"""
        # Define icons mapping
        icons = {
            self.low_btn: 'fa5s.th-large',
            self.medium_btn: 'fa5s.th',
            self.high_btn: 'fa5s.th-list',
            self.custom_btn: 'fa5s.sliders-h'
        }
        
        # Update all buttons
        for btn, icon_name in icons.items():
            if btn.isChecked():
                # Active: Primary Blue icon
                btn.setIcon(qta.icon(icon_name, color='#1DA1F2'))
            else:
                # Inactive: Grey icon
                btn.setIcon(qta.icon(icon_name, color='#5f6368'))

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
            color = QColor('#4caf50') if is_available else QColor('#ef5350')
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
        # Update database path when region changes
        self.DB_PATH = self.get_region_db_path()
        self.logger.log_status(f"Switched to region: {city}, database: {self.DB_PATH}")
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
        """Query panorama results from database within bounding box"""
        try:
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
            self.logger.log_status(f"Found {len(results)} results from database")
            return results
        except Exception as e:
            self.logger.log_exception(f"Database query failed: {e}")
            return []
    
    def get_current_crawling_distance(self):
        """Get current crawling distance in meters based on density selection"""
        return self.density_distances[self.current_density]
    
    def meters_to_degrees(self, meters):
        """Convert meters to approximate degrees (latitude)"""
        # 1 degree latitude ≈ 111,000 meters
        return meters / 111000.0
    
    def generate_grid_points(self, north, south, east, west, spacing_meters=None):
        """
        Generate a grid of lat/lng points within the bounding box.
        spacing_meters: distance between points in meters (uses current density if None)
        """
        if spacing_meters is None:
            spacing_meters = self.get_current_crawling_distance()
        
        spacing = self.meters_to_degrees(spacing_meters)
        
        points = []
        lat = north
        while lat >= south:
            lon = west
            while lon <= east:
                points.append((lat, lon))
                lon += spacing
            lat -= spacing
        self.logger.log_status(f"Generated {len(points)} grid points (spacing: {spacing_meters}m)")
        return points
    
    def fetch_panoramas_from_api(self, points, max_points=None):
        """
        Fetch panorama data from Google Street View API for given points.
        Returns list of (lat, lon, pano_id) tuples.
        max_points: Maximum number of points to check (None = unlimited)
        """
        if not self.api_key:
            self.logger.log_status("No API key available for fetching panoramas")
            return []
        
        results = []
        # Use all points if max_points is None, otherwise limit
        points_to_check = points if max_points is None else points[:max_points]
        
        self.logger.log_status(f"Fetching panoramas from Google API for {len(points_to_check)} points...")
        
        for i, (lat, lon) in enumerate(points_to_check):
            try:
                # Query Google Street View Metadata API
                api_url = f"https://maps.googleapis.com/maps/api/streetview/metadata"
                params = {
                    "location": f"{lat},{lon}",
                    "key": self.api_key
                }
                
                response = requests.get(api_url, params=params, timeout=5)
                
                if response.status_code == 200:
                    metadata = response.json()
                    if metadata.get('status') == 'OK':
                        # Use actual coordinates from API response
                        actual_lat = metadata['location']['lat']
                        actual_lon = metadata['location']['lng']
                        pano_id = metadata.get('pano_id', '')
                        results.append((actual_lat, actual_lon, pano_id))
                        
                # Update progress every 10 requests
                if (i + 1) % 10 == 0:
                    self.logger.log_status(f"API fetch progress: {i+1}/{len(points_to_check)}")
                    
            except Exception as e:
                self.logger.log_exception(f"API request failed for ({lat}, {lon}): {e}")
                continue
        
        self.logger.log_status(f"Found {len(results)} panoramas from Google API")
        return results

    def setup_map(self):
        # Setup WebChannel communication
        self.api_key = os.getenv("API_KEY")
        
        # Validate API key
        if not self.api_key or self.api_key == "None":
            self.logger.log_status("ERROR: Google Maps API key not found! Map will not load.")
            self.logger.log_status("Please ensure API_KEY is set in your .env file")
            return
        
        self.logger.log_status(f"API Key loaded: {self.api_key[:10]}...")
        
        self.channel = QWebChannel()
        self.coord_receiver = CoordinateReceiver()
        self.coord_receiver.coordinatesReceived.connect(self.on_coordinates)
        self.channel.registerObject('coordReceiver', self.coord_receiver)
        
        # Setup place selection receiver for autocomplete
        self.place_receiver = PlaceReceiver()
        self.place_receiver.placeSelected.connect(self.on_place_selected)
        self.channel.registerObject('placeReceiver', self.place_receiver)
        
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
        
        # Convert location pin icon to base64 data URL for WebView compatibility
        import base64
        icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'icons', 'location-pin.png')
        try:
            with open(icon_path, 'rb') as f:
                icon_data = base64.b64encode(f.read()).decode('utf-8')
                icon_url = f"data:image/png;base64,{icon_data}"
        except Exception as e:
            self.logger.log_exception(f"Failed to load location pin icon: {e}")
            # Fallback to Google Maps blue dot
            icon_url = "http://maps.google.com/mapfiles/ms/icons/blue-dot.png"
        
        # Load Google Maps HTML with JS selection tools
        html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="initial-scale=1.0, user-scalable=yes" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; padding: 0 }}
    .controls {{
        margin-top: 10px;
        border: 1px solid transparent;
        border-radius: 2px 0 0 2px;
        box-sizing: border-box;
        -moz-box-sizing: border-box;
        height: 32px;
        outline: none;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
    }}

    #pac-input {{
        background-color: #fff;
        font-family: Roboto;
        font-size: 15px;
        font-weight: 400;
        margin-left: 12px;
        padding: 0 11px 0 13px;
        text-overflow: ellipsis;
        width: 350px;
        height: 40px;
        line-height: 40px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2), 0 -1px 0px rgba(0,0,0,0.02);
        border: none;
    }}

    #pac-input:focus {{
        border-color: #4d90fe;
    }}
    
    .pac-container {{
        z-index: 10000 !important;
        background-color: #fff;
        border-top: 1px solid #d9d9d9;
        font-family: Roboto, Arial, sans-serif;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
        border-radius: 0 0 8px 8px;
        margin-top: 5px;
    }}
    
    .pac-item {{
        cursor: default;
        padding: 0 4px;
        text-overflow: ellipsis;
        overflow: hidden;
        white-space: nowrap;
        line-height: 30px;
        text-align: left;
        border-top: 1px solid #e6e6e6;
        font-size: 11px;
        color: #999;
    }}
    
    .pac-item:hover {{
        background-color: #fafafa;
    }}
    
    .pac-item-query {{
        font-size: 13px;
        color: #000;
        padding-right: 3px;
    }}
  </style>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <script>
    let map, drawingManager, shapes=[];
    let autocomplete;
    
    // Cache management functions for persistent map state
    function saveMapState() {{
        try {{
            const state = {{
                center: {{ lat: map.getCenter().lat(), lng: map.getCenter().lng() }},
                zoom: map.getZoom(),
                mapType: map.getMapTypeId(),
                timestamp: Date.now()
            }};
            localStorage.setItem('riskmap_state', JSON.stringify(state));
            console.log('Map state saved to cache');
        }} catch (e) {{
            console.error('Failed to save map state:', e);
        }}
    }}
    
    function loadMapState() {{
        try {{
            const cached = localStorage.getItem('riskmap_state');
            if (cached) {{
                const state = JSON.parse(cached);
                console.log('Loaded cached map state:', state);
                return state;
            }}
        }} catch (e) {{
            console.error('Failed to load cached state:', e);
        }}
        return null;
    }}
    
    function initMap() {{
        console.log('initMap called');
        
        if (typeof google === 'undefined') {{
            console.error('Google Maps API not loaded!');
            setTimeout(initMap, 500); // Retry after 500ms
            return;
        }}
        
        console.log('Google Maps API loaded successfully');
        const aizawlBounds = {self.map_bounds};
        
        // Try to restore from cache
        const cachedState = loadMapState();

        try {{
            map = new google.maps.Map(document.getElementById('map'), {{
                center: cachedState?.center || {self.map_centre}, 
                zoom: cachedState?.zoom || 11,
                minZoom: 1,
                maxZoom: 20,
                mapTypeId: cachedState?.mapType || google.maps.MapTypeId.ROADMAP,
                mapTypeControl: true,
                mapTypeControlOptions: {{
                    style: google.maps.MapTypeControlStyle.HORIZONTAL_BAR,
                    position: google.maps.ControlPosition.TOP_RIGHT,
                    mapTypeIds: ['roadmap', 'satellite', 'hybrid', 'terrain']
                }},
                streetViewControl: false,
                fullscreenControl: true
            }});
            
            // Add tile load listener
            google.maps.event.addListener(map, 'tilesloaded', function() {{
                console.log('Map tiles loaded successfully');
            }});
            
            // Auto-save map state on changes (debounced)
            let saveTimeout;
            google.maps.event.addListener(map, 'idle', function() {{
                console.log('Map is idle and ready');
                // Debounce save to avoid excessive writes
                clearTimeout(saveTimeout);
                saveTimeout = setTimeout(saveMapState, 500);
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
                new QWebChannel(qt.webChannelTransport, channel => {{
                    channel.objects.coordReceiver.receiveCoordinates(coords);
                }});
            }});
            
            console.log('Map initialized successfully');
            
            // Add Street View coverage layer to show where panoramas are available
            const streetViewLayer = new google.maps.StreetViewCoverageLayer();
            streetViewLayer.setMap(map);
            console.log('Street View coverage layer added');
            
            // Initialize Google Places Autocomplete after map loads
            initAutocomplete();
        }} catch (error) {{
            console.error('Error initializing map:', error);
        }}
    }}
    
    function initAutocomplete() {{
        console.log('Initializing Places Autocomplete');
        
        // Wait for map and library
        setTimeout(function() {{
            try {{
                if (!google.maps.places) {{
                    console.error('Google Maps Places library is NOT loaded. Check API key and libraries parameter.');
                    return;
                }}

                let input = document.getElementById('pac-input');
                if (!input) {{
                   // Create if missing
                   input = document.createElement('input');
                   input.id = 'pac-input';
                   input.className = 'controls';
                   input.type = 'text';
                   input.placeholder = 'Search Google Maps';
                   map.controls[google.maps.ControlPosition.TOP_LEFT].push(input);
                }}

                // Use 'input' variable DIRECTLY. Do not re-query 'getElementById' immediately.
                const searchInput = input;

                // Wait for element to be "pushed" to map controls (small delay)
                setTimeout(function() {{
                    // Initialize autocomplete
                    autocomplete = new google.maps.places.Autocomplete(searchInput, {{
                        fields: ['geometry', 'name', 'formatted_address']
                    }});
                    
                    autocomplete.bindTo('bounds', map);
                    
                    autocomplete.addListener('place_changed', function() {{
                        // ... existing handler logic ...
                        const place = autocomplete.getPlace();
                        console.log('Place selected (raw): ' + JSON.stringify(place));

                        if (!place.geometry || !place.geometry.location) {{
                            console.log('No geometry for place. User might have hit Enter without selecting suggestion.');
                            
                            // Fallback: Geocode the name or query
                            const query = place.name || searchInput.value;
                            if (query) {{
                                console.log('Attempting Geocode fallback for: ' + query);
                                const geocoder = new google.maps.Geocoder();
                                geocoder.geocode({{ 'address': query }}, function(results, status) {{
                                    if (status === 'OK' && results[0]) {{
                                        console.log('Geocode successful');
                                        processPlace(results[0]);
                                    }} else {{
                                        console.error('Geocode fallback failed: ' + status);
                                    }}
                                }});
                            }}
                            return;
                        }}
                        
                        processPlace(place);
                    }});
                    
                }}, 200);
                
                function processPlace(place) {{
                    console.log('Processing place: ' + place.name || place.formatted_address);
                    
                    if (place.geometry.viewport) {{
                        map.fitBounds(place.geometry.viewport);
                    }} else {{
                        map.setCenter(place.geometry.location);
                        map.setZoom(13);
                    }}
                    
                    setTimeout(function() {{
                        const bounds = map.getBounds();
                        if (bounds) {{
                            const placeData = {{
                                name: place.name || '',
                                address: place.formatted_address || '',
                                lat: place.geometry.location.lat(),
                                lng: place.geometry.location.lng(),
                                north: bounds.getNorthEast().lat(),
                                south: bounds.getSouthWest().lat(),
                                east: bounds.getNorthEast().lng(),
                                west: bounds.getSouthWest().lng()
                            }};
                            
                            new QWebChannel(qt.webChannelTransport, function(channel) {{
                                channel.objects.placeReceiver.receivePlaceData(placeData);
                            }});
                        }}
                    }}, 500);
                }}
                
                console.log('Autocomplete initialized successfully');
            }} catch (error) {{
                console.error('Error initializing autocomplete:', error);
            }}
        }}, 1000);
    }}
    
    // ... Helper functions ...
    function enableRectangle() {{ drawingManager.setDrawingMode(google.maps.drawing.OverlayType.RECTANGLE); }}
    function enableCircle() {{ drawingManager.setDrawingMode(google.maps.drawing.OverlayType.CIRCLE); }}
    function enablePolygon() {{ drawingManager.setDrawingMode(google.maps.drawing.OverlayType.POLYGON); }}
    function enableHand() {{ drawingManager.setDrawingMode(null); }}
    
    function toggleMapType() {{
        if (map.getMapTypeId() === 'satellite') {{
            map.setMapTypeId('roadmap');
            console.log('Switched to roadmap');
        }} else {{
            map.setMapTypeId('satellite');
            console.log('Switched to satellite');
        }}
    }}
    
    var markers = [];
    function addMarker(lat, lng) {{
        var marker = new google.maps.Marker({{
            position: {{lat: lat, lng: lng}},
            map: map,
            icon: {{
                url: '{icon_url}',
                scaledSize: new google.maps.Size(32, 32),
                anchor: new google.maps.Point(16, 32)
            }},
            title: 'Panorama Location'
        }});
        markers.push(marker);
    }}
    function clearMarkers() {{
        markers.forEach(m => m.setMap(null));
        markers = [];
    }}
    function fitBounds(minLat, minLng, maxLat, maxLng) {{
        var bounds = new google.maps.LatLngBounds(
            new google.maps.LatLng(minLat, minLng),
            new google.maps.LatLng(maxLat, maxLng)
        );
        map.fitBounds(bounds);
    }}

    function clearSelection() {{ 
        shapes.forEach(s=>s.setMap(null)); 
        shapes=[]; 
        clearMarkers();
    }}
  </script>
  <script async defer src="https://maps.googleapis.com/maps/api/js?key={self.api_key}&libraries=drawing,places&loading=async&callback=initMap"></script>
</head>
<body>
  <div id="map"></div>
</body>
</html>"""
        from PyQt5.QtCore import QUrl
        self.view.setHtml(html, baseUrl=QUrl("http://localhost/"))
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

    def on_place_selected(self, place_data):
        """Handle place selection from Google Places Autocomplete"""
        try:
            place_name = place_data.get('name', 'Unknown')
            address = place_data.get('address', '')
            lat = place_data.get('lat', 0)
            lng = place_data.get('lng', 0)
            
            self.logger.log_status(f"Place selected: {place_name}")
            self.logger.log_status(f"Address: {address}")
            self.logger.log_status(f"Coordinates: ({lat}, {lng})")
            
            # Update region for metadata database (use place name)
            self.region = place_name
            self.DB_PATH = self.get_region_db_path()
            self.logger.log_status(f"Updated database path: {self.DB_PATH}")
            
        except Exception as e:
            self.logger.log_exception(f"Error handling place selection: {e}")
    
    def on_coordinates(self, coords):
        if not coords: return
        self.logger.log_status(f"Coordinates received: {len(coords)} points")
        
        # Parse coords
        try:
            coords = [[float(c[0]), float(c[1])] for c in coords]
        except Exception as e:
            self.logger.log_exception(f"Error parsing coords: {e}")
            return

        # Determine Bounds
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        north, south = max(lats), min(lats)
        east, west = max(lngs), min(lngs)
        
        # Store selected area for later use (when Download button is clicked)
        self.current_shape_coords = coords
        
        # Calculate and update UI stats (but don't fetch yet)
        self.update_stats_ui()
        
        self.logger.log_status(f"Area selected. Click 'Download Area' to fetch panoramas.")
    
    def update_stats_ui(self):
        """Update UI stats based on current selection and density"""
        if not self.current_shape_coords:
            return
        
        coords = self.current_shape_coords
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        north, south = max(lats), min(lats)
        east, west = max(lngs), min(lngs)
        
        # Calculate area
        area = self.calculate_area(coords)
        self.area_label.setText(f"Area: {area:.2f} km²")
        
        # Get current crawling distance
        crawling_distance = self.get_current_crawling_distance()
        self.crawling_label.setText(f"Crawling distance: {crawling_distance} m ({int(crawling_distance * 3.28084)} ft)")
        
        # Estimate number of grid points/requests
        grid_points = self.generate_grid_points(north, south, east, west, crawling_distance)
        num_requests = len(grid_points)
        self.requests_label.setText(f"Number of requests: {num_requests}")
        
        # Estimate panoramas (rough estimate: ~30-50% of requests find panoramas)
        estimated_panos = int(num_requests * 0.4)
        self.pano_label.setText(f"Estimated panoramas: ~{estimated_panos}")
    
    def on_download_area_clicked(self):
        """Handle Download Area button click - fetch panorama metadata asynchronously"""
        if not self.current_shape_coords:
            QMessageBox.warning(self, "No Area Selected", "Please select an area on the map first.")
            return
        
        coords = self.current_shape_coords
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        north, south = max(lats), min(lats)
        east, west = max(lngs), min(lngs)
        
        # Reset UI state for new search
        self.view_results_btn.setVisible(False)
        
        # Try to query database first
        data = []
        if os.path.exists(self.DB_PATH):
            data = self.query_results(self.DB_PATH, north, south, east, west)
        
        # If data found in database, display immediately
        if data:
            # Convert DB tuples to rich metadata format for the UI
            formatted_data = []
            for item in data:
                formatted_data.append({
                    'location': {'lat': item[0], 'lng': item[1]},
                    'panoId': item[2],
                    'date': '(Cached)',
                    'copyright': 'Unknown',
                    'status': 'OK'
                })
            self.process_search_results(formatted_data)
            return
        
        # No data in database - fetch from API asynchronously
        self.logger.log_status("No data in database, fetching from Google Street View API...")
        
        # Generate grid points with current density setting
        crawling_distance = self.get_current_crawling_distance()
        grid_points = self.generate_grid_points(north, south, east, west, crawling_distance)
        
        # Disable download button during fetch
        self.download_btn.setEnabled(False)
        self.download_btn.setText("  Fetching...")
        self.download_panos_btn.setVisible(False)  # Hide until fetch completes
        
        # Show progress bar
        self.progress.setMaximum(len(grid_points))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        
        # Start async fetching
        self.fetcher = PanoramaFetcher(grid_points, self.api_key, self.logger)
        self.fetcher.progress.connect(self.on_fetch_progress)
        self.fetcher.finished.connect(self.on_fetch_finished)
        self.fetcher.error.connect(self.on_fetch_error)
        self.fetcher.start()
    
    def on_fetch_progress(self, current, total):
        """Update progress bar during fetch"""
        self.progress.setValue(current)
        if current % 10 == 0:  # Log every 10 requests
            self.logger.log_status(f"Fetching progress: {current}/{total}")
    
    def on_fetch_error(self, error_msg):
        """Handle fetch error"""
        self.download_btn.setEnabled(True)
        self.download_btn.setText("  Download Area")
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Fetch Error", f"Failed to fetch panoramas: {error_msg}")
    
    
    def on_fetch_finished(self, data):
        """Handle fetch completion (signal slot)"""
        self.process_search_results(data)

    def process_search_results(self, data):
        """Process and display search results (common for API and DB)"""
        self.download_btn.setEnabled(True)
        self.download_btn.setText("  Download Area")
        self.progress.setVisible(False)
        self.view_results_btn.setVisible(True) # Enable navigation back to results
        
        if not data:
            self.logger.log_status("No panoramas found in this area.")
            QMessageBox.information(self, "No Results", "No Google Street View panoramas found in the selected area.")
            return

        # 'data' is now a list of dicts (rich metadata)
        # We need to extract the tuples for the existing downloader logic
        self.FOUND_COORDS = []
        for item in data:
            lat = item.get('location', {}).get('lat')
            lng = item.get('location', {}).get('lng')
            pid = item.get('panoId')
            if lat is not None and pid:
                self.FOUND_COORDS.append((lat, lng, pid))
        
        count = len(self.FOUND_COORDS)
        self.logger.log_status(f"Found {count} results")

        # --- Embed Results in Bottom Panel ---
        # Create Widget
        self.results_widget = SearchResultsWidget(data, self)
        
        # Connect Signals
        self.results_widget.back_clicked.connect(self.show_search_controls)
        self.results_widget.download_clicked.connect(self.start_download)
        
        # Add to stack (Index 1)
        # Remove old if exists
        if self.bottom_stack.count() > 1:
            old = self.bottom_stack.widget(1)
            self.bottom_stack.removeWidget(old)
            old.deleteLater()
            
        self.bottom_stack.addWidget(self.results_widget)
        self.bottom_stack.addWidget(self.results_widget)
        
        # Switch to view
        self.show_results_view()
        
        # Determine Bounds for map fitting
        lats = [c[0] for c in self.FOUND_COORDS]
        lngs = [c[1] for c in self.FOUND_COORDS]
        
        if lats:
            north, south = max(lats), min(lats)
            east, west = max(lngs), min(lngs)
            
            # Fixed: Wrap in IIFE to avoid const redeclaration error when density changes
            js_code = f"""
            (function() {{
                clearMarkers();
                const points = {json.dumps(self.FOUND_COORDS)};
                points.forEach(p => {{
                    addMarker(p[0], p[1]);
                }});
            }})();
            """
            
            if count > 0:
                js_code += f"fitBounds({south}, {west}, {north}, {east});"
                self.run_js(js_code)
                
                # Show Download Panoramas button (in case they closed dialog but want to download later)
                # Not needed in embedded view as we have download button there
                # self.download_panos_btn.setVisible(True)
        
        # Update Stats UI
        self.pano_label.setText(f"Panoramas: {count}")

    def show_search_controls(self):
        """Switch back to search controls view"""
        self.bottom_stack.setCurrentIndex(0)
        self.bottom_panel.setMinimumHeight(100) # Reset height
        self.bottom_panel.setMaximumHeight(250)

    def show_results_view(self):
        """Switch to search results view and expand panel"""
        if self.bottom_stack.count() > 1:
            self.bottom_stack.setCurrentIndex(1)
            self.bottom_panel.setMinimumHeight(400)
            # Remove max height constraint to allow expansion if needed, or keep it consistent
            self.bottom_panel.setMaximumHeight(16777215) # QWIDGETSIZE_MAX

    
    def display_panoramas_on_map(self, data, coords):
        """Display panorama markers on the map and show Download Panoramas button"""
        self.FOUND_COORDS = []
        
        # Calculate bounds from coords
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        north, south = max(lats), min(lats)
        east, west = max(lngs), min(lngs)
        
        # Prepare JS for markers
        js_code = "clearMarkers();"
        
        # Filter results to only include points strictly within the selection
        for i in data:
            lat, lon = i[0], i[1]
            pano_id = i[2]
            
            # Check if point is inside the polygon/rectangle
            if self.is_point_in_polygon(lat, lon, coords):
                # Use the coordinates directly from the fetched data
                # No need for additional API calls - data already verified during fetch
                self.FOUND_COORDS.append((lat, lon, pano_id))
                js_code += f"addMarker({lat}, {lon});"

        count = len(self.FOUND_COORDS)
        self.logger.log_status(f"Found {count} results in bounds")
        
        if count > 0:
            js_code += f"fitBounds({south}, {west}, {north}, {east});"
            self.run_js(js_code)
            
            # Show Download Panoramas button
            self.download_panos_btn.setVisible(True)
            self.logger.log_status(f"Download Panoramas button shown ({count} panoramas ready)")
        
        # Update Stats UI
        self.pano_label.setText(f"Panoramas: {count}")
        
        area = self.calculate_area(coords)
        self.area_label.setText(f"Area: {area:.2f} km²")
    
    def is_point_in_polygon(self, lat, lon, polygon_coords):
        """
        Check if a point (lat, lon) is inside a polygon using ray casting algorithm.
        polygon_coords: list of [lat, lon] pairs
        """
        if len(polygon_coords) < 3:
            # For rectangle (2 points), use simple bounding box check
            if len(polygon_coords) == 2:
                min_lat = min(polygon_coords[0][0], polygon_coords[1][0])
                max_lat = max(polygon_coords[0][0], polygon_coords[1][0])
                min_lon = min(polygon_coords[0][1], polygon_coords[1][1])
                max_lon = max(polygon_coords[0][1], polygon_coords[1][1])
                return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
            return False
        
        # Ray casting algorithm for polygon
        inside = False
        n = len(polygon_coords)
        p1_lat, p1_lon = polygon_coords[0]
        
        for i in range(1, n + 1):
            p2_lat, p2_lon = polygon_coords[i % n]
            
            if lon > min(p1_lon, p2_lon):
                if lon <= max(p1_lon, p2_lon):
                    if lat <= max(p1_lat, p2_lat):
                        if p1_lon != p2_lon:
                            x_intersection = (lon - p1_lon) * (p2_lat - p1_lat) / (p2_lon - p1_lon) + p1_lat
                        if p1_lat == p2_lat or lat <= x_intersection:
                            inside = not inside
            
            p1_lat, p1_lon = p2_lat, p2_lon
        
        return inside

    def calculate_area(self, coords):
        if len(coords) < 3:
            # Rectangle Case (2 points from JS: NE, SW)
            if len(coords) == 2:
                lat1, lon1 = coords[0]
                lat2, lon2 = coords[1]
                dlat = abs(lat1 - lat2) * 111.0
                avg_lat = (lat1 + lat2) / 2.0
                dlon = abs(lon1 - lon2) * 111.0 * abs(math.cos(math.radians(avg_lat)))
                return dlat * dlon
            return 0.0
            
        # Polygon Case
        avg_lat = sum(c[0] for c in coords) / len(coords)
        cos_lat = math.cos(math.radians(avg_lat))
        
        x = [c[1] * 111.0 * cos_lat for c in coords]
        y = [c[0] * 111.0 for c in coords]
        
        area = 0.0
        j = len(coords) - 1
        for i in range(len(coords)):
            area += (x[j] + x[i]) * (y[j] - y[i])
            j = i
        return abs(area / 2.0)

    def start_download(self):
        """Handle Download Panoramas button click - download actual panorama images"""
        try:
            if not self.FOUND_COORDS:
                QMessageBox.warning(self, "No Panoramas", "No panoramas found. Please click 'Download Area' first.")
                return
            
            # Prompt user to select save location
            folder = QFileDialog.getExistingDirectory(
                self,
                "Select Folder to Save Panoramas",
                str(self.output_dir),  # Convert Path to string
                QFileDialog.ShowDirsOnly
            )
            
            if not folder:
                self.logger.log_status("Download cancelled - no folder selected")
                return
            
            # Update output directory
            self.output_dir = folder
            self.logger.log_status(f"Downloading {len(self.FOUND_COORDS)} panoramas to {folder}")
            
            # Disable Download Panoramas button during download
            self.download_panos_btn.setEnabled(False)
            self.download_panos_btn.setText("  Downloading...")
            
            # Start download thread
            self.downloader = StreetViewDownloader(
                folder, None, self.logger, self.config, self.FOUND_COORDS
            )
            self.downloader.progress.connect(self.update_progress)
            self.downloader.finished.connect(self.on_download_finished)
            self.progress.setMaximum(len(self.FOUND_COORDS))
            self.progress.setValue(0)
            self.progress.setVisible(True)
            self.downloader.start()
            
        except Exception as e:
            self.logger.log_exception(f"Failed to start download: {e}")
            QMessageBox.critical(self, "Download Error", f"Failed to start download: {e}")
    
    def on_download_finished(self):
        """Handle download completion"""
        self.download_panos_btn.setEnabled(True)
        self.download_panos_btn.setText("  Download Panoramas")
        self.progress.setVisible(False)
        self.logger.log_status("Download completed")
        QMessageBox.information(
            self,
            "Download Complete",
            f"Successfully downloaded {len(self.FOUND_COORDS)} panoramas to:\n{self.output_dir}"
        )

    def update_progress(self, current, total):
        self.progress.setValue(current)
        self.logger.log_status(f"Progress: {current}/{total}")

    def show_density_info(self):
        """Show information about search density settings"""
        info_text = (
            "<h3>Search Density Explained</h3>"
            "<p>Search density determines how closely we scan the selected area for panoramas. "
            "It controls the distance between grid points where we check for Street View availability.</p>"
            "<ul>"
            "<li><b>Low (~262m spacing):</b> Best for large rural areas or quick scans. Uses fewer API requests.</li>"
            "<li><b>Medium (~113m spacing):</b> Balanced coverage for suburban areas.</li>"
            "<li><b>High (~53m spacing):</b> Very thorough. Best for dense urban areas to catch every street. Uses significantly more API requests.</li>"
            "</ul>"
            "<p><i>Note: The 'Estimated Panoramas' count will update based on your selection.</i></p>"
        )
        QMessageBox.information(self, "About Search Density", info_text)
