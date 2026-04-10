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
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtCore import QThread, pyqtSignal, QObject, pyqtSlot
from config_ import Config
from AppLogger import Logger
from utils import cleanup_process, resolve_path
from sklearn.decomposition import PCA
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Qt5Agg')

class DuplicateClassifier:
    def __init__(self, config: Config, logger: Logger):
        self.config = config
        self.logger = logger
        self.MODEL = None
        self.processor = None
        self.metadata_file = self.config.get_duplicates_data()["metadata_file_name"]
        self.is_paused = False
        self.is_cancelled = False
        self.class_color_map: Dict[str, str] = {}

    def load_model(self):
        model_folder = self.config.get_duplicates_model_folder()
        
        # Explicit fallback if config returns None
        if model_folder is None:
            model_folder = resolve_path("models/duplicates")
            self.logger.log_status("Config returned None for duplicates model folder. Using default: " + str(model_folder), "WARNING")
        
        # Ensure it's a string for os.environ
        os.environ['TF_KERAS_CACHE_DIR'] = str(model_folder)
        self.logger.log_status(f"os.environ['TF_KERAS_CACHE_DIR'] is set to {model_folder}")

        from tensorflow.keras.applications import EfficientNetB7
        from tensorflow.keras.applications.efficientnet import preprocess_input
        
        self.MODEL = EfficientNetB7(include_top=False, pooling='avg')
        self.processor = preprocess_input
        self.logger.log_status("EfficientNetB7 model loaded")

    def _load_and_preprocess_image(self, img_path: Path) -> np.ndarray:
        from tensorflow.keras.preprocessing import image
        self.loader = image
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
        cluster_labels = DBSCAN(eps=0.26, min_samples=2, metric='cosine').fit_predict(features)
        return cluster_labels

    def _assign_color(self, class_id: str) -> str:
        if class_id not in self.class_color_map:
            self.class_color_map[class_id] = f"#{random.randint(0, 0xFFFFFF):06x}"
        return self.class_color_map[class_id]

    def _save_classified_locations(self, folder_path: Path, clusters: Dict[int, List[str]]):
        output_file = folder_path / "duplicates_found.txt"
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

    def process_folder(self, folder_path: Path, progress_callback, viz_callback=None) -> float:
        start_time = time.time()
        specs = self.config.get_duplicates_data()
        image_extensions = specs["image_extensions"].split(',')
        images = sorted([p for p in folder_path.iterdir() if p.suffix.lower() in image_extensions])

        if not images:
            return 0.0

        self.source_folder = folder_path
        
        # Accumulators
        feature_list = []
        file_names = []
        
        # Incremental Processing Loop
        # We merge _extract_features logic here to allow real-time updates
        total_images = len(images)
        for idx, img_path in enumerate(images):
             while self.is_paused:
                 time.sleep(0.1)
             if self.is_cancelled:
                 break
            
             # 1. Extract Feature
             try:
                 arr = self._load_and_preprocess_image(img_path)
                 feat = self.MODEL.predict(arr, verbose=0)[0]
                 feature_list.append(feat)
                 file_names.append(str(img_path))
             except Exception as e:
                 self.logger.log_exception(f"Error processing {img_path}: {e}")
                 continue

             # 2. Update Progress
             # percent = int(((idx + 1) / total_images) * 50) # First 50% for extraction? 
             # Let's keep existing progress logic later, but maybe emit indeterminate or partial here?
             # For now, duplicate logic relies on 2 passes (copying is the second pass).
             # We can just log status or minimal progress if needed.

             # 3. Real-time Visualization (every 5 images or last image)
             if viz_callback and (len(feature_list) >= 2) and ((idx % 5 == 0) or (idx == total_images - 1)):
                 try:
                     current_features = np.array(feature_list)
                     # Run DBSCAN on what we have so far
                     # Note: This might be slow for very large datasets, strictly O(N^2)
                     temp_labels = self._cluster_features(current_features)
                     
                     # Count distribution
                     unique_labels = set(temp_labels)
                     stats = {}
                     for k in unique_labels:
                         count = np.sum(temp_labels == k)
                         name = f"Cluster {k}" if k != -1 else "Unique"
                         stats[name] = count
                     
                     viz_callback(stats, None)
                 except Exception as e:
                     self.logger.log_exception(f"Real-time viz error: {e}")

        # Final Clustering (for file moving logic)
        features = np.array(feature_list)
        self.logger.log_status(f"Final features shape:{features.shape}")
        
        if len(features) > 0:
            labels = self._cluster_features(features)
        else:
            labels = []

        clusters: Dict[int, List[str]] = {}
        clusters_unique: Dict[int, List[str]] = {}
        for label, file_name in zip(labels, file_names):
            if label != -1:
                clusters.setdefault(label, []).append(file_name)
            else:
                clusters_unique.setdefault(label, []).append(file_name)

        base_path = self.config.get_duplicates_destination_folder()
        os.makedirs(base_path, exist_ok=True)
        
        # ... (Rest of processing) ...
        # Copied logic for file moving to ensure it persists
        all_cluster_files = set(clusters)
        all_unique_files = set(clusters_unique)
        
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

    def process_multiple_folders(self, folder_paths: List[Path], progress_callback, viz_callback=None) -> float:
        time_taken_all = 0.0
        try:
            for folder_path in folder_paths:
                time_taken = self.process_folder(folder_path, progress_callback, viz_callback)
                self.logger.log_status(f"Folder {folder_path.name} was processed for {time_taken}")
                time_taken_all += time_taken
        except Exception as e:
            self.logger.log_exception(f'An error occured while processing duplicates: {e}')
        return time_taken_all


