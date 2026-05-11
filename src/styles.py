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


# ─────────────────────────────────────────────────────────────────────────────
# DARK THEME
# ─────────────────────────────────────────────────────────────────────────────
DARK_THEME = f"""
/* ═══════════════════════════════════════════════════════
   DARK THEME — RiskMap
   Elevated surfaces · precise type scale · smooth motion
   ═══════════════════════════════════════════════════════ */

/* === Base Reset === */
QWidget {{
    background-color: #1c1c1f;
    color: #e8e8ec;
    font-family: {_FONT_STACK};
    font-size: 13.5px;
    letter-spacing: 0.01em;
}}

/* === Main Window & Dialogs === */
QMainWindow, QDialog {{
    background-color: #1c1c1f;
}}

/* === Groups & Frames === */
QGroupBox {{
    background-color: #252528;
    border: 1px solid #38383d;
    border-radius: 10px;
    margin-top: 22px;
    padding: 16px 14px 12px 14px;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #8b8b96;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: #5ba3d9;
    background-color: #252528;
    border-radius: 3px;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}

/* === Buttons === */
QPushButton {{
    background-color: #2d2d32;
    border: 1px solid #44444a;
    border-radius: 7px;
    padding: 7px 16px;
    color: #e0e0e6;
    font-weight: 500;
    font-size: 13px;
    letter-spacing: 0.015em;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: #36363c;
    border-color: #5a5a64;
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: #0e7fc4;
    border-color: #0e7fc4;
    color: #ffffff;
    padding-top: 8px;
    padding-bottom: 6px;
}}
QPushButton:disabled {{
    background-color: #232327;
    color: #4a4a52;
    border-color: #2e2e34;
}}
QPushButton:focus {{
    outline: none;
    border: 2px solid #3a9fd6;
}}

/* === Call to Action === */
QPushButton#PrimaryButton {{
    background-color: #0e7fc4;
    border: 1px solid #0a6aaa;
    color: #ffffff;
    font-weight: 600;
    border-radius: 7px;
    padding: 8px 20px;
}}
QPushButton#PrimaryButton:hover {{
    background-color: #1991d9;
    border-color: #1480c0;
}}
QPushButton#PrimaryButton:pressed {{
    background-color: #0b6aaa;
}}

/* === Input Fields === */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: #141417;
    border: 1.5px solid #38383d;
    border-radius: 7px;
    padding: 6px 10px;
    color: #e8e8ec;
    selection-background-color: #0e7fc4;
    selection-color: #ffffff;
    min-height: 24px;
    font-size: 13px;
}}
QLineEdit:hover, QTextEdit:hover, QComboBox:hover {{
    border-color: #54545e;
    background-color: #17171b;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 2px solid #3a9fd6;
    padding: 5px 9px;
    background-color: #12121a;
}}
QLineEdit:disabled, QTextEdit:disabled {{
    background-color: #1e1e22;
    color: #45454e;
    border-color: #2a2a30;
}}

/* === Tab Widget === */
QTabWidget::pane {{
    border: 1px solid #38383d;
    background-color: #1e1e22;
    border-radius: 8px;
    border-top-left-radius: 0px;
    top: -1px;
}}
QTabWidget::tab-bar {{
    left: 0px;
    alignment: left;
}}
QTabBar::tab {{
    background-color: #252528;
    color: #7a7a86;
    padding: 9px 20px;
    border: 1px solid #38383d;
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    margin-right: 3px;
    font-weight: 500;
    font-size: 12.5px;
    letter-spacing: 0.01em;
    min-width: 80px;
}}
QTabBar::tab:hover {{
    background-color: #2e2e34;
    color: #c0c0cc;
}}
QTabBar::tab:selected {{
    background-color: #1e1e22;
    color: #4eb5f5;
    border-color: #38383d;
    border-bottom: 2px solid #1e1e22;
    border-top: 2px solid #3a9fd6;
    font-weight: 600;
}}
QTabBar::tab:pressed {{
    padding-top: 10px;
    padding-bottom: 8px;
}}
QTabBar QToolButton {{
    background-color: #252528;
    border: none;
    color: #7a7a86;
}}

/* === ScrollBars === */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #3a3a42;
    min-height: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #55555f;
}}
QScrollBar::handle:vertical:pressed {{
    background: #3a9fd6;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: #3a3a42;
    min-width: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #55555f;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* === Labels === */
QLabel {{
    color: #e0e0e6;
    background-color: transparent;
    padding: 0px;
}}

/* === Tooltips === */
QToolTip {{
    background-color: #0f0f12;
    color: #e8e8ec;
    border: 1px solid #44444a;
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 12px;
    letter-spacing: 0.01em;
}}

/* === Progress Bar === */
QProgressBar {{
    border: none;
    border-radius: 5px;
    background-color: #252528;
    text-align: center;
    min-height: 8px;
    max-height: 18px;
    font-size: 11px;
    color: #8b8b96;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0e7fc4, stop:1 #1aa3f5);
    border-radius: 5px;
}}

/* === Tree / Table === */
QTreeWidget, QTableWidget {{
    border: 1px solid #38383d;
    border-radius: 8px;
    background-color: #1e1e22;
    alternate-background-color: #232327;
    gridline-color: #2a2a30;
    outline: none;
}}
QTreeWidget::item, QTableWidget::item {{
    padding: 5px 10px;
    border: none;
}}
QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: #1a3a55;
    color: #4eb5f5;
    border-radius: 4px;
}}
QTreeWidget::item:hover, QTableWidget::item:hover {{
    background-color: #252530;
}}
QHeaderView::section {{
    background-color: #252528;
    color: #8b8b96;
    font-weight: 600;
    font-size: 11.5px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 7px 10px;
    border: none;
    border-bottom: 2px solid #38383d;
}}

/* === Splitter === */
QSplitter::handle {{
    background-color: #38383d;
    width: 1px;
    margin: 6px 10px;
    border-radius: 1px;
}}
QSplitter::handle:hover {{
    background-color: #3a9fd6;
}}

/* === Scroll Area === */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* === CheckBox === */
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    color: #c0c0cc;
    background-color: transparent;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1.5px solid #44444a;
    border-radius: 4px;
    background-color: #141417;
}}
QCheckBox::indicator:checked {{
    background-color: #0e7fc4;
    border-color: #0e7fc4;
}}
QCheckBox::indicator:hover {{
    border-color: #3a9fd6;
}}

/* === Stat Labels === */
QLabel#StatValue {{
    color: #4eb5f5;
    font-weight: 700;
    font-size: 15px;
    background-color: transparent;
    letter-spacing: -0.01em;
}}
QLabel#StatLabel {{
    color: #7a7a86;
    font-size: 12px;
    background-color: transparent;
    letter-spacing: 0.02em;
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# LIGHT THEME
# ─────────────────────────────────────────────────────────────────────────────
LIGHT_THEME = f"""
/* ═══════════════════════════════════════════════════════
   LIGHT THEME — RiskMap
   Clean surfaces · refined type · crisp interactions
   ═══════════════════════════════════════════════════════ */

