"""
workers/streetview_downloader.py — Background QThread for downloading panoramas.
Extracted from ``api_window.py``.
"""

import os
from PyQt5.QtCore import QThread, pyqtSignal
from tile_downloader import download_panorama


class StreetViewDownloader(QThread):
    """
    Downloads Street View panorama images for a list of coordinates.

    Signals
    -------
    progress(int, int)
        ``(current_index, total)`` after each download.
    finished()
        Emitted when all downloads complete.
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, output_dir, max_images, logger, config, FOUND_COORDS):
        super().__init__()
        self.coords = FOUND_COORDS
        self.api_key = os.getenv("API_KEY")
        self.config = config
        self.region = self.config.get_general_data()["region"]
        self.output_dir = output_dir
        self.max_images = max_images
        self.logger = logger

    def run(self):
        try:
            total = len(self.coords)
            count = 0
            for i, (lat, lng, pan_id) in enumerate(self.coords, 1):
                if self.max_images and count >= self.max_images:
                    self.logger.log_status(
                        f"Reached max_images limit: {self.max_images}"
                    )
                    break
                try:
                    self.logger.log_status(
                        f"Requesting Street View for ({lat}, {lng})"
                    )
                    download_panorama(
                        pano_id=pan_id, save_dir=self.output_dir,
                        coords=(lat, lng),
                    )
                    count += 1
                    self.logger.log_status(
                        f"Saved image {self.region}_{lat}_{lng}"
                    )
                except Exception as e:
                    self.logger.log_exception(
                        f"Failed to download at ({lat},{lng}): {e}"
                    )
                self.progress.emit(i, total)
            self.logger.log_status("Street View download finished")
        except Exception as e:
            self.logger.log_exception(f"Downloader thread failed: {e}")
        finally:
            self.finished.emit()
