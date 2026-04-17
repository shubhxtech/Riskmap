import os
import sys
from typing import Union
StrOrBytesPath = Union[str, bytes, os.PathLike]

# LAZY IMPORTS: TensorFlow and matplotlib are imported inside Trainer class to improve startup time
# These heavy libraries (~5-10 seconds load time) are only loaded when Model Training tab is accessed

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QComboBox, QProgressBar, QMessageBox, QGridLayout, QGroupBox, QScrollArea, QSizePolicy, QSplitter,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QDialog, QHBoxLayout
)
from PyQt5.QtCore import QObject, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QImage, QColor, QBrush, QPen, QFont
from PyQt5 import QtGui, QtCore

from pathlib import Path
from config_ import Config
from app_logger import Logger
from utils import resolve_path




class DatasetGuidelineDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dataset Guidelines")
        self.resize(500, 400)
        # No hardcoded stylesheet -> Inherits BRAND_THEME from App
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Header
        header = QLabel("Dataset Structure Requirements")
        # Use Brand Blue or Dark Grey
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #1DA1F2;") 
        layout.addWidget(header)
        
        # Content
        content = QLabel()
        content.setWordWrap(True)
        content.setStyleSheet("font-size: 14px; line-height: 1.4; color: #333;")
        content.setTextFormat(Qt.RichText)
        content.setText("""
            <p>To ensure successful training, your dataset folder must interpret the subdirectory names as class labels.</p>
            <p><strong>Required Structure:</strong></p>
            <div style="background-color: #f0f0f0; padding: 15px; border-radius: 5px; font-family: Consolas, monospace; border: 1px solid #ccc; color: #333;">
                📂 <strong>Selected Folder</strong><br>
                &nbsp;├── 📂 <strong>Class_A</strong> (e.g., 'Brick_House')<br>
                &nbsp;│&nbsp;&nbsp;&nbsp;├── 🖼️ image_01.jpg<br>
                &nbsp;│&nbsp;&nbsp;&nbsp;└── ...<br>
                &nbsp;├── 📂 <strong>Class_B</strong> (e.g., 'Mud_House')<br>
                &nbsp;│&nbsp;&nbsp;&nbsp;├── 🖼️ image_01.jpg<br>
                &nbsp;│&nbsp;&nbsp;&nbsp;└── ...<br>
            </div>
            <p style="color: #666; font-size: 12px;"><i>Note: File formats supported: JPG, PNG, JPEG.</i></p>
        """)
        layout.addWidget(content)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        open_btn = QPushButton("Continue to Browse")
        open_btn.setObjectName("ActionButton") # Matches BRAND_THEME
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        
        layout.addLayout(btn_layout)


