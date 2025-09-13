import os
import shutil
import random
import time
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QPushButton,
    QCheckBox, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot
from .config_ import Config
from .AppLogger import Logger
from .utils import cleanup_process, resolve_path
from tensorflow.keras.preprocessing import image

class DuplicateClassifier:
    def __init__(self, config: Config, logger: Logger, folder: Path):
        self.config = config
        self.logger = logger
        self.MODEL = None
        self.processor = None
        self.loader = image
        self.metadata_file = self.config.get_duplicates_data()["metadata_file_name"]
        self.save_folder = folder
        self.is_paused = False
        self.is_cancelled = False
        self.class_color_map: Dict[str, str] = {}

    def load_model(self):
        os.environ['TF_KERAS_CACHE_DIR'] = resolve_path('models')

        from tensorflow.keras.applications import EfficientNetB7
        from tensorflow.keras.applications.efficientnet import preprocess_input
        
        self.MODEL = EfficientNetB7(include_top=False, pooling='avg')
        self.processor = preprocess_input
        self.logger.log_status("EfficientNetB7 model loaded")

    def _load_and_preprocess_image(self, img_path: Path) -> np.ndarray:
        img = self.loader.load_img(img_path, target_size=(600, 600))
        img_array = self.loader.img_to_array(img)
        img_array = np.expand_dims(img_array, axis=0)
        return self.processor(img_array)

    def _extract_features(self, images: List[Path]) -> Tuple[np.ndarray, List[str]]:
        feature_list = []
        file_names = []

        for img_path in images:
            while self.is_paused:
                time.sleep(0.1)
            if self.is_cancelled:
                break
            arr = self._load_and_preprocess_image(img_path)
            features = self.MODEL.predict(arr, verbose=0)[0]
            feature_list.append(features)
            file_names.append(str(img_path))

        return np.array(feature_list), file_names
    
    def _cluster_features(self, features: np.ndarray) -> np.ndarray:
        from sklearn.cluster import DBSCAN
        clustering = DBSCAN(eps=0.5, min_samples=2, metric='euclidean').fit(features)
        return clustering.labels_

    def _assign_color(self, class_id: str) -> str:
        if class_id not in self.class_color_map:
            self.class_color_map[class_id] = f"#{random.randint(0, 0xFFFFFF):06x}"
        return self.class_color_map[class_id]

    def _save_classified_locations(self, folder_path: Path, clusters: Dict[int, List[str]]):
        output_file = folder_path / "classified_locations.txt"
        location_class_map = {}

        for class_id, files in clusters.items():
            for file in files:
                file_path = Path(file)
                name_parts = file_path.stem.split('_')
                if len(name_parts) >= 2:
                    lat, lon = name_parts[0], name_parts[1]
                    location_class_map[(lat, lon)] = str(class_id)

        t = 'a' if output_file.exists() else 'w'
        with open(output_file, t) as f:
            for (lat, lon), class_id in location_class_map.items():
                f.write(f"{lat}:{lon}:{class_id}\n")

    def process_folder(self, folder_path: Path, progress_callback) -> float:
        start_time = time.time()
        specs = self.config.get_duplicates_data()
        image_extensions = specs["image_extensions"].split(',')
        images = sorted([p for p in folder_path.iterdir() if p.suffix.lower() in image_extensions])

        if not images:
            return 0.0

        self.source_folder = folder_path

        features, file_names = self._extract_features(images)
        labels = self._cluster_features(features)

        clusters: Dict[int, List[str]] = {}
        clusters_unique: Dict[int, List[str]] = {}
        for label, file_name in zip(labels, file_names):
            if label != -1:
                clusters.setdefault(label, []).append(file_name)
            else:
                clusters_unique.setdefault(label, []).append(file_name)

        base_path = specs['destination_parent_folder']
        os.makedirs(base_path, exist_ok=True)

        total = len(clusters)
        for count, (cluster_id, files) in enumerate(clusters.items(), start=1):
            while self.is_paused:
                time.sleep(0.1)
            if self.is_cancelled:
                break

            cluster_folder = base_path / f"cluster_{cluster_id}"
            os.makedirs(cluster_folder, exist_ok=True)
            for file in files:
                dst = cluster_folder / Path(file).name
                shutil.copy(file, dst)

            percent = int((count / total) * 100)
            progress_callback(percent)

        total = len(clusters_unique)
        for count, (cluster_id, files) in enumerate(clusters_unique.items(), start=1):
            while self.is_paused:
                time.sleep(0.1)
            if self.is_cancelled:
                break

            cluster_folder = base_path / "Unique"
            os.makedirs(cluster_folder, exist_ok=True)

            for file in files:
                dst = cluster_folder / Path(file).name
                shutil.copy(file, dst)

            percent = int((count / total) * 100)
            progress_callback(percent)

        self._save_classified_locations(folder_path, clusters)
        return time.time() - start_time

    def process_multiple_folders(self, folder_paths: List[Path], progress_callback) -> float:
        time_taken_all = 0.0
        try:
            for folder_path in folder_paths:
                time_taken = self.process_folder(folder_path, progress_callback)
                self.logger.log_status(f"folder {folder_path.name} was processed for {time_taken}")
                time_taken_all += time_taken
            return time_taken_all
        except Exception as e:
            self.logger.log_exception(f'An error occured while processing duplicaes: {e}')


