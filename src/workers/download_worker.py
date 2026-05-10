"""
workers/download_worker.py — Background QThread for downloading NodeODM results.
Extracted from ``rapidscan/odm_tab.py``.
"""

import os
import zipfile
from PyQt5.QtCore import QThread, pyqtSignal


class DownloadWorker(QThread):
    """
    Downloads the all.zip results archive from a completed NodeODM task
    and extracts it to the output directory.

    Signals
    -------
    progress(int)
        Download percentage 0–100.
    log(str)
        Human-readable status messages.
    finished(str)
        Emitted with the extraction directory path on success.
    error(str)
        Emitted with error message on failure.
    """

    progress = pyqtSignal(int)
    log      = pyqtSignal(str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, client, task_uuid, output_dir):
        super().__init__()
        self.client     = client
        self.task_uuid  = task_uuid
        self.output_dir = output_dir

    def run(self):
        try:
            zip_path = os.path.join(self.output_dir, "all.zip")
            self.log.emit("Downloading results (all.zip)…")
            self.client.download_all(
                self.task_uuid, zip_path,
                progress_cb=lambda p: self.progress.emit(p),
            )
            self.log.emit("Download complete. Extracting…")
            extract_dir = os.path.join(self.output_dir, "odm_results")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            os.remove(zip_path)
            self.log.emit(f"Extracted to: {extract_dir}")
            self.finished.emit(extract_dir)
        except Exception as e:
            self.error.emit(str(e))
