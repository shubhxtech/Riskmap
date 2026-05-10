"""
workers/polling_worker.py — Background QThread that polls NodeODM task status.
Extracted from ``rapidscan/odm_tab.py``.
"""

import time
from PyQt5.QtCore import QThread, pyqtSignal


class PollingWorker(QThread):
    """
    Polls a NodeODM task's status every *poll_interval* seconds until
    the task reaches a terminal state (completed/failed/cancelled).

    Signals
    -------
    status_update(dict)
        Full task info dict from ``/task/{uuid}/info``.
    log_lines(list)
        New console output lines from ``/task/{uuid}/output``.
    finished(dict)
        Final task info when a terminal status is reached.
    error(str)
        Emitted on network or unexpected errors.
    """

    status_update = pyqtSignal(dict)
    log_lines     = pyqtSignal(list)
    finished      = pyqtSignal(dict)
    error         = pyqtSignal(str)

    # Safety guard: stop after 4 hours at 5-second intervals
    MAX_ITERATIONS = 2880

    def __init__(self, client, task_uuid, poll_interval=5):
        super().__init__()
        self.client        = client
        self.task_uuid     = task_uuid
        self.poll_interval = poll_interval
        self.running       = True
        self._last_line    = 0

    def run(self):
        iterations = 0
        while self.running and iterations < self.MAX_ITERATIONS:
            try:
                info = self.client.task_info(self.task_uuid)
                self.status_update.emit(info)

                # Fetch new log lines
                try:
                    lines = self.client.task_output(
                        self.task_uuid, self._last_line,
                    )
                    if lines:
                        self.log_lines.emit(lines)
                        self._last_line += len(lines)
                except Exception:
                    pass

                code = info.get("status", {}).get("code", 0)
                if code in (30, 40, 50):  # failed, completed, cancelled
                    self.finished.emit(info)
                    return

            except Exception as e:
                self.error.emit(str(e))

            iterations += 1
            time.sleep(self.poll_interval)

        if iterations >= self.MAX_ITERATIONS:
            self.error.emit("Polling timeout: task exceeded maximum wait time.")

    def stop(self):
        """Signal the worker to stop polling on the next iteration."""
        self.running = False
