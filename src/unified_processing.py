from PyQt5.QtWidgets import QWidget, QHBoxLayout, QGroupBox, QVBoxLayout, QScrollArea, QSplitter
from PyQt5.QtCore import Qt
from config_ import Config
from app_logger import Logger

from crop_window import CropWindow
from building_detection_window import BuildingDetectionWindow

class UnifiedProcessingWindow(QWidget):
    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.config = config
        self.logger = logger
        self.init_ui()

    def init_ui(self):
        # Main Horizontal Layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(20)

        # Create Splitter for resizable areas
        splitter = QSplitter(Qt.Horizontal)

        # === Left Side: Image Processing (Crop) ===
        left_group = QGroupBox("Step 1: Image Pre-processing")
        left_layout = QVBoxLayout(left_group)
        
        # Instantiate CropWindow
        self.crop_window = CropWindow(self.config, self.logger)
        left_layout.addWidget(self.crop_window)
        
        splitter.addWidget(left_group)

        # === Right Side: Object Detection ===
        right_group = QGroupBox("Step 2: Object Detection")
        right_layout = QVBoxLayout(right_group)

        # Instantiate BuildingDetectionWindow
        self.detection_window = BuildingDetectionWindow(self.config, self.logger)
        right_layout.addWidget(self.detection_window)

        splitter.addWidget(right_group)

        # Set initial sizes (50/50 split)
        splitter.setSizes([500, 500])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        main_layout.addWidget(splitter)
