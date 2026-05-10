"""
rapidscan/_risk_panel.py
MplCanvas helper, RiskCalcThread, and RiskAssessmentPanel widget.
"""

import os
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPushButton,
    QLabel, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QGroupBox, QDoubleSpinBox, QSpinBox,
    QGridLayout, QProgressBar, QTextEdit, QSizePolicy,
    QLineEdit, QDialog, QDialogButtonBox, QFormLayout
)

from .constants import (
    BG_CARD, BG_PANEL, BORDER, ACCENT, ACCENT3,
    TXT_HI, TXT_MID, TXT_LOW, MPL_STYLE, DS_COLORS, DEFAULT_GPS_ORIGIN,
)

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

try:
    from risk_engine import (
        ScenarioParams, BuildingRecord, BuildingResult,
        run_scenario, run_actual_pga, portfolio_summary,
        CLASS_TO_ARCHETYPE, FRAGILITY_LIB, LOSS_RATIO,
        boore_atkinson_2008_pga, fragility_prob,
        register_custom_typology,
    )
    _RISK_OK  = True
    _RISK_ERR = ""
except Exception as _risk_err:
    _RISK_OK  = False
    _RISK_ERR = str(_risk_err)
    FRAGILITY_LIB = {}
    def fragility_prob(pga, median, beta): return 0.0


# ── MplCanvas ────────────────────────────────────────────────────────────────
class MplCanvas(FigureCanvas):
    def __init__(self, figsize=(5, 3.5)):
        with plt.rc_context(MPL_STYLE):
            self.fig = Figure(figsize=figsize, tight_layout=True)
            self.ax  = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"background: {BG_PANEL};")


# ── RiskCalcThread ────────────────────────────────────────────────────────────
class RiskCalcThread(QThread):
    finished = pyqtSignal(object, object, object)
    progress = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, buildings, params, actual_pga_df=None):
        super().__init__()
        self.buildings = buildings
        self.params    = params
        self.actual_pga_df = actual_pga_df

    def run(self):
        if not _RISK_OK:
            self.error.emit(f"risk_engine not available: {_RISK_ERR}")
            return
        try:
            if self.actual_pga_df is not None:
                self.progress.emit("Processing actual empirical PGA data…")
                results, df = run_actual_pga(self.buildings, self.actual_pga_df)
            else:
                self.progress.emit("Computing ground-motion field (BA08 GMPE)…")
                results, df = run_scenario(self.buildings, self.params)
            
            self.progress.emit("Aggregating damage states…")
            summary = portfolio_summary(results)
            self.progress.emit("Done.")
            self.finished.emit(results, df, summary)
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")


