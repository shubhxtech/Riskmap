
"""
RiskMap Styles — Cross-platform (Windows + macOS)

Design System:
  - Primary: #1DA1F2 (Brand Blue)
  - Accent:  #ED7A05 (Brand Orange)
  - Success: #28a745
  - Text:    #1e1e1e (Dark), #5f6368 (Muted), #ffffff (Inverse)
  - Surface: #ffffff, #f8f9fa, #f0f0f0
  - Border:  #dadce0, #c0c0c0
  
Font Stack (macOS first, Windows fallback):
  "SF Pro Display", "Segoe UI", "Roboto", "Helvetica Neue", sans-serif
"""

import sys

# Cross-platform font stack
if sys.platform == "darwin":
    _FONT_STACK = '".AppleSystemUIFont", "Helvetica Neue", "Helvetica", sans-serif'
    _MONO_FONT = '"Menlo", "SF Mono", "Consolas", monospace'
else:
    _FONT_STACK = '"Segoe UI", "Roboto", "Helvetica", sans-serif'
    _MONO_FONT = '"Cascadia Code", "Consolas", "Courier New", monospace'


# RiskMap Styles
DARK_THEME = f"""
/* General Application Style */
QWidget {{
    background-color: #2b2b2b;
    color: #e0e0e0;
    font-family: {_FONT_STACK};
    font-size: 14px;
}}

/* Main Window & Dialogs */
QMainWindow, QDialog {{
    background-color: #2b2b2b;
}}

/* Groups & Frames */
QGroupBox {{
    border: 1px solid #4d4d4d;
    border-radius: 6px;
    margin-top: 20px;
    font-weight: bold;
    color: #ffffff;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: #4da6ff;
}}

/* Buttons */
QPushButton {{
    background-color: #3e3e42;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 6px 12px;
    color: #ffffff;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: #4f4f53;
    border-color: #666666;
}}
QPushButton:pressed {{
    background-color: #007acc; /* Visual Studio Blue accent */
    border-color: #007acc;
}}
QPushButton:disabled {{
    background-color: #2d2d30;
    color: #6d6d6d;
    border-color: #3e3e42;
}}

/* Call to Action Button Style (Optional usage via objectName) */
QPushButton#PrimaryButton {{
    background-color: #007acc;
    border-color: #007acc;
}}
QPushButton#PrimaryButton:hover {{
    background-color: #1c97ea;
}}

/* Input Fields */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: #1e1e1e;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    padding: 4px;
    color: #e0e0e0;
    selection-background-color: #007acc;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid #007acc;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid #3e3e42;
    background-color: #2b2b2b;
    border-radius: 4px;
}}
QTabBar::tab {{
    background-color: #2d2d30;
    color: #b0b0b0;
    padding: 8px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: #1e1e1e;
    color: #ffffff;
    border-bottom: 2px solid #007acc;
}}
QTabBar::tab:hover {{
    background-color: #3e3e42;
    color: #ffffff;
}}

/* ScrollBars */
QScrollBar:vertical {{
    border: none;
    background: #2b2b2b;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #4d4d4d;
    min-height: 20px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: #666666;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Labels */
QLabel {{
    color: #e0e0e0;
}}

/* Tooltips */
QToolTip {{
    background-color: #1e1e1e;
    color: #ffffff;
    border: 1px solid #4d4d4d;
    padding: 4px;
}}

/* Progress Bar */
QProgressBar {{
    border: 1px solid #3e3e42;
    border-radius: 4px;
    text-align: center;
    background-color: #1e1e1e;
    color: #ffffff;
}}
QProgressBar::chunk {{
    background-color: #007acc;
    width: 20px;
}}
"""

