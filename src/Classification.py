import matplotlib.pyplot as plt

from tqdm import tqdm

from config_ import Config
from AppLogger import Logger

import os
import time
import random
import shutil
from pathlib import Path

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QLabel, QLineEdit, QPushButton
from PyQt5.QtCore import QThread, pyqtSignal, QObject

import torch
from PIL import Image

from utils import ensure_directory_exists, cleanup_process


class Classify:
    def __init__(self, config: Config, logger: Logger, model_dir, num_classes=24, device=None):
        self.config = config
        self.logger = logger
        params = self.config.get_classification_data()

        self.supported_files = tuple(f.strip() for f in self.config.get_allowed_file_types().split(','))
        self.save_folder = self.config.get_paths_data()["classification_save_folder_path"]
        ensure_directory_exists(self.save_folder)
        self.metadata_file = Path(self.save_folder) / "processed_metadata.json"

        self.model_dir = model_dir

        self.parent_folder = params["parent_folder"]

        self.output_folder = params["output_folder"]
        self.class_names = params["class_names"].split(',')
        self.confidence_threshold = float(params["confidence_threshold"])

        self.image_extensions = self.config.get_img_ext()
        self.image_extensions = tuple(self.image_extensions.split(','))


        self.device = device if device else torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.logger.log_status(f"Using device: {self.device}")

    def instantiate_model(self):
        model_path = self.model_dir
        # BEiT model initialization moved into QThread
        from transformers import BeitForImageClassification, BeitImageProcessor
        model = BeitForImageClassification.from_pretrained(
            "microsoft/beit-base-patch16-224-pt22k-ft22k",
            num_labels=len(self.class_names),
            ignore_mismatched_sizes=True,
            local_files_only=True
        )
        try:
            checkpoint = torch.load(model_path, map_location=self.device, weights_only=True)
            state = checkpoint.get('model_state_dict', checkpoint)
            model.load_state_dict(state)
            self.logger.log_status("Model successfully loaded for classification")
        except Exception as e:
            self.logger.log_exception(f"Error loading model: {e}")
        model.to(self.device).eval()

        processor = BeitImageProcessor.from_pretrained(
            "microsoft/beit-base-patch16-224-pt22k-ft22k", 
            revision="ae5a6db7d11451821f40ed294ceae691e68203e2"
        )
        return model, processor

    def make_folders(self):
        names = self.config.get_foldr_names_classif().split(',')
        foldr_name = self.config.get_classif_folder_name()
        foldr = self.config.get_current_working_folder() / foldr_name
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

            with torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = torch.nn.functional.softmax(outputs.logits, dim=1)
                predicted_class = torch.argmax(probabilities, dim=1).item()
                confidence = probabilities[0][predicted_class].item()

            return predicted_class, confidence
        except Exception as e:
            self.logger.log_exception(f"Error processing image {image_path}: {str(e)}")
            return None, None

    def organize_images(self, check_value, output_file_path, progress_callback, labels, selected_model):
        self.input_folder = [i for i in Path(self.parent_folder).glob('Unique')]
        self.logger.log_status(f'input_folder {self.input_folder}')
        self.model_path = selected_model
        self.logger.log_status('reached organize_images')
        try:
            os.makedirs(self.output_folder, exist_ok=True)
            uncertain_folder = os.path.join(self.output_folder, "uncertain")
            os.makedirs(uncertain_folder, exist_ok=True)
            self.logger.log_status(f'Prepared output folders at {self.output_folder}')
        except Exception as e:
            self.logger.log_exception(f"Error making folders: {e}")

        self.make_folders()

        image_files = []
        for folder in self.input_folder:
            print(folder)
            for f in folder.glob("*"):
                print(f)
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
            print(output_file_path)
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
                    labels[class_name][0].setText(f"{class_name}: {stats['class_counts'][class_name]}")
                progress_callback(((stats['processed'] + stats['failed'])/ stats['total']) * 100)

                lat, lon = image_path.name.split('_')[3:5]
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
    processing_done = QtCore.pyqtSignal(Path)

    def __init__(self, processor, check_value, selected_model, labels, output_folder):
        super().__init__()
        self.processor = processor
        self.check_value = check_value
        self.selected_model = selected_model
        self.labels = labels
        self.output_folder = Path(output_folder)

    def run(self):
        print('reached run')
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
        self.processing_done.emit(output_file_path)


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
    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.logger = logger
        self.config = config
        
        params = self.config.get_classification_data()
        self.model_path = params["model_path"]
        self.model_ext = params["model_ext"]
        self.available_models = params["available_models"].split(',')
        self.folder = params["parent_folder"]
        self.input_folder_name = Path(self.folder).name

        self.setToolTip("Use classification models to assign labels to images based on their visual content.")
        self.init_ui()
        self.process_button.setEnabled(False)
        self.model_dir = os.path.join(self.model_path,self.available_models[0] + self.model_ext)
        self.logger.log_status(f"Loaded in {self.model_dir}")

        self.processor = Classify(config, logger, self.model_dir)
        self.loader_thread = ModelLoaderThread(self.processor, self.model_dir)
        self.loader_thread.model_ready.connect(self.on_model_loaded)
        self.loader_thread.model_failed.connect(self.on_model_failed)
        self.loader_thread.start()

    def on_model_loaded(self, model, processor):
        # Store loaded model and processor
        self.processor.model = model
        self.processor.processor = processor
        self.model_status_label.setText("Model import complete")
        self.process_button.setEnabled(True)

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

        self.folder_label = QLabel("Destination Folder:")
        self.folder_input = QLineEdit(str(self.folder))
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_folder)

        layout.addWidget(self.folder_label)
        layout.addWidget(self.folder_input)
        layout.addWidget(self.browse_button)

        self.top_layout.addWidget(self.process_button)
        self.top_layout.addWidget(self.drop_down)
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
            label = QtWidgets.QLabel(f"{name.strip()} : 0")
            self.labels[name.strip()] = (label, 0)
            row = i if i < 12 else i - 12
            col = 0 if i < 12 else 1
            grid_container.addWidget(label, row, col)

        layout.addWidget(label_container)
        self.text_output = QtWidgets.QTextEdit()
        self.text_output.setReadOnly(True)
        layout.addWidget(self.text_output)
        self.model_status_label = QLabel("Model is loading in...")
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

    def browse_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if folder:
            self.folder_input.setText(folder)
            self.folder = Path(folder)

    def start_process(self):
        self.process_button.setEnabled(False)

        self.timer_thread = _ClassificationTimer()
        self.timer_thread.time_updated.connect(self.timer_label.setText)
        self.timer_thread.done.connect(self.logger.log_status)
        self.timer_thread.start()

        check_value = self.remove_checkbox.isChecked()
        self.worker = _ClassificationWorker(self.processor, check_value, self.selected_model, self.labels, self.folder_input.text())
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

    def on_process_done(self, location_file_path: Path):
        class GeoScatterWorker(QObject):
            finished = pyqtSignal()
        
            def __init__(self, config, logger, location_file_path, folder):
                from geoscatter import GeoAnalysis
                super().__init__()
                self.geo = GeoAnalysis(config, logger)
                self.path = location_file_path
                self.folder = folder

            def run(self):
                self.geo.geoscatter(self.path, self.folder)
                self.finished.emit()

        self.process_button.setEnabled(True)
        self.timer_threader_2.running = False
        self.threader_2 = QThread()
        self.worker = GeoScatterWorker(self.config, self.logger, location_file_path, self.folder)

        self.worker.moveToThread(self.threader_2)
        self.threader_2.started.connect(self.worker.run)
        self.worker.finished.connect(self.threader_2.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.threader_2.finished.connect(self.threader_2.deleteLater)

        self.threader_2.start()


    