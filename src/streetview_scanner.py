import sys
import os
import sqlite3
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, wait_exponential, stop_after_attempt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QHBoxLayout, QMessageBox, QFileDialog
)
from PyQt5.QtCore import QUrl, QTimer, pyqtSignal, QThread
from PyQt5.QtWebEngineWidgets import QWebEngineView
import folium

from app_logger import Logger
from config_ import Config

# Default settings — overridden at instance level from config
RATE_LIMIT_PER_MIN = 30000
_DEFAULT_COARSE_SPACING = 0.003
_DEFAULT_FINE_SPACING = 0.001
_DEFAULT_DB_PATH = "scan_data.db"

class RateLimiter:
    def __init__(self, max_calls_per_minute):
        self.max_calls = max_calls_per_minute
        self.period = 60.0
        self.allowance = max_calls_per_minute
        self.last_check = time.time()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            current = time.time()
            elapsed = current - self.last_check
            self.last_check = current
            self.allowance += elapsed * (self.max_calls / self.period)
            if self.allowance > self.max_calls:
                self.allowance = self.max_calls
            if self.allowance < 1.0:
                return False 
            else:
                self.allowance -= 1
                return True

class ScanThread(QThread):
    def __init__(self, scanner_widget):
        super().__init__()
        self.widget = scanner_widget

    def run(self):
        self.widget.scan_loop()