LIGHT_THEME = f"""
/* General Application Style */
QWidget {{
    background-color: #ffffff;
    color: #1e1e1e;
    font-family: {_FONT_STACK};
    font-size: 14px;
}}

/* Main Window & Dialogs */
QMainWindow, QDialog {{
    background-color: #f5f5f5;
}}

/* Groups & Frames */
QGroupBox {{
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    margin-top: 20px;
    font-weight: bold;
    color: #1e1e1e;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: #0078d4;
}}

/* Buttons */
QPushButton {{
    background-color: #f0f0f0;
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    padding: 6px 12px;
    color: #1e1e1e;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: #e5e5e5;
    border-color: #a0a0a0;
}}
QPushButton:pressed {{
    background-color: #0078d4;
    border-color: #0078d4;
    color: #ffffff;
}}
QPushButton:disabled {{
    background-color: #f5f5f5;
    color: #a0a0a0;
    border-color: #d0d0d0;
}}

/* Call to Action Button Style (Optional usage via objectName) */
QPushButton#PrimaryButton {{
    background-color: #0078d4;
    border-color: #0078d4;
    color: #ffffff;
}}
QPushButton#PrimaryButton:hover {{
    background-color: #1c97ea;
}}

/* Input Fields */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    padding: 4px;
    color: #1e1e1e;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid #0078d4;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid #d0d0d0;
    background-color: #ffffff;
    border-radius: 4px;
}}
QTabBar::tab {{
    background-color: #f0f0f0;
    color: #606060;
    padding: 8px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: #ffffff;
    color: #1e1e1e;
    border-bottom: 2px solid #0078d4;
}}
QTabBar::tab:hover {{
    background-color: #e5e5e5;
    color: #1e1e1e;
}}

/* ScrollBars */
QScrollBar:vertical {{
    border: none;
    background: #f5f5f5;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #c0c0c0;
    min-height: 20px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: #a0a0a0;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Labels */
QLabel {{
    color: #1e1e1e;
}}

/* Tooltips */
QToolTip {{
    background-color: #ffffff;
    color: #1e1e1e;
    border: 1px solid #c0c0c0;
    padding: 4px;
}}

/* Progress Bar */
QProgressBar {{
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    text-align: center;
    background-color: #f5f5f5;
    color: #1e1e1e;
}}
QProgressBar::chunk {{
    background-color: #0078d4;
    width: 20px;
}}
"""

