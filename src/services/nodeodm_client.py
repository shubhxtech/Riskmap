"""
services/nodeodm_client.py — Pure REST client for NodeODM.
==========================================================
No PyQt5 or UI dependencies. Uses only ``requests``.

Extracted from ``rapidscan/odm_tab.py`` to decouple network
logic from the presentation layer.

NodeODM API docs: https://docs.webodm.org/
"""

import os
import json
import requests


class NodeODMClient:
    """
    Lightweight REST client for NodeODM / WebODM.

    Parameters
    ----------
    host : str
        NodeODM hostname (default ``"localhost"``).
    port : int
        NodeODM port (default ``3000``).
    token : str
        Optional authentication token.
    timeout : int
        HTTP timeout in seconds for normal requests.
    """

    def __init__(self, host="localhost", port=3000, token="", timeout=30):
        self.base = f"http://{host}:{port}"
        self.token = token
        self.timeout = timeout

    # ── Internal helpers ──────────────────────────────────────────────────

    def _params(self, extra=None):
        p = {}
        if self.token:
            p["token"] = self.token
        if extra:
            p.update(extra)
        return p

    # ── Public API ────────────────────────────────────────────────────────

    def info(self):
        """GET /info — server version, engine, limits."""
        r = requests.get(
            f"{self.base}/info",
            params=self._params(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def options(self):
        """GET /options — available processing options."""
        r = requests.get(
            f"{self.base}/options",
            params=self._params(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def create_task(self, image_paths, options, name="BuildScan Task",
                    webhook=None, progress_cb=None):
        """
        Upload images and create a task via POST /task/new (multipart).

        Parameters
        ----------
        image_paths : list[str]
            Paths to drone images.
        options : dict
            Processing options ``{name: value}``.
        name : str
            Human-readable task name.
        webhook : str, optional
            Webhook URL for completion notification.
        progress_cb : callable, optional
            ``progress_cb(n, total)`` called after each image is added.

        Returns
        -------
        dict
            Task dict with ``"uuid"`` key.
        """
        url = f"{self.base}/task/new"
        opts_json = json.dumps([
            {"name": k, "value": v} for k, v in options.items()
        ])
        file_handles = []
        files = []
        try:
            for i, path in enumerate(image_paths):
                fh = open(path, "rb")
                file_handles.append(fh)
                files.append((
                    "images",
                    (os.path.basename(path), fh, "image/jpeg"),
                ))
                if progress_cb:
                    progress_cb(i + 1, len(image_paths))

            data = {"name": name, "options": opts_json}
            if webhook:
                data["webhook"] = webhook

            r = requests.post(
                url, params=self._params(), data=data,
                files=files, timeout=self.timeout * 10,
            )
            r.raise_for_status()
            return r.json()
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    def task_info(self, task_uuid):
        """GET /task/{uuid}/info — current task status."""
        r = requests.get(
            f"{self.base}/task/{task_uuid}/info",
            params=self._params(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def task_output(self, task_uuid, line=0):
        """GET /task/{uuid}/output — console log lines starting at *line*."""
        r = requests.get(
            f"{self.base}/task/{task_uuid}/output",
            params=self._params({"line": line}),
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()  # list of strings

    def download_all(self, task_uuid, dest_path, progress_cb=None):
        """
        GET /task/{uuid}/download/all.zip — download results archive.

        Parameters
        ----------
        task_uuid : str
            Task UUID to download.
        dest_path : str
            Local path to write the ZIP file.
        progress_cb : callable, optional
            ``progress_cb(pct)`` called with integer 0–100.

        Returns
        -------
        str
            The *dest_path* after successful download.
        """
        url = f"{self.base}/task/{task_uuid}/download/all.zip"
        r = requests.get(
            url, params=self._params(),
            stream=True, timeout=600,
        )
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        progress_cb(int(downloaded / total * 100))
        return dest_path

    def cancel_task(self, task_uuid):
        """POST /task/{uuid}/cancel — cancel a running task."""
        r = requests.post(
            f"{self.base}/task/{task_uuid}/cancel",
            params=self._params(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def delete_task(self, task_uuid):
        """POST /task/{uuid}/remove — delete a task from the server."""
        r = requests.post(
            f"{self.base}/task/{task_uuid}/remove",
            params=self._params(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def list_tasks(self):
        """GET /task/list — all tasks on the server."""
        r = requests.get(
            f"{self.base}/task/list",
            params=self._params(), timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()
