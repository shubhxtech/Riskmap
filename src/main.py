import sys, time, os, platform

# --- CONFIGURATION ---
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["TORCH_ALLOW_DIRECT_IMPORT"] = "1"  # Suppress CVE-2025-32434 warning

# --- Launch App ---

try:
    import torch
    print(f"✓ Torch pre-loaded successfully: {torch.__version__}")
except ImportError as e:
    print(f"Warning: Could not pre-load torch: {e}")
except Exception as e:
    print(f"Warning: Error pre-loading torch: {e}")

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QTextEdit, QLabel, QPushButton, QScrollArea, QGroupBox,
    QMessageBox, QCheckBox, QLineEdit, QHBoxLayout,  QGridLayout, QDialog
)
from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect, QEasingCurve, QSize
from utils import resolve_path

## We need to download PyQT and PyQt5.QtWebEngineWidgets seperately

# --- Setup Logging ---
from app_logger import Logger
logger = Logger(__name__)
logger.log_status("Starting App")

# --- Configuration ---
# Ensure icons exist
def ensure_icons():
    import qtawesome as qta
    from PyQt5.QtCore import QSize
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    assets_path = os.path.join(base_path, "assets", "icons")
    
    if not os.path.exists(assets_path):
        os.makedirs(assets_path)
    
    down_path = os.path.join(assets_path, "arrow_down.png")
    up_path = os.path.join(assets_path, "arrow_up.png")
    
    # Generate if missing
    if not os.path.exists(down_path):
        processed = False
        try:
            # We need a QApplication instance before qtawesome can work fully sometimes
            # But main usually has one created later. 
            # We will convert qta icons to images. 
            # Note: qtawesome needs a QApp instance for some font loading.
            pass 
        except:
            pass

# We will call the actual generation inside MainApp or after App creation

from config_ import Config  # Custom config module
config = Config(logger, resolve_path("config_.ini"))
logger.log_status(resolve_path("config_.ini"))


# --- Check if map index exists ---
if not config.get_map_index_path().exists():
    import map_index_maker
    map_index_maker.create_index()

### Create a pop-up that allows you to select which models you want to download.

# --- Import refactored Qt versions of feature windows ---
a = time.time()
from api_window import ApiWindow
# from classification import ClassificationWindow (loaded by SplitProcessingWindow)
# from duplicates import DuplicatesWindow  (loaded by SplitProcessingWindow)
from model_training import Trainer
from rapid_scan_window import RapidScanWindow
from results_window import ResultsWindow
logger.log_status(f'Time taken to import modules: {time.time()-a}.')

logger.log_status('Modules imported. Starting Main App')

