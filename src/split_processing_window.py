from PyQt5.QtWidgets import QWidget, QVBoxLayout, QSplitter, QGroupBox
from PyQt5.QtCore import Qt
from duplicates import DuplicatesWindow
from classification import ClassificationWindow

class SplitProcessingWindow(QWidget):
    def __init__(self, config, logger):
        super().__init__()
        self.config = config
        self.logger = logger
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        # Create the splitter
        splitter = QSplitter(Qt.Horizontal)

        # === Left Side: Duplicates ===
        self.duplicates_group = QGroupBox("Step 1: Duplicate Removal")
        dup_layout = QVBoxLayout(self.duplicates_group)
        self.duplicates_window = DuplicatesWindow(self.config, self.logger)
        dup_layout.addWidget(self.duplicates_window)
        splitter.addWidget(self.duplicates_group)

        # === Right Side: Classification ===
        self.classification_group = QGroupBox("Step 2: Image Classification")
        class_layout = QVBoxLayout(self.classification_group)
        self.classification_window = ClassificationWindow(self.config, self.logger)
        class_layout.addWidget(self.classification_window)
        splitter.addWidget(self.classification_group)

        # Set initial sizes to be equal (50/50)
        splitter.setSizes([500, 500])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        layout.addWidget(splitter)
        self.setLayout(layout)

        # Proxy signals
        self.classification_window.add_model_requested.connect(self.on_add_model_requested)

    # We need a custom signal to forward this up to MainApp if we want to keep the same architecture
    # But MainApp expects the direct widget to have the signal. 
    # Since SplitProcessingWindow is now the tab, we should define the signal here.
    from PyQt5.QtCore import pyqtSignal
    add_model_requested = pyqtSignal()

    def on_add_model_requested(self):
        self.add_model_requested.emit()
