from PyQt5 import QtWidgets, QtCore
from pathlib import Path
from config_ import Config
from AppLogger import Logger
from BuildingDetection import ObjectDetectionProcessor
from utils import cleanup_process
import time

class _DetectionWorker(QtCore.QThread):
    progress_done = QtCore.pyqtSignal()

    def __init__(self, processor: ObjectDetectionProcessor, remove_after: bool):
        super().__init__()
        self.processor = processor
        self.remove_after = remove_after

        # Connect processor signals (forward to UI):
        self.processor.progress_updated.connect(self._emit_progress)
        self.processor.log_message.connect(self._emit_log)
        self.processor.image_saved.connect(self._emit_image_saved)

    # These attributes will be connected by the parent at runtime:
    progress_changed = QtCore.pyqtSignal(float)
    log_message = QtCore.pyqtSignal(str)
    image_saved = QtCore.pyqtSignal(str)

    def _emit_progress(self, pct: float):
        self.progress_changed.emit(pct)

    def _emit_log(self, msg: str):
        self.log_message.emit(msg)

    def _emit_image_saved(self, path: str):
        self.image_saved.emit(path)

    def run(self):
        self.processor.process()
        if self.remove_after:
            cleanup_process(True, self.processor.input_dir)
        self.progress_done.emit()


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

        # === 1) Input Folder Selection ===
        folder_layout = QtWidgets.QHBoxLayout()
        self.folder_btn = QtWidgets.QPushButton("Select Input Folder")
        self.folder_label = QtWidgets.QLabel(str(self.config.get_bd_input_dir()))
        folder_layout.addWidget(self.folder_btn)
        folder_layout.addWidget(self.folder_label)
        layout.addLayout(folder_layout)

        # === 2) Hyperparameter Controls ===
        params_box = QtWidgets.QGroupBox("Detection Hyperparameters")
        params_layout = QtWidgets.QFormLayout(params_box)

        # 2.1 Model Path
        self.model_path_edit = QtWidgets.QLineEdit(str(self.config.get_bd_model_path()))
        self.model_browse_btn = QtWidgets.QPushButton("Browse Model...")
        model_path_layout = QtWidgets.QHBoxLayout()
        model_path_layout.addWidget(self.model_path_edit)
        model_path_layout.addWidget(self.model_browse_btn)
        params_layout.addRow("Model Path:", model_path_layout)

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
        self.reset_button = QtWidgets.QPushButton("Reset to Defaults")
        self.remove_checkbox = QtWidgets.QCheckBox("Remove input folder after processing")
        self.process_button = QtWidgets.QPushButton("Detect buildings")
        self.process_button.setEnabled(False)  # will be enabled after validation
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        button_layout.addWidget(self.remove_checkbox)
        button_layout.addWidget(self.process_button)
        layout.addLayout(button_layout)

        # === 4) Progress + Timer ===
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QtWidgets.QLabel("0.00%")
        self.timer_label = QtWidgets.QLabel("Elapsed Time: 0.00 sec")

        progress_layout = QtWidgets.QHBoxLayout()
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.timer_label)
        layout.addLayout(progress_layout)

        # === 5) Log Output ===
        self.text_output = QtWidgets.QTextEdit()
        self.text_output.setReadOnly(True)
        layout.addWidget(self.text_output)

        # === 6) Signal Connections ===
        self.folder_btn.clicked.connect(self.choose_input_folder)
        self.model_browse_btn.clicked.connect(self.choose_model_dir)
        self.output_browse_btn.clicked.connect(self.choose_output_folder)

        self.reset_button.clicked.connect(self.reset_to_defaults)
        self.process_button.clicked.connect(self.on_process_clicked)

        # Re-validate whenever relevant fields change
        self.model_path_edit.textChanged.connect(self._update_process_button_state)
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

        # Validate model_path
        model_path_str = self.model_path_edit.text().strip()
        if not model_path_str:
            self.model_path_edit.setToolTip("Model path cannot be empty.")
            valid = False
        else:
            p = Path(model_path_str)
            if not p.exists() or not p.is_dir():
                self.model_path_edit.setToolTip("Model path must point to an existing directory.")
                valid = False
            else:
                self.model_path_edit.setToolTip("")

        # Validate target_classes
        tc = self.target_classes_edit.text().strip()
        if not tc:
            self.target_classes_edit.setToolTip("Target classes cannot be empty.")
            valid = False
        else:
            # Ensure there is at least one non-empty class name
            classes_list = [c.strip() for c in tc.split(",") if c.strip()]
            if not classes_list:
                self.target_classes_edit.setToolTip("Enter at least one class name, separated by commas.")
                valid = False
            else:
                self.target_classes_edit.setToolTip("")

        # Validate output_dir
        output_str = self.output_dir_edit.text().strip()
        if not output_str:
            self.output_dir_edit.setToolTip("Output directory cannot be empty.")
            valid = False
        else:
            out_p = Path(output_str)
            if not out_p.exists() or not out_p.is_dir():
                self.output_dir_edit.setToolTip("Output must point to an existing directory.")
                valid = False
            else:
                self.output_dir_edit.setToolTip("")

        # Optionally validate input_dir too (uncomment if required):
        input_str = self.folder_label.text().strip()
        in_p = Path(input_str)
        if not in_p.exists() or not in_p.is_dir():
            self.folder_label.setToolTip("Input folder must exist.")
            valid = False
        else:
            self.folder_label.setToolTip("")

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
            self.config.set_building_detection_param("input_dir", folder)
            # You could also re‐validate here if you enforce input_dir validity
            # self._update_process_button_state()

    def choose_model_dir(self):
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Model Directory",
            str(self.config.get_bd_model_path()),
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            self.model_path_edit.setText(folder)

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

    def reset_to_defaults(self):
        """
        Pull recommended/default values from config.get_building_detection_recommended(),
        update all six widgets, and write them back to the .ini so future launches use them.
        """
        rec = self.config.get_building_detection_recommended()

        # 1) Update the UI widgets
        self.model_path_edit.setText(rec["model_path"])
        self.target_classes_edit.setText(rec["target_classes"])
        self.output_dir_edit.setText(rec["output_dir"])
        self.threshold_spin.setValue(float(rec["threshold"]))
        self.expand_spin.setValue(float(rec["expand_factor"]))
        self.min_dim_spin.setValue(int(rec["min_dim"]))

        # You may also want to update the folder_label if you reset input_dir:
        self.folder_label.setText(rec["input_dir"])

        # 2) Write them back to config_.ini immediately
        self.config.set_building_detection_param("model_path", rec["model_path"])
        self.config.set_building_detection_param("target_classes", rec["target_classes"])
        self.config.set_building_detection_param("output_dir", rec["output_dir"])
        self.config.set_building_detection_param("threshold", rec["threshold"])
        self.config.set_building_detection_param("expand_factor", rec["expand_factor"])
        self.config.set_building_detection_param("min_dim", rec["min_dim"])
        self.config.set_building_detection_param("input_dir", rec["input_dir"])

        # 3) Re‐validate to update tooltips and button state
        self._update_process_button_state()

        self.log_to_output("Reset all hyperparameters to recommended defaults.")

    def on_process_clicked(self):
        """
        When “Detect buildings” is clicked:
         1. Gather all six values,
         2. Write them to config_.ini,
         3. Instantiate a new processor, hook signals, start threads.
        """
        model_path_val = self.model_path_edit.text().strip()
        target_classes_val = self.target_classes_edit.text().strip()
        output_dir_val = self.output_dir_edit.text().strip()
        threshold_val = f"{self.threshold_spin.value():.2f}"
        expand_val = f"{self.expand_spin.value():.2f}"
        min_dim_val = str(self.min_dim_spin.value())

        # Write back to config
        self.config.set_building_detection_param("model_path", model_path_val)
        self.config.set_building_detection_param("target_classes", target_classes_val)
        self.config.set_building_detection_param("output_dir", output_dir_val)
        self.config.set_building_detection_param("threshold", threshold_val)
        self.config.set_building_detection_param("expand_factor", expand_val)
        self.config.set_building_detection_param("min_dim", min_dim_val)

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
        self.worker.progress_changed = self.update_progress
        self.worker.log_message = self.log_to_output
        self.worker.image_saved = self.log_to_output
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
        Append a line to the QTextEdit and scroll to bottom.
        """
        self.text_output.append(message)
        self.text_output.verticalScrollBar().setValue(
            self.text_output.verticalScrollBar().maximum()
        )

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