/* === Base Reset === */
QWidget {{
    background-color: #fafafa;
    color: #1e1e1e;
    font-family: {_FONT_STACK};
    font-size: 13.5px;
    letter-spacing: 0.01em;
}}

/* === Main Window & Dialogs === */
QMainWindow, QDialog {{
    background-color: #f2f3f5;
}}

/* === Groups & Frames === */
QGroupBox {{
    background-color: #ffffff;
    border: 1px solid #e0e2e6;
    border-radius: 10px;
    margin-top: 22px;
    padding: 16px 14px 12px 14px;
    font-weight: 600;
    font-size: 11.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #8a8f9a;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: #0070c5;
    background-color: #ffffff;
    border-radius: 3px;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}

/* === Buttons === */
QPushButton {{
    background-color: #ffffff;
    border: 1px solid #d0d4da;
    border-radius: 7px;
    padding: 7px 16px;
    color: #2a2a2a;
    font-weight: 500;
    font-size: 13px;
    letter-spacing: 0.01em;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: #f5f6f8;
    border-color: #adb4be;
    color: #111111;
}}
QPushButton:pressed {{
    background-color: #0070c5;
    border-color: #0062ae;
    color: #ffffff;
    padding-top: 8px;
    padding-bottom: 6px;
}}
QPushButton:disabled {{
    background-color: #f5f5f5;
    color: #b0b8c4;
    border-color: #e0e2e6;
}}
QPushButton:focus {{
    outline: none;
    border: 2px solid #0084e0;
}}

/* === Call to Action === */
QPushButton#PrimaryButton {{
    background-color: #0078d4;
    border: 1px solid #006abf;
    color: #ffffff;
    font-weight: 600;
    border-radius: 7px;
    padding: 8px 20px;
}}
QPushButton#PrimaryButton:hover {{
    background-color: #1688e0;
    border-color: #0874cc;
}}
QPushButton#PrimaryButton:pressed {{
    background-color: #0062b5;
}}

