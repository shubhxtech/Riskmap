import sys
import os
import json
import time
import requests
import threading
from tenacity import retry, retry_if_exception, wait_exponential, stop_after_attempt
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
                             QProgressBar, QHBoxLayout, QMessageBox)
from PyQt5.QtCore import Qt, QTimer

SAVE_FILE = "scan_progress.json"

class StreetViewScanner(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Street View Area Scanner")
        self.initUI()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)
        self.scanning = False
        self.load_progress()

    def initUI(self):
        layout = QVBoxLayout()

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter API Key")
        layout.addWidget(self.api_key_input)

        self.edge_inputs = {}
        for edge in ["North (max lat)", "South (min lat)", "East (max lon)", "West (min lon)"]:
            row = QHBoxLayout()
            label = QLabel(edge)
            input_field = QLineEdit()
            self.edge_inputs[edge] = input_field
            row.addWidget(label)
            row.addWidget(input_field)
            layout.addLayout(row)

        self.start_btn = QPushButton("Start Scan")
        self.start_btn.clicked.connect(self.start_scan)
        layout.addWidget(self.start_btn)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def load_progress(self):
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, 'r') as f:
                self.progress = json.load(f)
        else:
            self.progress = {
                "scanned": [],
                "latest_status": "",
                "next_lat": None,
                "next_lon": None
            }

    def save_progress(self):
        with open(SAVE_FILE, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def update_ui(self):
        if self.scanning:
            self.status_label.setText(self.progress.get("latest_status", ""))
            self.progress_bar.setValue(len(self.progress['scanned']) % 100)

    def start_scan(self):
        if self.scanning:
            QMessageBox.warning(self, "Busy", "Scan already in progress")
            return

        try:
            self.api_key = self.api_key_input.text()
            self.north = float(self.edge_inputs["North (max lat)"].text())
            self.south = float(self.edge_inputs["South (min lat)"].text())
            self.east = float(self.edge_inputs["East (max lon)"].text())
            self.west = float(self.edge_inputs["West (min lon)"].text())
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid input values.")
            return

        self.grid_spacing = 0.001  # ~100m
        self.scanning = True
        threading.Thread(target=self.scan_area).start()

    @staticmethod
    def retry_if_5xx_error(exception):
        """Return True if exception is HTTPError with status 5xx."""
        return (
            isinstance(exception, requests.exceptions.HTTPError)
            and exception.response is not None
            and 500 <= exception.response.status_code < 600
        )
    
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(retry_if_5xx_error)
    )
    def safe_get(self, url, params = None):
        return requests.get(url=url, params=params)


    def scan_area(self):
        lat = self.progress.get("next_lat", self.north)
        while lat >= self.south:
            lon = self.progress.get("next_lon", self.west)
            while lon <= self.east:
                location = f"{lat},{lon}"
                metadata_url = f"https://maps.googleapis.com/maps/api/streetview/metadata?location={location}&key={self.api_key}"
                response = self.safe_get(url = metadata_url)
                response.raise_for_status()
                result = response.json()

                if result.get("status") == "OK":
                    self.progress['scanned'].append({"lat": lat, "lon": lon, "pano_id": result.get("pano_id")})

                self.progress['latest_status'] = f"Scanned: {len(self.progress['scanned'])} | Now: {location}"
                self.progress['next_lat'] = lat
                self.progress['next_lon'] = lon + self.grid_spacing
                self.save_progress()

                time.sleep(1.5)  # rate limit for free tier

                if len(self.progress['scanned']) >= 90:
                    self.progress['latest_status'] = "Free tier limit reached. Come back tomorrow."
                    self.scanning = False
                    return

            lat -= self.grid_spacing
            self.progress['next_lon'] = self.west
        self.scanning = False
        self.progress['latest_status'] = "Scan completed."
        self.save_progress()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    scanner = StreetViewScanner()
    scanner.show()
    sys.exit(app.exec_())
