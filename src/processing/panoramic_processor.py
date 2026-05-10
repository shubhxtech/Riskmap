"""
processing/panoramic_processor.py
==================================
QThread wrapper for the 360° spatial-sampling pipeline.

Phase 1 — ffmpeg splits 360° video → 8 perspective MP4s
Phase 2 — helper_code runs GPS-spatial detection + classification
"""

import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

PERSPECTIVE_VIDEOS = {
    "front":  "view_0_front.mp4",
    "fr45":   "view_1_fr45.mp4",
    "right":  "view_2_right.mp4",
    "br135":  "view_3_br135.mp4",
    "back":   "view_4_back.mp4",
    "bl225":  "view_5_bl225.mp4",
    "left":   "view_6_left.mp4",
    "fl315":  "view_7_fl315.mp4",
}

ALL_ANGLES = list(PERSPECTIVE_VIDEOS.keys())

PERSPECTIVE_YAWS = {
    "front":   0, "fr45":  45, "right":  90, "br135": 135,
    "back":  180, "bl225": -135, "left": -90, "fl315": -45,
}

H_FOV, V_FOV = 90, 110


def _find_ffmpeg():
    """Find ffmpeg binary in PATH or common macOS installation paths."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    
    # Fallback paths for GUI apps that might not inherit full shell PATH
    fallbacks = [
        "/opt/homebrew/bin/ffmpeg",  # Apple Silicon Homebrew
        "/usr/local/bin/ffmpeg",     # Intel Homebrew
        "/opt/local/bin/ffmpeg",     # MacPorts
    ]
    for path in fallbacks:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path
            
    return None


def _build_ffmpeg_command(input_path, output_dir,
                          h_fov=H_FOV, v_fov=V_FOV,
                          width=1280, height=1280, crf=20):
    ffmpeg_bin = _find_ffmpeg()
    if not ffmpeg_bin:
        raise FileNotFoundError(
            "ffmpeg executable not found in PATH or standard Homebrew locations. "
            "Please ensure ffmpeg is installed (e.g., 'brew install ffmpeg')."
        )
        
    names = list(PERSPECTIVE_VIDEOS.keys())
    yaws = [PERSPECTIVE_YAWS[a] for a in names]
    n = len(names)
    splits = "".join(f"[v{i}]" for i in range(n))
    parts = [f"[0:v]split={n}{splits}"]
    for i, (name, yaw) in enumerate(zip(names, yaws)):
        parts.append(
            f"[v{i}]v360=e:flat:yaw={yaw}:pitch=0:"
            f"h_fov={h_fov}:v_fov={v_fov}:w={width}:h={height}[{name}]"
        )
    cmd = [ffmpeg_bin, "-y", "-i", input_path, "-filter_complex", "; ".join(parts)]
    for name, fname in PERSPECTIVE_VIDEOS.items():
        cmd += ["-map", f"[{name}]", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", str(crf),
                os.path.join(output_dir, fname)]
    return cmd


class PanoramicProcessor(QThread):
    """Runs the full 360° pipeline in a background thread."""

    status_update   = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    step_changed    = pyqtSignal(int, str)   # (step_num, description)
    finished_ok     = pyqtSignal(str)
    finished_err    = pyqtSignal(str)

    def __init__(self, video_path, gps_csv_path, output_dir,
                 checkpoint_path, spatial_interval_m=15.0,
                 active_angles=None, parent=None):
        super().__init__(parent)
        self.video_path         = video_path
        self.gps_csv_path       = gps_csv_path
        self.output_dir         = output_dir
        self.checkpoint_path    = checkpoint_path
        self.spatial_interval_m = spatial_interval_m
        self.active_angles      = active_angles or ALL_ANGLES
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._run_pipeline()
        except Exception as exc:
            self.finished_err.emit(f"{exc}\n{traceback.format_exc()}")

    def _run_pipeline(self):
        self._stop = False
        os.makedirs(self.output_dir, exist_ok=True)
        views_dir = os.path.join(self.output_dir, "views")
        os.makedirs(views_dir, exist_ok=True)

        # ── STEP 1: ffmpeg split ──────────────────────────────────────────────
        self.step_changed.emit(1, "Splitting 360° video into perspective clips…")
        missing = [f for f in PERSPECTIVE_VIDEOS.values()
                   if not os.path.exists(os.path.join(views_dir, f))]
        if missing:
            self.progress_update.emit(2)
            cmd = _build_ffmpeg_command(self.video_path, views_dir)
            self.status_update.emit("▶ Running ffmpeg…")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                if line.strip():
                    self.status_update.emit(line.strip())
                if self._stop:
                    proc.kill()
                    self.finished_err.emit("Stopped by user.")
                    return
            proc.wait()
            if proc.returncode != 0:
                self.finished_err.emit(
                    f"ffmpeg failed (exit {proc.returncode}). Is ffmpeg installed?")
                return
            self.status_update.emit("✅ Video split complete.")
        else:
            self.status_update.emit("✅ Perspective clips already exist — skipping.")
        self.progress_update.emit(10)
        if self._stop:
            self.finished_err.emit("Stopped."); return

        # ── STEP 2: helper_code pipeline ──────────────────────────────────────
        self.step_changed.emit(2, "Running detection & classification pipeline…")
        self.status_update.emit("⏳ Loading models and GPS data…")
        src_dir = str(Path(__file__).parent.parent)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        import helper_code as hc
        hc.VIDEO_DIR          = views_dir
        hc.BASE_OUTPUT_DIR    = self.output_dir
        hc.GPS_CSV_PATH       = self.gps_csv_path
        hc.CLASSIFICATION_MODEL_CHECKPOINT = self.checkpoint_path
        hc.SPATIAL_INTERVAL_M = self.spatial_interval_m
        hc.ACTIVE_ANGLES      = self.active_angles

        import builtins
        _real_print = builtins.print
        def _cap(*args, **kw):
            self.status_update.emit(" ".join(str(a) for a in args))
            _real_print(*args, **kw)
        builtins.print = _cap
        try:
            hc.process_spatial(
                spatial_interval_m=self.spatial_interval_m,
                use_sequential=False,
                active_angles=self.active_angles)
        finally:
            builtins.print = _real_print

        self.progress_update.emit(100)
        self.step_changed.emit(3, "Complete")
        self.finished_ok.emit(self.output_dir)