/* === Input Fields === */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: #ffffff;
    border: 1.5px solid #d0d4da;
    border-radius: 7px;
    padding: 6px 10px;
    color: #1e1e1e;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
    min-height: 24px;
    font-size: 13px;
}}
QLineEdit:hover, QTextEdit:hover, QComboBox:hover {{
    border-color: #a8b0bc;
    background-color: #fdfdfd;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 2px solid #0084e0;
    padding: 5px 9px;
    background-color: #ffffff;
}}
QLineEdit:disabled, QTextEdit:disabled {{
    background-color: #f5f5f7;
    color: #b0b8c4;
    border-color: #e4e6ea;
}}

/* === Tab Widget === */
QTabWidget::pane {{
    border: 1px solid #dde0e6;
    background-color: #ffffff;
    border-radius: 8px;
    border-top-left-radius: 0px;
    top: -1px;
}}
QTabWidget::tab-bar {{
    left: 0px;
    alignment: left;
}}
QTabBar::tab {{
    background-color: #f2f3f5;
    color: #7a8290;
    padding: 9px 20px;
    border: 1px solid #dde0e6;
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    margin-right: 3px;
    font-weight: 500;
    font-size: 12.5px;
    letter-spacing: 0.01em;
    min-width: 80px;
}}
QTabBar::tab:hover {{
    background-color: #e8eaee;
    color: #2a2a2a;
}}
QTabBar::tab:selected {{
    background-color: #ffffff;
    color: #0078d4;
    border-color: #dde0e6;
    border-bottom: 2px solid #ffffff;
    border-top: 2px solid #0078d4;
    font-weight: 600;
}}
QTabBar::tab:pressed {{
    padding-top: 10px;
    padding-bottom: 8px;
}}
QTabBar QToolButton {{
    background-color: #f2f3f5;
    border: none;
}}

/* === ScrollBars === */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #d0d4da;
    min-height: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #b0b8c4;
}}
QScrollBar::handle:vertical:pressed {{
    background: #0078d4;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: #d0d4da;
    min-width: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #b0b8c4;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* === Labels === */
QLabel {{
    color: #1e1e1e;
    background-color: transparent;
    padding: 0px;
}}

/* === Tooltips === */
QToolTip {{
    background-color: #1a1a1e;
    color: #f0f0f4;
    border: 1px solid #3a3a42;
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 12px;
    letter-spacing: 0.01em;
}}

/* === Progress Bar === */
QProgressBar {{
    border: none;
    border-radius: 5px;
    background-color: #eaedf1;
    text-align: center;
    min-height: 8px;
    max-height: 18px;
    font-size: 11px;
    color: #7a8290;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0078d4, stop:1 #1ea0f5);
    border-radius: 5px;
}}

/* === Tree / Table === */
QTreeWidget, QTableWidget {{
    border: 1px solid #dde0e6;
    border-radius: 8px;
    background-color: #ffffff;
    alternate-background-color: #f8f9fb;
    gridline-color: #eef0f4;
    outline: none;
}}
QTreeWidget::item, QTableWidget::item {{
    padding: 5px 10px;
    border: none;
}}
QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: #ddeeff;
    color: #0068c0;
    border-radius: 4px;
}}
QTreeWidget::item:hover, QTableWidget::item:hover {{
    background-color: #f0f4fa;
}}
QHeaderView::section {{
    background-color: #f2f3f5;
    color: #7a8290;
    font-weight: 600;
    font-size: 11.5px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 7px 10px;
    border: none;
    border-bottom: 2px solid #dde0e6;
}}

/* === Splitter === */
QSplitter::handle {{
    background-color: #dde0e6;
    width: 1px;
    margin: 6px 10px;
    border-radius: 1px;
}}
QSplitter::handle:hover {{
    background-color: #0078d4;
}}

/* === Scroll Area === */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* === CheckBox === */
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    color: #3a3a3a;
    background-color: transparent;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1.5px solid #c0c8d4;
    border-radius: 4px;
    background-color: #ffffff;
}}
QCheckBox::indicator:checked {{
    background-color: #0078d4;
    border-color: #0078d4;
}}
QCheckBox::indicator:hover {{
    border-color: #0084e0;
}}

