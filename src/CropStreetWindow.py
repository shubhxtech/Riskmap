import os
import json
import cv2
import numpy as np
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QLineEdit, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsLineItem, QCheckBox
from PyQt5.QtGui import QPixmap, QImage, QPen, QPainter
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QPointF, Qt
from config_ import Config
from AppLogger import Logger
from utils import ensure_directory_exists, save_image, resolve_path


### Show what types of photo types are allowed in the file browse dialog
### Multiple models 
# After building detection, labelled data can be used for training ML.
# Add browse folder for output in the building detection as well as others.for loading as well as saving
# Allow changing of hyperparameters
# Upload checkpoint to process model

class ImageProcessorWorker(QObject):
    progress_updated = pyqtSignal(int)
    file_processed = pyqtSignal(str)
    processing_complete = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, config: Config, logger: Logger, save_folder: Path):
        super().__init__()
        self.config = config
        self.logger = logger
        self.is_paused = False
        self.is_cancelled = False
        self.save_folder = save_folder
        ensure_directory_exists(self.save_folder)

        self.supported_files = tuple(
            item.strip() for item in self.config.get_allowed_file_types().split(',')
        )

    def _parts_of_img(self, img, dimensions: tuple[int, int] = (100, 100)) -> list:
        x, y = dimensions
        return [img[0:y, 0:x//2], img[0:y, x//2:x]] if x > 0 and y > 0 else []

    def _save_image_with_coords(self, image, save_folder: Path, name, coordinates=(0, 0)):
        save_path = save_folder/f'{name}_{coordinates}.jpg'
        return save_image(image, save_path, logger=self.logger), save_path

    def _get_all_addresses(self) -> list:
        directory = self.config.get_current_input_folder_process()
        if not directory.exists():
            return []
        files = []
        for ext in self.supported_files:
            files.extend(directory.glob(f"*{ext}"))
        return files

    def _process_file(self, image_path: Path) -> dict:
        size_img = self.config.get_image_size()
        if isinstance(size_img, str):
            size_img = tuple(int(i) for i in size_img.split(','))
        blur_region = self.config.get_blur_size()

        image = cv2.imread(str(image_path))
        if image is None:
            return {"source_file": str(image_path), "saved_files": [], "success": False}

        images = self._parts_of_img(image, (size_img[0], size_img[1] - blur_region))

        saved_files = []
        for x, img in enumerate(images):
            if img is not None:
                success, path = self._save_image_with_coords(img, self.save_folder, name=image_path.stem, coordinates=(0, x))
                if success:
                    saved_files.append(str(path))

        return {
            "source_file": str(image_path),
            "saved_files": saved_files,
            "success": bool(saved_files)
        }

    @pyqtSlot()
    def run(self):
        image_paths = self._get_all_addresses()
        if not image_paths:
            self.error_occurred.emit("No valid image files found.")
            return

        all_metadata = []
        success_count = 0

        metadata_file = self.save_folder/"processed_metadata.json"

        for index, path in enumerate(image_paths):
            while self.is_paused:
                QThread.msleep(100)

            if self.is_cancelled:
                self.logger.log_status("Processing cancelled by user.")
                break

            result = self._process_file(path)
            all_metadata.append(result)

            if result["success"]:
                success_count += 1
                self.file_processed.emit(str(path))

            progress = int(((index + 1) / len(image_paths)) * 100)
            self.progress_updated.emit(progress)

        if not self.is_cancelled:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(all_metadata, f, indent=4)

            self.config.set_input_folder_detection(str(self.save_folder))
            self.processing_complete.emit(success_count)


class ImageCropperView(QGraphicsView):
    def __init__(self,config:Config,  logger: Logger, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.config = config
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.image_item = None
        self.h_line = None
        self.v_line = None
        self.img_height = 100
        self.cv_img = None
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.NoDrag)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    def set_image(self, cv_img, img_height):
        self.scene.clear()
        self.img_height = img_height
        self.cv_img = cv_img
        self._update_display()

    def _update_display(self):
        """
        updates the display
        """
        if self.cv_img is None:
            return

        img = cv2.cvtColor(self.cv_img, cv2.COLOR_BGR2RGB)
        height, width, channels = img.shape
        bytes_per_line = channels * width
        q_img = QImage(img.data, width, height, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        self.scene.clear()

        self.image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.image_item)
        self.fitInView(self.image_item, Qt.KeepAspectRatio)
        self._draw_lines(pixmap.width(), pixmap.height())
        self.config.set_size_of_images(height, width)

    def _draw_lines(self, width, height):
        pen = QPen(Qt.red, 5, Qt.DashLine)

        # Horizontal line (modifiable height)
        y = min(max(0, self.img_height), height)
        y = height-y
        self.h_line = self.scene.addLine(0, y, width, y, pen)

        # Vertical middle line
        x = width // 2
        self.v_line = self.scene.addLine(x, 0, x, height, pen)

    def update_crop_height(self, new_height):
        self.img_height = int(new_height)
        self.logger.log_status(f'new image height = {self.img_height}')
        self._update_display()

class CropWindow(QWidget):
    def __init__(self, config: Config, logger: Logger):
        super().__init__()
        self.config = config
        self.logger = logger
        self.threader = None
        self.worker = None

        self.save_folder = resolve_path(self.config.get_processed_data()["save_folder"])
        os.makedirs(self.save_folder, exist_ok=True)
        
        self.setToolTip("Perform custom image slicing, blurring, or other preprocessing operations before model inference.")
        
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout()           # Main layout (Vertical)
        self.layout_2 = QHBoxLayout()         # Top row layout

        # Inputs and buttons
        self.folder_input = QLineEdit(self)
        self.folder_input.setText(self.config.get_processed_data()["input_folder"])
        self.browse_button = QPushButton("Browse Folder", self)

        self.save_folder_input = QLineEdit(self)
        self.save_folder_input.setText(self.save_folder)
        self.browse_button_save = QPushButton("Browse for Output Folder")

        self.process_button = QPushButton("Start Processing", self)
        self.status_label = QLabel("Status: Idle", self)

        # Column 1 layout
        vert_layout_1 = QVBoxLayout()
        vert_layout_1.addWidget(self.folder_input)
        vert_layout_1.addWidget(self.save_folder_input)
        container_widget_1 = QWidget()
        container_widget_1.setLayout(vert_layout_1)
        self.layout_2.addWidget(container_widget_1)

        # Column 2 layout
        vert_layout_2 = QVBoxLayout()
        vert_layout_2.addWidget(self.browse_button)
        vert_layout_2.addWidget(self.browse_button_save)
        container_widget_2 = QWidget()
        container_widget_2.setLayout(vert_layout_2)
        self.layout_2.addWidget(container_widget_2)

        # Add buttons
        self.layout_2.addWidget(self.process_button)
        self.layout_2.addWidget(self.status_label)

        top_widget = QWidget()
        top_widget.setLayout(self.layout_2)

        self.layout.addWidget(top_widget, stretch=1)

        # Image crop preview and control UI
        self.image_view = ImageCropperView(self.config, self.logger)
        self.layout.addWidget(self.image_view, stretch=3)

        # UI controls for crop height
        controls_layout = QHBoxLayout()
        self.use_custom_crop = QCheckBox("Use custom values?")
        self.use_custom_crop.setChecked(False)

        self.height_input = QLineEdit()
        self.height_input.setText(str(self.config.get_image_size().split(',')[1]))
        self.height_input.setEnabled(False)

        self.save_crop_button = QPushButton("Save Crop Settings")
        self.save_crop_button.setEnabled(False)

        self.height_check_btn = QPushButton()
        self.height_check_btn.setText("Check with new values?")
        self.height_check_btn.setEnabled(False)

        controls_layout.addWidget(self.use_custom_crop)
        controls_layout.addWidget(QLabel("Height:"))
        controls_layout.addWidget(self.height_input)
        controls_layout.addWidget(self.height_check_btn)
        controls_layout.addWidget(self.save_crop_button)

        self.layout.addLayout(controls_layout)

        # Load first image
        self.update_image_display()

        # Connect checkbox and save
        self.use_custom_crop.stateChanged.connect(self.toggle_crop_editing)
        self.save_crop_button.clicked.connect(self.save_crop_values)
        self.height_check_btn.clicked.connect(lambda: self.image_view.update_crop_height(self.height_input.text()))

        # Set main layout
        self.setLayout(self.layout)

        self.browse_button.clicked.connect(self.browse_folder)
        self.browse_button_save.clicked.connect(self.change_save_folder)
        self.process_button.clicked.connect(self.start_processing)
    
    def update_image_display(self):
        input_folder = Path(self.folder_input.text())
        image_paths = list(input_folder.glob("*"))
        self.supported_files = tuple(
            item.strip() for item in self.config.get_allowed_file_types().split(',')
        )
        first_image_path = next((p for p in image_paths if p.suffix.lower() in self.supported_files), None)


        if first_image_path:
            self.logger.log_status(f"Read {str(first_image_path)} for display")
            img = cv2.imread(str(first_image_path))
            height_str = self.config.get_image_size().split(',')[1]
            self.image_view.set_image(img, int(height_str))

    @pyqtSlot()
    def change_save_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output folder")
        if folder:
            self.save_folder_input.setText(folder)            
            self.config.set_save_folder_process(folder)


    @pyqtSlot()
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if folder:
            self.folder_input.setText(folder)
            self.config.set_input_folder_process(folder)
            self.update_image_display()

    @pyqtSlot()
    def start_processing(self):
        self.process_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.status_label.setText("Status: Processing...")

        self.save_folder = Path(resolve_path(self.save_folder_input.text()))

        self.threader = QThread()
        self.worker = ImageProcessorWorker(self.config, self.logger, self.save_folder)
        self.worker.moveToThread(self.threader)

        self.threader.started.connect(self.worker.run)
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.file_processed.connect(self.on_file_processed)
        self.worker.processing_complete.connect(self.on_processing_complete)
        self.worker.error_occurred.connect(self.on_error)

        self.threader.start()

    def toggle_crop_editing(self, state):
        editing = state == Qt.Checked
        self.height_input.setEnabled(editing)
        self.save_crop_button.setEnabled(editing)
        self.height_check_btn.setEnabled(editing)

    def save_crop_values(self):
        try:
            new_height = int(self.height_input.text())
            old_size = self.config.get_image_size().split(',')
            new_size = f"{old_size[0]},{new_height}"
            self.config.set_blur_size(old_size[0]-new_size)
            

            # Update preview
            input_folder = Path(self.folder_input.text())
            image_paths = list(input_folder.glob("*"))
            first_image_path = next((p for p in image_paths if p.suffix.lower() in self.worker.supported_files), None)

            if first_image_path:
                img = cv2.imread(str(first_image_path))
                self.image_view.set_image(img, new_height)

            self.logger.log_status(f"Crop height updated to {new_height}px")

        except Exception as e:
            self.logger.log_status(f"Failed to save crop values: {e}")


    def on_progress(self, progress):
        self.status_label.setText(f"Progress: {progress}%")

    def on_file_processed(self, filename):
        self.logger.log_status(f"Processed: {filename}")

    def on_processing_complete(self, count):
        self.status_label.setText(f"Completed! {count} files processed.")
        self.process_button.setEnabled(True)
        self.browse_button.setEnabled(True)

    def on_error(self, message):
        self.status_label.setText(f"Error: {message}")
        self.process_button.setEnabled(True)
        self.browse_button.setEnabled(True)

