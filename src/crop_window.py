import os
import sys
import json
import cv2
import numpy as np
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QLineEdit, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsLineItem, QCheckBox, QGraphicsDropShadowEffect
from PyQt5.QtGui import QPixmap, QImage, QPen, QPainter, QColor, QFont, QPainterPath, QBrush
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QPointF, Qt, QTimer, QPropertyAnimation, QRectF, QEasingCurve, QParallelAnimationGroup
from config_ import Config
from app_logger import Logger
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
    def __init__(self, config: Config, logger: Logger, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.config = config
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        
        self.img_blur_height = self.config.get_blur_size()
        self.cv_img = None
        
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.NoDrag)
        
        # Animation state
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance_animation)
        self.animation_step = 0
        self.is_animating = True
        
        # Multiple images support
        self.image_list = []
        self.current_image_index = 0
        
        # Graphics Items
        self.full_image_item = None
        self.left_part_item = None
        self.right_part_item = None
        self.blur_cover_item = None
        self.caption_text = None
        
        # Settings
        self.anim_speed = 1200  # ms per phase (1.2 seconds)
        self.timer.start(self.anim_speed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.is_animating:
            self._update_static_display()
        else:
             self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def set_image(self, cv_img, img_height):
        # Support both single image and list of images
        if isinstance(cv_img, list):
            self.image_list = cv_img
            self.cv_img = cv_img[0] if cv_img else None
        else:
            self.image_list = [cv_img] if cv_img is not None else []
            self.cv_img = cv_img
            
        self.current_image_index = 0
        self.img_blur_height = int(img_height)
        
        if self.is_animating:
            self.restart_animation()
        else:
            self._update_static_display()

    def update_crop_height(self, blur_height):
        self.img_blur_height = int(blur_height)
        # Stop animation when user interacts
        self.stop_animation() 
        self._update_static_display()

    def stop_animation(self):
        self.is_animating = False
        self.timer.stop()
        self._update_static_display()

    def restart_animation(self):
        self.is_animating = True
        self.animation_step = 0
        self.timer.start(self.anim_speed)
        self.advance_animation()

    def _update_static_display(self):
        if self.cv_img is None: return
        self.scene.clear()
        
        # Show full image with lines for editing
        pixmap = self._cv_to_pixmap(self.cv_img)
        self.full_image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.full_image_item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        
        # Draw Edit Lines
        pen = QPen(Qt.red, 4, Qt.DashLine)
        h = pixmap.height()
        w = pixmap.width()
        
        # Crop Line
        y = h - self.img_blur_height
        self.scene.addLine(0, y, w, y, pen)
        
        # Split Line
        self.scene.addLine(w/2, 0, w/2, h, pen)
        
        self.fitInView(self.full_image_item, Qt.KeepAspectRatio)

    def advance_animation(self):
        if self.cv_img is None or not self.image_list: 
            return
            
        self.scene.clear()
        
        # Get current image and convert to simple pixmap
        current_cv_img = self.image_list[self.current_image_index]
        base_pixmap = self._cv_to_pixmap(current_cv_img)
        w, h = base_pixmap.width(), base_pixmap.height()
        
        # Apply rounded corners to the MAIN base pixmap
        rounded_pixmap = self._get_rounded_pixmap(base_pixmap, radius=30)
        
        self.scene.setSceneRect(0, 0, w, h)
        
        # Cross-platform font
        _anim_font = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
        title_font = QFont(_anim_font, int(h/22), QFont.Bold)
        desc_font = QFont(_anim_font, int(h/30))
        
        step = self.animation_step % 4
        
        # Helper for stylish text badge
        def add_badge_text(text, x, y, bg_color=QColor(0, 0, 0, 180)):
            # Text item
            t_item = self.scene.addText(text, title_font)
            t_item.setDefaultTextColor(Qt.white)
            
            # Badge background (Round Rect)
            brect = t_item.boundingRect()
            padding = 10
            rect = QRectF(x, y, brect.width() + 2*padding, brect.height())
            
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            
            bg = self.scene.addPath(path, QPen(Qt.NoPen), QBrush(bg_color))
            bg.setZValue(1) # Behind text
            
            t_item.setPos(x + padding, y)
            t_item.setZValue(2)
            return bg

        # Shadow helper for elements inside image
        def add_shadow(item):
            eff = QGraphicsDropShadowEffect()
            eff.setBlurRadius(15)
            eff.setColor(QColor(0,0,0,150))
            eff.setOffset(0, 5)
            item.setGraphicsEffect(eff)

        # Image Counter Badge (Top Right)
        if len(self.image_list) > 1:
            counter_text = f"Image {self.current_image_index + 1} / {len(self.image_list)}"
            # Calculate position based on simplified text width estimate or hardcoded right align
            # Since we can't easily get width before adding, we add standard text first to measure
            dummy = self.scene.addText(counter_text, title_font)
            c_width = dummy.boundingRect().width()
            self.scene.removeItem(dummy)
            add_badge_text(counter_text, w - c_width - 40, 20, QColor(0, 0, 0, 100))

        if step == 0:
            # Phase 1: Input
            item = QGraphicsPixmapItem(rounded_pixmap)
            add_shadow(item)
            self.scene.addItem(item)
            
            add_badge_text("Step 1: Input Source", 20, 20)
            
            self._draw_minimal_progress(w, h, 0, 3)
            
        elif step == 1:
            # Phase 2: Identify Blur
            item = QGraphicsPixmapItem(rounded_pixmap)
            add_shadow(item)
            self.scene.addItem(item)
            
            crop_y = h - self.img_blur_height
            
            # Highlight blur area (using path for rounded bottom corners matches)
            # Simpler: Just overlay rect clipped to shape? 
            # We'll just draw a rect overlay.
            
            blur_rect = self.scene.addRect(0, crop_y, w, self.img_blur_height, 
                                          QPen(Qt.NoPen), QColor(255, 50, 50, 60))
                                          
            # Dashed Line
            line = self.scene.addLine(0, crop_y, w, crop_y, QPen(QColor(255, 255, 255), 2, Qt.DashLine))
            add_shadow(line)
            
            add_badge_text("Step 2: Detect Blur", 20, 20)
            
            # Info badge near cut
            add_badge_text(f"Cut: {self.img_blur_height}px", 20, crop_y - 50, QColor(200, 50, 50, 200))

            self._draw_minimal_progress(w, h, 1, 3)
            
        elif step == 2:
            # Phase 3: Split
            # Create a rounded cropped image
            crop_y = h - self.img_blur_height
            cropped_orig = base_pixmap.copy(0, 0, w, crop_y)
            rounded_cropped = self._get_rounded_pixmap(cropped_orig, 30)
            
            item = QGraphicsPixmapItem(rounded_cropped)
            add_shadow(item)
            self.scene.addItem(item)
            
            # Split Line
            split = self.scene.addLine(w/2, 0, w/2, crop_y, QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            add_shadow(split)
            
            add_badge_text("Step 3: Vertical Split", 20, 20)
            
            self._draw_minimal_progress(w, h, 2, 3)
            
        elif step == 3:
            # Phase 4: Output
            crop_y = h - self.img_blur_height
            cropped_orig = base_pixmap.copy(0, 0, w, crop_y)
            
            w_half = w // 2
            left_orig = cropped_orig.copy(0, 0, w_half, crop_y)
            right_orig = cropped_orig.copy(w_half, 0, w_half, crop_y)
            
            # Round the separated parts
            r_left = self._get_rounded_pixmap(left_orig, 20)
            r_right = self._get_rounded_pixmap(right_orig, 20)
            
            l_item = QGraphicsPixmapItem(r_left)
            r_item = QGraphicsPixmapItem(r_right)
            add_shadow(l_item)
            add_shadow(r_item)
            
            gap = w * 0.04
            l_item.setPos(-gap, 0)
            r_item.setPos(w_half + gap, 0)
            
            self.scene.addItem(l_item)
            self.scene.addItem(r_item)
            
            add_badge_text("Output: Split & Clean", 20, 20, QColor(0, 150, 100, 200))
            
            self._draw_minimal_progress(w, h, 3, 3)
        
        self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.animation_step += 1
        
        if self.animation_step % 4 == 0 and len(self.image_list) > 1:
            self.current_image_index = (self.current_image_index + 1) % len(self.image_list)
            self.cv_img = self.image_list[self.current_image_index]
            
    def _get_rounded_pixmap(self, pixmap, radius=20):
        """Returns a new pixmap with rounded corners"""
        if pixmap.isNull(): return pixmap
        
        rounded = QPixmap(pixmap.size())
        rounded.fill(Qt.transparent)
        
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        path = QPainterPath()
        rect = QRectF(0, 0, pixmap.width(), pixmap.height())
        path.addRoundedRect(rect, radius, radius)
        
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return rounded
    
    def _draw_minimal_progress(self, w, h, current, total):
        """Minimal thin progress bar at bottom"""
        bar_height = 3
        bar_y = h - 10
        
        # Transparent track
        self.scene.addRect(0, bar_y, w, bar_height, QPen(Qt.NoPen), QColor(255, 255, 255, 30))
        
        # Active progress
        rect_width = w / (total + 1)
        x_pos = rect_width * current
        
        # Smooth accent color
        self.scene.addRect(x_pos, bar_y, rect_width, bar_height, 
                          QPen(Qt.NoPen), QColor(10, 140, 207))  # Brand blue

    def _cv_to_pixmap(self, cv_img):
        img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, c = img.shape
        q_img = QImage(img.data, w, h, c*w, QImage.Format_RGB888)
        return QPixmap.fromImage(q_img)

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
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        self.layout_2 = QHBoxLayout()         # Top row layout
        self.layout_2.setSpacing(10)

        # Inputs and buttons
        self.folder_input = QLineEdit(self)
        self.folder_input.setText(self.config.get_processed_data()["input_folder"])
        self.browse_button = QPushButton("Browse Folder", self)

        self.save_folder_input = QLineEdit(self)
        self.save_folder_input.setText(self.save_folder)
        self.browse_button_save = QPushButton("Browse for Output Folder")

        self.process_button = QPushButton("Start Processing", self)
        self.status_label = QLabel("Status: Idle", self)
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Column 1 layout
        vert_layout_1 = QVBoxLayout()
        vert_layout_1.setSpacing(5)
        vert_layout_1.addWidget(self.folder_input)
        vert_layout_1.addWidget(self.save_folder_input)
        container_widget_1 = QWidget()
        container_widget_1.setLayout(vert_layout_1)
        self.layout_2.addWidget(container_widget_1)

        # Column 2 layout
        vert_layout_2 = QVBoxLayout()
        vert_layout_2.setSpacing(5)
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
        controls_layout.setSpacing(10)
        self.use_custom_crop = QCheckBox("Use custom values?")
        self.use_custom_crop.setChecked(False)

        self.height_input = QLineEdit()
        self.height_input.setText(str(self.config.get_blur_size()))
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
        
        # Load up to 5 images for animation
        valid_images = [p for p in image_paths if p.suffix.lower() in self.supported_files][:5]
        
        if valid_images:
            self.logger.log_status(f"Loaded {len(valid_images)} images for animation")
            image_list = []
            for img_path in valid_images:
                img = cv2.imread(str(img_path))
                if img is not None:
                    image_list.append(img)
            
            if image_list:
                blur_height = self.config.get_blur_size()
                self.image_view.set_image(image_list, blur_height)

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
        
        if editing:
            self.image_view.stop_animation()
        else:
            self.image_view.restart_animation()

    def save_crop_values(self):
        try:
            new_blur_height = self.height_input.text()
            self.config.set_blur_size(new_blur_height)
            
            # Update preview
            input_folder = Path(self.folder_input.text())
            image_paths = list(input_folder.glob("*"))

            self.supported_files = tuple(
            item.strip() for item in self.config.get_allowed_file_types().split(',')
            )
            first_image_path = next((p for p in image_paths if p.suffix.lower() in self.supported_files), None)

            if first_image_path:
                img = cv2.imread(str(first_image_path))
                self.image_view.set_image(img, int(new_blur_height))

            self.logger.log_status(f"Crop blur height updated to {new_blur_height}px")

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
        self.threader.terminate()

    def on_error(self, message):
        self.status_label.setText(f"Error: {message}")
        self.process_button.setEnabled(True)
        self.browse_button.setEnabled(True)