/* === Stat Labels === */
QLabel#StatValue {{
    color: #0068c0;
    font-weight: 700;
    font-size: 15px;
    background-color: transparent;
    letter-spacing: -0.01em;
}}
QLabel#StatLabel {{
    color: #7a8290;
    font-size: 12px;
    background-color: transparent;
    letter-spacing: 0.02em;
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# BRAND THEME
# ─────────────────────────────────────────────────────────────────────────────
BRAND_THEME = f"""
/* ═══════════════════════════════════════════════════════
   BRAND THEME — RiskMap / RAPID-Lens
   Cross-platform: macOS + Windows
   System: 8-point grid · fluid type · elevated surfaces
   ═══════════════════════════════════════════════════════ */

/* === Base Reset === */
QWidget {{
    background-color: #ffffff;
    color: #1e1e1e;
    font-family: {_FONT_STACK};
    font-size: 13.5px;
    letter-spacing: 0.012em;
}}

QMainWindow, QDialog {{
    background-color: #f4f5f7;
}}

/* === Labels === */
QLabel {{
    color: #1e1e1e;
    padding: 0px;
    background-color: transparent;
    letter-spacing: 0.01em;
}}

/* === Groups & Frames === */
QGroupBox {{
    border: 1px solid #e2e5ea;
    border-radius: 10px;
    margin-top: 26px;
    padding: 18px 16px 14px 16px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #9ba3ae;
    background-color: #ffffff;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 16px;
    padding: 2px 8px;
    color: #1DA1F2;
    background-color: #ffffff;
    border-radius: 4px;
    font-size: 10.5px;
    letter-spacing: 0.10em;
    text-transform: uppercase;
}}

/* === Floating Widgets (Map overlay) === */
QFrame#FloatingWidget {{
    background-color: rgba(255, 255, 255, 0.96);
    border: none;
    border-radius: 14px;
    padding: 6px;
}}

/* === Bottom Panel === */
QFrame#BottomPanel {{
    background-color: #ffffff;
    border-top: 2px solid #1DA1F2;
    min-height: 160px;
}}

/* === Stat Labels === */
QLabel#StatValue {{
    color: #1e2a3a;
    font-weight: 700;
    font-size: 16px;
    letter-spacing: -0.02em;
    background-color: transparent;
}}
QLabel#StatLabel {{
    color: #6b7280;
    font-size: 12px;
    letter-spacing: 0.03em;
    background-color: transparent;
}}

/* ═══════════════════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════════════════ */
QPushButton {{
    background-color: #1DA1F2;
    border: 1px solid #1690db;
    border-radius: 8px;
    padding: 8px 20px;
    color: #ffffff;
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.015em;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: #1690db;
    border-color: #127ec0;
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: #1278b5;
    border-color: #0f6a9e;
    padding-top: 9px;
    padding-bottom: 7px;
}}
QPushButton:disabled {{
    background-color: #e9ecf0;
    color: #aab0ba;
    border-color: #dde1e7;
}}
QPushButton:focus {{
    outline: none;
    border: 2px solid #69c4f8;
    padding: 7px 19px;
}}

/* === Action Button (CTA) === */
QPushButton#ActionButton {{
    background-color: #1DA1F2;
    color: #ffffff;
    border: none;
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.01em;
    padding: 13px 30px;
    border-radius: 10px;
    min-height: 26px;
}}
QPushButton#ActionButton:hover {{
    background-color: #1690db;
}}
QPushButton#ActionButton:pressed {{
    background-color: #1278b5;
    padding-top: 14px;
    padding-bottom: 12px;
}}
QPushButton#ActionButton:focus {{
    border: 2px solid #69c4f8;
    padding: 11px 28px;
}}

/* === Tooltips === */
QToolTip {{
    background-color: #1a2030;
    color: #f0f4f8;
    border: 1px solid #2d3748;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12px;
    font-weight: 400;
    letter-spacing: 0.01em;
}}

/* === Tool Buttons (Map toolbar) === */
QPushButton#ToolButton {{
    background-color: transparent;
    border: none;
    color: #6b7280;
    font-size: 16px;
    border-radius: 9px;
    padding: 7px;
    min-height: 30px;
    min-width: 30px;
}}
QPushButton#ToolButton:hover {{
    background-color: #f0f4f8;
    color: #1DA1F2;
}}
QPushButton#ToolButton:checked {{
    background-color: #dff0fc;
    color: #1DA1F2;
    border: 1.5px solid #1DA1F2;
}}
QPushButton#ToolButton:pressed {{
    background-color: #cce8f8;
}}

/* ═══════════════════════════════════════════════════════
   INPUT FIELDS
   ═══════════════════════════════════════════════════════ */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background-color: #ffffff;
    border: 1.5px solid #dde1e7;
    border-radius: 8px;
    padding: 7px 12px;
    color: #1e1e1e;
    selection-background-color: #1DA1F2;
    selection-color: #ffffff;
    min-height: 24px;
    font-size: 13px;
}}
QLineEdit:hover, QTextEdit:hover {{
    border-color: #b0bac8;
    background-color: #fdfeff;
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 2px solid #1DA1F2;
    padding: 6px 11px;
    background-color: #f9fdff;
}}
QLineEdit:disabled, QTextEdit:disabled {{
    background-color: #f5f7fa;
    color: #aab0ba;
    border-color: #e2e7ed;
}}

/* === Modern Dropdown === */
QComboBox {{
    background-color: #ffffff;
    border: 1.5px solid #dde1e7;
    border-radius: 8px;
    padding: 7px 14px;
    padding-right: 38px;
    color: #1e1e1e;
    selection-background-color: #1DA1F2;
    selection-color: #ffffff;
    min-height: 24px;
    font-size: 13px;
}}
QComboBox:hover {{
    background-color: #f8fafc;
    border-color: #b0bac8;
}}
QComboBox:focus {{
    border: 2px solid #1DA1F2;
    padding: 6px 13px;
    padding-right: 37px;
    background-color: #f9fdff;
}}
QComboBox:on {{
    border: 2px solid #1DA1F2;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
    background-color: #f9fdff;
}}

/* Dropdown Arrow */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 34px;
    border-left: none;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background-color: transparent;
}}
QComboBox::drop-down:hover {{
    background-color: rgba(29, 161, 242, 0.08);
    border-radius: 0 8px 8px 0;
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
    border: 1.5px solid #dde1e7;
    border-top: none;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
    selection-background-color: #dff0fc;
    selection-color: #1DA1F2;
    outline: none;
    padding: 4px 4px 6px 4px;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 14px;
    border-radius: 6px;
    min-height: 22px;
    font-size: 13px;
    color: #1e1e1e;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: #f0f8fe;
    color: #1DA1F2;
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: #dff0fc;
    color: #1DA1F2;
    font-weight: 600;
}}

/* ═══════════════════════════════════════════════════════
   TAB WIDGET
   ═══════════════════════════════════════════════════════ */
QTabWidget::pane {{
    border: 1px solid #e2e5ea;
    top: -1px;
    background-color: #ffffff;
    border-radius: 8px;
    border-top-left-radius: 0px;
}}
QTabWidget::tab-bar {{
    left: 0px;
    alignment: left;
}}
QTabBar {{
    alignment: left;
}}
QTabBar::tab {{
    background-color: #f4f5f7;
    color: #6b7280;
    padding: 10px 28px;
    border: 1px solid #e2e5ea;
    border-bottom: none;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    margin-right: 4px;
    min-width: 110px;
    min-height: 20px;
    font-weight: 500;
    font-size: 13px;
    letter-spacing: 0.01em;
}}
QTabBar::tab:hover {{
    background-color: #eaf3fc;
    color: #1690db;
}}
QTabBar::tab:selected {{
    background-color: #ffffff;
    color: #1DA1F2;
    border-color: #e2e5ea;
    border-bottom: 2px solid #ffffff;
    border-top: 3px solid #1DA1F2;
    font-weight: 600;
}}
QTabBar::tab:pressed {{
    background-color: #d5e9f8;
    padding-top: 12px;
    padding-bottom: 8px;
}}
QTabBar QToolButton {{
    background-color: #f4f5f7;
    border: none;
    border-radius: 5px;
}}

/* ═══════════════════════════════════════════════════════
   PROGRESS BAR
   ═══════════════════════════════════════════════════════ */
QProgressBar {{
    border: none;
    border-radius: 5px;
    background-color: #edf0f4;
    text-align: center;
    min-height: 8px;
    max-height: 20px;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.02em;
    color: #6b7280;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1DA1F2, stop:0.65 #38b2f5, stop:1 #ED7A05);
    border-radius: 5px;
}}

/* ═══════════════════════════════════════════════════════
   SCROLLBARS
   ═══════════════════════════════════════════════════════ */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #d0d4da;
    min-height: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #b0b8c4;
}}
QScrollBar::handle:vertical:pressed {{
    background: #1DA1F2;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: #d0d4da;
    min-width: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #b0b8c4;
}}
QScrollBar::handle:horizontal:pressed {{
    background: #1DA1F2;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ═══════════════════════════════════════════════════════
   DENSITY BUTTONS
   ═══════════════════════════════════════════════════════ */
QPushButton#DensityButton {{
    background-color: #ffffff;
    color: #6b7280;
    border: 1.5px solid #e2e5ea;
    border-radius: 9px;
    padding: 10px 18px;
    font-weight: 500;
    font-size: 13px;
    letter-spacing: 0.01em;
    min-width: 84px;
    text-align: left;
}}
QPushButton#DensityButton:hover {{
    background-color: #eaf3fc;
    border-color: #1DA1F2;
    color: #1DA1F2;
}}
QPushButton#DensityButton:checked {{
    background-color: #1DA1F2;
    color: #ffffff;
    border: 2px solid #1690db;
    font-weight: 700;
    letter-spacing: 0.02em;
}}
QPushButton#DensityButton:checked:hover {{
    background-color: #1690db;
    border-color: #127ec0;
}}
QPushButton#DensityButton:pressed {{
    background-color: #1690db;
    padding-top: 11px;
    padding-bottom: 9px;
}}

/* Individual density button spacing */
QPushButton#DensityButton[class="first"],
QPushButton#DensityButton[class="middle"],
QPushButton#DensityButton[class="last"] {{
    border-radius: 9px;
    margin-right: 8px;
}}
QPushButton#DensityButton[class="last"] {{
    margin-right: 0px;
}}

/* ═══════════════════════════════════════════════════════
   CHECKBOX
   ═══════════════════════════════════════════════════════ */
QCheckBox {{
    spacing: 9px;
    font-size: 13px;
    letter-spacing: 0.01em;
    color: #374151;
    background-color: transparent;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1.5px solid #dde1e7;
    border-radius: 5px;
    background-color: #ffffff;
}}
QCheckBox::indicator:checked {{
    background-color: #1DA1F2;
    border-color: #1DA1F2;
}}
QCheckBox::indicator:hover {{
    border-color: #1DA1F2;
    background-color: #f0f8fe;
}}
QCheckBox::indicator:checked:hover {{
    background-color: #1690db;
    border-color: #1690db;
}}

/* ═══════════════════════════════════════════════════════
   STAT LABELS (Brand override — orange accent)
   ═══════════════════════════════════════════════════════ */
QLabel#StatValue {{
    color: #ED7A05;
    font-weight: 700;
    font-size: 15px;
    letter-spacing: -0.01em;
    background-color: transparent;
}}

/* ═══════════════════════════════════════════════════════
   FORM LAYOUT
   ═══════════════════════════════════════════════════════ */
QFormLayout {{
    margin: 0px;
}}

/* ═══════════════════════════════════════════════════════
   SPLITTER HANDLE
   ═══════════════════════════════════════════════════════ */
QSplitter::handle {{
    background-color: #e2e5ea;
    width: 1px;
    margin: 6px 10px;
    border-radius: 1px;
}}
QSplitter::handle:hover {{
    background-color: #1DA1F2;
    width: 2px;
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
    border: 1px solid #e2e5ea;
    border-radius: 8px;
    background-color: #ffffff;
    alternate-background-color: #f8f9fb;
    gridline-color: #eef1f5;
    outline: none;
}}
QTreeWidget::item, QTableWidget::item {{
    padding: 5px 10px;
    border: none;
}}
QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: #dff0fc;
    color: #1DA1F2;
    border-radius: 4px;
}}
QTreeWidget::item:hover, QTableWidget::item:hover {{
    background-color: #f3f8fd;
}}
QHeaderView::section {{
    background-color: #f4f5f7;
    color: #6b7280;
    font-weight: 600;
    font-size: 11.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid #e2e5ea;
}}
QHeaderView::section:hover {{
    background-color: #eaf3fc;
    color: #1DA1F2;
}}
"""