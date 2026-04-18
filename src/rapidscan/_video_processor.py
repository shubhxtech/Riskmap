"""
rapidscan/_video_processor.py
Background QThread that runs Faster-RCNN detection + BEiT classification.
"""

import os
import time
import traceback

import cv2
import numpy as np
from PIL import Image

from PyQt5.QtCore import QThread, pyqtSignal

try:
    from sklearn.cluster import DBSCAN
    _SKLEARN_OK = True
except ImportError:
    _SKLEARN_OK = False

from ._constants import (
    CLASS_NAMES, DEFAULT_GPS_ORIGIN, _M_PER_DEG_LAT,
    building_coords, open_video, calculate_iou,
)


class VideoProcessor(QThread):
    """
    Runs detection + classification in a background thread.

    Signal contract
    ───────────────
    frame_ready(ndarray)              — throttled preview frames (~15 fps)
    detection_made(float,float,str,int) — one per unique building after DBSCAN
    status_update(str)                — log messages
    progress_update(int)              — 0–100
    finished()                        — done
    """
    frame_ready     = pyqtSignal(np.ndarray)
    detection_made  = pyqtSignal(float, float, str, int)
    status_update   = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    finished        = pyqtSignal()

    def __init__(self, video_path, checkpoint_path, class_names=None,
                 detection_fps=30, gps_origin=DEFAULT_GPS_ORIGIN):
        super().__init__()
        self.video_path      = video_path
        self.checkpoint_path = checkpoint_path
        self.class_names     = class_names or CLASS_NAMES
        self.detection_fps   = detection_fps
        self.gps_origin      = gps_origin
        self.running          = True
        self._next_id         = 0
        self._active_trackers = []   # IoU-based live dedup (matching RapidRisk)
        self.output_folder    = None
        self.crops_dir        = None
        self.dup_dir          = None
        self.orig_dir         = None
        self.output_video_path = None

        # Throttle preview to ~15 fps
        self._preview_interval_s = 1.0 / 15.0
        self._last_preview_t     = 0.0

    # ── Lazy-load TF detector ─────────────────────────────────────────────────
    def _load_detector(self):
        self.status_update.emit("Loading Faster R-CNN detector (TF Hub)…")
        self.detector = None
        self._tf      = None
        self._gpus    = []
        try:
            import tensorflow as tf
            import tensorflow_hub as hub
            self._tf = tf
            gpus   = tf.config.list_physical_devices("GPU")
            device = "/GPU:0" if gpus else "/CPU:0"
            with tf.device(device):
                module = hub.load(
                    "https://tfhub.dev/google/faster_rcnn/openimages_v4/"
                    "inception_resnet_v2/1"
                )
            self.detector = module.signatures["default"]
            self._gpus    = gpus
            self.status_update.emit(f"Detector loaded on {device}")
        except Exception as e:
            self.status_update.emit(f"Detector load failed: {e}")

    # ── Lazy-load BEiT classifier ─────────────────────────────────────────────
    def _load_classifier(self):
        self.status_update.emit("Loading BEiT classifier…")
        self.classifier    = None
        self._torch        = None
        self._torch_device = None
        self._transform    = None
        try:
            import torch
            from transformers import BeitForImageClassification
            from torchvision import transforms

            if torch.cuda.is_available():
                device = torch.device("cuda")
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = torch.device("mps")
            else:
                device = torch.device("cpu")
            self._torch_device = device

            model = BeitForImageClassification.from_pretrained(
                "microsoft/beit-base-patch16-224-pt22k-ft22k",
                num_labels=len(self.class_names),
                ignore_mismatched_sizes=True,
                local_files_only=False,
            )
            if self.checkpoint_path and os.path.exists(self.checkpoint_path):
                ckpt  = torch.load(self.checkpoint_path, map_location=device,
                                   weights_only=False)
                state = ckpt.get("model_state_dict", ckpt)
                model.load_state_dict(state, strict=False)
                self.status_update.emit(
                    f"Custom checkpoint loaded: {self.checkpoint_path}"
                )
            model.to(device).eval()
            self.classifier = model
            self._transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.5] * 3, [0.5] * 3),
            ])
            self._torch = torch
            self.status_update.emit(f"Classifier loaded on {device}")
        except Exception as e:
            self.status_update.emit(f"Classifier load failed: {e}")

    def _classify_crop(self, crop_bgr) -> str:
        if self.classifier is None or self._transform is None:
            return "Unknown"
        try:
            pil_img = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
            tensor  = self._transform(pil_img).unsqueeze(0).to(self._torch_device)
            with self._torch.no_grad():
                idx = self.classifier(tensor).logits.argmax(1).item()
            return self.class_names[idx]
        except Exception as e:
            self.status_update.emit(f"Classification error: {e}")
            return "Unknown"

    def _apply_dbscan_and_emit(self):
        """
        Deduplicate crops with DBSCAN, classify each unique one,
        then emit detection_made once per unique building.
        """
        if not getattr(self, "all_crops", None):
            self.status_update.emit("No crops collected — nothing to classify.")
            return

        crops       = self.all_crops
        olat, olon  = self.gps_origin

        if _SKLEARN_OK and len(crops) >= 2:
            coords  = np.array([[c["lat"], c["lon"]] for c in crops])
            eps_deg = 15.0 / _M_PER_DEG_LAT
            labels  = DBSCAN(eps=eps_deg, min_samples=1).fit(coords).labels_

            seen, unique_crops, n_dup = {}, [], 0
            for i, label in enumerate(labels):
                if label == -1:
                    unique_crops.append(crops[i])
                elif label not in seen:
                    seen[label] = i
                    unique_crops.append(crops[i])
                else:
                    n_dup += 1
            self.status_update.emit(
                f"DBSCAN: {len(unique_crops)} unique buildings, "
                f"{n_dup} duplicate crops removed."
            )
        else:
            unique_crops = crops
            self.status_update.emit(
                f"Skipping DBSCAN (<2 crops or sklearn unavailable). "
                f"{len(unique_crops)} buildings."
            )

        self.status_update.emit("Classifying unique crops…")
        for seq_id, crop_rec in enumerate(unique_crops):
            if not self.running:
                break
            pred_class = self._classify_crop(crop_rec["crop"])
            # Use coordinates stored per-crop (set during detection pass)
            lat = crop_rec["lat"]
            lon = crop_rec["lon"]
            self.detection_made.emit(lat, lon, pred_class, seq_id)
            self.status_update.emit(
                f"  [{seq_id + 1}/{len(unique_crops)}] {pred_class} @ "
                f"{lat:.5f},{lon:.5f}"
            )

    def run(self):
        import sys as _sys
        try:
            self._load_detector()
            self._load_classifier()

            cap = open_video(self.video_path)
            if not cap.isOpened():
                self.status_update.emit(
                    f"ERROR: Cannot open video: {self.video_path}\n"
                    "Possible causes:\n"
                    "  • File is incomplete or corrupted ('moov atom not found')\n"
                    "  • Codec not supported by this OpenCV build\n"
                    "  • Try re-encoding with: ffmpeg -i input.mp4 -c copy output.mp4"
                )
                self.finished.emit()
                return

            fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            det_interval = max(1, int(fps / max(1, self.detection_fps)))

            self.status_update.emit(
                f"Video: {w}×{h} @ {fps:.1f} fps  |  "
                f"{total} frames  |  detecting every {det_interval} frames"
            )

            # Optional annotated output
            # On Windows: avc1 requires openh264-1.8.0-win64.dll (rarely present).
            # Prefer mp4v/XVID on Windows; allow avc1 on macOS/Linux.
            out, out_path = None, None
            if self.output_folder:
                try:
                    out_path = os.path.join(self.output_folder, "annotated_video.mp4")
                    if _sys.platform == "win32":
                        codec_order = ("mp4v", "XVID", "MJPG")
                    else:
                        codec_order = ("avc1", "mp4v", "MJPG")
                    for codec in codec_order:
                        fourcc = cv2.VideoWriter_fourcc(*codec)
                        out    = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
                        if out.isOpened():
                            self.status_update.emit(f"VideoWriter: {codec}")
                            break
                        out.release()
                        out = None
                except Exception as e:
                    self.status_update.emit(f"VideoWriter error: {e}")
                    out = None

            self.all_crops = []
            frame_count    = 0

            while self.running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    ret, frame = cap.read()
                    if not ret:
                        break

                # ── Detection pass (matches RapidRisk logic) ────────────────
                if frame_count % det_interval == 0 and self.detector is not None:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    # Decrement TTL on active trackers
                    for t_ in self._active_trackers:
                        t_["ttl"] -= 1

                    try:
                        t = self._tf.convert_to_tensor(
                            rgb, dtype=self._tf.float32
                        ) / 255.0
                        result  = self.detector(t[self._tf.newaxis, ...])
                        boxes   = np.array(result["detection_boxes"]).reshape(-1, 4)
                        scores  = np.array(result["detection_scores"]).flatten()
                        raw_cls = np.array(
                            result["detection_class_entities"]
                        ).flatten()

                        for i in range(len(scores)):
                            if scores[i] < 0.30:
                                continue
                            cname = (
                                raw_cls[i].decode("utf-8")
                                if isinstance(raw_cls[i], bytes)
                                else str(raw_cls[i])
                            )
                            if cname not in {"House","Building","Skyscraper","Tower"}:
                                continue

                            box = boxes[i]

                            # IoU tracker check: update TTL if already tracked
                            match_found = False
                            for t_ in self._active_trackers:
                                if calculate_iou(box, t_["box"]) > 0.4:
                                    t_["box"] = box
                                    t_["ttl"] = 2
                                    match_found = True
                                    break

                            # 10% margin around crop (matches RapidRisk)
                            ymin, xmin, ymax, xmax = box
                            margin_y = int(0.1 * (ymax - ymin) * h)
                            margin_x = int(0.1 * (xmax - xmin) * w)
                            y1 = max(0, int(ymin * h) - margin_y)
                            x1 = max(0, int(xmin * w) - margin_x)
                            y2 = min(h, int(ymax * h) + margin_y)
                            x2 = min(w, int(xmax * w) + margin_x)

                            crop = rgb[y1:y2, x1:x2]
                            if crop.size == 0:
                                continue

                            crop_bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)

                            # Coordinate system: diagonal spread matching RapidRisk
                            # lat = origin_lat + id*0.0001, lon = origin_lon + id*0.0001
                            rec_id = self._next_id
                            self._next_id += 1
                            p_lat = self.gps_origin[0] + rec_id * 0.0001
                            p_lon = self.gps_origin[1] + rec_id * 0.0001

                            self.all_crops.append({
                                "id": rec_id, "crop": crop_bgr,
                                "lat": p_lat, "lon": p_lon,
                            })
                            if self.crops_dir:
                                cv2.imwrite(
                                    os.path.join(self.crops_dir, f"{rec_id}.jpg"),
                                    crop_bgr,
                                )

                            # Annotate preview frame
                            cv2.rectangle(frame, (x1,y1), (x2,y2), (29,161,242), 2)
                            cv2.putText(
                                frame, f"Bldg #{rec_id}",
                                (x1, max(y1-8, 0)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                (29, 161, 242), 2,
                            )
                            # Only register as new tracker if not already tracked
                            if not match_found:
                                self._active_trackers.append({"box": box, "ttl": 2})
                    except Exception as e:
                        self.status_update.emit(
                            f"Detection error frame {frame_count}: {e}"
                        )

                    # Remove expired trackers
                    self._active_trackers = [
                        t for t in self._active_trackers if t["ttl"] > 0
                    ]

                # Throttled preview
                now = time.monotonic()
                if now - self._last_preview_t >= self._preview_interval_s:
                    self.frame_ready.emit(frame.copy())
                    self._last_preview_t = now

                if out:
                    out.write(frame)

                frame_count += 1
                if total > 0:
                    self.progress_update.emit(int(frame_count / total * 100))

            cap.release()
            if out:
                out.release()
            self.output_video_path = out_path

            self.status_update.emit(
                f"Detection pass done — {len(self.all_crops)} raw crops. "
                "Running DBSCAN + BEiT classification…"
            )
            self._apply_dbscan_and_emit()

        except Exception as e:
            self.status_update.emit(
                f"Fatal VideoProcessor error: {e}\n{traceback.format_exc()}"
            )
        finally:
            self.finished.emit()

    def stop(self):
        self.running = False
