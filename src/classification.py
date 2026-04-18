import matplotlib.pyplot as plt

from tqdm import tqdm

from config_ import Config
from app_logger import Logger

import os
import time
import random
import shutil
from pathlib import Path

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QLabel, QLineEdit, QPushButton
from PyQt5.QtCore import QThread, pyqtSignal, QObject

# torch is imported lazily in Classify.__init__() to prevent loading during app startup
from PIL import Image

from utils import ensure_directory_exists, cleanup_process, resolve_path



DISPLAY_MAPPING = {
    "AD_H1": "Assam Type (1-Story)",
    "AD_H2": "Assam Type (2-Story)",
    "MR_H1 flat roof": "Masonry (1-Story, Flat)",
    "MR_H1 gable roof": "Masonry (1-Story, Gable)",
    "MR_H2 flat roof": "Masonry (2-Story, Flat)",
    "MR_H2 gable roof": "Masonry (2-Story, Gable)",
    "MR_H3": "Masonry (3-Story)",
    "Metal_H1": "Metal Structure",
    "Non_Building": "Not a Building",
    "RCC_H1 flat roof": "Reinf. Conc. (1-Story, Flat)",
    "RCC_H1 gable roof": "Reinf. Conc. (1-Story, Gable)",
    "RCC_H2 flat roof": "Reinf. Conc. (2-Story, Flat)",
    "RCC_H2 gable roof": "Reinf. Conc. (2-Story, Gable)",
    "RCC_H3 flat roof": "Reinf. Conc. (3-Story, Flat)",
    "RCC_H3 gable roof": "Reinf. Conc. (3-Story, Gable)",
    "RCC_H4 flat roof": "Reinf. Conc. (4-Story, Flat)",
    "RCC_H4 gable roof": "Reinf. Conc. (4-Story, Gable)",
    "RCC_H5": "Reinf. Conc. (5-Story)",
    "RCC_H6": "Reinf. Conc. (6-Story)",
    "RCC_OS_H1": "RCC Open Storey (1-Story)",
    "RCC_OS_H2": "RCC Open Storey (2-Story)",
    "RCC_OS_H3": "RCC Open Storey (3-Story)",
    "RCC_OS_H4": "RCC Open Storey (4-Story)",
    "Timber": "Timber Structure"
}