class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        # Use a cleaner style (e.g., fast/default) and customize
        # plt.style.use('seaborn-v0_8-whitegrid') # Optional if available, else default
        fig = plt.figure(figsize=(width, height), dpi=dpi)
        fig.patch.set_facecolor('#f0f0f0') # Match light app background roughly
        self.axes = fig.add_subplot(111)
        # self.axes.set_facecolor('#ffffff')
        super(MplCanvas, self).__init__(fig)
        self.setParent(parent)
        FigureCanvas.setSizePolicy(self,
                                   branch_policy := 1 | 2, # QSizePolicy.Expanding
                                   branch_policy)
        FigureCanvas.updateGeometry(self)


class DuplicateModelLoaderThread(QThread):
    model_loaded = pyqtSignal()
    model_failed = pyqtSignal(str)

    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.config = config
        self.logger = logger
        self.loader = DuplicateClassifier(self.config, self.logger)

    def run(self):
        try:            
            self.loader.load_model()
            self.model_loaded.emit()
        except Exception as e:
            self.model_failed.emit(str(e))


class DuplicatesWorker(QObject):
    progress_updated = pyqtSignal(int)
    processing_complete = pyqtSignal(float)
    progress_updated = pyqtSignal(int)
    processing_complete = pyqtSignal(float)
    error_occurred  = pyqtSignal(str)
    viz_update = pyqtSignal(object, object) # points, labels

    def __init__(self, config: Config, logger: Logger, remove_dir: bool):
        super().__init__()
        self.config = config
        self.logger = logger
        self.remove_dir = remove_dir
        self.processor: DuplicateClassifier | None = None

    @pyqtSlot()
    def run(self):
        try:
            self.processor = DuplicateClassifier(self.config, self.logger)
            self.processor.load_model()
            elapsed = self.processor.process_multiple_folders(
                [self.config.get_duplicates_source_folder()],
                self.progress_updated.emit,
                self.viz_update.emit
            )

            if self.remove_dir:
                cleanup_process(self.remove_dir, self.config.get_duplicates_source_folder())

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
        self.source_folder = self.config.get_duplicates_source_folder()
        self.destination_folder = self.config.get_duplicates_destination_folder()
        self.worker_thread = None
        self.timer_thread = None
        self.worker = None
        self.loader_thread = None
        self.init_ui()

        self.process_button.setEnabled(False)
        self.loader_thread = DuplicateModelLoaderThread(self.config, self.logger)
        self.loader_thread.model_loaded.connect(self.on_model_loaded)
        self.loader_thread.model_failed.connect(self.on_model_failed)
        self.loader_thread.start()

    def init_ui(self):
        layout = QVBoxLayout()

        self.source_folder_btn = QPushButton("Select Input Folder")
        self.source_folder_label = QLabel(f"{self.source_folder}")
        self.source_folder_btn.clicked.connect(self.choose_source_folder)
        layout.addWidget(self.source_folder_btn)
        layout.addWidget(self.source_folder_label)

        self.destination_folder_btn = QPushButton("Select Output Folder")
        self.destination_folder_label = QLabel(f"{self.destination_folder}")
        self.destination_folder_btn.clicked.connect(self.choose_destination_folder)
        self.destination_folder_btn.clicked.connect(self.choose_destination_folder)
        layout.addWidget(self.destination_folder_btn)
        layout.addWidget(self.destination_folder_label)

        # Plot Widget
        self.plot_canvas = MplCanvas(self, width=5, height=4, dpi=100)
        layout.addWidget(self.plot_canvas)

        self.files_processed_text = QTextEdit()
        self.files_processed_text.setReadOnly(True)
        self.files_processed_text.setMaximumHeight(100) # Limit height to give more room to plot
        layout.addWidget(self.files_processed_text)

        self.timer_label = QLabel("Elapsed Time: 0.00 sec")
        layout.addWidget(self.timer_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.check_box = QCheckBox(f"Remove {self.config.get_duplicates_source_folder().name} directory")
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

    def choose_destination_folder(self):
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
            if folder:
                self.destination_folder = folder
                self.config.set_duplicates_destination_folder(folder)
                self.destination_folder_label.setText(folder)
                self.logger.log_status(f"Output folder set to {folder}")
        except Exception as e:
            self.logger.log_exception(f"Folder selection failed: {e}")
    
    def choose_source_folder(self):
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Input Folder", options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
            if folder:
                self.source_folder = folder
                self.config.set_duplicates_source_folder(folder)
                self.source_folder_label.setText(folder)
                self.logger.log_status(f"Input folder set to {folder}")
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
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.processing_complete.connect(self.processing_done)
        self.worker.error_occurred.connect(self.log_error)
        self.worker.viz_update.connect(self.update_plot)

        self.worker_thread.start()
        self.process_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.status_label.setText("Processing started")

    def update_timer(self, seconds):
        self.timer_label.setText(f"Elapsed Time: {seconds:.2f} sec")

    @pyqtSlot(float)
    def processing_done(self, seconds):
        self.process_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.files_processed_text.append(f"Done. Processed in {seconds:.2f} seconds.")
        self.status_label.setText(f"Done. Processed in {seconds:.2f} seconds.")
        if self.worker_thread:
            self.worker_thread.quit()

    @pyqtSlot(str)
    def log_error(self, msg):
        self.files_processed_text.append(f"Error: {msg}")

    @pyqtSlot(object, object)
    def update_plot(self, stats, _ignored):
        self.plot_canvas.axes.clear()
        
        if not stats or not isinstance(stats, dict):
            return

        # Prepare data for Bar Chart
        categories = list(stats.keys())
        counts = list(stats.values())
        
        # Sort by count descending for better readability
        if len(categories) > 0:
             combined = sorted(zip(counts, categories), reverse=True)
             counts = [x[0] for x in combined]
             categories = [x[1] for x in combined]

        # Use a nice color palette
        colors = plt.cm.viridis(np.linspace(0.3, 0.8, len(categories)))

        bars = self.plot_canvas.axes.bar(categories, counts, color=colors, edgecolor='black', alpha=0.8)
        
        # Add grid
        self.plot_canvas.axes.grid(True, axis='y', linestyle='--', alpha=0.6)
        
        # Remove top and right spines
        self.plot_canvas.axes.spines['top'].set_visible(False)
        self.plot_canvas.axes.spines['right'].set_visible(False)

        # Add counts on top
        for bar in bars:
            height = bar.get_height()
            self.plot_canvas.axes.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', color='black', fontsize=9, fontweight='bold')

        self.plot_canvas.axes.set_title(f"Cluster Distribution ({sum(counts)} images processed)", fontsize=10, fontweight='bold', color='#333333')
        self.plot_canvas.axes.set_ylabel("Number of Images", color='#333333')
        # self.plot_canvas.axes.set_xlabel("Clusters", color='#333333')
        self.plot_canvas.axes.tick_params(axis='x', rotation=45, colors='#333333') 
        self.plot_canvas.axes.tick_params(axis='y', colors='#333333')

        self.plot_canvas.draw()

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
