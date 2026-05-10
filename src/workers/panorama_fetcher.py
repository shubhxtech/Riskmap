"""
workers/panorama_fetcher.py — Background QThread for fetching panorama metadata.
Extracted from ``api_window.py``.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PyQt5.QtCore import QThread, pyqtSignal


class PanoramaFetcher(QThread):
    """
    Background thread for fetching panorama metadata from Google Street View API.
    Uses a thread pool (10 workers) for parallel requests.

    Signals
    -------
    progress(int, int)
        ``(completed, total)`` after each batch of requests.
    finished(list)
        List of metadata dicts on success.
    error(str)
        Emitted with error message on failure.
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error    = pyqtSignal(str)

    def __init__(self, grid_points, api_key, logger):
        super().__init__()
        self.grid_points = grid_points
        self.api_key = api_key
        self.logger = logger

    def fetch_single_point(self, lat, lon):
        """Fetch metadata for a single point from Google Street View API."""
        try:
            api_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
            params = {
                "location": f"{lat},{lon}",
                "key": self.api_key,
            }

            response = requests.get(api_url, params=params, timeout=5)

            if response.status_code == 200:
                metadata = response.json()
                if metadata.get("status") == "OK":
                    return {
                        "location": metadata["location"],
                        "panoId": metadata.get("pano_id", ""),
                        "date": metadata.get("date", ""),
                        "copyright": metadata.get("copyright", ""),
                        "status": metadata.get("status", ""),
                    }
            return None
        except Exception as e:
            self.logger.log_exception(
                f"API request failed for ({lat}, {lon}): {e}"
            )
            return None

    def run(self):
        try:
            results = []
            total = len(self.grid_points)
            completed = 0

            self.logger.log_status(
                f"Fetching panoramas from Google API for {total} points (parallel mode)..."
            )

            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_point = {
                    executor.submit(self.fetch_single_point, lat, lon): (lat, lon)
                    for lat, lon in self.grid_points
                }

                for future in as_completed(future_to_point):
                    result = future.result()
                    if result:
                        results.append(result)

                    completed += 1
                    if completed % 10 == 0 or completed == total:
                        self.progress.emit(completed, total)

            self.logger.log_status(
                f"Found {len(results)} panoramas from Google API"
            )
            self.finished.emit(results)

        except Exception as e:
            self.logger.log_exception(f"Panorama fetcher thread failed: {e}")
            self.error.emit(str(e))
