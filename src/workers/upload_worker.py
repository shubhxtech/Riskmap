"""
workers/upload_worker.py — Background QThread for uploading images to NodeODM.
Extracted from ``rapidscan/odm_tab.py``.
"""

from PyQt5.QtCore import QThread, pyqtSignal


class UploadWorker(QThread):
    """
    Uploads drone images to a NodeODM server and creates a processing task.

    Signals
    -------
    progress(int, int)
        ``(uploaded_count, total_count)`` after each image.
    log(str)
        Human-readable status messages.
    finished(str)
        Emitted with the task UUID on success.
    error(str)
        Emitted with error message on failure.
    """

    progress = pyqtSignal(int, int)
    log      = pyqtSignal(str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, client, image_paths, options, task_name):
        super().__init__()
        self.client      = client
        self.image_paths = image_paths
        self.options     = options
        self.task_name   = task_name

    def run(self):
        try:
            self.log.emit(f"Uploading {len(self.image_paths)} images to NodeODM…")
            result = self.client.create_task(
                self.image_paths, self.options, self.task_name,
                progress_cb=lambda n, t: self.progress.emit(n, t),
            )
            uuid = result.get("uuid", "")
            if not uuid:
                self.error.emit(f"No UUID returned: {result}")
                return
            self.log.emit(f"Task created: {uuid}")
            self.finished.emit(uuid)
        except Exception as e:
            self.error.emit(str(e))