from styles import DARK_THEME, LIGHT_THEME, BRAND_THEME

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        name_stats = config.get_general_data()
        self.setWindowTitle(name_stats["name_of_main_app"])
        self.center_window()

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)

        # Generate Icons for Dropdown (One-time check)
        self.generate_dropdown_icons()








        # Main Tabs (Notebook equivalent)
        self.tabs = QTabWidget()
        # Left-align tabs and prevent text clipping
        tab_bar = self.tabs.tabBar()
        tab_bar.setExpanding(False)         # Don't stretch tabs to fill width → keeps them left-aligned
        tab_bar.setElideMode(Qt.ElideNone)  # Don't truncate tab text with "..."

        logger.log_status('Adding widgets')

        # Add tabs with Qt-based UI and threaded processing
        # Add tabs with Qt-based UI and threaded processing
        self.add_tab(ApiWindow, name_stats["name_of_api_window"])
        
        # Unified Processing Tab (Merges Crop & Detection)
        from unified_processing import UnifiedProcessingWindow
        self.add_tab(UnifiedProcessingWindow, "Image Processing")
        
        self.add_tab(Trainer, name_stats["name_of_training_window"])
        from split_processing_window import SplitProcessingWindow
        # Add Unified Split Tab
        split_tab = self.add_tab(SplitProcessingWindow, "Analyze & Filter")
        split_tab.add_model_requested.connect(self.add_model_form)
        
        # ── Results: image classification viewer ──────
        self.add_tab(ResultsWindow, "Results")

        # ── Risk Assessment: real-time video detection + seismic risk ──
        self.add_tab(RapidScanWindow, "Risk Assessment")
        
        layout.addWidget(self.tabs, 7)


    def center_window(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def show_geoscatter(self):
        from geoscatter import GeoAnalysis
        geoscatter_path = resolve_path('Scatter')
        Geo = GeoAnalysis(config, logger)
        Geo.geoscatter(geoscatter_path)
        window = QDialog(self)
        window.setWindowTitle("Image Viewer")

        # Create layout and label
        layout = QVBoxLayout()
        label = QLabel(window)
        layout.addWidget(label)

        # Load and set image
        img_path = os.path.join(geoscatter_path, "geoscatter_plot.png") 
        pixmap = QPixmap(img_path) 
        label.setPixmap(pixmap)
        label.setScaledContents(True)  # Makes the image scale to label size

        window.setLayout(layout)
        window.resize(pixmap.width(), pixmap.height())
        global a
        print(time.time()-a)
        window.exec_()

    def add_tab(self, WindowClass, label):
        # Each window class builds its own UI in the passed layout
        wrapper_widget = WindowClass(config=config, logger=logger)
        self.tabs.addTab(wrapper_widget, label)
        return wrapper_widget

    def show_logs(self):
        log_window = QWidget(self)
        log_window.setWindowTitle("Logs")
        log_window.resize(800, 600)
        layout = QVBoxLayout(log_window)

        text_edit = QTextEdit()
        try:
            with open(config.get_log_file(), "r") as f:
                text_edit.setPlainText(f.read())
        except Exception as e:
            text_edit.setPlainText(f"Error loading log: {e}")

        close_button = QPushButton("Close")
        close_button.clicked.connect(log_window.close)

        layout.addWidget(text_edit)
        layout.addWidget(close_button)
        log_window.show()
            
    def add_model_form(self):
        class AddModelDialog(QDialog):
            def __init__(dialog_self):
                super().__init__(self)  
                dialog_self.setWindowTitle("Add a new model to classify images")
                dialog_self.resize(800, 200)

                model_path_str = str(config.get_model_save_folder())
                model_url_str, model_name_str = "", ""
                target_classes_str = str(config.get_target_classes())

                # Widgets
                model_path_label = QLabel("Model Path:")
                model_path_entry = QLineEdit(model_path_str)
                model_path_entry.setDisabled(True)

                model_path_check = QCheckBox("Do you want to change the model's path?")
                model_path_check.stateChanged.connect(
                    lambda: model_path_entry.setEnabled(model_path_check.isChecked())
                )

                model_url_label = QLabel("Model URL:")
                model_url_entry = QLineEdit(model_url_str)

                model_name_label = QLabel("Model Name:")
                model_name_entry = QLineEdit(model_name_str)

                target_classes_label = QLabel("Target Classes:")
                target_classes_entry = QLineEdit(target_classes_str)
                target_classes_entry.setDisabled(True)

                class_names_check = QCheckBox("Do you want to change or add class names?")
                class_names_check.stateChanged.connect(
                    lambda: target_classes_entry.setEnabled(class_names_check.isChecked())
                )

                submit_button = QPushButton("Submit")
                submit_button.clicked.connect(lambda: dialog_self.submit(
                    model_url_entry, model_name_entry, target_classes_entry
                ))

                # Layout
                layout = QGridLayout()
                layout.addWidget(model_path_label, 0, 0)
                layout.addWidget(model_path_entry, 0, 1)

                layout.addWidget(model_url_label, 1, 0)
                layout.addWidget(model_url_entry, 1, 1, 1, 2)

                layout.addWidget(model_name_label, 2, 0)
                layout.addWidget(model_name_entry, 2, 1, 1, 2)

                layout.addWidget(target_classes_label, 3, 0)
                layout.addWidget(target_classes_entry, 3, 1)
                layout.addWidget(class_names_check, 3, 3)

                layout.addWidget(submit_button, 4, 1)

                layout.setColumnStretch(1, 1)
                dialog_self.setLayout(layout)

            def submit(dialog_self, model_url_entry, model_name_entry, target_classes_entry):
                Model_URL =  model_url_entry.text()
                Model_Name = model_name_entry.text()
                Target_Classes =  target_classes_entry.text()
                Target_Classes = Target_Classes[1:-1].split(',')
                Target_Classes = [str(i) for i in Target_Classes]
                data = {
                    Model_Name: {
                        'url': Model_URL, 
                        'classes': tuple(Target_Classes)
                        }
                    }
                config.set_model_data(data)
                dialog_self.accept()  # Close dialog with success

        # Show dialog
        dialog = AddModelDialog()
        dialog.exec_()  # Model dialog – blocks main window until closed
        

    
    def show_config(root, config: Config):
        # Create a dialog window as the settings panel
        window = QDialog(root)
        window.setObjectName("settings")
        window.resize(800, 800)

        # Set up a scrollable area
        scroll_area = QScrollArea(window)
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)

        # Main layout for the dialog
        main_layout = QVBoxLayout(window)
        main_layout.addWidget(scroll_area)

        entry_fields = {}

        # Read the config and populate fields
        config_data = config.read_config()
        for i, section in enumerate(config_data.sections()):
            # Group box for each section
            group = QGroupBox(section, scroll_content)
            group_layout = QGridLayout(group)

            # Populate each option/value pair
            for j, (option, value) in enumerate(config.get_all(section).items()):
                lbl = QLabel(option, group)
                entry = QLineEdit(group)
                entry.setText(value)
                # Optionally you can store entry references if you need to retrieve data later:
                # entry.setObjectName(f"{section}.{option}")
                group_layout.addWidget(lbl, j, 0)
                group_layout.addWidget(entry, j, 1)

                entry_fields[(section, option)] = entry

            scroll_layout.addWidget(group)
        
        save_button = QPushButton("Save", window)

        def save_changes():
            for (section, option), entry in entry_fields.items():
                config.parser.set(section, option, entry.text())
            config.save_config()
            QMessageBox.information(window, "Success", "Configuration saved successfully!")

        save_button.clicked.connect(save_changes)
        main_layout.addWidget(save_button)

        window.setLayout(main_layout)
        window.exec_()


    def generate_dropdown_icons(self):
        try:
            import qtawesome as qta
            from PyQt5.QtCore import QSize
            base_path = os.path.dirname(os.path.abspath(__file__))
            assets_path = os.path.join(base_path, "assets", "icons")
            if not os.path.exists(assets_path):
                os.makedirs(assets_path)
            
            down_path = os.path.join(assets_path, "arrow_down.png")
            if not os.path.exists(down_path):
                qta.icon('fa5s.chevron-down', color='#5f6368').pixmap(QSize(16, 16)).save(down_path)
                
            up_path = os.path.join(assets_path, "arrow_up.png")
            if not os.path.exists(up_path):
                qta.icon('fa5s.chevron-up', color='#1DA1F2').pixmap(QSize(16, 16)).save(up_path)
        except Exception as e:
            logger.log_error(f"Failed to generate icons: {e}")

# --- Launch App ---
if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    
    app = QApplication(sys.argv)
    
    # Resolve icon path for stylesheet
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icons_dir = os.path.join(base_dir, "assets", "icons").replace("\\", "/")
    
    # Inject path into theme
    theme_with_icons = BRAND_THEME.replace("%ICON_PATH%", icons_dir)
    app.setStyleSheet(theme_with_icons)
    
    # Cross-platform font selection
    if sys.platform == 'darwin':
        font = QFont("Helvetica Neue", 14)
    else:
        font = QFont("Segoe UI", 14)
    app.setFont(font)

    icon_path = os.path.join(os.path.dirname(__file__), "app.ico")
    window = MainApp()
    window.showMaximized()
    print(time.time()-a)
    app.setWindowIcon(QIcon(icon_path))
    sys.exit(app.exec_())
