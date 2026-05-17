import os
import sys
from typing import Union
StrOrBytesPath = Union[str, bytes, os.PathLike]

# LAZY IMPORTS: TensorFlow and matplotlib are imported inside Trainer class to improve startup time
# These heavy libraries (~5-10 seconds load time) are only loaded when Model Training tab is accessed

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QComboBox, QProgressBar, QMessageBox, QGridLayout, QGroupBox, QScrollArea, QSizePolicy, QSplitter,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QDialog, QHBoxLayout, QFrame, QTextEdit
)
from PyQt5.QtCore import QObject, QThread, pyqtSignal, Qt, QPropertyAnimation, QEasingCurve, QRect
from PyQt5.QtGui import QPixmap, QImage, QColor, QBrush, QPen, QFont, QPalette
from PyQt5 import QtGui, QtCore

from pathlib import Path
from config_ import Config
from app_logger import Logger
from utils import resolve_path


# ─── Shared Style Constants ───────────────────────────────────────────────────
_FONT = "SF Pro Display" if sys.platform == "darwin" else "Segoe UI"
_MONO = "SF Mono" if sys.platform == "darwin" else "Consolas"

PALETTE = {
    "bg":           "#F7F8FA",
    "surface":      "#FFFFFF",
    "surface_alt":  "#F0F2F5",
    "border":       "#E4E7EB",
    "border_focus": "#1DA1F2",
    "text_primary": "#111827",
    "text_secondary":"#6B7280",
    "text_muted":   "#9CA3AF",
    "accent":       "#1DA1F2",
    "accent_hover": "#0D8FDB",
    "success":      "#10B981",
    "warning":      "#F59E0B",
    "danger":       "#EF4444",
    "chart_blue":   "#3B82F6",
    "chart_red":    "#EF4444",
}

# Applied once at the QApplication level via setStyleSheet
APP_STYLESHEET = f"""
/* ── Base ── */
QWidget {{
    font-family: "{_FONT}", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: {PALETTE['text_primary']};
    background-color: transparent;
}}

/* ── GroupBox (card style) ── */
QGroupBox {{
    background-color: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-size: 12px;
    font-weight: 600;
    color: {PALETTE['text_secondary']};
    letter-spacing: 0.6px;
    text-transform: uppercase;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 12px;
    top: -1px;
    background-color: {PALETTE['surface']};
    color: {PALETTE['text_secondary']};
}}

/* ── Inputs ── */
QLineEdit, QComboBox {{
    background-color: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 12px;
    color: {PALETTE['text_primary']};
    selection-background-color: {PALETTE['accent']};
    min-height: 24px;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1.5px solid {PALETTE['border_focus']};
    background-color: {PALETTE['surface']};
}}
QLineEdit:hover, QComboBox:hover {{
    border-color: #B0BAC8;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {PALETTE['text_secondary']};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 6px;
    selection-background-color: {PALETTE['accent']};
    selection-color: white;
    padding: 4px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: 4px;
    min-height: 22px;
}}

/* ── Labels ── */
QLabel {{
    color: {PALETTE['text_primary']};
    background: transparent;
    border: none;
}}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {PALETTE['border']};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #C0C8D4;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    height: 6px;
    background: transparent;
}}
QScrollBar::handle:horizontal {{
    background: {PALETTE['border']};
    border-radius: 3px;
}}

/* ── Progress Bar ── */
QProgressBar {{
    background-color: {PALETTE['surface_alt']};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    font-size: 10px;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {PALETTE['accent']};
    border-radius: 4px;
}}

/* ── Tree Widget ── */
QTreeWidget {{
    background-color: {PALETTE['surface']};
    border: none;
    border-radius: 6px;
    alternate-background-color: {PALETTE['surface_alt']};
    show-decoration-selected: 1;
    outline: none;
}}
QTreeWidget::item {{
    padding: 5px 8px;
    border-bottom: 1px solid {PALETTE['surface_alt']};
}}
QTreeWidget::item:selected {{
    background-color: #EBF5FF;
    color: {PALETTE['accent']};
    border-left: 2px solid {PALETTE['accent']};
}}
QTreeWidget::item:hover {{
    background-color: {PALETTE['surface_alt']};
}}
QHeaderView::section {{
    background-color: {PALETTE['surface_alt']};
    color: {PALETTE['text_secondary']};
    font-size: 11px;
    font-weight: 600;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {PALETTE['border']};
    letter-spacing: 0.4px;
    text-transform: uppercase;
}}

/* ── Buttons ── */
QPushButton {{
    background-color: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
    color: {PALETTE['text_primary']};
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: {PALETTE['surface_alt']};
    border-color: #B0BAC8;
}}
QPushButton:pressed {{
    background-color: #E8EDF3;
}}

QPushButton#ActionButton, QPushButton#StartButton {{
    background-color: {PALETTE['accent']};
    border: none;
    color: white;
    font-weight: 600;
    border-radius: 7px;
    letter-spacing: 0.3px;
}}
QPushButton#ActionButton:hover, QPushButton#StartButton:hover {{
    background-color: {PALETTE['accent_hover']};
}}
QPushButton#ActionButton:pressed, QPushButton#StartButton:pressed {{
    background-color: #0B7AC4;
}}

QPushButton#SaveButton {{
    background-color: transparent;
    border: 1px solid {PALETTE['border']};
    color: {PALETTE['text_secondary']};
    font-size: 12px;
}}
QPushButton#SaveButton:hover {{
    border-color: {PALETTE['accent']};
    color: {PALETTE['accent']};
    background-color: #EBF5FF;
}}

QPushButton#IconButton {{
    background-color: {PALETTE['surface_alt']};
    border: 1px solid {PALETTE['border']};
    border-radius: 6px;
    padding: 2px;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    font-size: 13px;
}}
QPushButton#IconButton:hover {{
    background-color: #EBF5FF;
    border-color: {PALETTE['accent']};
}}

/* ── Log output ── */
QTextEdit {{
    background-color: {PALETTE['surface']};
    color: {PALETTE['text_primary']};
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    font-family: "{_MONO}", monospace;
    font-size: 11px;
    padding: 8px;
    selection-background-color: {PALETTE['accent']};
}}

/* ── Dialog ── */
QDialog {{
    background-color: {PALETTE['bg']};
}}

/* ── Scroll Area ── */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
"""