class Classify:
    def __init__(self, config: Config, logger: Logger, model_dir, num_classes=24, device=None):
        # Lazy import torch - only loads when Classification tab is opened
        import torch
        self.torch = torch  # Store reference for use in methods
        
        self.config = config
        self.logger = logger
        params = self.config.get_classification_data()

        self.supported_files = tuple(f.strip() for f in self.config.get_allowed_file_types().split(','))
        self.save_folder = self.config.get_classification_data()["output_folder"]
        ensure_directory_exists(self.save_folder)
        self.metadata_file = Path(self.save_folder) / "processed_metadata.json"

        self.model_dir = model_dir

        self.parent_folder = params["parent_folder"]

        self.output_folder = params["output_folder"]
        self.class_names = params["class_names"].split(',')
        self.confidence_threshold = float(params["confidence_threshold"])

        self.image_extensions = self.config.get_img_ext()
        self.image_extensions = tuple(self.image_extensions.split(','))

        self.device = device if device else self.torch.device("cuda" if self.torch.cuda.is_available() else "cpu")
        self.logger.log_status(f"Using device: {self.device}")

    def instantiate_model(self):
        model_path = self.model_dir
        from transformers import BeitForImageClassification, BeitImageProcessor

        # Load BEiT base architecture — try online first (downloads & caches),
        # fall back to local cache for offline/frozen mode
        try:
            self.logger.log_status("Loading BEiT model architecture (may download on first run)...")
            model = BeitForImageClassification.from_pretrained(
                "microsoft/beit-base-patch16-224-pt22k-ft22k",
                num_labels=len(self.class_names),
                ignore_mismatched_sizes=True,
                local_files_only=False,  # Allow download if not cached
                use_safetensors=True     # Bypass torch.load CVE-2025-32434 check
            )
        except Exception as e_online:
            self.logger.log_status(f"Online download failed ({e_online}), trying local cache...")
            model = BeitForImageClassification.from_pretrained(
                "microsoft/beit-base-patch16-224-pt22k-ft22k",
                num_labels=len(self.class_names),
                ignore_mismatched_sizes=True,
                local_files_only=True,
                use_safetensors=True     # Bypass torch.load CVE-2025-32434 check
            )

        # Load custom trained weights from .pth file
        try:
            checkpoint = self.torch.load(model_path, map_location=self.device, weights_only=False)
            state = checkpoint.get('model_state_dict', checkpoint)
            model.load_state_dict(state, strict=False)
            self.logger.log_status("Custom classification weights loaded successfully")
        except Exception as e:
            self.logger.log_exception(f"Error loading model weights from {model_path}: {e}")
            raise
        model.to(self.device).eval()

        # Load image processor — same online-first strategy
        try:
            processor = BeitImageProcessor.from_pretrained(
                "microsoft/beit-base-patch16-224-pt22k-ft22k",
                revision="ae5a6db7d11451821f40ed294ceae691e68203e2"
            )
        except Exception:
            processor = BeitImageProcessor.from_pretrained(
                "microsoft/beit-base-patch16-224-pt22k-ft22k"
            )
        return model, processor

    def make_folders(self):
        names = self.config.get_foldr_names_classif().split(',')
        foldr_name = self.config.get_classif_folder_name() # Is dead code
        foldr = Path(self.output_folder)
        for i in names:
            dir = foldr / i
            try:
                os.makedirs(dir, exist_ok=True)
                self.logger.log_status(f"Created folder: {dir}")
            except Exception as e:
                self.logger.log_exception(f'Failed to create folder {dir}. Exception: {e}')

    def save_image(self, image_path, filename, class_: str):
        try:
            shutil.copy2(str(image_path), os.path.join(class_, filename))
            self.logger.log_status(f"Saved image to {class_}")
        except Exception as e:
            self.logger.log_exception(f"Failed to save image to {class_}. Exception: {e}")

    def predict_image(self, image_path):
        try:
            image = Image.open(image_path).convert('RGB')
            inputs = self.processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with self.torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = self.torch.nn.functional.softmax(outputs.logits, dim=1)
                predicted_class = self.torch.argmax(probabilities, dim=1).item()
                confidence = probabilities[0][predicted_class].item()

            return predicted_class, confidence
        except Exception as e:
            self.logger.log_exception(f"Error processing image {image_path}: {str(e)}")
            return None, None

    def organize_images(self, check_value, output_file_path, progress_callback, labels, selected_model):
        self.input_folder = Path(self.parent_folder)
        self.logger.log_status(f'input_folder for classification: {self.input_folder}')
        self.model_path = selected_model
        self.logger.log_status('Reached organize_images')
        try:
            os.makedirs(self.output_folder, exist_ok=True)
            uncertain_folder = os.path.join(self.output_folder, "uncertain")
            os.makedirs(uncertain_folder, exist_ok=True)
            self.logger.log_status(f'Prepared output folders at {self.output_folder}')
        except Exception as e:
            self.logger.log_exception(f"Error making folders: {e}")

        self.make_folders()

        image_files = []
        self.logger.log_status(f"Getting all images in folder {self.input_folder}")
        for f in self.input_folder.glob("*"):
            self.logger.log_status(f"Found image: {f}")
            if f.suffix.lower() in self.image_extensions:
                image_files.append(f)

        self.logger.log_status(f"Found {len(image_files)} images to classify")

        stats = {
            'total': len(image_files),
            'processed': 0,
            'uncertain': 0,
            'failed': 0,
            'class_counts': {class_name: 0 for class_name in self.class_names}
        }

        with open(output_file_path, 'w') as locfile:
            self.logger.log_status(output_file_path)
            for image_path in tqdm(image_files, desc="Processing images"):
                predicted_class, confidence = self.predict_image(str(image_path))

                if predicted_class is None:
                    self.logger.log_status(f"An image failed to be classified. Image_path: {image_path}", 'WARNING')
                    stats['failed'] += 1
                    continue

                class_name = self.class_names[predicted_class]
                uncertain = False
                if confidence >= self.confidence_threshold:
                    target_folder = os.path.join(self.output_folder, class_name)
                    stats['class_counts'][class_name] += 1
                else:
                    target_folder = uncertain_folder
                    stats['uncertain'] += 1
                    uncertain = True
                
                os.makedirs(target_folder, exist_ok=True)
                filename = f"{confidence:.2f}_{image_path.name}"
                self.save_image(image_path, filename, target_folder)

                stats['processed'] += 1
                if not uncertain:
                    # Update label text using display mapping
                    display_name = DISPLAY_MAPPING.get(class_name.strip(), class_name.strip())
                    labels[class_name.strip()][0].setText(f"{display_name}: {stats['class_counts'][class_name]}")
                    
                progress_callback(((stats['processed'] + stats['failed'])/ stats['total']) * 100)

                self.logger.log_status("image_path.name: ", image_path.name)
                lat, lon = image_path.name.split(' ')[3:5]
                locfile.write(f"{lat}:{lon}:{class_name}\n")

        self.logger.log_status("Classification Complete:\n"+ f"Processed: {stats['processed']}, Uncertain: {stats['uncertain']}, Failed: {stats['failed']}")
        for class_name, count in stats['class_counts'].items():
            self.logger.log_status(f"{class_name}: {count} images")

        cleanup_process(check_value, self.parent_folder)