class Trainer(QWidget):
    def __init__(self, config=None, logger=None):
        super().__init__()
        self.logger = logger if logger else Logger()
        self.config = config if config else Config()
        
        # Lazy loading flags for heavy libraries
        self._tf = None
        self._keras = None
        self._matplotlib_loaded = False
        self._plt = None
        self._FigureCanvas = None
        self._NavigationToolbar = None
        self._Figure = None
        
        # Debounce timer to prevent lag when typing
        self.viz_update_timer = QtCore.QTimer()
        self.viz_update_timer.setSingleShot(True)
        self.viz_update_timer.timeout.connect(self._do_update_viz)
        
        self.init_ui()
        # Initial viz
        self.update_model_viz()
    
    def _ensure_tensorflow_loaded(self):
        """Lazy load TensorFlow and Keras only when needed"""
        if self._tf is None:
            import tensorflow as tf
            from tensorflow import keras
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import Dense, Flatten, Dropout
            from tensorflow.keras.optimizers import Adam
            
            self._tf = tf
            self._keras = keras
            self.Sequential = Sequential
            self.Dense = Dense
            self.Flatten = Flatten
            self.Dropout = Dropout
            self.Adam = Adam
            self.logger.log_status("TensorFlow loaded successfully")
    
    def _ensure_matplotlib_loaded(self):
        """Lazy load matplotlib only when needed"""
        if not self._matplotlib_loaded:
            import matplotlib
            matplotlib.use('Qt5Agg')
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
            from matplotlib.figure import Figure
            
            self._plt = plt
            self._FigureCanvas = FigureCanvas
            self._NavigationToolbar = NavigationToolbar
            self._Figure = Figure
            self._matplotlib_loaded = True
            self.logger.log_status("Matplotlib loaded successfully")

    def init_ui(self):
        main_layout = QGridLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 1. Top-Left: Parameters (Compact)
        params_group = self._create_params_panel()
        main_layout.addWidget(params_group, 0, 0)
        
        # 2. Middle-Left: Structure
        self.structure_group = self._create_structure_panel()
        main_layout.addWidget(self.structure_group, 1, 0)

        # 3. Bottom-Left: Logs
        logs_group = self._create_logs_panel()
        main_layout.addWidget(logs_group, 2, 0)

        # 4. Top-Right: Model Visualization
        viz_group = self._create_viz_panel()
        main_layout.addWidget(viz_group, 0, 1)

        # 5. Bottom-Right: Real-time Graph (Span 2 rows to match left side height roughly)
        graph_group = self._create_graph_panel()
        main_layout.addWidget(graph_group, 1, 1, 2, 1) # Span row 1 and 2

        # Layout stretches (Right side gets more width)
        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 2)
        
        # Row stretches
        # Row stretches
        main_layout.setRowStretch(0, 0) # Params - auto height
        main_layout.setRowStretch(1, 5) # Structure (50%)
        main_layout.setRowStretch(2, 5) # Logs (50%)

        self.setLayout(main_layout)

    def _create_params_panel(self):
        group = QGroupBox("Training Parameters")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form_layout = QGridLayout()
        
        # Reduced spacing for compactness
        form_layout.setVerticalSpacing(5)
        
        # --- Row 1: Data ---
        self.path_input = QLineEdit()
        self.browse_btn = QPushButton("📂")
        self.browse_btn.setFixedSize(30, 25)
        self.browse_btn.clicked.connect(self.browse_folder)
        self._add_param_row(form_layout, 0, "Dataset:", self.path_input, self.browse_btn)

        # --- Row 2: Model & Name ---
        self.model_selector = QComboBox()
        self.model_selector.addItems(["ResNet50", "MobileNetV2", "InceptionV3"])
        self.model_selector.currentIndexChanged.connect(self._do_update_viz)  # Immediate update for dropdown
        self._add_param_row(form_layout, 1, "Base Model:", self.model_selector)
        
        self.model_name_input = QLineEdit("my_model.h5")
        self._add_param_row(form_layout, 2, "Save Name:", self.model_name_input)

        # --- Row 3: Hyperparams ---
        self.epochs_input = QLineEdit("10")
        self._add_param_row(form_layout, 3, "Epochs:", self.epochs_input)
        
        self.batch_size_input = QLineEdit("32")
        self._add_param_row(form_layout, 4, "Batch Size:", self.batch_size_input)

        self.lr_input = QLineEdit("0.001")
        self._add_param_row(form_layout, 5, "Learning Rate:", self.lr_input)
        
        # --- Row 4: Config ---
        self.img_height_input = QLineEdit("224")
        self._add_param_row(form_layout, 6, "Img Height:", self.img_height_input)
        
        self.img_width_input = QLineEdit("224")
        self._add_param_row(form_layout, 7, "Img Width:", self.img_width_input)

        self.val_split_input = QLineEdit("0.2")
        self._add_param_row(form_layout, 8, "Val Split:", self.val_split_input)
        
        # --- Row 5: Customization ---
        self.layer_config_input = QLineEdit("128, 64") # Default custom layers
        self.layer_config_input.textChanged.connect(self.update_model_viz)  # Debounced update
        self._add_param_row(form_layout, 9, "Custom Layers:", self.layer_config_input)
        
        self.freeze_input = QComboBox()
        self.freeze_input.addItems(["True", "False"])
        self._add_param_row(form_layout, 10, "Freeze Base:", self.freeze_input)

        self.optimizer_selector = QComboBox()
        self.optimizer_selector.addItems(["adam", "sgd", "rmsprop"])
        self._add_param_row(form_layout, 11, "Optimizer:", self.optimizer_selector)

        self.loss_selector = QComboBox()
        self.loss_selector.addItems(["sparse_categorical_crossentropy", "categorical_crossentropy"])
        self._add_param_row(form_layout, 12, "Loss Function:", self.loss_selector)
        
        self.seed_input = QLineEdit("42")
        self._add_param_row(form_layout, 13, "Seed:", self.seed_input)
        
        self.plot_name_input = QLineEdit("training_plot.png")
        self._add_param_row(form_layout, 14, "Plot Filename:", self.plot_name_input)

        # --- Buttons ---
        self.start_btn = QPushButton("Start Training")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.start_btn.clicked.connect(self.start_training)
        
        self.save_config_btn = QPushButton("Save Config")
        self.save_config_btn.clicked.connect(self.save_config)

        # Button Layout
        btn_layout = QGridLayout() # Sub-grid for buttons
        btn_layout.addWidget(self.start_btn, 0, 0, 1, 2)
        btn_layout.addWidget(self.save_config_btn, 1, 0, 1, 2)
        
        # Add everything to main vertical layout of content
        content_layout = QVBoxLayout()
        content_layout.addLayout(form_layout)
        content_layout.addLayout(btn_layout)
        content_layout.addStretch() # Push everything up
        
        content.setLayout(content_layout)
        scroll.setWidget(content)
        
        layout = QVBoxLayout()
        layout.addWidget(scroll)
        group.setLayout(layout)
        return group

    def _add_param_row(self, layout, row, label_text, widget, extra_widget=None):
        lbl = QLabel(label_text)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(lbl, row, 0)
        layout.addWidget(widget, row, 1)
        if extra_widget:
            layout.addWidget(extra_widget, row, 2)

    def _create_logs_panel(self):
        group = QGroupBox("Training Logs")
        layout = QVBoxLayout()
        # We need a QTextEdit
        from PyQt5.QtWidgets import QTextEdit
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("font-family: 'SF Mono', 'Menlo', 'Consolas', monospace; font-size: 10px; background-color: #f0f0f0;")
        
        self.progress = QProgressBar()
        
        layout.addWidget(self.log_output)
        layout.addWidget(self.progress)
        group.setLayout(layout)
        return group

    def _create_viz_panel(self):
        group = QGroupBox("Model Architecture")
        layout = QVBoxLayout()
        layout.setSpacing(5)  # Reduce spacing
        
        # Info Label - readable size
        self.model_info_label = QLabel("Initializing...")
        self.model_info_label.setStyleSheet(
            "font-size: 11px; font-weight: 500; color: #444; padding: 5px; background-color: #f5f5f5; border-radius: 3px;"
        )
        self.model_info_label.setAlignment(Qt.AlignCenter)
        self.model_info_label.setWordWrap(False)  # Single line
        layout.addWidget(self.model_info_label)

        # Image Label - gets more space now
        self.model_viz_label = QLabel("Model visualization will appear here.")
        self.model_viz_label.setAlignment(Qt.AlignCenter)
        self.model_viz_label.setStyleSheet("background-color: white; border: 1px dashed gray;")
        self.model_viz_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.model_viz_label, 1)  # Stretch factor 1
        
        group.setLayout(layout)
        return group

    def _create_graph_panel(self):
        # Lazy load matplotlib when graph panel is created
        self._ensure_matplotlib_loaded()
        
        group = QGroupBox("Real-time Training Metrics")
        layout = QVBoxLayout()
        
        # Matlab-Style Figure
        self.figure = self._Figure(figsize=(5, 4), dpi=100)
        self.figure.patch.set_facecolor('#F0F0F0') # Matlab Gray
        
        self.canvas = self._FigureCanvas(self.figure)
        self.toolbar = self._NavigationToolbar(self.canvas, self) # Interactive Toolbar
        
        self.ax_acc = self.figure.add_subplot(121)
        self.ax_loss = self.figure.add_subplot(122)
        
        # Set axes bg to white
        self.ax_acc.set_facecolor('white')
        self.ax_loss.set_facecolor('white')
        
        self.figure.tight_layout()

        layout.addWidget(self.toolbar) # Add toolbar at top
        layout.addWidget(self.canvas)
        group.setLayout(layout)
        return group

    # Placeholder for browse_folder (keep existing logic or simplified)
    def browse_folder_placeholder(self):
        pass

    def _create_structure_panel(self):
        group = QGroupBox("Dataset Structure")
        layout = QVBoxLayout()
        
        self.structure_tree = QTreeWidget()
        self.structure_tree.setHeaderLabels(["Class Name", "Images"])
        self.structure_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.structure_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.structure_tree.setStyleSheet("font-size: 11px;")
        
        layout.addWidget(self.structure_tree)
        group.setLayout(layout)
        return group

    def browse_folder(self):
        try:
            # 1. Custom Guideline Dialog
            dialog = DatasetGuidelineDialog(self)
            
            if dialog.exec_() == QDialog.Accepted:
                folder = QFileDialog.getExistingDirectory(self, "Select Dataset Folder")
                if folder:
                    self.path_input.setText(folder)
                    self.visualize_dataset(folder)
        except Exception as e:
            self.logger.log_exception(f'An error occured while browsing for input folder. {e}')

    def visualize_dataset(self, folder_path):
        """Populates the structure tree with folder contents."""
        try:
            self.structure_tree.clear()
            folder = Path(folder_path)
            
            total_images = 0
            classes = []
            
            # Iterate through subdirectories
            for sub_dir in sorted(folder.iterdir()):
                if sub_dir.is_dir():
                    # Count images (extensions logic same as training loader usually)
                    images = list(sub_dir.glob('*.jpg')) + list(sub_dir.glob('*.png')) + list(sub_dir.glob('*.jpeg'))
                    count = len(images)
                    total_images += count
                    
                    item = QTreeWidgetItem([sub_dir.name, str(count)])
                    # Color code if empty
                    if count == 0:
                        item.setForeground(1, QBrush(QColor("red")))
                    
                    self.structure_tree.addTopLevelItem(item)
                    classes.append(sub_dir.name)
            
            if not classes:
                 item = QTreeWidgetItem(["No subfolders found!", "0"])
                 item.setForeground(0, QBrush(QColor("red")))
                 self.structure_tree.addTopLevelItem(item)
            
            self.logger.log_status(f"Loaded dataset: {len(classes)} classes, {total_images} images.")
            
        except Exception as e:
            self.logger.log_exception(f"Error visualizing dataset: {e}")


    def save_config(self):
        try:
            config = self.config.read_config()
            config["Model_Training"] = {
                "data_dir": self.path_input.text(),
                "epochs": self.epochs_input.text(),
                "learning_rate": self.lr_input.text(),
                "base_model": self.model_selector.currentText(),
                "custom_layers": self.layer_config_input.text(),
                "val_split": self.val_split_input.text(),
                "seed": self.seed_input.text(),
                "img_height": self.img_height_input.text(),
                "img_width": self.img_width_input.text(),
                "batch_size": self.batch_size_input.text(),
                "freeze_original_layers": self.freeze_input.currentText(),
                "optimizer": self.optimizer_selector.currentText(),
                "loss": self.loss_selector.currentText(),
                "model_name": self.model_name_input.text(),
                "plot_name": self.plot_name_input.text()
            }
            with open(self.config.config_file, 'w') as f:
                config.write(f)
        except Exception as e:
            self.logger.log_exception(f'An error occured while saving to config from Training. {e}')

    def start_training(self):
        try:
            # Initialize graph data
            self.train_acc = []
            self.val_acc = []
            self.train_loss = []
            self.val_loss = []
            self.epochs_list = []
            
            # Clear axes
            self.ax_acc.clear()
            self.ax_loss.clear()
            
            # Draw empty model viz
            self.update_model_viz()

            self.thread = QThread()
            self.worker = TrainWorker(self)

            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.progress_signal.connect(self.progress.setValue)
            self.worker.message_signal.connect(lambda msg: QMessageBox.information(self, "Success", msg))
            self.worker.error_signal.connect(lambda err: self.logger.log_exception(f"Training error: {err}"))
            
            # Connect log signal to log window
            self.worker.log_signal.connect(self.log_output.append)
            # Connect real-time graph
            self.worker.epoch_end_signal.connect(self.update_rt_graph)
            
            self.worker.finished_signal.connect(self.thread.quit)
            self.worker.finished_signal.connect(self.worker.deleteLater)
            # self.worker.plot_ready_signal.connect(self.open_plot_image) # No longer needed as we have live plot
            self.thread.finished.connect(self.thread.deleteLater)
            
            self.thread.start()
        except Exception as e:
            self.logger.log_exception(f'An error occurred while starting the training thread. {e}')

    def draw_horizontal_model_viz(self, layers_list, base_model_name):
        """Draws a refined Neural Network style visualization with dynamic sizing and auto-crop."""
        try:
            # --- Settings ---
            layer_spacing = 160  # Space between layers
            node_radius = 12
            node_diameter = node_radius * 2
            
            # Setup Canvas - Use a fixed large canvas to ensure high resolution calculation
            # We will crop it at the end, so size just needs to be "big enough"
            canvas_width = 2000
            canvas_height = 1000
            
            pixmap = QPixmap(canvas_width, canvas_height)
            pixmap.fill(QColor(255, 255, 255))
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
            
            center_y = canvas_height // 2
            
            # --- Fonts ---
            _viz_font = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
            font_title = QtGui.QFont(_viz_font, 10, QtGui.QFont.Bold)
            font_label = QtGui.QFont(_viz_font, 8)
            font_small = QtGui.QFont(_viz_font, 7)
            
            # --- 1. Analyze Layers & Calculate Layout ---
            layer_meta = []
            current_x = 50 # Start with some padding
            
            # Track bounds for auto-crop
            min_x, max_x = canvas_width, 0
            min_y, max_y = canvas_height, 0
            
            def update_bounds(x, y, w, h):
                nonlocal min_x, max_x, min_y, max_y
                min_x = min(min_x, x)
                max_x = max(max_x, x + w)
                min_y = min(min_y, y)
                max_y = max(max_y, y + h)

            for i, layer in enumerate(layers_list):
                meta = {}
                meta['layer_obj'] = layer
                
                # Identify Layer Type
                if hasattr(layer, "name"):
                    name = layer.name
                else:
                    name = str(type(layer).__name__)
                
                meta['is_block'] = False
                meta['nodes'] = [] 
                meta['color'] = QColor(200, 200, 200)
                
                if "resnet" in name.lower() or "mobilenet" in name.lower() or "inception" in name.lower():
                    meta['type'] = "Base"
                    meta['label'] = base_model_name
                    meta['is_block'] = True
                    meta['width'] = 140
                    meta['height'] = 120
                    meta['color'] = QColor(66, 133, 244) # Blue
                    
                elif "flatten" in name.lower():
                    meta['type'] = "Flatten"
                    meta['label'] = "Flatten"
                    meta['units'] = 2048 
                    meta['color'] = QColor(255, 179, 0) # Amber
                    
                elif "dense" in name.lower():
                    meta['type'] = "Dense"
                    units = layer.units
                    meta['units'] = units
                    meta['label'] = f"Dense ({units})"
                    
                    if units == 10 or i == len(layers_list) - 1:
                        meta['label'] = f"Output ({units})"
                        meta['color'] = QColor(234, 67, 53) # Red
                    else:
                        meta['color'] = QColor(52, 168, 83) # Green
                        
                else:
                    meta['type'] = "Layer"
                    meta['label'] = name
                    meta['units'] = 1
                    meta['color'] = QColor(150, 150, 150)

                # Determine Position
                if meta['is_block']:
                    meta['x'] = current_x
                    meta['y'] = center_y - meta['height'] // 2
                    meta['rect'] = QtCore.QRect(meta['x'], meta['y'], meta['width'], meta['height'])
                    meta['out_point'] = QtCore.QPoint(meta['x'] + meta['width'], center_y)
                    
                    update_bounds(meta['x'], meta['y'], meta['width'], meta['height'])
                    current_x += meta['width'] + layer_spacing
                else:
                    # Column of nodes
                    units = meta['units']
                    meta['x'] = current_x
                    
                    # DYNAMIC VISIBILITY LOGIC
                    # Scale visible nodes based on unit count to differentiate sizes visually
                    if units < 12:
                        nodes_per_side = units # Show all
                        is_collapsed = False
                    elif units < 64:
                        nodes_per_side = 4 
                        is_collapsed = True
                    elif units < 128:
                        nodes_per_side = 5
                        is_collapsed = True
                    elif units < 256:
                        nodes_per_side = 6
                        is_collapsed = True
                    else:
                        nodes_per_side = 8 # Max density for huge layers
                        is_collapsed = True

                    v_spacing = 35 # Tighter spacing
                    
                    if is_collapsed:
                        meta['collapsed'] = True
                        meta['nodes'] = []
                        
                        # Total visual height approximation
                        column_height = (nodes_per_side * 2 * v_spacing) + 60 # + gap
                        start_y = center_y - column_height // 2
                        
                        # Top cluster
                        for k in range(nodes_per_side):
                            y = start_y + k * v_spacing
                            meta['nodes'].append((current_x, y))
                        
                        # Bottom cluster
                        bottom_start_y = start_y + (nodes_per_side * v_spacing) + 60
                        for k in range(nodes_per_side):
                            y = bottom_start_y + k * v_spacing
                            meta['nodes'].append((current_x, y))
                            
                        meta['has_dots'] = True
                        meta['dots_y'] = start_y + (nodes_per_side * v_spacing) + 30
                        
                        update_bounds(current_x - 20, start_y, 40, column_height)

                    else:
                        meta['collapsed'] = False
                        total_h = (units - 1) * v_spacing
                        start_y = center_y - total_h // 2
                        for k in range(units):
                            y = start_y + k * v_spacing
                            meta['nodes'].append((current_x, y))
                        
                        update_bounds(current_x - 20, start_y, 40, total_h + 20)

                    current_x += layer_spacing 
                
                layer_meta.append(meta)
            
            # --- 2. Draw Connections ---
            for i in range(len(layer_meta) - 1):
                src = layer_meta[i]
                dst = layer_meta[i+1]
                
                # Dynamic opacity: fewer connections = darker, many = lighter
                # Base opacity 80, lower if dense
                opacity = 80
                if len(src.get('nodes', [])) * len(dst.get('nodes', [])) > 50:
                    opacity = 40
                
                pen = QPen(QColor(150, 150, 150, opacity))
                pen.setWidthF(1.0)
                painter.setPen(pen)
                
                if src['is_block']:
                    p1 = src['out_point']
                    for (nx, ny) in dst['nodes']:
                        painter.drawLine(p1.x(), p1.y(), nx, ny)
                else:
                    for (sx, sy) in src['nodes']:
                        for (dx, dy) in dst['nodes']:
                            painter.drawLine(sx, sy, dx, dy)

            # --- 3. Draw Nodes & Blocks ---
            def draw_neuron(x, y, radius, color):
                # Simple clean style
                painter.setBrush(color)
                painter.setPen(QPen(color.darker(130), 1))
                painter.drawEllipse(QtCore.QPoint(x, y), radius, radius)

            for meta in layer_meta:
                if meta['is_block']:
                    rect = meta['rect']
                    color = meta['color']
                    grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
                    grad.setColorAt(0, color.lighter(120))
                    grad.setColorAt(1, color.darker(110))
                    painter.setBrush(QBrush(grad))
                    painter.setPen(QPen(color.darker(150), 2))
                    painter.drawRoundedRect(rect, 8, 8)
                    painter.setPen(Qt.white)
                    painter.setFont(font_title)
                    painter.drawText(rect, Qt.AlignCenter, meta['label'] + "\n(Feature Extractor)")
                else:
                    color = meta['color']
                    if meta.get('has_dots', False):
                        painter.setBrush(QColor(100, 100, 100))
                        painter.setPen(Qt.NoPen)
                        dy = meta['dots_y']
                        dx = meta['x']
                        r = 3
                        painter.drawEllipse(QtCore.QPoint(dx, dy - 8), r, r)
                        painter.drawEllipse(QtCore.QPoint(dx, dy), r, r)
                        painter.drawEllipse(QtCore.QPoint(dx, dy + 8), r, r)
                    
                    for (nx, ny) in meta['nodes']:
                        draw_neuron(nx, ny, node_radius, color)
                    
                    # Labels
                    painter.setPen(Qt.black)
                    painter.setFont(font_title)
                    if meta['nodes']:
                        top_y = min(n[1] for n in meta['nodes'])
                        label_y = top_y - 35
                        painter.drawText(QtCore.QRect(meta['x'] - 75, label_y, 150, 30), Qt.AlignCenter, meta['label'])

            painter.end()
            
            # --- 4. Auto-Crop & Scale ---
            # Add padding to bounds
            pad = 20
            crop_rect = QtCore.QRect(
                max(0, min_x - pad), 
                max(0, min_y - 40), # Extra top padding for labels
                min(canvas_width, max_x - min_x + 2*pad), 
                min(canvas_height, max_y - min_y + 80)
            )
            
            final_pixmap = pixmap.copy(crop_rect)
            
            # Scale to verify view
            self.model_viz_label.setPixmap(
                final_pixmap.scaled(
                    self.model_viz_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )
            
        except Exception as e:
            self.logger.log_exception(f"Error drawing Neural Network viz: {e}")
            self.model_viz_label.setText("Visualization Error")

    def update_rt_graph(self, epoch, logs):
        """Update the live matplotlib graph with new epoch data"""
        try:
            self.epochs_list.append(epoch)
            self.train_acc.append(logs.get('accuracy', 0))
            self.val_acc.append(logs.get('val_accuracy', 0))
            self.train_loss.append(logs.get('loss', 0))
            self.val_loss.append(logs.get('val_loss', 0))

            # Update Accuracy Plot
            self.ax_acc.clear()
            self.ax_acc.plot(self.epochs_list, self.train_acc, 'b-o', label='Train Acc', markersize=4)
            self.ax_acc.plot(self.epochs_list, self.val_acc, 'r-o', label='Val Acc', markersize=4)
            self.ax_acc.set_title('Accuracy')
            self.ax_acc.set_xlabel('Epoch')
            self.ax_acc.set_ylabel('Accuracy')
            self.ax_acc.legend(loc='upper left')
            self.ax_acc.grid(True, linestyle='--', alpha=0.6)
            
            # Force auto-scale
            self.ax_acc.relim()
            self.ax_acc.autoscale_view()
            
            # Update Loss Plot
            self.ax_loss.clear()
            self.ax_loss.plot(self.epochs_list, self.train_loss, 'b-o', label='Train Loss', markersize=4)
            self.ax_loss.plot(self.epochs_list, self.val_loss, 'r-o', label='Val Loss', markersize=4)
            self.ax_loss.set_title('Loss')
            self.ax_loss.set_xlabel('Epoch')
            self.ax_loss.set_ylabel('Loss')
            self.ax_loss.legend(loc='upper right')
            self.ax_loss.grid(True, linestyle='--', alpha=0.6)
            
            # Force auto-scale
            self.ax_loss.relim()
            self.ax_loss.autoscale_view()
            
            self.canvas.draw_idle() # Better for frequent updates
        except Exception as e:
             self.logger.log_exception(f"Error updating graph: {e}")

    def update_model_viz(self):
        """Debounced update - restarts timer on each call"""
        self.viz_update_timer.stop()
        self.viz_update_timer.start(500)  # 500ms delay
    
    def _do_update_viz(self):
        """Actually generate and display model architecture diagram"""
        try:
            # Lazy load TensorFlow when visualization is needed
            self._ensure_tensorflow_loaded()
            
            base_model_name = self.model_selector.currentText()
            
            # Read image size safely from UI
            try:
                h = int(self.img_height_input.text())
                w = int(self.img_width_input.text())
            except:
                h, w = 224, 224 # Fallback defaults
                
            input_shape = (h, w, 3)
            
            if base_model_name == "ResNet50":
                base = self._keras.applications.ResNet50(include_top=False, weights=None, input_shape=input_shape)
            elif base_model_name == "MobileNetV2":
                base = self._keras.applications.MobileNetV2(include_top=False, weights=None, input_shape=input_shape)
            elif base_model_name == "InceptionV3":
                base = self._keras.applications.InceptionV3(include_top=False, weights=None, input_shape=input_shape)
            else:
                base = self._keras.applications.ResNet50(include_top=False, weights=None, input_shape=input_shape)

            # Revert to Sequential for cleaner Grouped Viz
            layers_list = [base, self.Flatten()]
            
            # --- Parse Custom Layers ---
            custom_layers_str = self.layer_config_input.text()
            custom_layers_desc = "None"
            
            if custom_layers_str:
                try:
                    dims = [int(x.strip()) for x in custom_layers_str.split(',') if x.strip()]
                    for d in dims:
                        layers_list.append(self.Dense(d))
                    if dims:
                        custom_layers_desc = str(dims)
                except ValueError:
                    self.logger.log_status("Invalid Custom Layer input for viz.")
            
            # Add final classification head
            layers_list.append(self.Dense(10))
            
            model = self.Sequential(layers_list)
            
            # --- Update Info Label ---
            total_params = model.count_params()
            layer_count = len(base.layers) # Base model layers
            
            # Compact info text
            info_text = f"{base_model_name} • {layer_count} layers • {custom_layers_desc} custom • {total_params:,} params"
            self.model_info_label.setText(info_text)
            
            # Use Custom Horizontal Painter (Robust & Research Paper Style)
            self.draw_horizontal_model_viz(layers_list, base_model_name)

        except Exception as e:
            self.logger.log_exception(f"Error generating model viz: {e}")
            self.model_viz_label.setText("Visualization failed.")
            
    def open_plot_image(self, image_path: StrOrBytesPath):
            try:
                window = QWidget()
                window.setWindowTitle("Training Plot")
                layout = QVBoxLayout()

                label = QLabel()
                pixmap = QPixmap(image_path)
                label.setPixmap(pixmap)
                label.setScaledContents(True)  

                layout.addWidget(label)
                window.setLayout(layout)
                window.resize(pixmap.width(), pixmap.height())

                self.plot_window = window

                window.show()
                
            except Exception as e:
                self.logger.log_exception(f'An error occured while open plotted metrics. {e}')

class TrainWorker(QObject):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    message_signal = pyqtSignal(str)
    plot_ready_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    epoch_end_signal = pyqtSignal(int, dict) # New signal for real-time graph

    def __init__(self, trainer):
        super().__init__()
        self.trainer = trainer

    def log(self, message):
        """Helper to log to both file and UI"""
        self.trainer.logger.log_status(message)
        self.log_signal.emit(message)

    def run(self):
        try:
            # Lazy load TensorFlow when training starts
            self.trainer._ensure_tensorflow_loaded()
            
            self.log("Training started.")
            # ... (Parameter reading logic is largely same, skipping for brevity in replacement if possible, 
            # but need to include context to reach LogCallback) ...
            # To be safe, I will just rewrite the run method up to the point of callback definition or read parameters again.
            # Actually, to minimize edit size, I'll allow "run" to be mostly unchanged until the callback part.
            
            self.data_dir = Path(self.trainer.path_input.text())
            self.epochs = int(self.trainer.epochs_input.text())
            self.lr = float(self.trainer.lr_input.text())
            self.base_model_name = self.trainer.model_selector.currentText()
            # Parse custom layers
            try:
                self.custom_layers = [int(size.strip()) for size in self.trainer.layer_config_input.text().split(',') if size.strip().isdigit()]
            except:
                self.custom_layers = [256] # Default fallback

            self.val_split = float(self.trainer.val_split_input.text())
            self.seed = int(self.trainer.seed_input.text())
            self.img_height = int(self.trainer.img_height_input.text())
            self.img_width = int(self.trainer.img_width_input.text())
            self.batch_size = int(self.trainer.batch_size_input.text())
            self.freeze_original_layers = bool(self.trainer.freeze_input.currentText().lower() == 'true')
            self.optimizer = self.trainer.optimizer_selector.currentText()
            self.loss = self.trainer.loss_selector.currentText()
            self.model_name = self.trainer.model_name_input.text() 
            self.plot_name = self.trainer.plot_name_input.text()
            
            self.trainer.save_config()
            self.progress_signal.emit(5)
            self.log("Configuration saved.")

            train_ds = self.trainer._tf.keras.preprocessing.image_dataset_from_directory(
                self.data_dir,
                validation_split=self.val_split,
                subset="training",
                seed=self.seed,
                image_size=(self.img_height, self.img_width),
                batch_size=self.batch_size)

            val_ds = self.trainer._tf.keras.preprocessing.image_dataset_from_directory(
                self.data_dir,
                validation_split=self.val_split,
                subset="validation",
                seed=self.seed,
                image_size=(self.img_height, self.img_width),
                batch_size=self.batch_size)

            num_classes = len(train_ds.class_names)
            self.log(f"Detected {num_classes} classes: {train_ds.class_names}")
            self.progress_signal.emit(20)

            input_shape = (self.img_height, self.img_width, 3)
            self.log(f"Building base model: {self.base_model_name}")
            
            if self.base_model_name == "ResNet50":
                base = self.trainer._keras.applications.ResNet50(include_top=False, weights="imagenet", input_shape=input_shape, pooling='avg')
            elif self.base_model_name == "MobileNetV2":
                base = self.trainer._keras.applications.MobileNetV2(include_top=False, weights="imagenet", input_shape=input_shape, pooling='avg')
            elif self.base_model_name == "InceptionV3":
                base = self.trainer._keras.applications.InceptionV3(include_top=False, weights="imagenet", input_shape=input_shape, pooling='avg')
            else:
                base = self.trainer._keras.applications.ResNet50(include_top=False, weights="imagenet", input_shape=input_shape, pooling='avg')

            if self.freeze_original_layers:
                base.trainable = False

            model = self.trainer.Sequential()
            model.add(base)
            model.add(self.trainer.Flatten())
            for size in self.custom_layers:
                model.add(self.trainer.Dense(size, activation='relu'))
                model.add(self.trainer.Dropout(0.5))
            model.add(self.trainer.Dense(num_classes, activation='softmax'))

            model.compile(optimizer=self.trainer.Adam(learning_rate=self.lr),
                          loss=self.loss,
                          metrics=['accuracy'])

            self.progress_signal.emit(40)
            self.log("Model compiled.")

            # Custom callback for emitting epoch stats
            class LogCallback(self.trainer._keras.callbacks.Callback):
                def __init__(self, worker_self):
                    self.worker = worker_self
                def on_epoch_end(self, epoch, logs=None):
                    self.worker.epoch_end_signal.emit(epoch + 1, logs)
                    msg = f"Epoch {epoch+1}: loss={logs['loss']:.4f}, acc={logs['accuracy']:.4f}, val_loss={logs['val_loss']:.4f}, val_acc={logs['val_accuracy']:.4f}"
                    self.worker.log(msg)

            history = model.fit(train_ds, validation_data=val_ds, epochs=self.epochs, callbacks=[LogCallback(self)])

            model.save(self.model_name)
            self.log(f"Model saved to {self.model_name}")
            self.progress_signal.emit(100)
            self.message_signal.emit(f"Training complete. Saved as {self.model_name}")
            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))


def main():
    app = QApplication(sys.argv)
    # Dummy config and logger instances should be passed here if running independently
    # Example: Trainer(Config(), Logger())
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