# ─── Metric Card Widget ────────────────────────────────────────────────────────
class MetricCard(QFrame):
    """Small stat card used in the training metrics header row."""
    def __init__(self, label: str, value: str = "—", accent: str = PALETTE["accent"], parent=None):
        super().__init__(parent)
        self._accent = accent
        self.setObjectName("MetricCard")
        self.setStyleSheet("""
            QFrame#MetricCard {
                background-color: #FFFFFF;
                border: 1px solid #E4E7EB;
                border-radius: 8px;
            }
        """)
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #9CA3AF; letter-spacing: 0.5px; text-transform: uppercase;")

        self._val = QLabel(value)
        self._val.setStyleSheet("font-size: 18px; font-weight: 700; color: #111827;")

        layout.addWidget(self._lbl)
        layout.addWidget(self._val)

    def set_value(self, v: str):
        self._val.setText(v)


# ─── Section Divider ──────────────────────────────────────────────────────────
class SectionDivider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setStyleSheet(f"color: {PALETTE['border']}; background: {PALETTE['border']}; max-height: 1px; border: none;")


# ─── Param Row Label ──────────────────────────────────────────────────────────
def _param_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {PALETTE['text_secondary']}; background: transparent;")
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return lbl


# ─── Dataset Guideline Dialog ─────────────────────────────────────────────────
class DatasetGuidelineDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dataset Guidelines")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(520, 420)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {PALETTE['bg']};
            }}
            QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Header bar ──
        header_frame = QFrame()
        header_frame.setStyleSheet(f"QFrame {{ background-color: {PALETTE['accent']}; border-radius: 0px; }}")
        header_frame.setFixedHeight(64)
        hf_layout = QHBoxLayout(header_frame)
        hf_layout.setContentsMargins(24, 0, 24, 0)

        icon_lbl = QLabel("📂")
        icon_lbl.setStyleSheet("font-size: 22px; background: transparent;")
        title_lbl = QLabel("Dataset Structure Requirements")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: white; background: transparent;")

        hf_layout.addWidget(icon_lbl)
        hf_layout.addSpacing(8)
        hf_layout.addWidget(title_lbl)
        hf_layout.addStretch()
        layout.addWidget(header_frame)

        # ── Body ──
        body = QWidget()
        body.setStyleSheet(f"QWidget {{ background-color: {PALETTE['bg']}; }}")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(14)

        desc = QLabel("To ensure successful training, your dataset folder must interpret the subdirectory names as class labels.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 13px; color: {PALETTE['text_secondary']}; background: transparent;")
        body_layout.addWidget(desc)

        # Code block
        code_frame = QFrame()
        code_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1C2333;
                border-radius: 8px;
                border: 1px solid #2D3748;
            }}
        """)
        code_layout = QVBoxLayout(code_frame)
        code_layout.setContentsMargins(16, 12, 16, 12)

        code_lbl = QLabel(
            '<span style="color:#7DD3FC;">📂 Selected Folder/</span><br>'
            '&nbsp;&nbsp;<span style="color:#86EFAC;">├── 📂 Class_A/</span><span style="color:#94A3B8;">  &larr; e.g., Brick_House</span><br>'
            '&nbsp;&nbsp;<span style="color:#6B7280;">│&nbsp;&nbsp;&nbsp;├── 🖼️ image_01.jpg</span><br>'
            '&nbsp;&nbsp;<span style="color:#6B7280;">│&nbsp;&nbsp;&nbsp;└── ...</span><br>'
            '&nbsp;&nbsp;<span style="color:#86EFAC;">├── 📂 Class_B/</span><span style="color:#94A3B8;">  &larr; e.g., Mud_House</span><br>'
            '&nbsp;&nbsp;<span style="color:#6B7280;">│&nbsp;&nbsp;&nbsp;├── 🖼️ image_01.jpg</span><br>'
            '&nbsp;&nbsp;<span style="color:#6B7280;">│&nbsp;&nbsp;&nbsp;└── ...</span>'
        )
        code_lbl.setStyleSheet(f"font-family: '{_MONO}', monospace; font-size: 12px; background: transparent; color: white; line-height: 1.6;")
        code_lbl.setTextFormat(Qt.RichText)
        code_layout.addWidget(code_lbl)
        body_layout.addWidget(code_frame)

        note = QLabel("Supported formats: JPG · PNG · JPEG")
        note.setStyleSheet(f"font-size: 11px; color: {PALETTE['text_muted']}; background: transparent;")
        body_layout.addWidget(note)

        body_layout.addStretch()

        # ── Footer ──
        footer = QFrame()
        footer.setStyleSheet(f"QFrame {{ background-color: {PALETTE['surface']}; border-top: 1px solid {PALETTE['border']}; border-radius: 0px; }}")
        footer.setFixedHeight(60)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 0, 20, 0)
        footer_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(90)
        cancel_btn.clicked.connect(self.reject)

        open_btn = QPushButton("Browse Folder →")
        open_btn.setObjectName("ActionButton")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setMinimumWidth(160)
        open_btn.clicked.connect(self.accept)

        footer_layout.addWidget(cancel_btn)
        footer_layout.addSpacing(8)
        footer_layout.addWidget(open_btn)

        layout.addWidget(body, 1)
        layout.addWidget(footer)


# ─── Trainer ──────────────────────────────────────────────────────────────────
class Trainer(QWidget):
    # Emitted when a model finishes training: (absolute_model_path, class_names_list)
    model_trained = pyqtSignal(str, list)

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

        self.setStyleSheet(APP_STYLESHEET)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(PALETTE["bg"]))
        self.setPalette(pal)

        self.init_ui()
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

    # ── Layout ────────────────────────────────────────────────────────────────
    def init_ui(self):
        main_layout = QGridLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
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

        # 5. Bottom-Right: Real-time Graph (Span 2 rows)
        graph_group = self._create_graph_panel()
        main_layout.addWidget(graph_group, 1, 1, 2, 1)

        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 2)

        main_layout.setRowStretch(0, 0)
        main_layout.setRowStretch(1, 5)
        main_layout.setRowStretch(2, 5)

        self.setLayout(main_layout)

    # ── Params Panel ──────────────────────────────────────────────────────────
    def _create_params_panel(self):
        group = QGroupBox("Training Parameters")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")

        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(6)
        form_layout.setHorizontalSpacing(8)
        form_layout.setContentsMargins(4, 4, 4, 4)
        form_layout.setColumnStretch(1, 1)

        # ── Data section ──
        self._add_section_header(form_layout, 0, "DATA")

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select dataset folder…")
        self.browse_btn = QPushButton("📂")
        self.browse_btn.setObjectName("IconButton")
        self.browse_btn.setToolTip("Browse for dataset folder")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.clicked.connect(self.browse_folder)
        self._add_param_row(form_layout, 1, "Dataset", self.path_input, self.browse_btn)

        self.model_selector = QComboBox()
        self.model_selector.addItems([
            "ResNet50",
            "MobileNetV2",
            "EfficientNetV2S",
            "InceptionV3",
        ])
        import platform
        if sys.platform == "darwin" and platform.machine() == "arm64":
            self.model_selector.setCurrentText("EfficientNetV2S")
        self.model_selector.currentIndexChanged.connect(self._do_update_viz)
        self._add_param_row(form_layout, 2, "Base Model", self.model_selector)

        self.model_name_input = QLineEdit("my_model.h5")
        self._add_param_row(form_layout, 3, "Save Name", self.model_name_input)

        # ── Hyperparams section ──
        self._add_section_header(form_layout, 4, "HYPERPARAMETERS")

        self.epochs_input = QLineEdit("10")
        self._add_param_row(form_layout, 5, "Epochs", self.epochs_input)

        self.batch_size_input = QLineEdit("64")
        self._add_param_row(form_layout, 6, "Batch Size", self.batch_size_input)

        self.lr_input = QLineEdit("0.001")
        self._add_param_row(form_layout, 7, "Learning Rate", self.lr_input)

        # ── Image Config section ──
        self._add_section_header(form_layout, 8, "IMAGE CONFIG")

        self.img_height_input = QLineEdit("224")
        self._add_param_row(form_layout, 9, "Height (px)", self.img_height_input)

        self.img_width_input = QLineEdit("224")
        self._add_param_row(form_layout, 10, "Width (px)", self.img_width_input)

        self.val_split_input = QLineEdit("0.2")
        self._add_param_row(form_layout, 11, "Val Split", self.val_split_input)

        # ── Architecture section ──
        self._add_section_header(form_layout, 12, "ARCHITECTURE")

        self.layer_config_input = QLineEdit("128, 64")
        self.layer_config_input.setPlaceholderText("e.g. 256, 128, 64")
        self.layer_config_input.textChanged.connect(self.update_model_viz)
        self._add_param_row(form_layout, 13, "Custom Layers", self.layer_config_input)

        self.dropout_rate_input = QLineEdit("0.5")
        self.dropout_rate_input.setPlaceholderText("0.0 – 1.0  (0.0 = no dropout)")
        self.dropout_rate_input.setToolTip(
            "Dropout rate applied after each Dense layer in the head.\n"
            "0.5 = randomly drop 50% of neurons during training to reduce overfitting.\n"
            "Set to 0.0 to disable dropout entirely."
        )
        self.dropout_rate_input.textChanged.connect(self.update_model_viz)
        self._add_param_row(form_layout, 14, "Dropout Rate", self.dropout_rate_input)

        self.freeze_input = QComboBox()
        self.freeze_input.addItems(["True", "False"])
        self._add_param_row(form_layout, 15, "Freeze Base", self.freeze_input)

        self.optimizer_selector = QComboBox()
        self.optimizer_selector.addItems(["adam", "sgd", "rmsprop"])
        self._add_param_row(form_layout, 16, "Optimizer", self.optimizer_selector)

        self.loss_selector = QComboBox()
        self.loss_selector.addItems(["sparse_categorical_crossentropy", "categorical_crossentropy"])
        self.loss_selector.setToolTip(
            "Use 'sparse_categorical_crossentropy' when labels are integers (default).\n"
            "Use 'categorical_crossentropy' only if labels are one-hot encoded."
        )
        self._add_param_row(form_layout, 17, "Loss Function", self.loss_selector)

        # ── Misc section ──
        self._add_section_header(form_layout, 18, "MISC")

        self.seed_input = QLineEdit("42")
        self._add_param_row(form_layout, 19, "Seed", self.seed_input)

        self.plot_name_input = QLineEdit("training_plot.png")
        self._add_param_row(form_layout, 20, "Plot Filename", self.plot_name_input)

        # ── Buttons ──
        btn_container = QWidget()
        btn_container.setStyleSheet("background: transparent;")
        btn_v = QVBoxLayout(btn_container)
        btn_v.setContentsMargins(0, 8, 0, 0)
        btn_v.setSpacing(6)

        self.start_btn = QPushButton("▶  Start Training")
        self.start_btn.setObjectName("StartButton")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setMinimumHeight(36)
        self.start_btn.setStyleSheet(f"""
            QPushButton#StartButton {{
                background-color: {PALETTE['success']};
                border: none; color: white;
                font-weight: 700; font-size: 13px;
                border-radius: 7px; letter-spacing: 0.4px;
            }}
            QPushButton#StartButton:hover {{
                background-color: #059669;
            }}
            QPushButton#StartButton:pressed {{
                background-color: #047857;
            }}
        """)
        self.start_btn.clicked.connect(self.start_training)

        self.save_config_btn = QPushButton("Save Config")
        self.save_config_btn.setObjectName("SaveButton")
        self.save_config_btn.setCursor(Qt.PointingHandCursor)
        self.save_config_btn.setMinimumHeight(30)
        self.save_config_btn.clicked.connect(self.save_config)

        btn_v.addWidget(self.start_btn)
        btn_v.addWidget(self.save_config_btn)

        form_layout.addWidget(btn_container, 21, 0, 1, 3)

        # Assemble
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addLayout(form_layout)
        content_layout.addStretch()
        content.setLayout(content_layout)
        scroll.setWidget(content)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        group.setLayout(layout)
        return group

    def _add_section_header(self, layout, row, text):
        """Adds a compact section divider label."""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 6, 0, 2)
        h.setSpacing(6)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {PALETTE['text_muted']}; letter-spacing: 1.0px; background: transparent;")
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {PALETTE['border']}; background: {PALETTE['border']}; max-height: 1px; border: none;")
        h.addWidget(lbl)
        h.addWidget(line, 1)
        layout.addWidget(w, row, 0, 1, 3)

    def _add_param_row(self, layout, row, label_text, widget, extra_widget=None):
        lbl = _param_label(label_text)
        layout.addWidget(lbl, row, 0)
        layout.addWidget(widget, row, 1)
        if extra_widget:
            layout.addWidget(extra_widget, row, 2)

    # ── Logs Panel ────────────────────────────────────────────────────────────
    def _create_logs_panel(self):
        group = QGroupBox("Training Logs")
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        # Progress bar with label
        prog_row = QWidget()
        prog_row.setStyleSheet("background: transparent;")
        prog_h = QHBoxLayout(prog_row)
        prog_h.setContentsMargins(0, 0, 0, 0)
        prog_h.setSpacing(8)

        self._prog_label = QLabel("Idle")
        self._prog_label.setStyleSheet(f"font-size: 10px; color: {PALETTE['text_muted']}; background: transparent;")
        self._prog_label.setFixedWidth(32)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)

        prog_h.addWidget(self._prog_label)
        prog_h.addWidget(self.progress, 1)

        layout.addWidget(self.log_output, 1)
        layout.addWidget(prog_row)
        group.setLayout(layout)
        return group

    # ── Viz Panel ─────────────────────────────────────────────────────────────
    def _create_viz_panel(self):
        group = QGroupBox("Model Architecture")
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Info pill row
        info_row = QWidget()
        info_row.setStyleSheet("background: transparent;")
        info_h = QHBoxLayout(info_row)
        info_h.setContentsMargins(0, 0, 0, 0)
        info_h.setSpacing(6)

        self.model_info_label = QLabel("Initializing…")
        self.model_info_label.setStyleSheet(f"""
            font-size: 11px; font-weight: 500;
            color: {PALETTE['text_secondary']};
            padding: 4px 10px;
            background-color: {PALETTE['surface_alt']};
            border-radius: 4px;
            border: 1px solid {PALETTE['border']};
        """)
        self.model_info_label.setAlignment(Qt.AlignCenter)
        self.model_info_label.setWordWrap(True)
        info_h.addWidget(self.model_info_label, 1)
        layout.addWidget(info_row)

        self.model_viz_label = QLabel("Model visualization will appear here.")
        self.model_viz_label.setAlignment(Qt.AlignCenter)
        self.model_viz_label.setStyleSheet(f"""
            background-color: {PALETTE['surface_alt']};
            border: 1px dashed {PALETTE['border']};
            border-radius: 8px;
            color: {PALETTE['text_muted']};
            font-size: 12px;
        """)
        self.model_viz_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.model_viz_label, 1)

        group.setLayout(layout)
        return group

    # ── Graph Panel ───────────────────────────────────────────────────────────
    def _create_graph_panel(self):
        self._ensure_matplotlib_loaded()

        group = QGroupBox("Real-time Training Metrics")
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Metric cards row ──
        cards_row = QWidget()
        cards_row.setStyleSheet("background: transparent;")
        cards_h = QHBoxLayout(cards_row)
        cards_h.setContentsMargins(0, 0, 0, 0)
        cards_h.setSpacing(8)

        self._card_train_acc  = MetricCard("Train Acc",  "—", PALETTE["chart_blue"])
        self._card_val_acc    = MetricCard("Val Acc",    "—", PALETTE["success"])
        self._card_train_loss = MetricCard("Train Loss", "—", PALETTE["warning"])
        self._card_val_loss   = MetricCard("Val Loss",   "—", PALETTE["danger"])
        self._card_epoch      = MetricCard("Epoch",      "0", PALETTE["accent"])

        for card in (self._card_epoch, self._card_train_acc, self._card_val_acc,
                     self._card_train_loss, self._card_val_loss):
            cards_h.addWidget(card)

        layout.addWidget(cards_row)

        # ── Matplotlib figure ──
        import matplotlib
        matplotlib.rcParams.update({
            'font.family':      'sans-serif',
            'font.sans-serif':  [_FONT, 'Helvetica Neue', 'Arial'],
            'axes.spines.top':  False,
            'axes.spines.right':False,
            'axes.grid':        True,
            'grid.alpha':       0.35,
            'grid.linestyle':   '--',
            'grid.linewidth':   0.6,
            'xtick.labelsize':  9,
            'ytick.labelsize':  9,
            'axes.labelsize':   9,
            'axes.titlesize':   10,
            'axes.titleweight': 'semibold',
            'figure.autolayout':True,
        })

        FIG_BG = "#FAFBFC"
        self.figure = self._Figure(figsize=(6, 3.2), dpi=100)
        self.figure.patch.set_facecolor(FIG_BG)

        self.canvas = self._FigureCanvas(self.figure)
        self.canvas.setStyleSheet(f"background-color: {FIG_BG}; border-radius: 8px;")

        self.toolbar = self._NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet(f"""
            QToolBar {{
                background: transparent;
                border: none;
                spacing: 2px;
            }}
            QToolButton {{
                background: {PALETTE['surface_alt']};
                border: 1px solid {PALETTE['border']};
                border-radius: 4px;
                padding: 2px;
                margin: 1px;
            }}
            QToolButton:hover {{
                background: #EBF5FF;
                border-color: {PALETTE['accent']};
            }}
        """)

        self.ax_acc  = self.figure.add_subplot(121)
        self.ax_loss = self.figure.add_subplot(122)

        for ax in (self.ax_acc, self.ax_loss):
            ax.set_facecolor("#FFFFFF")

        self.figure.tight_layout(pad=2.0)

        toolbar_row = QWidget()
        toolbar_row.setStyleSheet("background: transparent;")
        tr_h = QHBoxLayout(toolbar_row)
        tr_h.setContentsMargins(0, 0, 0, 0)
        tr_h.addWidget(self.toolbar)
        tr_h.addStretch()

        layout.addWidget(toolbar_row)
        layout.addWidget(self.canvas, 1)
        group.setLayout(layout)
        return group

    # ── Structure Panel ───────────────────────────────────────────────────────
    def _create_structure_panel(self):
        group = QGroupBox("Dataset Structure")
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)

        self.structure_tree = QTreeWidget()
        self.structure_tree.setHeaderLabels(["Class Name", "Images"])
        self.structure_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.structure_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.structure_tree.setAlternatingRowColors(True)
        self.structure_tree.setRootIsDecorated(False)
        # Show placeholder so users know they need to select a dataset
        placeholder = QTreeWidgetItem(["Select a dataset folder to view structure", ""])
        placeholder.setForeground(0, QBrush(QColor(PALETTE["text_muted"])))
        self.structure_tree.addTopLevelItem(placeholder)

        layout.addWidget(self.structure_tree)
        group.setLayout(layout)
        return group

    # ── Browse / Visualize ────────────────────────────────────────────────────
    def browse_folder(self):
        try:
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

            for sub_dir in sorted(folder.iterdir()):
                if sub_dir.is_dir():
                    images = list(sub_dir.glob('*.jpg')) + list(sub_dir.glob('*.png')) + list(sub_dir.glob('*.jpeg'))
                    count = len(images)
                    total_images += count

                    item = QTreeWidgetItem([sub_dir.name, str(count)])
                    if count == 0:
                        item.setForeground(1, QBrush(QColor(PALETTE["danger"])))
                        item.setForeground(0, QBrush(QColor(PALETTE["text_secondary"])))
                    else:
                        item.setForeground(1, QBrush(QColor(PALETTE["success"])))

                    self.structure_tree.addTopLevelItem(item)
                    classes.append(sub_dir.name)

            if not classes:
                item = QTreeWidgetItem(["No subfolders found!", "0"])
                item.setForeground(0, QBrush(QColor(PALETTE["danger"])))
                self.structure_tree.addTopLevelItem(item)

            self.logger.log_status(f"Loaded dataset: {len(classes)} classes, {total_images} images.")

        except Exception as e:
            self.logger.log_exception(f"Error visualizing dataset: {e}")

    # ── Save Config ───────────────────────────────────────────────────────────
    def save_config(self):
        try:
            config = self.config.read_config()
            config["Model_Training"] = {
                "data_dir": self.path_input.text(),
                "epochs": self.epochs_input.text(),
                "learning_rate": self.lr_input.text(),
                "base_model": self.model_selector.currentText(),
                "custom_layers": self.layer_config_input.text(),
                "dropout_rate": self.dropout_rate_input.text(),
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

    # ── Start Training ────────────────────────────────────────────────────────
    def start_training(self):
        try:
            self.train_acc = []
            self.val_acc = []
            self.train_loss = []
            self.val_loss = []
            self.epochs_list = []

            self.ax_acc.clear()
            self.ax_loss.clear()
            self.update_model_viz()

            self._prog_label.setText("0%")
            self.progress.setValue(0)

            # Reset metric cards
            for card in (self._card_epoch, self._card_train_acc, self._card_val_acc,
                         self._card_train_loss, self._card_val_loss):
                card.set_value("—")
            self._card_epoch.set_value("0")

            self.thread = QThread()
            self.worker = TrainWorker(self)

            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.progress_signal.connect(self._on_progress)
            self.worker.message_signal.connect(lambda msg: QMessageBox.information(self, "Success", msg))
            self.worker.error_signal.connect(lambda err: self.logger.log_exception(f"Training error: {err}"))
            self.worker.log_signal.connect(self.log_output.append)
            self.worker.epoch_end_signal.connect(self.update_rt_graph)
            self.worker.finished_signal.connect(self.thread.quit)
            self.worker.finished_signal.connect(self.worker.deleteLater)
            self.worker.model_trained_signal.connect(self.model_trained)
            self.thread.finished.connect(self.thread.deleteLater)

            self.thread.start()
        except Exception as e:
            self.logger.log_exception(f'An error occurred while starting the training thread. {e}')

    def _on_progress(self, value: int):
        self.progress.setValue(value)
        self._prog_label.setText(f"{value}%")

    # ── Model Visualization ───────────────────────────────────────────────────
    def draw_horizontal_model_viz(self, layers_list, base_model_name):
        """Draws a refined Neural Network style visualization with dynamic sizing and auto-crop."""
        try:
            layer_spacing = 160
            node_radius = 12
            node_diameter = node_radius * 2

            canvas_width = 2000
            canvas_height = 1000

            pixmap = QPixmap(canvas_width, canvas_height)
            pixmap.fill(QColor(PALETTE["surface_alt"]))
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.TextAntialiasing)

            center_y = canvas_height // 2

            _viz_font = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
            font_title = QtGui.QFont(_viz_font, 10, QtGui.QFont.Bold)
            font_label = QtGui.QFont(_viz_font, 8)
            font_small = QtGui.QFont(_viz_font, 7)

            layer_meta = []
            current_x = 50

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

                if hasattr(layer, "name"):
                    name = layer.name
                else:
                    name = str(type(layer).__name__)

                meta['is_block'] = False
                meta['nodes'] = []
                meta['color'] = QColor(200, 200, 200)

                if any(x in name.lower() for x in ["resnet", "mobilenet", "inception", "efficientnet"]):
                    meta['type'] = "Base"
                    meta['label'] = base_model_name
                    meta['is_block'] = True
                    meta['width'] = 140
                    meta['height'] = 120
                    meta['color'] = QColor(29, 161, 242)

                elif "flatten" in name.lower():
                    meta['type'] = "Flatten"
                    meta['label'] = "Flatten"
                    meta['units'] = 2048
                    meta['color'] = QColor(245, 158, 11)

                elif "dense" in name.lower():
                    meta['type'] = "Dense"
                    units = layer.units
                    meta['units'] = units
                    meta['label'] = f"Dense ({units})"

                    if units == 10 or i == len(layers_list) - 1:
                        meta['label'] = f"Output ({units})"
                        meta['color'] = QColor(239, 68, 68)
                    else:
                        meta['color'] = QColor(16, 185, 129)

                else:
                    meta['type'] = "Layer"
                    meta['label'] = name
                    meta['units'] = 1
                    meta['color'] = QColor(150, 150, 150)

                if meta['is_block']:
                    meta['x'] = current_x
                    meta['y'] = center_y - meta['height'] // 2
                    meta['rect'] = QtCore.QRect(meta['x'], meta['y'], meta['width'], meta['height'])
                    meta['out_point'] = QtCore.QPoint(meta['x'] + meta['width'], center_y)
                    update_bounds(meta['x'], meta['y'], meta['width'], meta['height'])
                    current_x += meta['width'] + layer_spacing
                else:
                    units = meta['units']
                    meta['x'] = current_x

                    if units < 12:
                        nodes_per_side = units
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
                        nodes_per_side = 8
                        is_collapsed = True

                    v_spacing = 35

                    if is_collapsed:
                        meta['collapsed'] = True
                        meta['nodes'] = []

                        column_height = (nodes_per_side * 2 * v_spacing) + 60
                        start_y = center_y - column_height // 2

                        for k in range(nodes_per_side):
                            y = start_y + k * v_spacing
                            meta['nodes'].append((current_x, y))

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

            # Draw connections
            for i in range(len(layer_meta) - 1):
                src = layer_meta[i]
                dst = layer_meta[i+1]

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

            def draw_neuron(x, y, radius, color):
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

                    painter.setPen(Qt.black)
                    painter.setFont(font_title)
                    if meta['nodes']:
                        top_y = min(n[1] for n in meta['nodes'])
                        label_y = top_y - 35
                        painter.drawText(QtCore.QRect(meta['x'] - 75, label_y, 150, 30), Qt.AlignCenter, meta['label'])

            painter.end()

            pad = 20
            crop_rect = QtCore.QRect(
                max(0, min_x - pad),
                max(0, min_y - 40),
                min(canvas_width, max_x - min_x + 2*pad),
                min(canvas_height, max_y - min_y + 80)
            )

            final_pixmap = pixmap.copy(crop_rect)
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

    # ── Real-time Graph ───────────────────────────────────────────────────────
    def update_rt_graph(self, epoch, logs):
        """Update the live matplotlib graph with new epoch data"""
        try:
            self.epochs_list.append(epoch)
            ta = logs.get('accuracy', 0)
            va = logs.get('val_accuracy', 0)
            tl = logs.get('loss', 0)
            vl = logs.get('val_loss', 0)

            self.train_acc.append(ta)
            self.val_acc.append(va)
            self.train_loss.append(tl)
            self.val_loss.append(vl)

            # Update metric cards
            self._card_epoch.set_value(str(epoch))
            self._card_train_acc.set_value(f"{ta:.3f}")
            self._card_val_acc.set_value(f"{va:.3f}")
            self._card_train_loss.set_value(f"{tl:.3f}")
            self._card_val_loss.set_value(f"{vl:.3f}")

            # ── Accuracy plot ──
            self.ax_acc.clear()
            self.ax_acc.set_facecolor("#FFFFFF")
            self.ax_acc.plot(self.epochs_list, self.train_acc,
                             color=PALETTE["chart_blue"], linewidth=2, marker='o', markersize=4,
                             label='Train', zorder=3)
            self.ax_acc.plot(self.epochs_list, self.val_acc,
                             color=PALETTE["success"], linewidth=2, marker='o', markersize=4,
                             linestyle='--', label='Val', zorder=3)
            self.ax_acc.fill_between(self.epochs_list, self.train_acc,
                                     alpha=0.08, color=PALETTE["chart_blue"])
            self.ax_acc.fill_between(self.epochs_list, self.val_acc,
                                     alpha=0.08, color=PALETTE["success"])
            self.ax_acc.set_title('Accuracy', pad=6)
            self.ax_acc.set_xlabel('Epoch')
            self.ax_acc.set_ylabel('Accuracy')
            self.ax_acc.legend(loc='lower right', fontsize=8, framealpha=0.85)
            self.ax_acc.relim()
            self.ax_acc.autoscale_view()

            # ── Loss plot ──
            self.ax_loss.clear()
            self.ax_loss.set_facecolor("#FFFFFF")
            self.ax_loss.plot(self.epochs_list, self.train_loss,
                              color=PALETTE["warning"], linewidth=2, marker='o', markersize=4,
                              label='Train', zorder=3)
            self.ax_loss.plot(self.epochs_list, self.val_loss,
                              color=PALETTE["danger"], linewidth=2, marker='o', markersize=4,
                              linestyle='--', label='Val', zorder=3)
            self.ax_loss.fill_between(self.epochs_list, self.train_loss,
                                      alpha=0.08, color=PALETTE["warning"])
            self.ax_loss.fill_between(self.epochs_list, self.val_loss,
                                      alpha=0.08, color=PALETTE["danger"])
            self.ax_loss.set_title('Loss', pad=6)
            self.ax_loss.set_xlabel('Epoch')
            self.ax_loss.set_ylabel('Loss')
            self.ax_loss.legend(loc='upper right', fontsize=8, framealpha=0.85)
            self.ax_loss.relim()
            self.ax_loss.autoscale_view()

            self.figure.tight_layout(pad=2.0)
            self.canvas.draw_idle()

        except Exception as e:
            self.logger.log_exception(f"Error updating graph: {e}")

    # ── Viz update (debounced) ────────────────────────────────────────────────
    def update_model_viz(self):
        """Debounced update - restarts timer on each call"""
        self.viz_update_timer.stop()
        self.viz_update_timer.start(500)

    def _do_update_viz(self):
        """Actually generate and display model architecture diagram"""
        try:
            base_model_name = self.model_selector.currentText()

            class MockLayer:
                def __init__(self, name, units=None):
                    self.name = name
                    self.units = units

            layers_list = [MockLayer(base_model_name), MockLayer("Flatten")]

            custom_layers_str = self.layer_config_input.text()
            custom_layers_desc = "None"

            # Read dropout rate — 0.0 means no dropout
            try:
                dropout_rate = float(self.dropout_rate_input.text().strip())
            except (ValueError, AttributeError):
                dropout_rate = 0.5  # safe fallback

            if custom_layers_str:
                try:
                    custom_layers = [int(x.strip()) for x in custom_layers_str.split(',') if x.strip()]
                    for size in custom_layers:
                        layers_list.append(MockLayer("Dense", units=size))
                        if dropout_rate > 0.0:
                            layers_list.append(MockLayer(f"Dropout({dropout_rate})"))
                    custom_layers_desc = str(custom_layers)
                except ValueError:
                    self.logger.log_status("Invalid Custom Layer input for viz.")

            num_classes = 24
            try:
                from pathlib import Path
                input_dir = Path(self.path_input.text())
                if input_dir.exists() and input_dir.is_dir():
                    classes = [d for d in input_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
                    if classes:
                        num_classes = len(classes)
            except Exception:
                pass
            layers_list.append(MockLayer("Dense", units=num_classes))

            total_params = "≈ 25M+"
            info_text = f"Base: {base_model_name}  ·  Custom: {custom_layers_desc}  ·  Params: {total_params}"
            self.model_info_label.setText(info_text)

            self.draw_horizontal_model_viz(layers_list, base_model_name)

        except Exception as e:
            self.logger.log_exception(f"Error generating model viz: {e}")
            self.model_viz_label.setText("Visualization failed.")

    # ── Plot Window ───────────────────────────────────────────────────────────
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


# TrainWorker has been extracted to workers/train_worker.py
# Re-export for backward compatibility
from workers.train_worker import TrainWorker  # noqa: F401


def main():
    app = QApplication(sys.argv)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()