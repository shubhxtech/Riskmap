import os
import json
import qtawesome as qta
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QSizePolicy
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import pyqtSignal, QSize, Qt, QUrl

from ui.map_receivers import CoordinateReceiver, PlaceReceiver, CustomWebPage
from templates import render_template

class ApiMapView(QWidget):
    coordinatesSelected = pyqtSignal(list)
    placeSelected = pyqtSignal(dict)

    def __init__(self, logger, api_key, bounds, centre, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.api_key = api_key
        self.map_bounds = bounds
        self.map_centre = centre
        
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Map View
        self.view = QWebEngineView(self)
        self.page = CustomWebPage(self.view, self.logger)
        self.view.setPage(self.page)
        self.main_layout.addWidget(self.view)
        
        # Floating Tool Bar
        self.tools_widget = QFrame(self)
        self.tools_widget.setObjectName("FloatingWidget")
        tools_layout = QHBoxLayout(self.tools_widget)
        tools_layout.setContentsMargins(5, 5, 5, 5)
        tools_layout.setSpacing(5)
        
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
        self.map_type_btn.setChecked(True)
        
        tools_layout.addWidget(self.hand_btn)
        tools_layout.addWidget(self.rect_btn)
        tools_layout.addWidget(self.poly_btn)
        tools_layout.addWidget(self.clear_btn)
        tools_layout.addWidget(self.map_type_btn)

        # Logic Connections
        self.hand_btn.clicked.connect(self.on_hand_clicked)
        self.rect_btn.clicked.connect(self.on_rect_clicked)
        self.poly_btn.clicked.connect(self.on_poly_clicked)
        self.clear_btn.clicked.connect(lambda: self.run_js('clearSelection()'))
        self.map_type_btn.clicked.connect(self.on_map_type_clicked)
        
        self.hand_btn.setChecked(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position Tools (Top Center)
        tool_x = (self.width() - self.tools_widget.width()) // 2
        self.tools_widget.move(tool_x, 20)

    def setup_map(self):
        # 1. Setup QWebChannel
        self.channel = QWebChannel()
        
        # Coordinate receiver
        self.coord_receiver = CoordinateReceiver()
        self.coord_receiver.coordinatesReceived.connect(self.coordinatesSelected.emit)
        self.channel.registerObject("coordReceiver", self.coord_receiver)
        
        # Place receiver for search autocomplete
        self.place_receiver = PlaceReceiver()
        self.place_receiver.placeSelected.connect(self.placeSelected.emit)
        self.channel.registerObject("placeReceiver", self.place_receiver)
        
        self.view.page().setWebChannel(self.channel)
        
        # 2. Get location pin icon
        import base64
        # Calculate correct path from src/ui/api_map_view.py to src/assets/icons/...
        src_dir = os.path.dirname(os.path.dirname(__file__))
        icon_path = os.path.join(src_dir, 'assets', 'icons', 'location-pin.png')
        try:
            with open(icon_path, 'rb') as f:
                icon_data = base64.b64encode(f.read()).decode('utf-8')
                icon_url = f"data:image/png;base64,{icon_data}"
        except Exception as e:
            self.logger.log_exception(f"Failed to load location pin icon: {e}")
            icon_url = "http://maps.google.com/mapfiles/ms/icons/blue-dot.png"
        
        # 3. Load HTML
        html = render_template(
            "api_map.html",
            MAP_BOUNDS=json.dumps(self.map_bounds),
            MAP_CENTRE=json.dumps(self.map_centre),
            ICON_URL=icon_url,
            API_KEY=self.api_key,
        )
        self.view.setHtml(html, baseUrl=QUrl("http://localhost/"))
        self.logger.log_status("Map initialized")

    def run_js(self, script):
        try:
            self.view.page().runJavaScript(script)
            self.logger.log_status(f"Executed JS: {script}")
        except Exception as e:
            self.logger.log_exception(f"JS execution failed: {e}")

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
