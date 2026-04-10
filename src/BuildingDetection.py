# LAZY IMPORT: TensorFlow is imported inside ObjectDetectionProcessor methods to improve startup time
import numpy as np
from PIL import Image
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal

from config_ import Config
from AppLogger import Logger
from utils import resolve_path

class ObjectDetectionProcessor(QObject):
    progress_updated = pyqtSignal(float)
    log_message = pyqtSignal(str)
    image_saved = pyqtSignal(str)
    # New signal: emits (image_path, list_of_detections) for UI visualization
    visualization_data_ready = pyqtSignal(str, list)
    finished = pyqtSignal()

    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.config = config
        self.logger = logger
        
        # Lazy loading for TensorFlow
        self._tf = None

        self._load_settings()
        self.detector = None # Load lazily in process() to avoid blocking UI
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _ensure_tensorflow_loaded(self):
        """Lazy load TensorFlow only when needed"""
        if self._tf is None:
            import tensorflow as tf
            self._tf = tf
            self.logger.log_status("TensorFlow loaded for Building Detection")

    def _load_settings(self):
        """
        Fetch all BUILDING_DETECTION settings from config (typed).
        """
        # Raw dict (string → string), if you ever need it:
        self.settings = self.config.get_BUILDING_DETECTION_data()

        # Typed getters:
        self.model_path = self.config.get_bd_model_path()
        self.input_dir = self.config.get_bd_input_dir()
        self.output_dir = self.config.get_bd_output_dir()
        self.threshold = self.config.get_bd_threshold()
        self.expand_factor = self.config.get_bd_expand_factor()
        self.min_dim = self.config.get_bd_min_dim()
        self.target_classes = self.config.get_bd_target_classes()

        self.logger.log_status(f"Loaded BUILDING_DETECTION settings:\n"
                               f"  model_path = {self.model_path}\n"
                               f"  input_dir  = {self.input_dir}\n"
                               f"  output_dir = {self.output_dir}\n"
                               f"  threshold = {self.threshold}\n"
                               f"  expand_factor = {self.expand_factor}\n"
                               f"  min_dim = {self.min_dim}\n"
                               f"  target_classes = {self.target_classes}")

    def _load_detector(self):
        """
        Attempt to load the TF SavedModel from model_path. If it fails, log and return None.
        """
        self._ensure_tensorflow_loaded()
        try:
            loaded = self._tf.saved_model.load(resolve_path(self.model_path))
            return loaded.signatures['default']
        except Exception as e:
            self.logger.log_exception(f"Failed to load model at {self.model_path}. Error: {e}")
            return None

    def _expand_box(self, box, img_width, img_height):
        """
        Given a normalized box [ymin, xmin, ymax, xmax], expand it by self.expand_factor,
        then convert to pixel coordinates (clamped to image bounds).
        """
        ymin, xmin, ymax, xmax = box
        box_w = xmax - xmin
        box_h = ymax - ymin

        expand_w = box_w * self.expand_factor
        expand_h = box_h * self.expand_factor

        xmin_exp = max(0, xmin - expand_w)
        ymin_exp = max(0, ymin - expand_h)
        xmax_exp = min(1, xmax + expand_w)
        ymax_exp = min(1, ymax + expand_h)

        return (
            int(xmin_exp * img_width),
            int(ymin_exp * img_height),
            int(xmax_exp * img_width),
            int(ymax_exp * img_height)
        )

    def crop_and_save(self, image: np.ndarray, box, save_path: Path):
        """
        Crop an image (H×W×3 in [0,1]) using a normalized box + expand_factor, then save
        only if both width and height ≥ min_dim.
        """
        img_h, img_w, _ = image.shape
        xmin, ymin, xmax, ymax = self._expand_box(box, img_w, img_h)
        cropped = image[ymin:ymax, xmin:xmax]

        # Discard patches that are too small
        if cropped.shape[0] < self.min_dim or cropped.shape[1] < self.min_dim:
            return

        try:
            cropped_uint8 = (cropped * 255).astype(np.uint8)
            Image.fromarray(cropped_uint8).save(save_path, format="JPEG", quality=90)
        except Exception as e:
            self.logger.log_exception(f"Error saving image to {save_path}: {e}")

    def calculate_iou(self, box1, box2) -> float:
        """
        Compute IoU between two normalized boxes [ymin,xmin,ymax,xmax].
        """
        try:
            y1_1, x1_1, y2_1, x2_1 = box1
            y1_2, x1_2, y2_2, x2_2 = box2

            inter_y1 = max(y1_1, y1_2)
            inter_x1 = max(x1_1, x1_2)
            inter_y2 = min(y2_1, y2_2)
            inter_x2 = min(x2_1, x2_2)

            inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
            area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
            area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
            union_area = area1 + area2 - inter_area
            return inter_area / union_area if union_area > 0 else 0.0
        except Exception as e:
            self.logger.log_exception(f"Failed to calculate IoU. Error: {e}")
            return 0.0

    def _deduplicate_boxes(self, boxes, scores, classes) -> list[dict]:
        """
        - Filter out any detection with score < self.threshold.
        - For remaining boxes, remove duplicates (IoU > 0.5) by keeping the higher‐scoring box.
        - Only keep classes in self.target_classes.
        Returns a list of dicts: {'class': str, 'box': np.ndarray, 'score': float}.
        """
        final_detections: list[dict] = []
        iou_threshold = 0.5

        for idx, score in enumerate(scores):
            if score < self.threshold:
                continue  # skip low‐confidence detections

            class_name = classes[idx].decode('utf-8').capitalize()
            if class_name not in self.target_classes:
                continue

            box = boxes[idx]
            is_duplicate = False

            for det in final_detections:
                if self.calculate_iou(box, det['box']) > iou_threshold:
                    # If this box has higher score, replace the old one
                    if score > det['score']:
                        final_detections.remove(det)
                        final_detections.append({'class': class_name, 'box': box, 'score': score})
                    is_duplicate = True
                    break

            if not is_duplicate:
                final_detections.append({'class': class_name, 'box': box, 'score': score})

        return final_detections

    def _read_and_prepare_image(self, image_path: Path):
        """
        Read image → decode → resize to (3600×3600) → normalize [0,1] → add batch dim. 
        Return a tf.Tensor of shape [1,3600,3600,3] or None on error.
        """
        try:
            image_raw = self._tf.io.read_file(str(image_path))
            image = self._tf.image.decode_image(image_raw, channels=3)
            image_resized = self._tf.image.resize(image, (3600, 3600))
            image_norm = self._tf.cast(image_resized, self._tf.float32) / 255.0
            return self._tf.expand_dims(image_norm, axis=0)
        except Exception as e:
            self.logger.log_exception(f"Error reading image {image_path}: {e}")
            return None

    def process(self):
        """
        Main entrypoint: iterate over all .jpg/.jpeg/.png files in input_dir,
        run detector, dedupe/filter, crop + save, emit progress/log, then finish.
        """
        # Load model here (in worker thread)
        if self.detector is None:
            self.log_message.emit("Loading detection model... (this may take a moment)")
            self.detector = self._load_detector()
            if self.detector is None:
                self.log_message.emit("Failed to load model. Aborting.")
                self.finished.emit()
                return

        image_files = (
            list(self.input_dir.glob("*.jpg")) +
            list(self.input_dir.glob("*.jpeg")) +
            list(self.input_dir.glob("*.png"))
        )

        total_files = len(image_files)
        self.log_message.emit(f"Total files = {total_files}")
        for idx, image_file in enumerate(image_files, start=1):
            progress = float(idx) / total_files if total_files else 0.0
            self.progress_updated.emit(progress * 100)  # emit 0–100
            self.log_message.emit(f"Processing image {image_file.name} ({idx}/{total_files})")

            image_tensor = self._read_and_prepare_image(image_file)
            if image_tensor is None or self.detector is None:
                continue

            try:
                results = self.detector(image_tensor)
                # DEBUG: Log keys to see what the model actually returns
                self.logger.log_status(f"Model output keys: {list(results.keys())}") 
                
                raw_boxes = results['detection_boxes'].numpy()
                raw_scores = results['detection_scores'].numpy().astype(np.float32)

                if 'detection_class_entities' in results:
                    raw_classes = results['detection_class_entities'].numpy()
                elif 'detection_classes' in results:
                    # Fallback for models returning class indices (e.g. COCO)
                    # We need a map. Minimal COCO map for common objects:
                    # Note: Indices are floats in tensor, need cast to int.
                    coco_map = {
                        1: 'Person', 2: 'Bicycle', 3: 'Car', 4: 'Motorcycle', 6: 'Bus', 8: 'Truck',
                        10: 'Traffic light', 13: 'Stop sign', 
                        # Note: COCO does not have 'Building' or 'House'
                    }
                    class_indices = results['detection_classes'].numpy().astype(int)
                    # Convert to byte strings to match existing logic
                    raw_classes = []
                    for idx in class_indices:
                        name = coco_map.get(idx, f"Class_{idx}")
                        raw_classes.append(name.encode('utf-8'))
                    raw_classes = np.array(raw_classes)
                else:
                    raise KeyError("Model output missing 'detection_class_entities' or 'detection_classes'")

                original_image = self._tf.squeeze(image_tensor).numpy()  # [3600×3600×3]
            except Exception as e:
                self.logger.log_exception(f"Detection failed on {image_file.name}: {e}")
                self.log_message.emit(f"Error processing {image_file.name}: {e}")
                continue

            detections = self._deduplicate_boxes(raw_boxes, raw_scores, raw_classes)
            base_name = image_file.stem

            if not detections:
                self.log_message.emit(f"No objects found matching: {self.target_classes}")
            
            # Emit visualization data (path must be string)
            self.visualization_data_ready.emit(str(image_file), detections)

            for i, det in enumerate(detections, start=1):
                save_path = self.output_dir / f"{base_name}-{i}.jpg"
                self.crop_and_save(original_image, det['box'], save_path)
                self.log_message.emit(f"Saved cropped image to {save_path}")
                self.image_saved.emit(str(save_path))

        self.log_message.emit("All image processing complete.")
        self.finished.emit()

