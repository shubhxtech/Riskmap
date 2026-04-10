from PyQt5 import QtWidgets, QtCore, QtGui
from pathlib import Path
from config_ import Config
from AppLogger import Logger
from BuildingDetection import ObjectDetectionProcessor
from model_download import download_model
from utils import cleanup_process
import time
import requests
import tarfile
import shutil
import os

class _DetectionWorker(QtCore.QThread):
    progress_done = QtCore.pyqtSignal()
    # These attributes will be connected by the parent at runtime:
    progress_changed = QtCore.pyqtSignal(float)
    log_message = QtCore.pyqtSignal(str)
    image_saved = QtCore.pyqtSignal(str)
    visualization_data_ready = QtCore.pyqtSignal(str, list)

    def __init__(self, processor: ObjectDetectionProcessor, remove_after: bool):
        super().__init__()
        self.processor = processor
        self.remove_after = remove_after

        # Connect processor signals (forward to UI):
        self.processor.progress_updated.connect(self._emit_progress)
        self.processor.log_message.connect(self._emit_log)
        self.processor.image_saved.connect(self._emit_image_saved)
        self.processor.visualization_data_ready.connect(self._emit_visualization)

    def _emit_progress(self, pct: float):
        self.progress_changed.emit(pct)

    def _emit_log(self, msg: str):
        self.log_message.emit(msg)

    def _emit_image_saved(self, path: str):
        self.image_saved.emit(path)

    def _emit_visualization(self, image_path: str, detections: list):
        self.visualization_data_ready.emit(image_path, detections)

    def run(self):
        self.processor.process()
        if self.remove_after:
            cleanup_process(True, self.processor.input_dir)
        self.progress_done.emit()


class DetectionVisualizer(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QtGui.QBrush(QtCore.Qt.white)) # White background
        
        # Add placeholder text
        self.placeholder = self.scene.addText("Waiting for detection data...", QtGui.QFont("Arial", 14))
        self.placeholder.setDefaultTextColor(QtGui.QColor(50, 50, 50)) # Dark text
        self._center_placeholder()
        
        self.last_update_time = 0
        self.min_update_interval = 0.5 

        # Palette for multiple boxes
        self.colors = [
            QtGui.QColor(255, 0, 0),    # Red
            QtGui.QColor(0, 180, 0),    # Green 
            QtGui.QColor(0, 0, 255),    # Blue
            QtGui.QColor(255, 0, 255),  # Magenta
            QtGui.QColor(0, 200, 200),  # Cyan
            QtGui.QColor(255, 128, 0),  # Orange
            QtGui.QColor(128, 0, 128),  # Purple
            QtGui.QColor(0, 0, 0)       # Black
        ]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_placeholder()
        self.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def _center_placeholder(self):
        if self.placeholder:
            pass 

    def update_visualization(self, image_path, detections):
        """
        image_path: str 
        detections: list of dicts {'box': [ymin, xmin, ymax, xmax], 'class': str/bytes, ...}
        """
        current_time = time.time()
        if current_time - self.last_update_time < self.min_update_interval:
            return 
        
        self.last_update_time = current_time
        
        self.scene.clear()
        self.placeholder = None 
        
        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            return
            
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QtCore.QRectF(pixmap.rect()))
        
        width = pixmap.width()
        height = pixmap.height()
        
        text_font = QtGui.QFont("Arial", 10, QtGui.QFont.Bold)

        # Count text
        count_text = self.scene.addText(f"Detections: {len(detections)}", QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        count_text.setDefaultTextColor(QtCore.Qt.white)
        # Background for count text
        bg_rect = self.scene.addRect(count_text.boundingRect(), brush=QtGui.QBrush(QtGui.QColor(0, 0, 0, 150)))
        bg_rect.setZValue(1) # Above image
        count_text.setZValue(2)
        count_text.setPos(10, 10)
        bg_rect.setPos(10, 10)

        for i, det in enumerate(detections):
            # Select distinct color
            base_color = self.colors[i % len(self.colors)]
            
            pen = QtGui.QPen(base_color)
            pen.setWidth(4)
            # Semi-transparent fill of same color
            fill_color = QtGui.QColor(base_color)
            fill_color.setAlpha(40) # 40/255 opacity
            brush = QtGui.QBrush(fill_color)
            
            box = det['box']
            ymin, xmin, ymax, xmax = box
            
            x = xmin * width
            y = ymin * height
            w = (xmax - xmin) * width
            h = (ymax - ymin) * height
            
            rect_item = QtWidgets.QGraphicsRectItem(x, y, w, h)
            rect_item.setPen(pen)
            rect_item.setBrush(brush)
            self.scene.addItem(rect_item)
            
            # Label
            cls_name = det.get('class', b'Unknown')
            if isinstance(cls_name, bytes):
                cls_name = cls_name.decode('utf-8', errors='ignore')
            
            label_text = f"{cls_name} {i+1}"
            text_item = QtWidgets.QGraphicsTextItem(label_text)
            text_item.setFont(text_font)
            text_item.setDefaultTextColor(QtCore.Qt.white)
            
            # Background rect for text
            text_bg = QtWidgets.QGraphicsRectItem(text_item.boundingRect())
            text_bg.setBrush(QtGui.QBrush(base_color))
            # No border for text background
            text_bg.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            
            # Position above box
            text_pos_x = x
            text_pos_y = y - text_item.boundingRect().height()
            if text_pos_y < 0: # If box is at top edge, put label inside
                text_pos_y = y
                
            text_item.setPos(text_pos_x, text_pos_y)
            text_bg.setPos(text_pos_x, text_pos_y)
            
            self.scene.addItem(text_bg)
            self.scene.addItem(text_item)
            
        self.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)