BRAND_THEME = f"""
/* ═══════════════════════════════════════════════════════
   BRAND THEME — RiskMap / RAPID-Lens
   Cross-platform: macOS + Windows
   ═══════════════════════════════════════════════════════ */

/* === Base Reset === */
QWidget {{
    background-color: #ffffff;
    color: #1e1e1e;
    font-family: {_FONT_STACK};
    font-size: 14px;
}}

QMainWindow, QDialog {{
    background-color: #f8f9fa;
}}

/* === Labels (force left-alignment on macOS) === */
QLabel {{
    color: #1e1e1e;
    padding: 0px;
    background-color: transparent;
}}

/* === Groups & Frames === */
QGroupBox {{
    border: 1px solid #dadce0;
    border-radius: 8px;
    margin-top: 24px;
    padding-top: 16px;
    font-weight: 600;
    font-size: 14px;
    color: #1DA1F2;
    background-color: #ffffff;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    color: #1DA1F2;
    background-color: #ffffff;
    border-radius: 4px;
}}

/* === Floating Widgets (Map overlay) === */
QFrame#FloatingWidget {{
    background-color: rgba(255, 255, 255, 0.95);
    border: none;
    border-radius: 12px;
    padding: 4px;
}}

/* === Bottom Panel === */
QFrame#BottomPanel {{
    background-color: #ffffff;
    border-top: 2px solid #1DA1F2;
    min-height: 160px;
}}

/* === Stats === */
QLabel#StatValue {{
    color: #3c4043;
    font-weight: 600;
    font-size: 15px;
    background-color: transparent;
}}
QLabel#StatLabel {{
    color: #5f6368;
    font-size: 13px;
    background-color: transparent;
}}

/* ═══════════════════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════════════════ */
QPushButton {{
    background-color: #1DA1F2;
    border: 1px solid #1A91DA;
    border-radius: 6px;
    padding: 8px 18px;
    color: #ffffff;
    font-weight: 600;
    font-size: 13px;
    min-height: 20px;
}}
QPushButton:hover {{
    background-color: #1A91DA;
    border-color: #1681BF;
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: #1681BF;
    border-color: #126FA6;
}}
QPushButton:disabled {{
    background-color: #E8E8E8;
    color: #A0A0A0;
    border-color: #D0D0D0;
}}

/* Action Button (CTA) */
QPushButton#ActionButton {{
    background-color: #1DA1F2;
    color: #ffffff;
    border: none;
    font-weight: 700;
    font-size: 14px;
    padding: 12px 28px;
    border-radius: 8px;
}}
QPushButton#ActionButton:hover {{
    background-color: #1A91DA;
}}
QPushButton#ActionButton:pressed {{
    background-color: #1681BF;
}}

/* === Tooltips === */
QToolTip {{
    background-color: #2d2d2d;
    color: #ffffff;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: normal;
}}

/* === Tool Buttons (Map toolbar) === */
QPushButton#ToolButton {{
    background-color: transparent;
    border: none;
    color: #555;
    font-size: 16px;
    border-radius: 8px;
    padding: 6px;
    min-height: 28px;
    min-width: 28px;
}}
QPushButton#ToolButton:hover {{
    background-color: #f0f0f0;
    color: #1DA1F2;
}}
QPushButton#ToolButton:checked {{
    background-color: #e3f2fd;
    color: #1DA1F2;
    border: 1px solid #1DA1F2;
}}

/* ═══════════════════════════════════════════════════════
   INPUT FIELDS
   ═══════════════════════════════════════════════════════ */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background-color: #ffffff;
    border: 1px solid #dadce0;
    border-radius: 6px;
    padding: 6px 10px;
    color: #1e1e1e;
    selection-background-color: #1DA1F2;
    selection-color: #ffffff;
    min-height: 22px;
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 2px solid #1DA1F2;
    padding: 5px 9px; /* compensate for thicker border */
}}
QLineEdit:disabled, QTextEdit:disabled {{
    background-color: #f5f5f5;
    color: #999999;
}}

/* === Modern Dropdown === */
QComboBox {{
    background-color: #ffffff;
    border: 1px solid #dadce0;
    border-radius: 8px;
    padding: 8px 14px;
    padding-right: 35px;
    color: #1e1e1e;
    selection-background-color: #1DA1F2;
    selection-color: #ffffff;
    min-height: 22px;
}}
QComboBox:hover {{
    background-color: #f8f9fa;
    border-color: #c0c0c0;
}}
QComboBox:focus {{
    border: 2px solid #1DA1F2;
    padding: 7px 13px;
    padding-right: 34px;
}}
QComboBox:on {{
    border: 2px solid #1DA1F2;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}}

/* Dropdown Arrow */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border-left: none;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background-color: transparent;
}}
QComboBox::drop-down:hover {{
    background-color: rgba(10, 140, 207, 0.1);
}}
QComboBox::down-arrow {{
    image: url(%ICON_PATH%/arrow_down.png);
    width: 14px;
    height: 14px;
    subcontrol-position: center;
    border: none;
}}
QComboBox::down-arrow:on {{
    image: url(%ICON_PATH%/arrow_up.png);
    height: 14px;
    width: 14px;
    subcontrol-position: center;
}}

/* Dropdown Popup */
QComboBox QAbstractItemView {{
    background-color: #ffffff;
    border: 1px solid #dadce0;
    border-radius: 6px;
    selection-background-color: #e3f2fd;
    selection-color: #1DA1F2;
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    border-radius: 4px;
    min-height: 20px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: #f0f7ff;
    color: #1DA1F2;
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: #e3f2fd;
    color: #1DA1F2;
    font-weight: 500;
}}

/* ═══════════════════════════════════════════════════════
   TAB WIDGET
   ═══════════════════════════════════════════════════════ */
QTabWidget::pane {{
    border: 1px solid #dadce0;
    top: -1px;
    background-color: #ffffff;
    border-radius: 4px;
    border-top-left-radius: 0px;
}}

/* Force tab bar left alignment */
QTabWidget::tab-bar {{
    left: 0px;
    alignment: left;
}}

QTabBar {{
    alignment: left;
}}

QTabBar::tab {{
    background-color: #f8f9fa;
    color: #5f6368;
    padding: 10px 28px;
    border: 1px solid #dadce0;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
    min-width: 110px;
    min-height: 18px;
    font-weight: 500;
    font-size: 13px;
}}
QTabBar::tab:hover {{
    background-color: #e8f0fe;
    color: #1a73e8;
}}
QTabBar::tab:selected {{
    background-color: #ffffff;
    color: #1DA1F2;
    border-color: #dadce0;
    border-bottom: 2px solid #ffffff;
    border-top: 3px solid #1DA1F2;
    font-weight: 600;
}}
QTabBar::tab:pressed {{
    background-color: #d2e3fc;
    padding-top: 12px;
    padding-bottom: 8px;
}}
QTabBar QToolButton {{
    background-color: #f1f3f4;
    border: none;
}}

/* === Stats Text === */
QLabel#StatValue {{
    color: #ED7A05;
    font-weight: bold;
    font-size: 14px;
    background-color: transparent;
}}

/* ═══════════════════════════════════════════════════════
   PROGRESS BAR
   ═══════════════════════════════════════════════════════ */
QProgressBar {{
    border: none;
    border-radius: 4px;
    background-color: #f0f0f0;
    text-align: center;
    min-height: 8px;
    max-height: 20px;
    font-size: 11px;
    color: #5f6368;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1DA1F2, stop:1 #ED7A05);
    border-radius: 4px;
}}

/* ═══════════════════════════════════════════════════════
   SCROLLBARS
   ═══════════════════════════════════════════════════════ */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c1c1c1;
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #999999;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 8px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #c1c1c1;
    min-width: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #999999;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ═══════════════════════════════════════════════════════
   DENSITY BUTTONS
   ═══════════════════════════════════════════════════════ */
QPushButton#DensityButton {{
    background-color: #ffffff;
    color: #5f6368;
    border: 1.5px solid #dadce0;
    border-radius: 8px;
    padding: 10px 16px;
    font-weight: 500;
    font-size: 13px;
    min-width: 80px;
    text-align: left;
}}
QPushButton#DensityButton:hover {{
    background-color: #e3f2fd;
    border-color: #1DA1F2;
    color: #1DA1F2;
}}
QPushButton#DensityButton:checked {{
    background-color: #1DA1F2;
    color: #ffffff;
    border: 2px solid #1DA1F2;
    font-weight: 600;
}}
QPushButton#DensityButton:checked:hover {{
    background-color: #1A91DA;
    border-color: #1A91DA;
}}
QPushButton#DensityButton:pressed {{
    background-color: #1A91DA;
}}

/* Individual density button spacing */
QPushButton#DensityButton[class="first"],
QPushButton#DensityButton[class="middle"],
QPushButton#DensityButton[class="last"] {{
    border-radius: 8px;
    margin-right: 8px;
}}
QPushButton#DensityButton[class="last"] {{
    margin-right: 0px;
}}

/* ═══════════════════════════════════════════════════════
   CHECKBOX
   ═══════════════════════════════════════════════════════ */
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    color: #3c4043;
    background-color: transparent;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid #dadce0;
    border-radius: 4px;
    background-color: #ffffff;
}}
QCheckBox::indicator:checked {{
    background-color: #1DA1F2;
    border-color: #1DA1F2;
}}
QCheckBox::indicator:hover {{
    border-color: #1DA1F2;
}}

/* ═══════════════════════════════════════════════════════
   FORM LAYOUT (QFormLayout label alignment)
   ═══════════════════════════════════════════════════════ */
QFormLayout {{
    margin: 0px;
}}

/* ═══════════════════════════════════════════════════════
   SPLITTER HANDLE
   ═══════════════════════════════════════════════════════ */
QSplitter::handle {{
    background-color: #dadce0;
    width: 2px;
    margin: 4px 8px;
    border-radius: 1px;
}}
QSplitter::handle:hover {{
    background-color: #1DA1F2;
}}

/* ═══════════════════════════════════════════════════════
   SCROLL AREA
   ═══════════════════════════════════════════════════════ */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* ═══════════════════════════════════════════════════════
   TREE / TABLE WIDGETS
   ═══════════════════════════════════════════════════════ */
QTreeWidget, QTableWidget {{
    border: 1px solid #dadce0;
    border-radius: 6px;
    background-color: #ffffff;
    alternate-background-color: #f8f9fa;
    gridline-color: #f0f0f0;
}}
QTreeWidget::item, QTableWidget::item {{
    padding: 4px 8px;
    border: none;
}}
QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: #e3f2fd;
    color: #1DA1F2;
}}
QHeaderView::section {{
    background-color: #f8f9fa;
    color: #3c4043;
    font-weight: 600;
    padding: 6px 8px;
    border: none;
    border-bottom: 2px solid #dadce0;
}}
"""
