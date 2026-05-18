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
        self.torch = None  # Loaded lazily later
        self._user_device = device
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

        self.device = None  # Will be set in instantiate_model

    def instantiate_model(self):
        model_path = str(self.model_dir)

        # ── Keras / TensorFlow path ───────────────────────────────────────────
        if model_path.endswith('.keras') or model_path.endswith('.h5'):
            self.model_type = "keras"
            self.logger.log_status(f"Loading Keras model from {model_path}…")
            try:
                import tensorflow as tf
            except ImportError:
                raise RuntimeError(
                    "TensorFlow is not installed on this machine.\n"
                    "Run: pip install tensorflow"
                )
            self.tf = tf
            self.torch = None  # not needed for Keras

            # 1. Disable mixed-precision globally so the model loads on CPU/any GPU
            try:
                tf.keras.mixed_precision.set_global_policy("float32")
            except Exception:
                pass

            # 2. Try native load; if it fails try safe_format=False (legacy HDF5)
            model = None
            load_errors = []
            for kwargs in [
                {},                            # default (tries SavedModel then HDF5)
                {"compile": False},            # skip optimizer restore — fixes legacy.Adam crash
                {"compile": False, "safe_mode": False},  # TF 2.13+
            ]:
                try:
                    model = tf.keras.models.load_model(model_path, **kwargs)
                    self.logger.log_status(
                        f"Keras model loaded (kwargs={kwargs or 'default'})"
                    )
                    break
                except Exception as e:
                    load_errors.append(f"  attempt {len(load_errors)+1}: {e}")

            if model is None:
                detail = "\n".join(load_errors)
                raise RuntimeError(
                    f"Failed to load Keras model '{model_path}' after all attempts:\n{detail}\n"
                    "Tip: Re-train the model on this machine, or export it with:\n"
                    "  model.save('my_model.keras', include_optimizer=False)"
                )

            # 3. Cast all layers to float32 so inference works on any platform
            try:
                for layer in model.layers:
                    layer_cfg = layer.get_config()
                    if layer_cfg.get("dtype") == "float16":
                        layer._dtype_policy = tf.keras.mixed_precision.Policy("float32")
            except Exception:
                pass  # non-critical — carry on

            self.logger.log_status("Keras classification weights loaded successfully")
            return model, None  # No processor needed for Keras

        # ── PyTorch / HuggingFace BEiT path ──────────────────────────────────
        self.model_type = "pytorch"
        try:
            import torch
        except ImportError:
            raise RuntimeError(
                "PyTorch is not installed on this machine.\n"
                "Install from https://pytorch.org/get-started/locally/"
            )
        self.torch = torch

        # Safe cross-platform device selection
        if self._user_device:
            self.device = self._user_device
        else:
            if torch.cuda.is_available():
                self.device = torch.device("cuda")
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self.device = torch.device("mps")
            else:
                self.device = torch.device("cpu")
        self.logger.log_status(f"Using device: {self.device}")

        from transformers import BeitForImageClassification, BeitImageProcessor

        # Online-first, local-cache fallback
        for local_only in (False, True):
            try:
                model = BeitForImageClassification.from_pretrained(
                    "microsoft/beit-base-patch16-224-pt22k-ft22k",
                    num_labels=len(self.class_names),
                    ignore_mismatched_sizes=True,
                    local_files_only=local_only,
                    use_safetensors=True,
                )
                break
            except Exception as e:
                if local_only:  # both attempts failed
                    raise RuntimeError(
                        f"BEiT architecture download failed: {e}\n"
                        "Check internet connection or run with a cached copy."
                    )

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Model file not found at exact path:\n{os.path.abspath(model_path)}\n\n"
                f"Troubleshooting on Windows:\n"
                f"1. Make sure you placed it in the ROOT 'assets' folder, NOT 'src/assets'\n"
                f"2. Windows hides file extensions by default. Your file might actually be named 'best_model.pth.pth'."
            )

        # Load weights with safe cross-platform map_location
        try:
            checkpoint = torch.load(
                model_path,
                map_location=self.device,
                weights_only=False,
            )
            state = checkpoint.get("model_state_dict", checkpoint)
            model.load_state_dict(state, strict=False)
            self.logger.log_status("Custom PyTorch weights loaded successfully")
        except Exception as e:
            self.logger.log_exception(f"Error loading PyTorch weights from {model_path}: {e}")
            raise

        model.to(self.device).eval()

        for local_only in (False, True):
            try:
                processor = BeitImageProcessor.from_pretrained(
                    "microsoft/beit-base-patch16-224-pt22k-ft22k",
                    local_files_only=local_only,
                )
                break
            except Exception as e:
                if local_only:
                    raise RuntimeError(f"BEiT processor download failed: {e}")

        return model, processor

    def make_folders(self):
        names = self.config.get_foldr_names_classif().split(',')
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
            if getattr(self, 'model_type', 'pytorch') == 'keras':
                import numpy as np

                # Resolve input size safely — avoid AttributeError on unbuilt models
                try:
                    shape = self.model.input_shape  # (None, H, W, C)
                    target_size = (int(shape[1]), int(shape[2]))
                    if None in target_size or 0 in target_size:
                        raise ValueError("Unresolved input shape")
                except Exception:
                    target_size = (224, 224)  # safe universal fallback

                image = self.tf.keras.preprocessing.image.load_img(
                    image_path, target_size=target_size
                )
                input_arr = self.tf.keras.preprocessing.image.img_to_array(image)
                # Normalize to [0,1] so float32 inference is stable on all platforms
                input_arr = input_arr / 255.0
                input_arr = np.expand_dims(input_arr, axis=0).astype("float32")

                predictions = self.model.predict(input_arr, verbose=0)
                predicted_class = int(np.argmax(predictions, axis=1)[0])
                confidence = float(predictions[0][predicted_class])
                return predicted_class, confidence
            else:
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
            if f.suffix.lower() in self.image_extensions:
                image_files.append(f)

        # Smart fallback: check if 'Unique' subfolder (created by Duplicates filter) exists
        if not image_files:
            unique_subfolder = self.input_folder / "Unique"
            if unique_subfolder.is_dir():
                self.logger.log_status(f"No images found directly in {self.input_folder}. Looking inside 'Unique' folder...")
                for f in unique_subfolder.glob("*"):
                    if f.suffix.lower() in self.image_extensions:
                        image_files.append(f)

        # Recursive fallback: if still empty, find all matching files recursively
        if not image_files:
            self.logger.log_status(f"No images found. Performing recursive search in {self.input_folder}...")
            for f in self.input_folder.rglob("*"):
                if f.is_file() and f.suffix.lower() in self.image_extensions:
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

                # Safe bounds check for class names (prevents IndexError if PyTorch returns 21k classes)
                if predicted_class >= len(self.class_names):
                    class_name = self.class_names[0] if len(self.class_names) > 0 else "Unknown"
                else:
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
                if not uncertain and class_name.strip() in labels:
                    # Update label text using display mapping
                    display_name = DISPLAY_MAPPING.get(class_name.strip(), class_name.strip())
                    labels[class_name.strip()][0].setText(f"{display_name}: {stats['class_counts'][class_name]}")
                    
                progress_callback(((stats['processed'] + stats['failed'])/ stats['total']) * 100)

                self.logger.log_status(f"image_path.name: {image_path.name}")
                try:
                    lat, lon = image_path.name.split(' ')[3:5]
                except ValueError:
                    lat, lon = "0.0", "0.0"
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
        self.model_ext = params.get("model_ext", ".pth")
        
        # Build an internal registry of model Name -> Absolute Path
        self.model_registry = {}
        
        # 1. Register default models from config
        self.available_models = params["available_models"].split(',')
        for am in self.available_models:
            self.model_registry[am] = resolve_path(os.path.join(self.model_path, am + self.model_ext))
            
        # 2. Auto-discover trained custom Keras models in current directory
        try:
            src_dir = Path(__file__).parent
            for ext in ('*.h5', '*.keras'):
                for model_file in src_dir.glob(ext):
                    # Only register if it has a classes sidecar (e.g. my_model.h5.classes.json)
                    sidecar = model_file.with_name(model_file.name + '.classes.json')
                    if sidecar.exists():
                        name = model_file.name
                        self.model_registry[name] = str(model_file.resolve())
        except Exception as e:
            self.logger.log_exception(f"Error auto-discovering models: {e}")

        self.input_folder = params["parent_folder"]
        self.input_folder_name = Path(self.input_folder).name

        self.output_folder = params["output_folder"]

        # Determine which model to select by default (prefer 'best_model', then custom Keras models)
        self.default_model_name = list(self.model_registry.keys())[0]
        if "best_model" in self.model_registry:
            self.default_model_name = "best_model"
        else:
            for name in self.model_registry.keys():
                if name.endswith('.h5') or name.endswith('.keras'):
                    self.default_model_name = name
                    break
                
        self.setToolTip("Use classification models to assign labels to images based on their visual content.")
        self.init_ui()
        self.process_button.setEnabled(False)
        
        self.model_dir = self.model_registry[self.default_model_name]
        self.logger.log_status(f"Loaded in {self.model_dir}")

        self.processor = Classify(config, logger, self.model_dir)
        self.loader_thread = None  # Created on-demand — don't load at startup
        self._model_loaded = False

        # Sync class labels to the auto-selected model AFTER processor is created
        self._refresh_class_labels_for_model(self.default_model_name)

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
        self.drop_down.addItems(list(self.model_registry.keys()))
        # Block signals during setup to prevent on_select firing before processor is initialized
        self.drop_down.blockSignals(True)
        self.drop_down.setCurrentText(self.default_model_name)
        self.drop_down.blockSignals(False)
        self.selected_model = self.model_registry.get(self.default_model_name, list(self.model_registry.values())[0])
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
        self.model_status_label.setWordWrap(True)
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
        """Called whenever the model dropdown changes — update path AND class labels."""
        if text in self.model_registry:
            self.selected_model = self.model_registry[text]
        else:
            self.selected_model = self.model_path + text + self.model_ext # Fallback
            
        # VERY IMPORTANT: update processor and internal dir!
        self.model_dir = self.selected_model
        if hasattr(self, 'processor'):
            self.processor.model_dir = self.selected_model
            
        # Try to refresh labels: first check sidecar, then config
        self._refresh_class_labels_for_model(text)
        # Mark model as needing reload
        self._model_loaded = False
        self.model_status_label.setText(
            f"Model changed to '{text}' — click '\u21af Load Model' to load."
        )

    def _refresh_class_labels_for_model(self, model_name: str):
        """Update the class label grid to match the selected model."""
        import json, os as _os
        
        # 1. Check for local sidecar (e.g. my_model.h5 -> my_model.h5.classes.json)
        sidecar_path = None
        if model_name in self.model_registry:
            model_path = self.model_registry[model_name]
            sidecar_path = model_path + '.classes.json'
        else:
            sidecar_path = _os.path.join(self.model_path, model_name + '.classes.json')
        if _os.path.exists(sidecar_path):
            try:
                with open(sidecar_path) as f:
                    data = json.load(f)
                self._set_class_labels(data["class_names"])
                return
            except Exception:
                pass

        # 2. Fallback: config model_data (for models added via 'Add Model' dialog)
        try:
            model_data = self.config.get_model_data()
            if model_name in model_data:
                self._set_class_labels(list(model_data[model_name]['classes']))
                return
        except Exception:
            pass

        # 3. Final fallback: use the default class_names from config
        try:
            default = self.config.get_classification_data()["class_names"].split(',')
            self._set_class_labels([n.strip() for n in default])
        except Exception:
            pass

    def _set_class_labels(self, class_names: list):
        """Rebuild the class-count grid in place."""
        if hasattr(self, 'processor'):
            self.processor.class_names = class_names

        # Find and clear existing label_container
        layout = self.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QtWidgets.QWidget):
                w = item.widget()
                # Identify by having a QGridLayout child
                if isinstance(w.layout(), QtWidgets.QGridLayout):
                    layout.removeWidget(w)
                    w.deleteLater()
                    break

        label_container = QtWidgets.QWidget()
        grid_container = QtWidgets.QGridLayout(label_container)
        self.labels = {}
        for i, name in enumerate(class_names):
            clean_name = name.strip()
            display_name = DISPLAY_MAPPING.get(clean_name, clean_name)
            label = QtWidgets.QLabel(f"{display_name} : 0")
            self.labels[clean_name] = (label, 0)
            row = i if i < 12 else i - 12
            col = 0 if i < 12 else 1
            grid_container.addWidget(label, row, col)
        # Insert before the text_output widget
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() is self.text_output:
                layout.insertWidget(i, label_container)
                return
        layout.addWidget(label_container)

    def add_trained_model(self, model_path: str, class_names: list):
        """Called automatically after training completes.
        Adds the freshly trained model to the dropdown and refreshes the class grid.
        """
        import os as _os
        model_name = _os.path.basename(model_path)

        # Register it internally with absolute path
        self.model_registry[model_name] = model_path

        # Add to dropdown if not already present
        existing = [self.drop_down.itemText(i) for i in range(self.drop_down.count())]
        if model_name not in existing:
            self.drop_down.blockSignals(True)
            self.drop_down.addItem(model_name)
            self.drop_down.blockSignals(False)

        # Switch to the new model
        self.drop_down.blockSignals(True)
        self.drop_down.setCurrentText(model_name)
        self.drop_down.blockSignals(False)

        # Update the internal path to the full absolute path
        self.selected_model = model_path

        # Refresh class labels immediately
        self._set_class_labels(class_names)

        # Mark model as needing reload
        self._model_loaded = False
        self.model_status_label.setText(
            f"\u2705 Newly trained '{model_name}' added ({len(class_names)} classes). "
            f"Click '\u21af Load Model' to load."
        )

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
        self.loader_thread = ModelLoaderThread(self.processor, self.selected_model)
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
        # Synchronize UI input/output folder text fields to the processor
        self.processor.parent_folder = self.input_folder_input.text()
        self.processor.output_folder = self.output_folder_input.text()
        
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
        # Graceful shutdown instead of unsafe terminate()
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(5000)
        if hasattr(self, 'timer_thread'):
            self.timer_thread.running = False
            self.timer_thread.quit()
            self.timer_thread.wait(2000)
        self.process_button.setEnabled(True)
        self.model_status_label.setText("Processing Complete!")