class StreetViewDensityScanner(QWidget):
    update_ui_signal = pyqtSignal(bool)

    def __init__(self, city, config=None, logger=None):
        super().__init__()
        self.city = city
        self.logger = logger or Logger(__name__)
        self.config = config or Config(logger=self.logger)

        # Read settings from config (with safe fallbacks)
        try:
            dl_data = self.config.get_download_data()
            self.COARSE_SPACING = float(dl_data.get("coarse_spacing", _DEFAULT_COARSE_SPACING))
            self.FINE_SPACING = float(dl_data.get("fine_spacing", _DEFAULT_FINE_SPACING))
            self.DEFAULT_DB_PATH = self.config.get_paths_data().get("metadata_database_path", _DEFAULT_DB_PATH)
        except Exception:
            self.COARSE_SPACING = _DEFAULT_COARSE_SPACING
            self.FINE_SPACING = _DEFAULT_FINE_SPACING
            self.DEFAULT_DB_PATH = _DEFAULT_DB_PATH

        self.setWindowTitle("Street View Density-Based Scanner")
        self.init_ui()
        self.scanning = False
        self.db_lock = threading.Lock()
        self.update_ui_signal.connect(self.update_status_ui)

    def init_ui(self):
        layout = QVBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("API Key")

        layout.addWidget(self.api_key_input)

        self.edge_inputs = {}
        for e in ["North (max lat)", "South (min lat)", "East (max lon)", "West (min lon)"]:
            row = QHBoxLayout()
            lbl = QLabel(e)
            inp = QLineEdit()

            self.edge_inputs[e] = inp

            row.addWidget(lbl)
            row.addWidget(inp)
            layout.addLayout(row)

        self.workers_input = QLineEdit()
        self.workers_input.setPlaceholderText("Max Threads (e.g. 10)")
        layout.addWidget(self.workers_input)

        self.dbfile_input = QLineEdit()
        self.dbfile_input.setPlaceholderText(self.DEFAULT_DB_PATH)
        browse_btn = QPushButton("Browse DB File...")
        browse_btn.clicked.connect(self.browse_db)

        dbrow = QHBoxLayout()
        dbrow.addWidget(self.dbfile_input)
        dbrow.addWidget(browse_btn)
        layout.addLayout(dbrow)

        self.size_label = QLabel("DB Size: N/A")
        layout.addWidget(self.size_label)
        self.start_btn = QPushButton("Start/Resume Scan")
        self.start_btn.clicked.connect(self.start_scan)
        layout.addWidget(self.start_btn)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        self.map_view = QWebEngineView()

        try:
            folder_name = self.config.get_download_data().get("folder_name", "Metadata_Maps")
        except Exception:
            folder_name = "Metadata_Maps"
        self.map_file = os.path.join(folder_name, f'{self.city}_map.html')
        layout.addWidget(self.map_view, stretch=1)

        self.setLayout(layout)

    def browse_db(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Select DB file", "", "SQLite DB (*.db);;All Files(*)")
        if fname: 
            self.dbfile_input.setText(fname)

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coords (
                    id INTEGER PRIMARY KEY,
                    lat REAL, lon REAL,
                    stage TEXT, scanned INTEGER DEFAULT 0
                )""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    coord_id INTEGER, pano_id TEXT,
                    FOREIGN KEY(coord_id) REFERENCES coords(id)
                )""")

            # Temporary table that stores the http responses received when querying for metadata
            cur.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    coord_id INTEGER, response TEXT
                )""")
            conn.commit()

    def populate_coarse(self, north, south, east, west):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM coords")
            if cur.fetchone()[0] == 0:
                lat = north; batch = []
                while lat >= south:
                    lon = west
                    while lon <= east:
                        batch.append((lat, lon, 'coarse'))
                        lon += self.COARSE_SPACING
                    lat -= self.COARSE_SPACING
                cur.executemany("INSERT INTO coords(lat, lon, stage) VALUES(?, ?, ?)", batch)
                conn.commit()

    def start_scan(self):
        if self.scanning:
            return

        try:
            self.api_key = self.api_key_input.text().strip()
            north = float(self.edge_inputs["North (max lat)"].text())
            south = float(self.edge_inputs["South (min lat)"].text())
            east = float(self.edge_inputs["East (max lon)"].text())
            west = float(self.edge_inputs["West (min lon)"].text())
            self.max_workers = int(self.workers_input.text() or 5)
            self.db_path = self.dbfile_input.text().strip() or self.DEFAULT_DB_PATH
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid input values")
            return

        self.init_db()
        self.populate_coarse(north, south, east, west)
        self.rate_limiter = RateLimiter(RATE_LIMIT_PER_MIN)
        self.scanning = True

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.update_ui_signal.emit(False))
        self.timer.start(2000)

        self.scan_thread = ScanThread(self)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.start()

    def scan_loop(self):
        while True:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT id,lat,lon,stage FROM coords WHERE scanned=0 ORDER BY stage DESC LIMIT ?", (self.max_workers * 2,))
                batch = cur.fetchall()
            if not batch:
                break

            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                for cid, lat, lon, stage in batch:
                    ex.submit(self.fetch_and_store, cid, lat, lon, stage)

            # update UI after batch
            self.update_ui_signal.emit(False)

        self.scanning = False
        self.update_ui_signal.emit(True)
        

    def update_status_ui(self, final):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM coords")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM coords WHERE scanned=1")
            done = cur.fetchone()[0]

        self.status_label.setText(f"Scanned {done}/{total}")
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)

        try:
            size = os.path.getsize(self.db_path)
            self.size_label.setText(f"DB Size: {size/1e6:.2f} MB")
        except Exception:
            self.size_label.setText("DB Size: N/A")
        self.refresh_map()
        if final:
            self.timer.stop()
            self.status_label.setText("Scan completed")

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    def safe_get(self, lat, lon):
        return requests.get(
            "https://maps.googleapis.com/maps/api/streetview/metadata",
            params={"location": f"{lat},{lon}", "key": self.api_key}, timeout=10
        )
    
    def fetch_and_store(self, coord_id, lat, lon, stage):
        while not self.rate_limiter.acquire():
            time.sleep(0.1)  # backoff or yield
        
        data = self.safe_get(lat=lat, lon=lon).json()
        with self.db_lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("UPDATE coords SET scanned=1 WHERE id=?", (coord_id,))
                if data.get("status")=="OK":
                    cur.execute("INSERT INTO results(coord_id,pano_id) VALUES(?,?)", (coord_id, data.get("pano_id")))
                    if stage=='coarse':
                        for dlat in (-self.FINE_SPACING, 0, self.FINE_SPACING):
                            for dlon in (-self.FINE_SPACING, 0, self.FINE_SPACING):
                                if dlat==0 and dlon==0: continue
                                cur.execute("INSERT INTO coords(lat,lon,stage) VALUES(?,?,?)", (lat+dlat, lon+dlon, 'fine'))
                
                cur.execute("INSERT INTO responses(coord_id,response) VALUES(?,?)", (coord_id, data.get("status")))
                conn.commit()

    def refresh_map(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT lat,lon,stage,scanned FROM coords")
            records = cur.fetchall()

        if not records: 
            return
        
        avg_lat = sum(r[0] for r in records)/len(records)
        avg_lon = sum(r[1] for r in records)/len(records)
        m = folium.Map(location=(avg_lat, avg_lon), zoom_start=13)

        for lat, lon, stage, scanned in records:
            color = 'green' if (scanned and stage=='coarse') else 'blue' if (scanned and stage=='fine') else 'gray'
            folium.CircleMarker((lat, lon), radius=3, color=color, fill=True).add_to(m)
        
        m.save(self.map_file)
        self.map_view.load(QUrl.fromLocalFile(os.path.abspath(self.map_file)))

if __name__=='__main__':
    app = QApplication(sys.argv)
    win = StreetViewDensityScanner(); win.show(); sys.exit(app.exec_())