class ModelLoaderThread(QThread):
    model_ready = pyqtSignal(object, object)
    model_failed = pyqtSignal(str)

    def __init__(self, processor: Classify, model_path: str):
        super().__init__()
        self.processor = processor
        self.model_path = model_path

    def run(self):
        try:
            model, processor = self.processor.instantiate_model()
            self.model_ready.emit(model, processor)
        except Exception as e:
            self.model_failed.emit(str(e))


class _ClassificationWorker(QtCore.QThread):
    progress_updated = QtCore.pyqtSignal(float)
    message_logged = QtCore.pyqtSignal(str)
    processing_done = QtCore.pyqtSignal(bool)

    def __init__(self, processor, check_value, selected_model, labels, output_folder):
        super().__init__()
        self.processor = processor
        self.check_value = check_value
        self.selected_model = selected_model
        self.labels = labels
        self.output_folder = Path(output_folder)

    def run(self):
        print('Reached Run for Classification Worker')
        self.output_folder.mkdir(parents=True, exist_ok=True)

        new_filename = "classified_locations.txt"
        i = 1
        while self.output_folder.joinpath(new_filename).exists():
            new_filename = f"classified_locations_{i}.txt"
            i += 1

        output_file_path = self.output_folder.joinpath(new_filename)

        self.processor.organize_images(
            self.check_value,
            output_file_path,
            self.progress_updated.emit,
            self.labels,
            self.selected_model
        )
        self.processing_done.emit(True)


class _ClassificationTimer(QtCore.QThread):
    time_updated = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        self.elapsed_seconds = 0
        while self.running:
            time.sleep(1)
            self.elapsed_seconds += 1
            self.time_updated.emit(f"Elapsed Time: {self.elapsed_seconds:.2f} sec")
        self.done.emit(f"Processed for {self.elapsed_seconds} seconds")


