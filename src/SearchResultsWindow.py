import json
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QPushButton, QLabel, QHeaderView, QAbstractItemView, QMessageBox, 
    QFileDialog, QApplication, QFrame, QScrollArea, QWidget, QFormLayout, 
    QStackedWidget
)
from PyQt5.QtCore import Qt, QSize, QUrl, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QDesktopServices, QClipboard
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
import qtawesome as qta

class SearchResultsWidget(QWidget):
    back_clicked = pyqtSignal()
    download_clicked = pyqtSignal()

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data # List of dicts with full metadata
        # self.setWindowTitle("Search Results") # Not needed for embedded widget
        # self.resize(1000, 600) # Size managed by layout
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20) # Add padding to the whole widget
        layout.setSpacing(15) # Add space between toolbar and table
        
        # --- Header & Toolbar ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10) # Space between buttons
        
        # Back Button
        self.btn_back = QPushButton(" Back")
        self.btn_back.setIcon(qta.icon('fa5s.arrow-left', color='#5f6368'))
        self.btn_back.clicked.connect(self.back_clicked.emit)
        toolbar.addWidget(self.btn_back)
        
        # Stats
        count = len(self.data)
        unique_panos = len(set(d.get('pano_id', '') for d in self.data))
        stats_text = QLabel(f"<b>{count} Locations</b> ({unique_panos} unique panoramas)")
        stats_text.setStyleSheet("font-size: 13px; margin-left: 10px;")
        toolbar.addWidget(stats_text)
        
        toolbar.addStretch()
        
        # Export Actions
        self.btn_copy_ids = QPushButton(" Copy IDs")
        self.btn_copy_ids.setIcon(qta.icon('fa5s.clipboard', color='#5f6368'))
        self.btn_copy_ids.setToolTip("Copy Panorama IDs to Clipboard")
        self.btn_copy_ids.clicked.connect(self.copy_ids_to_clipboard)
        
        self.btn_export_json = QPushButton(" JSON")
        self.btn_export_json.setIcon(qta.icon('fa5s.file-code', color='#5f6368'))
        self.btn_export_json.setToolTip("Export as JSON")
        self.btn_export_json.clicked.connect(self.export_json)
        
        self.btn_download = QPushButton(" Download Images")
        self.btn_download.setIcon(qta.icon('fa5s.file-download', color='#1a73e8'))
        self.btn_download.setStyleSheet("color: #1a73e8; font-weight: bold;")
        self.btn_download.clicked.connect(self.download_clicked.emit) 
        
        toolbar.addWidget(self.btn_copy_ids)
        toolbar.addWidget(self.btn_export_json)
        toolbar.addWidget(self.btn_download)
        
        # Apply style to all toolbar buttons for consistent padding/height
        for btn in [self.btn_back, self.btn_copy_ids, self.btn_export_json, self.btn_download]:
            if btn == self.btn_download:
                continue # Skip download as it has custom style, but we can append to it
            btn.setStyleSheet("""
                QPushButton {
                    padding: 6px 12px;
                    border: 1px solid #dadce0;
                    border-radius: 4px;
                    background-color: white;
                    color: #3c4043;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #f1f3f4;
                    border-color: #d2e3fc;
                }
            """)
            
        # Refine Download Button Style
        self.btn_download.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #1a73e8;
                border-radius: 4px;
                background-color: #fff;
                color: #1a73e8;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1a73e8;
                color: white;
            }
        """)
        
        layout.addLayout(toolbar)
        
        # --- Results Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date", "Location", "Pano ID", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Location stretches
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents) # ID fixed
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                gridline-color: #f0f0f0;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                color: #5f6368;
                border: none;
                border-bottom: 2px solid #e0e0e0;
                padding: 8px 12px;
                font-weight: 600;
                font-size: 12px;
                text-transform: uppercase;
            }
            QTableWidget::item:selected {
                background-color: #e8f0fe;
                color: #1967d2;
            }
        """)
        
        self.populate_table()
        layout.addWidget(self.table)
        
        # Connect row click/double click to detail view
        self.table.cellDoubleClicked.connect(self.show_detail)
        
    def populate_table(self):
        self.table.setRowCount(len(self.data))
        for row, item in enumerate(self.data):
            # Parse Date
            date_str = item.get('date', 'N/A')
            if isinstance(date_str, dict): 
                year = date_str.get('year', '')
                month = date_str.get('month', '')
                date_str = f"{year}-{month:02d}" if year and month else "N/A"
            
            # Location
            lat = item.get('location', {}).get('lat', 0)
            lng = item.get('location', {}).get('lng', 0)
            loc_str = f"{lat:.5f}, {lng:.5f}"
            
            # Pano ID - Shorten for display? No, keep logic simple
            pano_id = item.get('panoId', '')
            
            # Add Items
            self.table.setItem(row, 0, QTableWidgetItem(str(date_str)))
            self.table.setItem(row, 1, QTableWidgetItem(loc_str))
            
            id_item = QTableWidgetItem(pano_id)
            id_item.setToolTip(pano_id)
            self.table.setItem(row, 2, id_item)
            
            # Action Buttons Cell
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)
            
            info_btn = QPushButton()
            info_btn.setIcon(qta.icon('fa5s.info-circle', color='#5f6368'))
            info_btn.setToolTip("View Details")
            info_btn.setFlat(True)
            info_btn.setFixedSize(24, 24)
            # Fix lambda capture!
            info_btn.clicked.connect(lambda checked, r=row: self.show_detail(r))
            
            gmaps_btn = QPushButton()
            gmaps_btn.setIcon(qta.icon('fa5s.map-marked-alt', color='#5f6368'))
            gmaps_btn.setToolTip("Open in Google Maps")
            gmaps_btn.setFlat(True)
            gmaps_btn.setFixedSize(24, 24)
            gmaps_btn.clicked.connect(lambda checked, pid=pano_id: self.open_in_google_maps(pid))
            
            btn_layout.addWidget(info_btn)
            btn_layout.addWidget(gmaps_btn)
            btn_layout.addStretch()
            
            self.table.setCellWidget(row, 3, btn_widget)

    def copy_ids_to_clipboard(self):
        ids = [d.get('panoId', '') for d in self.data if d.get('panoId')]
        text = "\n".join(ids)
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "Success", f"Copied {len(ids)} Panorama IDs to clipboard.")

    def export_json(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Results", "panoramas.json", "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.data, f, indent=2)
                QMessageBox.information(self, "Success", "Export successful.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def show_detail(self, row, col=None):
        data_item = self.data[row]
        detail_dialog = PanoramaDetailDialog(data_item, self)
        detail_dialog.exec_()


    def open_in_google_maps(self, pano_id):
        url = f"https://www.google.com/maps/@?api=1&map_action=pano&pano={pano_id}"
        QDesktopServices.openUrl(QUrl(url))


class PanoramaDetailDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("Panorama Details")
        self.resize(800, 500)
        self.init_ui()
        
    def init_ui(self):
        layout = QHBoxLayout(self) # Split View: Image Left, Info Right
        
        # --- Left: Image Preview ---
        # Note: Actual Street View Image requires separate API call (Static API) or billing.
        # We will use a placeholder or try to load if URL available.
        # For now, let's show a nice placeholder with "Preview"
        
        image_container = QLabel("Preview Loading...")
        image_container.setAlignment(Qt.AlignCenter)
        image_container.setStyleSheet("background-color: #202124; color: #fff;")
        image_container.setMinimumWidth(500)
        
        # Attempt to load static preview if API key is available (passed via data?)
        # Or simple street view URL
        pano_id = self.data.get('panoId')
        # We can't easily fetch the actual image without authenticated Static API call here.
        # Let's verify we can show a robust placeholder layout.
        image_container.setText(f"Panorama ID:\n{pano_id}\n\n(Preview requires Static API)")
        
        layout.addWidget(image_container, 2)
        
        # --- Right: Metadata ---
        info_scroll = QScrollArea()
        info_widget = QWidget()
        info_layout = QFormLayout(info_widget)
        info_layout.setSpacing(15)
        
        # Helper to add rows
        def add_row(icon_name, label, value):
            container = QWidget()
            row_layout = QHBoxLayout(container)
            row_layout.setContentsMargins(0,0,0,0)
            
            icon = QLabel()
            icon.setPixmap(qta.icon(icon_name, color='#5f6368').pixmap(QSize(16, 16)))
            icon.setFixedWidth(24)
            
            lbl = QLabel(f"<b>{label}</b>") # Bold label
            lbl.setStyleSheet("color: #5f6368;")
            
            val = QLabel(str(value))
            val.setWordWrap(True)
            
            row_layout.addWidget(icon)
            # row_layout.addWidget(lbl) # Optional: Icon IS the label visual
            
            text_container = QVBoxLayout()
            text_container.setSpacing(2)
            text_container.addWidget(lbl)
            text_container.addWidget(val)
            
            row_layout.addLayout(text_container)
            info_layout.addRow(container)
            
        # Extract data
        location = self.data.get('location', {})
        lat = location.get('lat')
        lng = location.get('lng')
        date = self.data.get('date', 'N/A')
        copyright_text = self.data.get('copyright', 'Google')
        
        add_row('fa5s.file', "File location", "N/A (Not downloaded)")
        add_row('fa5s.link', "Panorama ID", pano_id)
        add_row('fa5s.crosshairs', "Geolocation", f"{lat}, {lng}")
        add_row('fa5s.calendar-alt', "Date taken", date)
        add_row('fa5s.image', "Resolution", "Highest Available")
        add_row('fa5s.copyright', "Copyright", copyright_text)

        info_scroll.setWidget(info_widget)
        info_scroll.setWidgetResizable(True)
        layout.addWidget(info_scroll, 1)