class _DetectionTimer(QtCore.QThread):
    time_updated = QtCore.pyqtSignal(str)
    time_logged = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.elapsed_seconds = 0

    def run(self):
        while self.running:
            time.sleep(1)
            self.elapsed_seconds += 1
            self.time_updated.emit(f"Elapsed Time: {self.elapsed_seconds:.2f} sec")

    def stop(self):
        self.running = False
        self.time_logged.emit(f"Total elapsed time: {self.elapsed_seconds:.2f} sec")


class ModelDownloadWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int) # This might not be used by download_model but kept for interface
    log = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(str)  
    error = QtCore.pyqtSignal(str)

    def __init__(self, config, logger):
        super().__init__()
        self.config = config
        self.logger = logger

    def run(self):
        try:
            # download_model relies on config paths.
            # It downloads to config.get_model_save_folder().
            self.log.emit("Starting download via model_download module...")
            download_model(self.logger, self.config, model_name='faster_rcnn')
            
            # After download, we figure out where it went
            model_dir = self.config.get_model_save_folder()
            
            # Use 'resolve_path' logic or check typical subfolders
            # TF Hub models unzip generic variables/saved_model files. 
            # If download_model extracts to MODEL_DIR, then MODEL_DIR is the model path.
            # Let's verify if saved_model.pb is there
            if os.path.exists(os.path.join(model_dir, "saved_model.pb")):
                self.finished.emit(str(model_dir))
            else:
                self.finished.emit(str(model_dir)) # Fallback

        except Exception as e:
            self.error.emit(str(e))


