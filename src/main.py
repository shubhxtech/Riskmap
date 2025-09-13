import sys, time, os
sys.path.append(os.path.dirname(__file__))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QTextEdit, QLabel, QPushButton, QScrollArea, QGroupBox,
    QMessageBox, QCheckBox, QLineEdit, QHBoxLayout,  QGridLayout, QDialog
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect
from utils import resolve_path

## We need to download PyQT and PyQt5.QtWebEngineWidgets seperately

# --- Setup Logging ---
from AppLogger import Logger
logger = Logger(__name__)
logger.log_status("Starting App")

# --- Configuration ---
from config_ import Config  # Custom config module
config = Config(logger, resolve_path("config_.ini"))
logger.log_status(resolve_path("config_.ini"))
# --- Model Download ---
from model_download import download_model
from pathlib import Path

# --- Check model path ---
if not config.get_model_save_folder().exists():
    download_model(logger, config) #Downloading faster_rcnn as default

# --- Check if map index exists ---
if not config.get_map_index_path().exists():
    import map_index_maker
    map_index_maker.create_index()

### Create a pop-up that allows you to select which models you want to download.

# --- Import refactored Qt versions of feature windows ---
a = time.time()
from ApiWindow import ApiWindow
from CropStreetWindow import CropWindow 
from BuildingDetectionWindow import BuildingDetectionWindow
from Classification import ClassificationWindow
from Duplicates_Better import DuplicatesWindow
from model_training import Trainer
logger.log_status(f'Time taken to import modules: {time.time()-a}.')

logger.log_status('Modules imported. Starting Main App')


class OverlaySidebar(QWidget):
    def __init__(self, parent=None, config=None, callback_refs=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet("background-color: #FFFFFF; color: black;")
        self.setGeometry(-200, 0, 200, parent.height())  # Start off-screen
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setLayout(layout)

        self.config = config

        # Unpack callback references
        self.show_logs = callback_refs.get("show_logs")
        self.show_config = callback_refs.get("show_config")
        self.add_model_form = callback_refs.get("add_model_form")
        self.show_geoscatter = callback_refs.get("show_geoscatter")

        logs_button = QPushButton("Show Logs")
        logs_button.clicked.connect(self.show_logs)
        layout.addWidget(logs_button)

        show_settings_button = QPushButton("Show Config")
        show_settings_button.clicked.connect(lambda: self.show_config(config=self.config))
        layout.addWidget(show_settings_button)

        add_model_button = QPushButton("Add New Model")
        add_model_button.clicked.connect(self.add_model_form)
        layout.addWidget(add_model_button)

        show_geoscatter_button = QPushButton("Show Geoscatter")
        show_geoscatter_button.clicked.connect(self.show_geoscatter)
        layout.addWidget(show_geoscatter_button)



    def slide_in(self):
        self.show()
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(300)
        anim.setStartValue(QRect(-200, 0, 200, self.height()))
        anim.setEndValue(QRect(0, 0, 200, self.height()))
        anim.start()
        self.anim = anim

    def slide_out(self):
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(300)
        anim.setStartValue(QRect(0, 0, 200, self.height()))
        anim.setEndValue(QRect(-200, 0, 200, self.height()))
        anim.finished.connect(self.hide)
        anim.start()
        self.anim = anim



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


        logger.log_status('Setting up topbar')
        # TopBar
        topbar = QHBoxLayout()
        self.burger_button = QPushButton("☰")
        self.burger_button.setFixedSize(40, 40)
        self.burger_button.clicked.connect(self.toggle_sidebar)
        topbar.addWidget(self.burger_button, alignment=Qt.AlignLeft)
        topbar.addStretch()

        layout.addLayout(topbar)


        # Main Tabs (Notebook equivalent)
        self.tabs = QTabWidget()

        logger.log_status('Adding widgets')

        # Add tabs with Qt-based UI and threaded processing
        self.add_tab(ApiWindow, name_stats["name_of_api_window"])
        self.add_tab(CropWindow, name_stats["name_of_crop_window"])
        self.add_tab(BuildingDetectionWindow, name_stats["name_of_building_detection"])
        self.add_tab(Trainer, name_stats["name_of_training_window"])
        self.add_tab(DuplicatesWindow, name_stats["name_of_duplicates_window"])
        self.add_tab(ClassificationWindow, name_stats["name_of_classification"])
        layout.addWidget(self.tabs, 7)
        # Sidebar overlay
        self.sidebar_open = False
        self.sidebar = OverlaySidebar(
            parent=self,
            config=config,
            callback_refs={
                "show_logs": self.show_logs,
                "show_config": self.show_config,
                "add_model_form": self.add_model_form,
                "show_geoscatter": self.show_geoscatter,
            },
        )
        self.sidebar.hide()

    def toggle_sidebar(self):
        if self.sidebar_open:
            self.sidebar.slide_out()
        else:
            self.sidebar.slide_in()
        self.sidebar_open = not self.sidebar_open

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


# --- Launch App ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainApp()
    window.showMaximized()
    print(time.time()-a)
    sys.exit(app.exec_())