# ── RiskAssessmentPanel ───────────────────────────────────────────────────────
class RiskAssessmentPanel(QWidget):
    """Seismic risk assessment panel embedded in RapidScanWindow."""

    # Emitted so RapidScanWindow can update map markers
    # args: (marker_id: int, color: str, classification: str, lat: float, lon: float)
    map_update_requested = pyqtSignal(int, str, str, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buildings   = []
        self.csv_mode_active = False
        self.results     = []
        self.df          = None
        self.actual_pga_df = None
        self.summary     = {}
        self.calc_thread = None
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # LEFT: scenario inputs
        left = QWidget()
        left.setMaximumWidth(330)
        ll = QVBoxLayout(left)
        ll.setSpacing(10)

        # ── Pipeline Results loader ───────────────────────────────────────────
        results_grp = QGroupBox("📂  PIPELINE RESULTS")
        rg = QVBoxLayout(results_grp); rg.setSpacing(6)

        self.results_lbl = QLabel("No results loaded")
        self.results_lbl.setWordWrap(True)
        self.results_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:10px;")

        self.btn_load_results = QPushButton("📁  Load Output Folder…")
        self.btn_load_results.setCursor(Qt.PointingHandCursor)
        self.btn_load_results.setStyleSheet(
            f"background:{ACCENT}; color:#fff; font-weight:700; border:none; "
            f"border-radius:6px; padding:8px; font-size:11px;"
        )
        self.btn_load_results.clicked.connect(self.load_pipeline_results)

        self.btn_clear_map = QPushButton("🗑  Clear Map Markers")
        self.btn_clear_map.setCursor(Qt.PointingHandCursor)
        self.btn_clear_map.setStyleSheet(
            f"background:{BG_CARD}; color:{TXT_MID}; border:1px solid {BORDER}; "
            f"border-radius:6px; padding:6px; font-size:10px;"
        )
        self.btn_clear_map.clicked.connect(
            lambda: self.map_update_requested.emit(-1, "__clear__", "", 0.0, 0.0)
        )

        rg.addWidget(self.results_lbl)
        rg.addWidget(self.btn_load_results)
        rg.addWidget(self.btn_clear_map)
        ll.addWidget(results_grp)

        # Exposure
        exp_grp = QGroupBox("EXPOSURE")
        eg = QVBoxLayout(exp_grp)
        self.exposure_lbl = QLabel("No buildings loaded")
        self.exposure_lbl.setWordWrap(True)
        self.exposure_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
        
        self.btn_load_csv = QPushButton("📂  Load Exposure CSV")
        self.btn_load_csv.setCursor(Qt.PointingHandCursor)
        self.btn_load_csv.clicked.connect(self.load_exposure_csv)
        
        self.pga_lbl = QLabel("No actual PGA loaded (using scenario)")
        self.pga_lbl.setWordWrap(True)
        self.pga_lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
        
        self.btn_load_pga = QPushButton("📂  Load PGA Actual CSV")
        self.btn_load_pga.setCursor(Qt.PointingHandCursor)
        self.btn_load_pga.clicked.connect(self.load_pga_csv)

        self.btn_add_typology = QPushButton("➕  Add Building Typology")
        self.btn_add_typology.setCursor(Qt.PointingHandCursor)
        self.btn_add_typology.setStyleSheet(
            f"background:{BG_CARD}; color:{ACCENT}; border:1px solid {ACCENT}; "
            f"border-radius:6px; padding:6px; font-weight:bold;"
        )
        self.btn_add_typology.clicked.connect(self.show_typology_dialog)
        
        eg.addWidget(self.exposure_lbl)
        eg.addWidget(self.btn_load_csv)
        eg.addSpacing(10)
        eg.addWidget(self.pga_lbl)
        eg.addWidget(self.btn_load_pga)
        eg.addSpacing(10)
        eg.addWidget(self.btn_add_typology)
        ll.addWidget(exp_grp)


        # Earthquake scenario
        eq_grp = QGroupBox("EARTHQUAKE SCENARIO")
        eg2 = QGridLayout(eq_grp)
        eg2.setSpacing(6)

        def lrow(label, widget, r, hint=None):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{TXT_MID}; font-size:11px;")
            eg2.addWidget(lbl, r, 0)
            eg2.addWidget(widget, r, 1)
            if hint:
                h = QLabel(hint)
                h.setStyleSheet(f"color:{TXT_LOW}; font-size:9px;")
                eg2.addWidget(h, r + 1, 0, 1, 2)

        self.mw_spin = QDoubleSpinBox()
        self.mw_spin.setRange(4.0, 9.0); self.mw_spin.setValue(6.5)
        self.mw_spin.setSingleStep(0.1); self.mw_spin.setSuffix(" Mw")
        lrow("Magnitude:", self.mw_spin, 0)

        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(1.0, 300.0); self.depth_spin.setValue(10.0)
        self.depth_spin.setSuffix(" km")
        lrow("Depth:", self.depth_spin, 1)

        self.src_lat = QDoubleSpinBox()
        self.src_lat.setRange(-90, 90); self.src_lat.setValue(31.70)
        self.src_lat.setDecimals(4); self.src_lat.setSingleStep(0.01)
        lrow("Source Lat:", self.src_lat, 2)

        self.src_lon = QDoubleSpinBox()
        self.src_lon.setRange(-180, 180); self.src_lon.setValue(76.93)
        self.src_lon.setDecimals(4); self.src_lon.setSingleStep(0.01)
        lrow("Source Lon:", self.src_lon, 3)

        self.vs30_spin = QDoubleSpinBox()
        self.vs30_spin.setRange(100, 1500); self.vs30_spin.setValue(400)
        self.vs30_spin.setSuffix(" m/s")
        lrow("Vs30:", self.vs30_spin, 4,
             hint="180=soft soil · 400=stiff · 760=rock")

        self.fault_combo = QComboBox()
        self.fault_combo.addItems(
            ["unspecified", "reverse", "normal", "strike-slip"]
        )
        lrow("Fault type:", self.fault_combo, 6)

        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(100, 5000); self.samples_spin.setValue(500)
        self.samples_spin.setSuffix(" samples")
        lrow("MC samples:", self.samples_spin, 7)
        ll.addWidget(eq_grp)

        # Quick presets
        preset_grp = QGroupBox("QUICK SCENARIOS  (Mandi, HP)")
        pg = QVBoxLayout(preset_grp)
        for name, mw, dep, slat, slon in [
            ("Mw 5.5  Moderate (R≈20 km)", 5.5, 10, 31.65, 76.99),
            ("Mw 6.5  Strong   (R≈15 km)", 6.5, 12, 31.62, 76.95),
            ("Mw 7.0  Major    (R≈10 km)", 7.0, 15, 31.68, 76.90),
            ("Mw 7.5  Severe   (R≈8 km)",  7.5, 20, 31.72, 76.87),
        ]:
            btn = QPushButton(name)
            btn.setStyleSheet(
                f"text-align:left; padding:5px 8px; font-size:10px; "
                f"background:{BG_CARD}; color:{TXT_MID}; "
                f"border:1px solid {BORDER}; border-radius:4px;"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _, m=mw, d=dep, la=slat, lo=slon:
                    self._apply_preset(m, d, la, lo)
            )
            pg.addWidget(btn)
        ll.addWidget(preset_grp)

        self.btn_run = QPushButton("▶  RUN RISK ASSESSMENT")
        self.btn_run.setEnabled(False)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setStyleSheet(
            f"background:{ACCENT}; color:#fff; font-weight:700; border:none; "
            f"border-radius:6px; padding:10px; font-size:13px;"
        )
        self.btn_run.clicked.connect(self.run_assessment)
        ll.addWidget(self.btn_run)

        self.risk_progress = QProgressBar()
        self.risk_progress.setRange(0, 0)
        self.risk_progress.setVisible(False)
        ll.addWidget(self.risk_progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        ll.addWidget(self.log)

        ll.addStretch()

        # RIGHT: results
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setSpacing(8)

        # KPI cards
        kpi_row = QWidget()
        kpi_l   = QHBoxLayout(kpi_row)
        kpi_l.setSpacing(8); kpi_l.setContentsMargins(0, 0, 0, 0)
        self.kpi_widgets = {}
        for key, label, default in [
            ("n_buildings",      "Buildings",       "—"),
            ("pga_mean_g",       "Mean PGA (g)",    "—"),
            ("avg_loss_ratio",   "Avg Loss Ratio",  "—"),
            ("total_loss_units", "Total Loss Units","—"),
        ]:
            card = QWidget()
            card.setStyleSheet(
                f"background:{BG_CARD}; border:1px solid {BORDER}; "
                f"border-radius:8px; padding:8px;"
            )
            cl = QVBoxLayout(card); cl.setSpacing(2)
            val_lbl = QLabel(default)
            val_lbl.setStyleSheet(
                f"color:{ACCENT}; font-size:20px; font-weight:700;"
            )
            val_lbl.setAlignment(Qt.AlignCenter)
            name_lbl = QLabel(label)
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setStyleSheet(f"color:{TXT_LOW}; font-size:10px;")
            cl.addWidget(val_lbl); cl.addWidget(name_lbl)
            kpi_l.addWidget(card)
            self.kpi_widgets[key] = val_lbl
        rl.addWidget(kpi_row)

        # Charts
        chart_row = QHBoxLayout()
        self.ds_canvas   = MplCanvas(figsize=(5, 3))
        self.frag_canvas = MplCanvas(figsize=(4.5, 3))
        chart_row.addWidget(self.ds_canvas,   3)
        chart_row.addWidget(self.frag_canvas, 2)
        rl.addLayout(chart_row)

        # Results table header
        tbl_hdr = QWidget()
        th_l = QHBoxLayout(tbl_hdr)
        th_l.setContentsMargins(0, 0, 0, 0)

        tbl_lbl = QLabel("BUILDING RESULTS")
        tbl_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:11px; font-weight:bold; "
            f"padding-bottom:3px;"
        )
        th_l.addWidget(tbl_lbl)
        th_l.addStretch()

        self.btn_export = QPushButton("💾 Export Results CSV")
        self.btn_export.setEnabled(False)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setStyleSheet(
            f"background:{BG_CARD}; color:{TXT_MID}; border:1px solid {BORDER}; "
            f"border-radius:4px; padding:4px 8px; font-size:10px;"
        )
        self.btn_export.clicked.connect(self.export_csv)
        th_l.addWidget(self.btn_export)

        rl.addWidget(tbl_hdr)
        self.table = QTableWidget(0, 15)
        self.table.setHorizontalHeaderLabels([
            "ID", "Class", "Arch", "PGA μ", "PGA σ",
            "DS1 μ", "DS1 σ", "DS2 μ", "DS2 σ",
            "DS3 μ", "DS3 σ", "DS4 μ", "DS4 σ", "Lat", "Lon"
        ])
        hdr = self.table.horizontalHeader()
        # All columns stretch equally — user can scroll with the horizontal bar
        for c in range(15):
            hdr.setSectionResizeMode(c, QHeaderView.Stretch)
        # Slightly narrower ID column
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 36)
        # Enable smooth horizontal scroll so nothing is clipped
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_table_select)
        rl.addWidget(self.table, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([310, 900])
        root.addWidget(splitter)

    # ── Exposure ──────────────────────────────────────────────────────────────
    def load_from_detections(self, detections: list):
        """Called by RapidScanWindow whenever detection list updates."""
        if not _RISK_OK or self.csv_mode_active:
            return
        self.buildings = []
        for det in detections:
            try:
                self.buildings.append(BuildingRecord(
                    id=int(det.get("id", len(self.buildings) + 1)),
                    lat=float(det.get("lat", DEFAULT_GPS_ORIGIN[0])),
                    lon=float(det.get("lon", DEFAULT_GPS_ORIGIN[1])),
                    beit_class=str(det.get("classification", "RCC_H1 flat roof")),
                ))
            except Exception:
                continue
        self._update_exposure_label()

    def load_exposure_csv(self):
        if not _RISK_OK or not _PANDAS_OK:
            self._log("risk_engine or pandas not available.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Exposure CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            df      = pd.read_csv(path)
            missing = {"id","lat","lon","classification"} - set(df.columns)
            if missing:
                self._log(f"CSV missing columns: {missing}"); return
            
            has_custom_id = "custom_site_id" in df.columns
            self.buildings = []
            self.csv_mode_active = True
            for _, r in df.iterrows():
                bld = BuildingRecord(
                    id=int(r["id"]), lat=float(r["lat"]),
                    lon=float(r["lon"]),
                    beit_class=str(r["classification"]),
                )
                if has_custom_id:
                    bld.custom_site_id = str(r["custom_site_id"])
                self.buildings.append(bld)
                
            self._update_exposure_label()
            # Plot loaded CSV buildings on the map (matches RapidRisk behaviour)
            for b in self.buildings:
                self.map_update_requested.emit(
                    b.id, "#00d4aa", b.beit_class, b.lat, b.lon
                )
            self._log(f"Loaded {len(self.buildings)} buildings from "
                      f"{os.path.basename(path)}")
        except Exception as e:
            self._log(f"CSV load error: {e}")

    def _update_exposure_label(self):
        n = len(self.buildings)
        self.exposure_lbl.setText(
            f"<b style='color:{ACCENT}'>{n}</b> buildings loaded"
        )
        self.btn_run.setEnabled(n > 0 and _RISK_OK)

    def load_pga_csv(self):
        if not _PANDAS_OK:
            self._log("pandas not available.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load PGA Actual CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            df = pd.read_csv(path, low_memory=False, comment='#')
            if "custom_site_id" not in df.columns or "gmv_PGA" not in df.columns:
                self._log("PGA CSV must contain 'custom_site_id' and 'gmv_PGA'.")
                return
            self.actual_pga_df = df
            n_sites = df["custom_site_id"].nunique()
            self.pga_lbl.setText(f"<b style='color:{ACCENT}'>{n_sites}</b> sites loaded from actual data")
            self._log(f"Loaded {len(df)} actual GMV records from {os.path.basename(path)}")
        except Exception as e:
            self._log(f"PGA CSV load error: {e}")

    def load_pipeline_results(self):
        """Load the 360° pipeline output folder and plot all buildings on the shared map."""
        import glob, json

        folder = QFileDialog.getExistingDirectory(
            self, "Select Pipeline Output Folder", ""
        )
        if not folder:
            return

        # ── Try GeoJSON first ─────────────────────────────────────────────────
        geojsons = glob.glob(os.path.join(folder, "*.geojson"))
        if geojsons:
            try:
                with open(geojsons[0], "r") as f:
                    gj = json.load(f)
                features = gj.get("features", [])
                count = 0
                for feat in features:
                    props = feat.get("properties", {})
                    geom  = feat.get("geometry", {})
                    coords = geom.get("coordinates", [0, 0])
                    lon = float(coords[0]) if len(coords) >= 2 else 0.0
                    lat = float(coords[1]) if len(coords) >= 2 else 0.0
                    bid = int(props.get("id", count + 1))
                    cls = str(props.get("classification", props.get("label", "Unknown")))
                    color = ("#3b82f6" if cls.startswith("RCC") else
                             "#f59e0b" if cls.startswith("MR") else
                             "#8b5cf6" if cls.startswith("Metal") else
                             "#9ca3af" if "Non_Building" in cls else "#00d4aa")
                    self.map_update_requested.emit(bid, color, cls, lat, lon)
                    count += 1
                self.results_lbl.setText(
                    f"<b style='color:{ACCENT}'>{count}</b> buildings plotted "
                    f"from {os.path.basename(geojsons[0])}"
                )
                self._log(f"✅ Plotted {count} buildings from GeoJSON on map.")
                return
            except Exception as e:
                self._log(f"GeoJSON load error: {e}")

        # ── Fallback: Excel ───────────────────────────────────────────────────
        if not _PANDAS_OK:
            self._log("pandas not available — cannot read Excel.")
            return
        xlsxs = glob.glob(os.path.join(folder, "*.xlsx"))
        if not xlsxs:
            self._log("No .geojson or .xlsx found in the selected folder.")
            return
        try:
            df = pd.read_excel(xlsxs[0])
            lat_col = next((c for c in df.columns if "lat" in c.lower()), None)
            lon_col = next((c for c in df.columns if "lon" in c.lower()), None)
            cls_col = next((c for c in df.columns
                            if "class" in c.lower() or "label" in c.lower()), None)
            if not all([lat_col, lon_col, cls_col]):
                self._log(f"Excel missing lat/lon/class columns. Found: {list(df.columns)}")
                return
            count = 0
            for i, row in df.iterrows():
                lat = float(row[lat_col])
                lon = float(row[lon_col])
                cls = str(row[cls_col])
                bid = int(row["id"]) if "id" in df.columns else i + 1
                color = ("#3b82f6" if cls.startswith("RCC") else
                         "#f59e0b" if cls.startswith("MR") else
                         "#8b5cf6" if cls.startswith("Metal") else
                         "#9ca3af" if "Non_Building" in cls else "#00d4aa")
                self.map_update_requested.emit(bid, color, cls, lat, lon)
                count += 1
            self.results_lbl.setText(
                f"<b style='color:{ACCENT}'>{count}</b> buildings plotted "
                f"from {os.path.basename(xlsxs[0])}"
            )
            self._log(f"✅ Plotted {count} buildings from Excel on map.")
        except Exception as e:
            self._log(f"Excel load error: {e}")

    def _apply_preset(self, mw, dep, slat, slon):
        self.mw_spin.setValue(mw)
        self.depth_spin.setValue(dep)
        self.src_lat.setValue(slat)
        self.src_lon.setValue(slon)

    # ── Run assessment ────────────────────────────────────────────────────────
    def run_assessment(self):
        if not self.buildings or not _RISK_OK:
            self._log("No buildings loaded or risk_engine unavailable.")
            return
        params = ScenarioParams(
            Mw=self.mw_spin.value(),
            depth_km=self.depth_spin.value(),
            source_lat=self.src_lat.value(),
            source_lon=self.src_lon.value(),
            Vs30=self.vs30_spin.value(),
            fault_type=self.fault_combo.currentText(),
            n_samples=self.samples_spin.value(),
        )
        if self.actual_pga_df is not None:
             self._log(f"[{datetime.now():%H:%M:%S}] Running Assessment using ACTUAL empirical PGA data — {len(self.buildings)} buildings")
        else:
             self._log(
                 f"[{datetime.now():%H:%M:%S}] Mw{params.Mw} scenario at "
                 f"({params.source_lat:.4f}, {params.source_lon:.4f}) — "
                 f"{len(self.buildings)} buildings"
             )
        self.btn_run.setEnabled(False)
        self.risk_progress.setVisible(True)
        self.calc_thread = RiskCalcThread(self.buildings, params, self.actual_pga_df)
        self.calc_thread.progress.connect(self._log)
        self.calc_thread.finished.connect(self._on_results)
        self.calc_thread.error.connect(self._on_error)
        self.calc_thread.start()

    @pyqtSlot(object, object, object)
    def _on_results(self, results, df, summary):
        self.results = results
        self.df      = df
        self.summary = summary
        self.risk_progress.setVisible(False)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(True)
        self._update_kpis(summary)
        self._draw_ds_chart(summary)
        self._fill_table(results)
        # Recolor map markers with DS colours (matches RapidRisk behaviour)
        for r in results:
            color = DS_COLORS.get(r.mean_ds, "#00d4aa")
            self.map_update_requested.emit(
                r.id, color, r.beit_class, r.lat, r.lon
            )
        self._log(
            f"✓ Complete — {summary.get('n_buildings',0)} buildings.  "
            f"Avg loss ratio: {summary.get('avg_loss_ratio',0):.1%}"
        )

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.risk_progress.setVisible(False)
        self.btn_run.setEnabled(True)
        self._log(f"ERROR: {msg}")

    # ── KPI / charts ──────────────────────────────────────────────────────────
    def _update_kpis(self, s: dict):
        self.kpi_widgets["n_buildings"].setText(str(s.get("n_buildings","—")))
        pga = s.get("pga_mean_g")
        self.kpi_widgets["pga_mean_g"].setText(
            f"{pga:.4f}" if pga is not None else "—"
        )
        alr = s.get("avg_loss_ratio")
        self.kpi_widgets["avg_loss_ratio"].setText(
            f"{alr:.1%}" if alr is not None else "—"
        )
        tlu = s.get("total_loss_units", s.get("total_loss"))
        self.kpi_widgets["total_loss_units"].setText(
            f"{tlu:.1f}" if tlu is not None else "—"
        )

    def _draw_ds_chart(self, summary: dict):
        ax = self.ds_canvas.ax
        ax.clear()
        ds_pct = summary.get("ds_pct", {})
        labels = ["None","DS1","DS2","DS3","DS4"]
        vals   = [ds_pct.get(k,0) for k in labels]
        colors = [DS_COLORS[k] for k in labels]
        bars   = ax.bar(labels, vals, color=colors,
                        edgecolor=BORDER, linewidth=0.7)
        for bar, val in zip(bars, vals):
            if val > 1:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.5,
                    f"{val:.1f}%",
                    ha="center", va="bottom", fontsize=9,
                )
        ax.set_ylabel("% of buildings")
        ax.set_title("Damage State Distribution", fontsize=11)
        ax.set_ylim(0, max(vals or [1]) * 1.2 + 5)
        ax.yaxis.grid(True, alpha=0.3); ax.set_axisbelow(True)
        self.ds_canvas.fig.tight_layout()
        self.ds_canvas.draw()

    def _draw_fragility(self, archetype: str, pga_median: float = None):
        if not _RISK_OK or not FRAGILITY_LIB:
            return
        ax = self.frag_canvas.ax
        ax.clear()
        params = FRAGILITY_LIB.get(
            archetype, FRAGILITY_LIB.get("CR_LFINF_DUL_H1", {})
        )
        if not params:
            ax.set_title("No fragility data", fontsize=10)
            self.frag_canvas.draw()
            return
        pga_range = np.linspace(0.01, 2.0, 300)
        for ds_key, ds_name, color in [
            ("DS1","Slight","#facc15"), ("DS2","Moderate","#f97316"),
            ("DS3","Extensive","#ef4444"), ("DS4","Complete","#7f1d1d"),
        ]:
            if ds_key not in params:
                continue
            med, beta = params[ds_key]
            if med >= 90:
                continue
            probs = [fragility_prob(p, med, beta) for p in pga_range]
            ax.plot(pga_range, probs, label=ds_name, color=color)
        if pga_median:
            ax.axvline(pga_median, color=ACCENT, linestyle="--",
                       linewidth=1.2, label=f"Site PGA={pga_median:.3f}g")
        ax.set_xlabel("PGA (g)")
        ax.set_ylabel("P(DS ≥ ds)")
        ax.set_title(f"Fragility: {archetype}", fontsize=10)
        ax.legend(fontsize=8, framealpha=0.3)
        ax.set_xlim(0, 2.0); ax.set_ylim(0, 1.05)
        ax.yaxis.grid(True, alpha=0.3); ax.set_axisbelow(True)
        self.frag_canvas.fig.tight_layout()
        self.frag_canvas.draw()

    def _fill_table(self, results):
        self.table.setRowCount(0)
        for r in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            ds_color = QColor(DS_COLORS.get(r.mean_ds, BG_CARD))
            vals = [
                str(r.id), r.beit_class, r.archetype,
                f"{r.pga_mean:.4f}",  f"{r.pga_sigma:.4f}",
                f"{r.ds_probs.get('DS1',0):.5f}", f"{r.ds_probs_sigma.get('DS1',0):.5f}",
                f"{r.ds_probs.get('DS2',0):.5f}", f"{r.ds_probs_sigma.get('DS2',0):.5f}",
                f"{r.ds_probs.get('DS3',0):.5f}", f"{r.ds_probs_sigma.get('DS3',0):.5f}",
                f"{r.ds_probs.get('DS4',0):.5f}", f"{r.ds_probs_sigma.get('DS4',0):.5f}",
                f"{r.lat:.5f}", f"{r.lon:.5f}",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setBackground(ds_color)
                self.table.setItem(row, col, item)

    def _on_table_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows or not self.results:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self.results):
            r = self.results[idx]
            self._draw_fragility(r.archetype, r.pga_median)

    def export_csv(self):
        if not _PANDAS_OK or self.df is None:
            self._log("pandas not available or no results to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Risk Results", "risk_results.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.df.to_csv(path, index=False)
            self._log(f"✓ Exported {len(self.df)} rows → {path}")

    def _log(self, msg: str):
        self.log.append(msg)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def show_typology_dialog(self):
        dlg = TypologyDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            name = data["name"]
            if not name:
                self._log("Error: Typology name cannot be empty.")
                return
            ds_params = {
                "DS1": (data["ds1_m"], data["ds1_b"]),
                "DS2": (data["ds2_m"], data["ds2_b"]),
                "DS3": (data["ds3_m"], data["ds3_b"]),
                "DS4": (data["ds4_m"], data["ds4_b"]),
            }
            register_custom_typology(name, ds_params, data["period"], data["damping"])
            self._log(f"Successfully added typology: {name}")


class TypologyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Building Typology")
        self.setStyleSheet(f"background:{BG_PANEL}; color:{TXT_HI};")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. MY_CUSTOM_RC")
        self.name_edit.setStyleSheet(f"background:{BG_CARD}; color:{TXT_HI}; border:1px solid {BORDER}; padding:4px;")
        form.addRow("Typology Name:", self.name_edit)
        
        self.spins = {}
        for ds in ["DS1", "DS2", "DS3", "DS4"]:
            m = QDoubleSpinBox()
            m.setRange(-10, 10); m.setDecimals(4); m.setSingleStep(0.1)
            # Find closest existing value or reasonable defaults
            m.setStyleSheet(f"background:{BG_CARD}; color:{TXT_HI};")
            
            b = QDoubleSpinBox()
            b.setRange(0.01, 2.0); b.setDecimals(4); b.setSingleStep(0.05); b.setValue(0.6)
            b.setStyleSheet(f"background:{BG_CARD}; color:{TXT_HI};")
            
            self.spins[f"{ds}_m"] = m
            self.spins[f"{ds}_b"] = b
            
            row = QHBoxLayout()
            row.addWidget(QLabel("Median:"))
            row.addWidget(m)
            row.addWidget(QLabel("Beta:"))
            row.addWidget(b)
            form.addRow(f"<b>{ds}</b> Parameters:", row)
            
        self.period_spin = QDoubleSpinBox()
        self.period_spin.setRange(0, 10); self.period_spin.setValue(0.3)
        self.period_spin.setStyleSheet(f"background:{BG_CARD}; color:{TXT_HI};")
        form.addRow("Fundamental Period (s):", self.period_spin)
        
        self.damping_spin = QDoubleSpinBox()
        self.damping_spin.setRange(0, 100); self.damping_spin.setValue(5.0)
        self.damping_spin.setStyleSheet(f"background:{BG_CARD}; color:{TXT_HI};")
        form.addRow("Damping Ratio (%):", self.damping_spin)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet(f"QPushButton {{ background:{BG_CARD}; color:{TXT_HI}; border:1px solid {BORDER}; padding:5px; }}")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
    def get_data(self):
        res = {
            "name": self.name_edit.text().strip(),
            "period": self.period_spin.value(),
            "damping": self.damping_spin.value()
        }
        for ds in ["DS1", "DS2", "DS3", "DS4"]:
            res[f"{ds.lower()}_m"] = self.spins[f"{ds}_m"].value()
            res[f"{ds.lower()}_b"] = self.spins[f"{ds}_b"].value()
        return res