class ClassificationWindow(QtWidgets.QWidget):
    add_model_requested = QtCore.pyqtSignal()

    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.logger = logger
        self.config = config
        
        params = self.config.get_classification_data()
        self.model_path = params["model_path"]
        self.model_ext = params["model_ext"]
        self.available_models = params["available_models"].split(',')
        self.input_folder = params["parent_folder"]
        self.input_folder_name = Path(self.input_folder).name

        self.output_folder = params["output_folder"]

        self.setToolTip("Use classification models to assign labels to images based on their visual content.")
        self.init_ui()
        self.process_button.setEnabled(False)
        self.model_dir = resolve_path(os.path.join(self.model_path,self.available_models[0] + self.model_ext))
        self.logger.log_status(f"Loaded in {self.model_dir}")

        self.processor = Classify(config, logger, self.model_dir)
        self.loader_thread = None  # Created on-demand — don't load at startup
        self._model_loaded = False

    def on_model_loaded(self, model, processor):
        # Store loaded model and processor
        self.processor.model = model
        self.processor.processor = processor
        self._model_loaded = True
        self.model_status_label.setText("Model loaded — ready to classify.")
        self.process_button.setEnabled(True)
        if hasattr(self, 'load_model_btn'):
            self.load_model_btn.setEnabled(False)  # Already loaded, no need to click again

    def on_model_failed(self, error):
        self.model_status_label.setText("Model loading failed")
        self.logger.log_exception(error)

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.top_layout = QtWidgets.QHBoxLayout()
        self.progress_label = QtWidgets.QLabel("0.0")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.timer_label = QtWidgets.QLabel("Elapsed Time: 0.00 sec")

        self.drop_down = QtWidgets.QComboBox()
        self.drop_down.addItems(self.available_models)
        self.drop_down.setCurrentIndex(0)
        self.selected_model = self.model_path + self.available_models[0]
        self.drop_down.currentTextChanged.connect(self.on_select)

        self.remove_checkbox = QtWidgets.QCheckBox(f"Remove {self.input_folder_name} directory")
        self.process_button = QtWidgets.QPushButton("Classify All Images")
        self.process_button.clicked.connect(self.start_process)

        self.input_folder_label = QLabel("Source Folder:")
        self.input_folder_input = QLineEdit(str(self.input_folder))
        self.input_browse_button = QPushButton("Browse")
        self.input_browse_button.clicked.connect(self.browse_input_folder)

        self.output_folder_label = QLabel("Destination Folder:")
        self.output_folder_input = QLineEdit(str(self.output_folder))
        self.output_browse_button = QPushButton("Browse")
        self.output_browse_button.clicked.connect(self.browse_output_folder)

        layout.addWidget(self.input_folder_label)
        layout.addWidget(self.input_folder_input)
        layout.addWidget(self.input_browse_button)

        layout.addWidget(self.output_folder_label)
        layout.addWidget(self.output_folder_input)
        layout.addWidget(self.output_browse_button)

        self.top_layout.addWidget(self.process_button)
        self.top_layout.addWidget(self.drop_down)
        
        self.add_model_btn = QtWidgets.QPushButton("Add Model")
        self.add_model_btn.clicked.connect(self.add_model_requested.emit)
        self.top_layout.addWidget(self.add_model_btn)

        self.load_model_btn = QtWidgets.QPushButton("↯ Load Model")
        self.load_model_btn.setToolTip("Load the BEiT classifier into memory (required before classifying)")
        self.load_model_btn.clicked.connect(self._trigger_model_load)
        self.top_layout.addWidget(self.load_model_btn)
        
        self.top_layout.addWidget(self.progress_bar)
        self.top_layout.addWidget(self.progress_label)

        layout.addLayout(self.top_layout)
        layout.addWidget(self.remove_checkbox)
        layout.addWidget(self.timer_label)

        label_container = QtWidgets.QWidget()
        grid_container = QtWidgets.QGridLayout(label_container)
        self.labels = {}
        class_names = self.config.get_classification_data()["class_names"].split(',')
        for i, name in enumerate(class_names):
            clean_name = name.strip()
            display_name = DISPLAY_MAPPING.get(clean_name, clean_name)
            label = QtWidgets.QLabel(f"{display_name} : 0")
            self.labels[clean_name] = (label, 0)
            row = i if i < 12 else i - 12
            col = 0 if i < 12 else 1
            grid_container.addWidget(label, row, col)

        layout.addWidget(label_container)
        self.text_output = QtWidgets.QTextEdit()
        self.text_output.setReadOnly(True)
        layout.addWidget(self.text_output)
        self.model_status_label = QLabel("Model not loaded — click '↯ Load Model' or 'Classify All Images' to begin.")
        layout.addWidget(self.model_status_label)

    def add_class_labels(self, model_name: str):
        label_container = QtWidgets.QWidget()
        grid_container = QtWidgets.QGridLayout(label_container)
        self.labels = {}
        class_names = self.config.get_model_data()[model_name]['classes']
        for i, name in enumerate(class_names):
            label = QtWidgets.QLabel(name.strip())
            self.labels[name.strip()] = (label, 0)
            row = i if i < 12 else i - 12
            col = 0 if i < 12 else 1
            grid_container.addWidget(label, row, col)

        return label_container

    def on_select(self, text):
        self.selected_model = self.model_path + text + self.model_ext

    def browse_output_folder(self):
        output_folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if output_folder:
            self.output_folder_input.setText(output_folder)
            self.output_folder = Path(output_folder)
            self.config.set_classif_output_foldr(output_folder)

    def browse_input_folder(self):
        input_folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Input folder")
        if input_folder:
            self.input_folder_input.setText(input_folder)
            self.input_folder = Path(input_folder)
            self.config.set_classif_input_foldr(input_folder)

    def _trigger_model_load(self):
        """Start loading the BEiT model if not already loaded/loading."""
        if self._model_loaded:
            self.model_status_label.setText("Model already loaded.")
            return
        if self.loader_thread and self.loader_thread.isRunning():
            self.model_status_label.setText("Model is loading… please wait.")
            return
        self.model_status_label.setText("Loading model… this may take a minute.")
        self.load_model_btn.setEnabled(False)
        self.loader_thread = ModelLoaderThread(self.processor, self.model_dir)
        self.loader_thread.model_ready.connect(self.on_model_loaded)
        self.loader_thread.model_failed.connect(self.on_model_failed)
        self.loader_thread.start()

    def start_process(self):
        # Auto-trigger model load if not yet done
        if not self._model_loaded:
            self._trigger_model_load()
            self.model_status_label.setText("Model loading… please wait, then click Classify again.")
            return
        self.process_button.setEnabled(False)

        self.timer_thread = _ClassificationTimer()
        self.timer_thread.time_updated.connect(self.timer_label.setText)
        self.timer_thread.done.connect(self.logger.log_status)
        self.timer_thread.start()

        check_value = self.remove_checkbox.isChecked()
        self.worker = _ClassificationWorker(self.processor, check_value, self.selected_model, self.labels, self.output_folder_input.text())
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.message_logged.connect(self.log_to_output)
        self.worker.processing_done.connect(self.on_process_done)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(int(value))
        self.progress_label.setText(f"{value:.2f}")

    def log_to_output(self, message: str):
        self.text_output.append(message)
        self.text_output.verticalScrollBar().setValue(self.text_output.verticalScrollBar().maximum())

    def on_process_done(self, valid: bool):
        self.worker.terminate()
        self.timer_thread.terminate()
        self.model_status_label.setText("Processing Complete!")