class DuplicateModelLoaderThread(QThread):
    model_loaded = pyqtSignal()
    model_failed = pyqtSignal(str)

    def __init__(self, config: Config, logger: Logger, folder):
        super().__init__()
        self.config = config
        self.logger = logger
        self.folder = folder

    def run(self):
        try:
            loader = DuplicateClassifier(self.config, self.logger, self.folder)
            loader.load_model()
            self.model_loaded.emit()
        except Exception as e:
            self.model_failed.emit(str(e))


class DuplicatesWorker(QObject):
    progress_updated = pyqtSignal(int)
    processing_complete = pyqtSignal(float)
    error_occurred  = pyqtSignal(str)

    def __init__(self, config: Config, logger: Logger, remove_dir: bool, folder):
        super().__init__()
        self.config = config
        self.logger = logger
        self.folder = folder
        self.remove_dir = remove_dir
        self.processor: DuplicateClassifier | None = None

    @pyqtSlot()
    def run(self):
        try:
            self.processor = DuplicateClassifier(self.config, self.logger, self.folder)
            self.processor.load_model()
            elapsed = self.processor.process_multiple_folders(
                [self.config.get_input_folder_dup()],
                self.progress_updated.emit
            )

            if self.remove_dir:
                cleanup_process(self.remove_dir, self.config.get_input_folder_dup())

            self.processing_complete.emit(elapsed)
        except Exception as e:
            self.error_occurred.emit(str(e))

    def pause(self):
        if self.processor:
            self.processor.is_paused = True

    def resume(self):
        if self.processor:
            self.processor.is_paused = False

    def cancel(self):
        if self.processor:
            self.processor.is_cancelled = True


class DuplicatesWindow(QWidget):
    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.config = config
        self.logger = logger
        self.save_folder = self.config.get_current_working_folder()
        self.worker_thread = None
        self.timer_thread = None
        self.worker = None
        self.loader_thread = None
        self.init_ui()

        self.process_button.setEnabled(False)
        self.loader_thread = DuplicateModelLoaderThread(self.config, self.logger, self.save_folder)
        self.loader_thread.model_loaded.connect(self.on_model_loaded)
        self.loader_thread.model_failed.connect(self.on_model_failed)
        self.loader_thread.start()

    def init_ui(self):
        layout = QVBoxLayout()

        self.folder_btn = QPushButton("Select Output Folder")
        self.folder_label = QLabel(f"{self.save_folder}")
        self.folder_btn.clicked.connect(self.choose_folder)
        layout.addWidget(self.folder_btn)
        layout.addWidget(self.folder_label)

        self.files_processed_text = QTextEdit()
        self.files_processed_text.setReadOnly(True)
        layout.addWidget(self.files_processed_text)

        self.timer_label = QLabel("Elapsed Time: 0.00 sec")
        layout.addWidget(self.timer_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.check_box = QCheckBox(f"Remove {self.config.get_input_folder_dup().name} directory")
        layout.addWidget(self.check_box)

        button_layout = QHBoxLayout()
        self.process_button = QPushButton("Filter Duplicates")
        self.process_button.clicked.connect(self.start_process)
        button_layout.addWidget(self.process_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_process)
        self.pause_button.setEnabled(False)
        button_layout.addWidget(self.pause_button)

        self.resume_button = QPushButton("Resume")
        self.resume_button.clicked.connect(self.resume_process)
        self.resume_button.setEnabled(False)
        button_layout.addWidget(self.resume_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_process)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.status_label = QLabel("Loading model...")
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def choose_folder(self):
        from PyQt5.QtWidgets import QFileDialog
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
            if folder:
                self.save_folder = folder
                self.folder_label.setText(folder)
                self.logger.log_status(f"Output folder set to {folder}")
        except Exception as e:
            self.logger.log_exception(f"Folder selection failed: {e}")

    @pyqtSlot()
    def on_model_loaded(self):
        self.process_button.setEnabled(True)
        self.status_label.setText("Model imports complete. Ready to filter duplicates.")
        self.logger.log_status("Model imports complete. Ready to filter duplicates.")

    @pyqtSlot(str)
    def on_model_failed(self, error: str):
        self.status_label.setText(f"Model import failed: {error}")
        self.logger.log_exception(f"Model import failed: {error}")
        self.process_button.setEnabled(True)

    def start_process(self):
        self.files_processed_text.clear()
        self.worker = DuplicatesWorker(self.config, self.logger, self.check_box.isChecked())
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.processing_complete.connect(self.processing_done)
        self.worker.error_occurred.connect(self.log_error)

        self.worker_thread.start()
        self.process_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

    def update_timer(self, seconds):
        self.timer_label.setText(f"Elapsed Time: {seconds:.2f} sec")

    @pyqtSlot(float)
    def processing_done(self, seconds):
        self.process_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.files_processed_text.append(f"Done. Processed in {seconds:.2f} seconds.")
        if self.worker_thread:
            self.worker_thread.quit()

    @pyqtSlot(str)
    def log_error(self, msg):
        self.files_processed_text.append(f"Error: {msg}")

    def pause_process(self):
        if self.worker:
            self.worker.pause()
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)

    def resume_process(self):
        if self.worker:
            self.worker.resume()
            self.resume_button.setEnabled(False)
            self.pause_button.setEnabled(True)

    def cancel_process(self):
        if self.worker:
            self.worker.cancel()
            self.process_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.files_processed_text.append("Process cancelled.")