class BuildingDetectionWindow(QtWidgets.QWidget):
    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.logger = logger
        self.config = config
        self.processor: ObjectDetectionProcessor | None = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Building Detection")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # === 1) Input Folder Selection ===
        folder_layout = QtWidgets.QHBoxLayout()
        folder_layout.setSpacing(10)
        self.folder_btn = QtWidgets.QPushButton("Select Input Folder")
        self.folder_label = QtWidgets.QLabel(str(self.config.get_bd_input_dir()))
        self.folder_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        folder_layout.addWidget(self.folder_btn)
        folder_layout.addWidget(self.folder_label, 1)  # stretch=1 to fill space
        layout.addLayout(folder_layout)

        # === 2) Hyperparameter Controls ===
        params_box = QtWidgets.QGroupBox("Detection Hyperparameters")
        params_layout = QtWidgets.QFormLayout(params_box)
        params_layout.setLabelAlignment(QtCore.Qt.AlignLeft)  # Left-align labels (macOS defaults to right)
        params_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)  # Fields expand to fill width
        params_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)  # Align form content left

        # 2.1 Model Path
        # 2.1 Model Selection
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(["Select Model...", "Faster R-CNN (Open Images)", "Custom Path..."])
        # Check if current config path matches default Faster R-CNN path or is custom
        current_path = str(self.config.get_bd_model_path())
        default_model_dir = str(self.config.get_model_save_folder())
        
        # Simple heuristic to set initial index
        if "faster_rcnn" in current_path or current_path == default_model_dir:
             self.model_combo.setCurrentIndex(1)
        elif current_path and current_path != ".":
             self.model_combo.setCurrentText("Custom Path...")
        else:
             self.model_combo.setCurrentIndex(0)

        self.model_combo.currentIndexChanged.connect(self.on_model_combo_changed)
        params_layout.addRow("Model:", self.model_combo)

        # Hidden label to show selected custom path or status
        self.model_status_label = QtWidgets.QLabel(current_path if len(current_path) > 3 else "No model selected")
        self.model_status_label.setStyleSheet("color: gray; font-size: 10px;")
        params_layout.addRow("", self.model_status_label)

        # 2.2 Target Classes
        classes_str = ",".join(self.config.get_bd_target_classes())
        self.target_classes_edit = QtWidgets.QLineEdit(classes_str)
        self.target_classes_edit.setToolTip("Enter comma-separated class names, e.g. House,Building,Skyscraper,Tower")
        params_layout.addRow("Target Classes:", self.target_classes_edit)

        # 2.3 Output Directory
        self.output_dir_edit = QtWidgets.QLineEdit(str(self.config.get_bd_output_dir()))
        self.output_browse_btn = QtWidgets.QPushButton("Browse Output...")
        output_path_layout = QtWidgets.QHBoxLayout()
        output_path_layout.addWidget(self.output_dir_edit)
        output_path_layout.addWidget(self.output_browse_btn)
        params_layout.addRow("Output Dir:", output_path_layout)

        # 2.4 Threshold
        self.threshold_spin = QtWidgets.QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setValue(self.config.get_bd_threshold())
        params_layout.addRow("Threshold:", self.threshold_spin)

        # 2.5 Expand Factor
        self.expand_spin = QtWidgets.QDoubleSpinBox()
        self.expand_spin.setRange(0.0, 1.0)
        self.expand_spin.setDecimals(2)
        self.expand_spin.setSingleStep(0.01)
        self.expand_spin.setValue(self.config.get_bd_expand_factor())
        params_layout.addRow("Expand Factor:", self.expand_spin)

        # 2.6 Min Dimension
        self.min_dim_spin = QtWidgets.QSpinBox()
        self.min_dim_spin.setRange(1, 5000)
        self.min_dim_spin.setSingleStep(1)
        self.min_dim_spin.setValue(self.config.get_bd_min_dim())
        params_layout.addRow("Min Dimension:", self.min_dim_spin)

        layout.addWidget(params_box)

        # === 3) Buttons: Reset & Process ===
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        self.reset_button = QtWidgets.QPushButton("Reset to Defaults")
        self.remove_checkbox = QtWidgets.QCheckBox("Remove input folder after processing")
        self.process_button = QtWidgets.QPushButton("Detect buildings")
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        
        # Add new download model button (REMOVED as per request)
        # self.download_model_btn = QtWidgets.QPushButton("Download Faster R-CNN")
        # self.download_model_btn.clicked.connect(self.download_faster_rcnn)
        # button_layout.addWidget(self.download_model_btn)
        
        button_layout.addWidget(self.remove_checkbox)
        button_layout.addWidget(self.process_button)
        layout.addLayout(button_layout)

        # === 4) Progress + Timer ===
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QtWidgets.QLabel("0.00%")
        self.timer_label = QtWidgets.QLabel("Elapsed Time: 0.00 sec")

        progress_layout = QtWidgets.QHBoxLayout()
        progress_layout.setSpacing(10)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.timer_label)
        layout.addLayout(progress_layout)

        # === 5) Visualization Only ===
        self.visualizer = DetectionVisualizer()
        layout.addWidget(self.visualizer)

        # === 6) Signal Connections ===
        self.folder_btn.clicked.connect(self.choose_input_folder)
        # self.model_browse_btn.clicked.connect(self.choose_model_dir) # Removed
        self.output_browse_btn.clicked.connect(self.choose_output_folder)

        self.reset_button.clicked.connect(self.reset_to_defaults)
        self.process_button.clicked.connect(self.on_process_clicked)

        # Re-validate whenever relevant fields change
        # self.model_path_edit.textChanged.connect(self._update_process_button_state) # Removed
        self.target_classes_edit.textChanged.connect(self._update_process_button_state)
        self.output_dir_edit.textChanged.connect(self._update_process_button_state)

        # Initial validation
        self._update_process_button_state()

    def _update_process_button_state(self):
        """
        Enable “Detect buildings” only if:
         - model_path exists and is a directory,
         - target_classes is non-empty,
         - output_dir exists and is a directory.
        Provide tooltips to indicate invalid fields.
        """
        valid = True
        self.logger.log_status("Starting update of process button")
        # Validate model_path (via Config now, as UI widget is Combo)
        model_path_str = str(self.config.get_bd_model_path())
        if not model_path_str or model_path_str == "." or len(model_path_str) < 3:
             self.process_button.setToolTip("Please select a valid model.")
             valid = False
        else:
            p = Path(model_path_str)
            # self.logger.log_status(f"Checking path {p}")
            if (not p.exists()) or (not p.is_dir()):
                # Only invalid if it's not the "Select Model..." placeholder state
                if self.model_combo.currentIndex() != 0: 
                     self.process_button.setToolTip("Model path does not exist.")
                valid = False
            else:
                 if valid:
                     self.process_button.setToolTip("Model Path valid")

        # Validate target_classes
        tc = self.target_classes_edit.text().strip()
        if not tc:
            self.process_button.setToolTip("Target classes cannot be empty.")
            valid = False
        else:
            # Ensure there is at least one non-empty class name
            classes_list = [c.strip() for c in tc.split(",") if c.strip()]
            if not classes_list:
                self.process_button.setToolTip("Enter at least one class name, separated by commas.")
                valid = False
            else:
                if valid:
                    self.process_button.setToolTip("Class names present")

        # Validate output_dir
        output_str = self.output_dir_edit.text().strip()
        if not output_str:
            self.process_button.setToolTip("Output directory cannot be empty.")
            valid = False
        else:
            out_p = Path(output_str)
            if (not out_p.exists()) or (not out_p.is_dir()):
                self.process_button.setToolTip("Output must point to an existing directory.")
                valid = False
            else:
                if valid:
                    self.process_button.setToolTip("Output points to an existing directory")

        # Optionally validate input_dir too (uncomment if required):
        input_str = self.folder_label.text().strip()
        in_p = Path(input_str)
        if not in_p.exists() or not in_p.is_dir():
            self.process_button.setToolTip("Input folder must exist.")
            valid = False
        else:
            if valid:
                self.process_button.setToolTip("input folder exists")
            
        if valid:
            self.process_button.setToolTip("Detect buildings with the press of this button")
        self.process_button.setEnabled(valid)

    def choose_input_folder(self):
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Input Folder",
            str(self.config.get_bd_input_dir()),
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            self.folder_label.setText(folder)
            self.config.set_input_folder_detection(folder)
            # You could also re‐validate here if you enforce input_dir validity
            self._update_process_button_state()

    def choose_model_dir(self):
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Model Directory",
            str(self.config.get_bd_model_path()),
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            # self.model_path_edit.setText(folder)
            self.model_status_label.setText(folder)
            self.config.set_model_path(folder)
            self._update_process_button_state()
        else:
            # If user cancels, revert to index 0?
            # Or keep previous? Let's just do nothing if they verify 'Cancel'
            pass

    def choose_output_folder(self):
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            str(self.config.get_bd_output_dir()),
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            self.output_dir_edit.setText(folder)
            self.config.set_output_detection_path(folder)

    def reset_to_defaults(self):
        """
        Pull recommended/default values from config.get_BUILDING_DETECTION_recommended(),
        update all six widgets, and write them back to the .ini so future launches use them.
        """
        rec = self.config.get_BUILDING_DETECTION_recommended()

        # 1) Update the UI widgets
        # self.model_path_edit.setText(rec["model_path"]) # No longer existing
        self.model_combo.setCurrentIndex(1) # Default to Faster R-CNN
        self.target_classes_edit.setText(rec["target_classes"])
        self.output_dir_edit.setText(rec["output_dir"])
        self.threshold_spin.setValue(float(rec["threshold"]))
        self.expand_spin.setValue(float(rec["expand_factor"]))
        self.min_dim_spin.setValue(int(rec["min_dim"]))

        # You may also want to update the folder_label if you reset input_dir:
        self.folder_label.setText(rec["input_dir"])

        # 2) Write them back to config_.ini immediately
        self.config.set_model_path(rec["model_path"])
        self.config.set_BUILDING_DETECTION_param("target_classes", rec["target_classes"])
        self.config.set_output_detection_path(rec["output_dir"])
        self.config.set_BUILDING_DETECTION_param("threshold", rec["threshold"])
        self.config.set_BUILDING_DETECTION_param("expand_factor", rec["expand_factor"])
        self.config.set_BUILDING_DETECTION_param("min_dim", rec["min_dim"])
        self.config.set_input_folder_detection(rec["input_dir"])

        # 3) Re‐validate to update tooltips and button state
        self._update_process_button_state()

        self.log_to_output("Reset all hyperparameters to recommended defaults.")

    def download_faster_rcnn(self):
        # We use the existing model_download module which fetches the Open Images based model
        # defined in config_.py (via model_data.json).
        # It downloads to whatever config.get_model_save_folder() points to.
        
        current_model_path = self.config.get_bd_model_path()
        if os.path.exists(os.path.join(current_model_path, "saved_model.pb")):
             reply = QtWidgets.QMessageBox.question(
                self, "Model Exists", 
                f"Model seems to exist at:\n{current_model_path}\n\nDownload again (overwrite)?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
             if reply == QtWidgets.QMessageBox.No:
                 return

        # self.download_model_btn.setEnabled(False) # Removed button
        self.log_to_output("Starting download of Faster R-CNN (Open Images)...")
        
        # Dialog to show it's happening
        self.download_dialog = QtWidgets.QProgressDialog("Downloading Faster R-CNN Model...", "Cancel", 0, 0, self)
        self.download_dialog.setWindowModality(QtCore.Qt.WindowModal)
        self.download_dialog.show()

        # Worker uses config and logger to call download_model()
        self.dl_worker = ModelDownloadWorker(self.config, self.logger)
        self.dl_worker.progress.connect(self.update_progress)
        self.dl_worker.log.connect(self.log_to_output)
        self.dl_worker.finished.connect(self.on_download_finished)
        self.dl_worker.error.connect(self.on_download_error)
        self.dl_worker.start()

    def on_model_combo_changed(self, index):
        if index == 1: # Faster R-CNN
            # Check if model exists
            default_save = self.config.get_model_save_folder()
            # If default save folder has the model file
            if os.path.exists(os.path.join(default_save, "saved_model.pb")):
                 self.config.set_model_path(str(default_save))
                 self.model_status_label.setText(str(default_save))
                 self._update_process_button_state()
            else:
                 # Download
                 self.download_faster_rcnn()
        
        elif index == 2: # Custom Path
             self.choose_model_dir()
        
        else:
             self.config.set_model_path("")
             self.model_status_label.setText("No model selected")
             self._update_process_button_state()

    def on_download_finished(self, model_path):
        # self.download_model_btn.setEnabled(True)
        if hasattr(self, 'download_dialog'):
            self.download_dialog.close()
            
        self.log_to_output(f"Model download complete at: {model_path}")
        # self.model_path_edit.setText(model_path) # Removed
        self.model_status_label.setText(str(model_path))
        # config is already updated by virtue of model_download using it? 
        # No, model_download READS from config. 
        # But we should ensure the UI reflects the path.
        self.config.set_model_path(model_path)
        self._update_process_button_state()
        QtWidgets.QMessageBox.information(self, "Download Complete", "Faster R-CNN (Open Images) model is ready.")

    def on_download_error(self, error_msg):
        # self.download_model_btn.setEnabled(True)
        if hasattr(self, 'download_dialog'):
            self.download_dialog.close()
        # Reset combo to select model
        self.model_combo.setCurrentIndex(0)
        self.log_to_output(f"Download Error: {error_msg}")
        QtWidgets.QMessageBox.critical(self, "Download Failed", f"An error occurred:\n{error_msg}")

    def on_process_clicked(self):
        """
        When “Detect buildings” is clicked:
        1. Gather all six values,
        2. Write them to config_.ini,
        3. Instantiate a new processor, hook signals, start threads.
        """
        # model_path_val = self.model_path_edit.text().strip() # Removed
        model_path_val = str(self.config.get_bd_model_path())
        target_classes_val = self.target_classes_edit.text().strip()
        output_dir_val = self.output_dir_edit.text().strip()
        threshold_val = f"{self.threshold_spin.value():.2f}"
        expand_val = f"{self.expand_spin.value():.2f}"
        min_dim_val = str(self.min_dim_spin.value())

        # Write back to config
        # Write back to config
        self.config.set_model_path(model_path_val)
        self.config.set_BUILDING_DETECTION_param("target_classes", target_classes_val)
        self.config.set_output_detection_path(output_dir_val)
        self.config.set_BUILDING_DETECTION_param("threshold", threshold_val)
        self.config.set_BUILDING_DETECTION_param("expand_factor", expand_val)
        self.config.set_BUILDING_DETECTION_param("min_dim", min_dim_val)
    
        # Instantiate processor with up‐to‐date config
        self.processor = ObjectDetectionProcessor(self.config, self.logger)

        # Connect processor→UI signals
        self.processor.progress_updated.connect(self.update_progress)
        self.processor.log_message.connect(self.log_to_output)
        self.processor.image_saved.connect(self.log_to_output)

        # Disable “Detect buildings” while running
        self.process_button.setEnabled(False)

        # Start timer thread
        self.timer_thread = _DetectionTimer()
        self.timer_thread.time_updated.connect(self.timer_label.setText)
        self.timer_thread.time_logged.connect(self.logger.log_status)
        self.timer_thread.start()

        # Start worker thread
        self.worker = _DetectionWorker(
            processor=self.processor,
            remove_after=self.remove_checkbox.isChecked()
        )
        self.worker.progress_changed.connect(self.update_progress)
        self.worker.log_message.connect(self.log_to_output)
        self.worker.image_saved.connect(self.log_to_output)
        self.worker.visualization_data_ready.connect(self.visualizer.update_visualization)
        self.worker.progress_done.connect(self.on_process_done)

        self.worker.start()

    def update_progress(self, value: float):
        """
        Slot to update progress bar and percentage label.
        """
        int_val = int(value)
        self.progress_bar.setValue(int_val)
        self.progress_label.setText(f"{int_val:.2f}%")

    def log_to_output(self, message: str):
        """
        Log to console instead of UI window (requested by user).
        """
        print(f"[BuildingDetection] {message}")

    def on_process_done(self):
        """
        Called when the worker signals that it’s finished:
        - Stop timer,
        - Re‐enable “Detect buildings”,
        - Log completion.
        """
        self.timer_thread.stop()
        self.process_button.setEnabled(True)
        self.log_to_output("Detection run completed.")
