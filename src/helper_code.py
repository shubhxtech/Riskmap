"""
360° Survey Pipeline — GPS-Spatial Sampling Edition (FIXED SEEKING)
====================================================================
Captures a full 8K equirectangular panorama every N metres (user-defined),
runs building detection, cross-view fusion, CNN dedup, and BEiT classification.

FIXES: Reliable frame seeking using multiple strategies (PTS, frame, sequential)
FLEXIBILITY: Choose which perspective angles to process

Author  : adapted from original multiview pipeline
"""

import os, shutil, bisect, math, json
from collections import defaultdict
import time

import chardet
import numpy as np
import pandas as pd
import cv2
from PIL import Image

import tensorflow as tf
import tensorflow_hub as hub
from tensorflow.keras.applications import EfficientNetB7
from tensorflow.keras.applications.efficientnet import preprocess_input
from sklearn.cluster import DBSCAN

import torch
from torchvision import transforms
from transformers import BeitForImageClassification, BeitConfig


# ==============================================================================
#  USER CONFIGURATION  — edit before running
# ==============================================================================

# Directory holding the 8 perspective MP4s produced by ffmpeg
VIDEO_DIR = r"E:\Mandi Survey\DCIM\100GOPRO\gs010021"

# Output root
BASE_OUTPUT_DIR = r"E:\Mandi Survey\DCIM\100GOPRO\gs010021\output_spatial"

# GPS track (ExifTool CSV)
GPS_CSV_PATH = r"E:\Mandi Survey\DCIM\100GOPRO\gs010021\gps_010021.csv"

# BEiT checkpoint
CLASSIFICATION_MODEL_CHECKPOINT = (
    r"D:\sukh backup\phd\Object_detection\Models\BiET_V7\checkpoints\best_model.pth"
)

# ── WHICH ANGLES TO PROCESS ──────────────────────────────────────────────────
# Choose which video angles to use for detection and stitching
# Options: 'front', 'fr45', 'right', 'br135', 'back', 'bl225', 'left', 'fl315'
# Example: ACTIVE_ANGLES = ['front', 'right', 'back', 'left']  # Only use 4 angles
#          ACTIVE_ANGLES = ['front', 'fr45', 'right', 'br135', 'back']  # Use 5 angles
#          ACTIVE_ANGLES = list(PERSPECTIVE_VIDEOS.keys())  # All 8 angles (default)

ACTIVE_ANGLES = [
    'front',    # 0 degrees
    'fr45',     # 45 degrees
    'right',    # 90 degrees
    'br135',    # 135 degrees
    'back',     # 180 degrees
    'bl225',    # -135 degrees
    'left',     # -90 degrees
    'fl315',    # -45 degrees
]  # ← Modify this list to choose which angles to use

# ── Spatial sampling ──────────────────────────────────────────────────────────
# Capture one panorama every SPATIAL_INTERVAL_M metres of travel.
SPATIAL_INTERVAL_M = 15.0      # metres between panorama captures

# ── Detection & classification ────────────────────────────────────────────────
DETECTION_SCORE_THRESHOLD = 0.30
IOU_DUPLICATE_THRESHOLD   = 0.50   # cross-view equirect IoU merge threshold
CNN_SIMILARITY_EPS        = 0.36   # DBSCAN eps for CNN dedup (cosine distance)
H_FOV = 90                         # horizontal FOV used in ffmpeg v360 filter
V_FOV = 110                         # vertical FOV used in ffmpeg v360 filter

NUM_CLASSES = 24
CLASS_NAMES = [
    'AD_H1', 'AD_H2', 'MR_H1 flat roof', 'MR_H1 gable roof', 'MR_H2 flat roof',
    'MR_H2 gable roof', 'MR_H3', 'Metal_H1', 'Non_Building', 'RCC_H1 flat roof',
    'RCC_H1 gable roof', 'RCC_H2 flat roof', 'RCC_H2 gable roof', 'RCC_H3 flat roof',
    'RCC_H3 gable roof', 'RCC_H4 flat roof', 'RCC_H4 gaqble roof', 'RCC_H5',
    'RCC_H6', 'RCC_OS_H1', 'RCC_OS_H2', 'RCC_OS_H3', 'RCC_OS_H4', 'Timber',
]

TARGET_CLASSES = {'House', 'Building', 'Skyscraper', 'Tower'}

# The 8 perspective MP4 filenames and their yaw angles (complete definition)
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

PERSPECTIVE_YAWS = {
    "front":   0, "fr45":  45, "right":  90, "br135": 135,
    "back":  180, "bl225":-135, "left": -90, "fl315": -45,
}

# Seeking strategy configuration
USE_PTS_SEEKING = True      # Use PTS (presentation timestamp) seeking first
USE_FRAME_SEEKING = True    # Fall back to frame-based seeking
USE_SEQUENTIAL_FALLBACK = True  # Ultimate fallback to sequential reading


# ==============================================================================
#  GEODESY
# ==============================================================================

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between two WGS-84 points."""
    r  = EARTH_RADIUS_M
    p  = math.pi / 180
    a  = (math.sin((lat2 - lat1) * p / 2) ** 2
          + math.cos(lat1 * p) * math.cos(lat2 * p)
          * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def build_cumulative_distance(gps_track):
    """
    Return a list of dicts with keys: dist, t, lat, lon, alt.
    dist is cumulative metres from the first GPS point.
    """
    result = [{'dist': 0.0, 't': gps_track[0][0],
               'lat': gps_track[0][1], 'lon': gps_track[0][2], 'alt': gps_track[0][3]}]
    cum = 0.0
    for i in range(1, len(gps_track)):
        t0, lat0, lon0, alt0 = gps_track[i-1]
        t1, lat1, lon1, alt1 = gps_track[i]
        step = haversine_m(lat0, lon0, lat1, lon1)
        cum += step
        result.append({'dist': cum, 't': t1, 'lat': lat1, 'lon': lon1, 'alt': alt1})
    return result


def compute_vehicle_speed(gps_track):
    """
    Compute speed at each GPS point (m/s) and return a sorted list of
    (timestamp_sec, speed_mps).
    """
    speeds = []
    for i in range(1, len(gps_track)):
        t0, lat0, lon0, _ = gps_track[i-1]
        t1, lat1, lon1, _ = gps_track[i]
        dt = t1 - t0
        if dt <= 0:
            continue
        d = haversine_m(lat0, lon0, lat1, lon1)
        spd = d / dt          # m/s
        mid_t = (t0 + t1) / 2
        speeds.append((mid_t, spd))
    return speeds


# ==============================================================================
#  GPS UTILITIES
# ==============================================================================

def load_gps_track(gps_csv_path):
    """Load ExifTool GPS CSV with proper DateTime parsing."""
    if not os.path.exists(gps_csv_path):
        print(f"⚠️  GPS file not found: {gps_csv_path}")
        return []

    with open(gps_csv_path, 'rb') as f:
        raw = f.read()

    # Detect encoding
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        encoding = 'utf-16'
    elif raw.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8-sig'
    else:
        detected = chardet.detect(raw)
        encoding = detected.get('encoding', 'utf-8') or 'utf-8'

    print(f"  GPS encoding: {encoding}")

    # Detect separator
    try:
        sample = raw.decode(encoding, errors='replace')[:5000]
    except Exception:
        sample = raw.decode('latin-1', errors='replace')[:5000]
        encoding = 'latin-1'

    first_lines = sample.split('\n')[:10]
    sep = '\t' if sum(l.count('\t') for l in first_lines) > sum(l.count(',') for l in first_lines) else ','
    print(f"  GPS separator: {'TAB' if sep == chr(9) else 'COMMA'}")

    # Read CSV
    try:
        df = pd.read_csv(gps_csv_path, encoding=encoding, sep=sep)
    except UnicodeError:
        df = pd.read_csv(gps_csv_path, encoding='latin-1', sep=sep)

    # Clean column names (strip whitespace)
    df.columns = [c.strip() for c in df.columns]
    print(f"  Columns found: {list(df.columns)}")

    # Find columns (case-insensitive)
    lat_col = None
    lon_col = None
    alt_col = None
    datetime_col = None
    
    for col in df.columns:
        col_lower = col.lower()
        if 'lat' in col_lower:
            lat_col = col
        elif 'lon' in col_lower or 'lng' in col_lower:
            lon_col = col
        elif 'alt' in col_lower or 'height' in col_lower:
            alt_col = col
        elif 'date' in col_lower or 'time' in col_lower or 'datetime' in col_lower:
            datetime_col = col
    
    if not lat_col or not lon_col:
        print(f"  ❌ Could not find lat/lon columns")
        print(f"     Available: {list(df.columns)}")
        return []
    
    if not datetime_col:
        print(f"  ❌ Could not find DateTime column")
        print(f"     Available: {list(df.columns)}")
        return []
    
    print(f"  Using columns:")
    print(f"     DateTime: '{datetime_col}'")
    print(f"     Latitude: '{lat_col}'")
    print(f"     Longitude: '{lon_col}'")
    print(f"     Altitude: '{alt_col if alt_col else 'None'}'")

    # Parse track
    track = []
    
    for idx, row in df.iterrows():
        try:
            # Parse DateTime string
            datetime_str = str(row[datetime_col]).strip()
            
            # Handle format: "2026:05:06 05:36:21.200"
            # Replace colons in date part with hyphens
            if ' ' in datetime_str:
                date_part, time_part = datetime_str.split(' ')
                # Fix date part: replace colons with hyphens
                date_part = date_part.replace(':', '-')
                datetime_str = f"{date_part} {time_part}"
            
            # Parse to datetime object
            dt = pd.to_datetime(datetime_str)
            
            # Convert to seconds since start of recording
            # First, get reference time (first timestamp will be normalized later)
            timestamp_sec = dt.timestamp()
            
            # Get coordinates
            lat = float(row[lat_col])
            lon = float(row[lon_col])
            alt = float(row[alt_col]) if alt_col and pd.notna(row[alt_col]) else 0.0
            
            track.append((timestamp_sec, lat, lon, alt))
            
        except Exception as e:
            print(f"  ⚠️  Error parsing row {idx}: {e}")
            print(f"     DateTime string: '{row[datetime_col]}'")
            continue
    
    if not track:
        print("  ❌ No valid GPS points found!")
        return []
    
    # Sort by timestamp
    track.sort(key=lambda x: x[0])
    
    # Normalize timestamps to start from 0
    t_start = track[0][0]
    print(f"  Raw timestamp range: {track[0][0]:.1f} to {track[-1][0]:.1f}")
    
    # Normalize to zero-based seconds
    track = [(t - t_start, lat, lon, alt) for t, lat, lon, alt in track]
    
    duration = track[-1][0]
    print(f"  ✅ {len(track)} GPS points | duration {format_timestamp(duration)} ({duration:.1f}s)")
    print(f"  Start GPS: {track[0][1]:.6f}, {track[0][2]:.6f}")
    print(f"  End GPS: {track[-1][1]:.6f}, {track[-1][2]:.6f}")
    
    # Verify timestamps are increasing
    for i in range(1, min(10, len(track))):
        dt = track[i][0] - track[i-1][0]
        if dt <= 0:
            print(f"  ⚠️  Non-increasing timestamp at index {i}: {track[i-1][0]:.3f} → {track[i][0]:.3f}")
    
    return track


def interpolate_gps(gps_track, timestamp_sec):
    """Linearly interpolate GPS at any timestamp. Returns (lat, lon, alt)."""
    if not gps_track:
        return None, None, None
    times = [p[0] for p in gps_track]
    if timestamp_sec <= times[0]:
        _, lat, lon, alt = gps_track[0]
        return round(lat,7), round(lon,7), round(alt,2)
    if timestamp_sec >= times[-1]:
        _, lat, lon, alt = gps_track[-1]
        return round(lat,7), round(lon,7), round(alt,2)
    idx = bisect.bisect_left(times, timestamp_sec)
    t0, lat0, lon0, alt0 = gps_track[idx-1]
    t1, lat1, lon1, alt1 = gps_track[idx]
    a = (timestamp_sec - t0) / (t1 - t0)
    return round(lat0+a*(lat1-lat0),7), round(lon0+a*(lon1-lon0),7), round(alt0+a*(alt1-alt0),2)


def format_timestamp(seconds):
    h = int(seconds//3600); m = int((seconds%3600)//60); s = seconds%60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# ==============================================================================
#  ROBUST VIDEO SEEKING
# ==============================================================================

class RobustVideoReader:
    """
    Handles reliable frame extraction from videos with multiple seeking strategies.
    """
    def __init__(self, video_path, name):
        self.video_path = video_path
        self.name = name
        self.cap = None
        self.fps = None
        self.total_frames = None
        self.duration = None
        self.frame_cache = {}  # Cache for sequential reading mode
        self.current_mode = "pts"  # pts, frame, sequential
        
    def open(self):
        """Open video and get properties"""
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            return False
        
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30.0  # fallback
            
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps if self.total_frames > 0 else 0
        
        return True
    
    def seek_and_read(self, target_sec):
        """
        Seek to timestamp and read frame using multiple strategies.
        Returns (frame, success, method_used)
        """
        if self.cap is None:
            return None, False, "none"
        
        # Strategy 1: PTS (millisecond) seeking
        if USE_PTS_SEEKING:
            self.cap.set(cv2.CAP_PROP_POS_MSEC, target_sec * 1000)
            ret, frame = self.cap.read()
            if ret:
                # Verify we got a different frame
                actual_msec = self.cap.get(cv2.CAP_PROP_POS_MSEC)
                actual_sec = actual_msec / 1000
                if abs(actual_sec - target_sec) < 0.5:  # within 0.5 seconds
                    return frame, True, "pts"
        
        # Strategy 2: Frame-based seeking
        if USE_FRAME_SEEKING:
            target_frame = int(round(target_sec * self.fps))
            target_frame = max(0, min(target_frame, self.total_frames - 1))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = self.cap.read()
            if ret:
                actual_frame = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
                actual_sec = actual_frame / self.fps
                if abs(actual_sec - target_sec) < 1.0:  # within 1 second
                    return frame, True, "frame"
        
        return None, False, "none"
    
    def close(self):
        """Release video capture"""
        if self.cap:
            self.cap.release()
            self.cap = None


class SequentialFrameLoader:
    """
    Pre-loads all frames for all capture points sequentially.
    Slower but 100% reliable.
    """
    def __init__(self, video_paths, capture_plan, fps, active_angles):
        self.video_paths = video_paths
        self.capture_plan = sorted(capture_plan, key=lambda x: x['timestamp_sec'])
        self.fps = fps
        self.active_angles = active_angles
        self.frames = {}
        
    def load_all(self):
        """Load frames for all capture points from all videos"""
        print("\n  Loading frames sequentially (reliable mode)...")
        
        for vname in self.active_angles:
            if vname not in self.video_paths:
                print(f"    ⚠️  {vname} not available in video_paths")
                continue
                
            vpath = self.video_paths[vname]
            print(f"    Processing {vname}...")
            cap = cv2.VideoCapture(vpath)
            if not cap.isOpened():
                print(f"      ⚠️  Could not open {vpath}")
                continue
            
            self.frames[vname] = {}
            frame_num = 0
            
            for cap_info in self.capture_plan:
                target_frame = int(round(cap_info['timestamp_sec'] * self.fps))
                
                # Read forward to target frame
                while frame_num < target_frame:
                    grabbed = cap.grab()
                    if not grabbed:
                        break
                    frame_num += 1
                
                # Retrieve frame
                if frame_num == target_frame:
                    ret, frame = cap.retrieve()
                    if ret:
                        self.frames[vname][cap_info['capture_idx']] = frame
                    else:
                        self.frames[vname][cap_info['capture_idx']] = None
                else:
                    self.frames[vname][cap_info['capture_idx']] = None
            
            cap.release()
            print(f"      Loaded {len([f for f in self.frames[vname].values() if f is not None])} frames")
        
        return self.frames


def diagnose_video_seeking(video_path):
    """Diagnose seeking behavior for a video"""
    print(f"\n🔍 Diagnosing seeking for: {os.path.basename(video_path)}")
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print("  ❌ Cannot open video")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    
    print(f"  FPS: {fps:.2f}")
    print(f"  Total frames: {total_frames}")
    print(f"  Duration: {duration:.2f}s")
    
    # Test timestamps at various points
    test_times = [0, 5, 10, 30, 60, 120, duration/2, duration - 5]
    test_times = [t for t in test_times if 0 <= t <= duration]
    
    # Get reference frame at 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ret0, frame0 = cap.read()
    
    results = []
    
    for t in test_times:
        target_frame = int(t * fps)
        
        # Test PTS seeking
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret_pts, frame_pts = cap.read()
        actual_pts_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        
        # Test frame seeking
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret_frame, frame_frame = cap.read()
        actual_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
        actual_frame_time = actual_frame / fps if fps > 0 else 0
        
        # Check if frames are identical to frame0 (bad seeking)
        diff_pts = np.mean(frame_pts - frame0) if frame_pts is not None and frame0 is not None else 999
        diff_frame = np.mean(frame_frame - frame0) if frame_frame is not None and frame0 is not None else 999
        
        result = {
            't': t,
            'pts_success': ret_pts,
            'pts_actual': actual_pts_time,
            'pts_diff': actual_pts_time - t,
            'pts_identical': diff_pts < 1.0 if ret_pts else False,
            'frame_success': ret_frame,
            'frame_actual': actual_frame_time,
            'frame_diff': actual_frame_time - t,
            'frame_identical': diff_frame < 1.0 if ret_frame else False
        }
        results.append(result)
    
    cap.release()
    
    # Print results
    print("\n  Seeking Test Results:")
    print("  " + "-" * 90)
    print(f"  {'Time(s)':<10} {'PTS Success':<12} {'PTS Actual':<12} {'PTS Diff':<12} {'Frame Success':<13} {'Frame Actual':<12} {'Frame Diff':<12}")
    print("  " + "-" * 90)
    
    for r in results:
        pts_status = "✅" if r['pts_success'] and not r['pts_identical'] else "⚠️" if r['pts_success'] else "❌"
        frame_status = "✅" if r['frame_success'] and not r['frame_identical'] else "⚠️" if r['frame_success'] else "❌"
        print(f"  {r['t']:<10.1f} {pts_status:<12} {r['pts_actual']:<12.2f} {r['pts_diff']:<+12.2f} {frame_status:<13} {r['frame_actual']:<12.2f} {r['frame_diff']:<+12.2f}")
    
    print("  " + "-" * 90)
    print("  ✅ = good seeking, ⚠️ = success but identical frame, ❌ = failed")
    
    # Determine best strategy
    pts_good = any(r['pts_success'] and not r['pts_identical'] for r in results)
    frame_good = any(r['frame_success'] and not r['frame_identical'] for r in results)
    
    print(f"\n  Recommendation:")
    if pts_good:
        print("    ✅ Use PTS seeking (CAP_PROP_POS_MSEC)")
    elif frame_good:
        print("    ⚠️ Use frame seeking (CAP_PROP_POS_FRAMES)")
    else:
        print("    ❌ Neither seeking method works reliably - use sequential reading")
    
    return results


# ==============================================================================
#  SPATIAL CAPTURE PLAN
# ==============================================================================

def build_spatial_capture_plan(gps_track, interval_m):
    """
    Walk the cumulative-distance table and yield one capture dict every
    `interval_m` metres along the route.
    """
    if len(gps_track) < 2:
        print("GPS track too short (< 2 points). Cannot build capture plan.")
        return []

    cum        = build_cumulative_distance(gps_track)
    total_dist = cum[-1]['dist']

    print(f"\n  Raw GPS points (first 10 of {len(gps_track)}):")
    for i, (t, lat, lon, alt) in enumerate(gps_track[:10]):
        print(f"    [{i:03d}] t={t:.3f}s  lat={lat:.8f}  lon={lon:.8f}  alt={alt:.1f}m")

    print(f"\n  Cumulative distance (first 10 segments):")
    for i, p in enumerate(cum[:10]):
        seg = p['dist'] - (cum[i-1]['dist'] if i > 0 else 0.0)
        print(f"    [{i:03d}] cum={p['dist']:.4f}m  seg={seg:.4f}m  "
              f"t={p['t']:.3f}s  ({p['lat']:.8f}, {p['lon']:.8f})")

    print(f"\n  Total route : {total_dist:.4f} m")
    print(f"  Time span   : {gps_track[0][0]:.3f}s to {gps_track[-1][0]:.3f}s")
    print(f"  GPS points  : {len(gps_track)}")

    if total_dist < 1.0:
        print("\n  PROBLEM: Total distance < 1 m!")
        print("  Possible causes:")
        print("  1. Lat/lon columns are identical (GPS lock failure in recording)")
        print("  2. Lat/lon columns are swapped")
        print("  3. All rows have the same coordinate value")
        print("  Please paste the first 5 rows of your GPS CSV here for diagnosis.")
        return []

    speeds = compute_vehicle_speed(gps_track)
    if speeds:
        spds = [s for _, s in speeds]
        print(f"  Speed km/h  : min={min(spds)*3.6:.1f}  "
              f"avg={sum(spds)/len(spds)*3.6:.1f}  "
              f"max={max(spds)*3.6:.1f}")

    n_expected = int(total_dist / interval_m) + 1
    print(f"  Interval    : {interval_m} m -> {n_expected} panoramas planned\n")

    cum_dists   = [p['dist'] for p in cum]
    plan        = []
    capture_idx = 0
    next_dist   = 0.0

    while next_dist <= total_dist + 1e-6:
        idx = bisect.bisect_left(cum_dists, next_dist)
        idx = min(idx, len(cum) - 1)

        if idx == 0 or cum[idx]['dist'] == cum[idx-1]['dist']:
            p = cum[idx]
            t, lat, lon, alt = p['t'], p['lat'], p['lon'], p['alt']
        else:
            p0    = cum[idx - 1]
            p1    = cum[idx]
            alpha = (next_dist - p0['dist']) / (p1['dist'] - p0['dist'])
            t     = p0['t']   + alpha * (p1['t']   - p0['t'])
            lat   = p0['lat'] + alpha * (p1['lat'] - p0['lat'])
            lon   = p0['lon'] + alpha * (p1['lon'] - p0['lon'])
            alt   = p0['alt'] + alpha * (p1['alt'] - p0['alt'])

        plan.append({
            'capture_idx':   capture_idx,
            'timestamp_sec': round(t, 3),
            'lat':           round(lat, 7),
            'lon':           round(lon, 7),
            'alt':           round(alt, 2),
            'dist_m':        round(next_dist, 2),
        })

        print(f"    plan[{capture_idx:04d}]  dist={next_dist:8.2f}m  "
              f"t={t:9.3f}s  frame~={int(round(t*30)):7d}  "
              f"GPS=({round(lat,6):.6f}, {round(lon,6):.6f})")

        capture_idx += 1
        next_dist   += interval_m

    return plan


# ==============================================================================
#  MODEL LOADERS
# ==============================================================================

def load_cnn_model():
    print("  Loading EfficientNetB7 (dedup features)...")
    return EfficientNetB7(weights="imagenet", include_top=False, pooling="avg")


def load_classification_model(checkpoint_path, num_classes):
    print("  Loading BEiT classifier...")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"    Device: {device}")
    config = BeitConfig.from_pretrained(
        "microsoft/beit-base-patch16-224-pt22k-ft22k", num_labels=num_classes)
    model = BeitForImageClassification.from_pretrained(
        "microsoft/beit-base-patch16-224-pt22k-ft22k",
        config=config, ignore_mismatched_sizes=True)
    try:
        model.load_state_dict(
            torch.load(checkpoint_path, map_location=device)['model_state_dict'])
    except KeyError:
        model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model.to(device); model.eval()
    return model, device


def load_detector():
    print("  Loading Faster R-CNN (Open Images)...")
    return hub.load(
        "https://tfhub.dev/google/faster_rcnn/openimages_v4/inception_resnet_v2/1"
    ).signatures['default']


# ==============================================================================
#  CLASSIFICATION
# ==============================================================================

def classify_pil(model, device, image, class_names):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.5,0.5,0.5], std=[0.5,0.5,0.5]),
    ])
    t = transform(image).unsqueeze(0).to(device)
    with torch.no_grad():
        _, pred = torch.max(model(t).logits, 1)
    return class_names[pred.item()]


def classify_path(model, device, path, class_names):
    return classify_pil(model, device, Image.open(path).convert("RGB"), class_names)


# ==============================================================================
#  DETECTION & GEOMETRY
# ==============================================================================

def calc_iou(b1, b2):
    y1 = max(b1[0],b2[0]); x1 = max(b1[1],b2[1])
    y2 = min(b1[2],b2[2]); x2 = min(b1[3],b2[3])
    inter = max(0,x2-x1)*max(0,y2-y1)
    union = (b1[2]-b1[0])*(b1[3]-b1[1]) + (b2[2]-b2[0])*(b2[3]-b2[1]) - inter
    return inter/union if union > 0 else 0


def detect_buildings(rgb_frame, detector):
    """Faster R-CNN inference on one perspective frame."""
    tensor = tf.image.convert_image_dtype(
        (rgb_frame/255.0).astype(np.float32), tf.float32)[tf.newaxis,...]
    result  = detector(tensor)
    dets    = []
    for i in range(len(result['detection_boxes'])):
        cls   = result['detection_class_entities'][i].numpy().decode()
        score = float(result['detection_scores'][i])
        if cls in TARGET_CLASSES and score >= DETECTION_SCORE_THRESHOLD:
            box = result['detection_boxes'][i].numpy().tolist()
            if not any(calc_iou(box, d['box']) > 0.6 for d in dets):
                dets.append({'box': box, 'score': score})
    return dets


def box_to_equirect(norm_box, yaw_deg, crop_w, crop_h,
                    h_fov=H_FOV, v_fov=V_FOV):
    """Reproject a perspective-crop detection box to equirectangular [0,1]."""
    y1n, x1n, y2n, x2n = norm_box
    corners = [
        (x1n*crop_w, y1n*crop_h), (x2n*crop_w, y1n*crop_h),
        (x1n*crop_w, y2n*crop_h), (x2n*crop_w, y2n*crop_h),
    ]
    fx = crop_w / (2*math.tan(math.radians(h_fov/2)))
    fy = crop_h / (2*math.tan(math.radians(v_fov/2)))
    cx = crop_w/2; cy = crop_h/2
    yr = math.radians(yaw_deg)
    eq_xs, eq_ys = [], []
    for (px,py) in corners:
        dx=(px-cx)/fx; dy=(py-cy)/fy; dz=1.0
        n=math.sqrt(dx*dx+dy*dy+dz*dz); dx/=n; dy/=n; dz/=n
        dx2=dx*math.cos(yr)+dz*math.sin(yr)
        dz2=-dx*math.sin(yr)+dz*math.cos(yr)
        dx=dx2; dz=dz2
        lon=math.atan2(dx,dz); lat=math.asin(max(-1,min(1,dy)))
        eq_xs.append((lon/math.pi+1)/2)
        eq_ys.append(0.5-lat/math.pi)
    return [min(eq_ys), min(eq_xs), max(eq_ys), max(eq_xs)]


def fuse_across_views(per_view):
    """NMS-style cross-view fusion in equirectangular space."""
    candidates = sorted(per_view, key=lambda d: d['score'], reverse=True)
    fused = []
    for cand in candidates:
        eq = cand['equirect_box']
        merged = False
        for ex in fused:
            iou = calc_iou(eq, ex['equirect_box'])
            if iou < IOU_DUPLICATE_THRESHOLD:
                iou = max(iou, calc_iou([eq[0],eq[1]-1,eq[2],eq[3]-1], ex['equirect_box']))
            if iou < IOU_DUPLICATE_THRESHOLD:
                iou = max(iou, calc_iou([eq[0],eq[1]+1,eq[2],eq[3]+1], ex['equirect_box']))
            if iou >= IOU_DUPLICATE_THRESHOLD:
                if cand['score'] > ex['score']:
                    crop = cand['crop_img']; ex.update(cand); ex['crop_img'] = crop
                ex.setdefault('merged_views', [ex['view_name']]).append(cand['view_name'])
                merged = True; break
        if not merged:
            cand['merged_views'] = [cand['view_name']]
            fused.append(cand)
    return fused


# ==============================================================================
#  PANORAMA STITCHING (UPDATED to use active angles)
# ==============================================================================

def stitch_equirectangular(view_frames, pano_w=8192, pano_h=4096):
    """
    Fixed Equirectangular stitch using Inverse Mapping to prevent black voids.
    Only uses the provided view_frames (active angles only)
    """
    pano = np.zeros((pano_h, pano_w, 3), dtype=np.uint8)
    
    # Create the coordinate grid for the panorama (destination)
    # We want to find the color for every single pixel in the 8192x4096 grid
    eq_x = np.linspace(0, pano_w - 1, pano_w)
    eq_y = np.linspace(0, pano_h - 1, pano_h)
    EQ_X, EQ_Y = np.meshgrid(eq_x, eq_y)

    # Convert pano pixel coordinates to spherical coordinates (longitude/latitude)
    lon = (EQ_X / pano_w - 0.5) * (2 * math.pi)
    lat = (0.5 - EQ_Y / pano_h) * math.pi

    # 3D Cartesian coordinates on a unit sphere
    # Note: These are the vectors pointing from the center to each pano pixel
    DX_global = np.cos(lat) * np.sin(lon)
    DY_global = np.sin(lat)
    DZ_global = np.cos(lat) * np.cos(lon)

    for view_name, bgr in view_frames.items():
        if bgr is None: continue
    
        yaw_deg = PERSPECTIVE_YAWS[view_name]
        h, w = bgr.shape[:2]
        yr = math.radians(-yaw_deg)

        # 1. Rotate global vectors to local
        DX_local = DX_global * math.cos(yr) + DZ_global * math.sin(yr)
        DY_local = DY_global
        DZ_local = -DX_global * math.sin(yr) + DZ_global * math.cos(yr)

        # 2. Project to camera plane
        fx = w / (2 * math.tan(math.radians(H_FOV / 2)))
        fy = h / (2 * math.tan(math.radians(V_FOV / 2)))
        cx, cy = w / 2, h / 2

        # 3. Create maps for the WHOLE panorama shape (2D)
        # We initialize with out-of-bounds values (-1)
        map_x = np.full((pano_h, pano_w), -1, dtype=np.float32)
        map_y = np.full((pano_h, pano_w), -1, dtype=np.float32)

        # Only calculate for pixels in front of the camera
        mask = DZ_local > 0.1
    
        px = (DX_local[mask] / DZ_local[mask]) * fx + cx
        py = (DY_local[mask] / DZ_local[mask]) * fy + cy

        # Filter pixels actually inside the source image
        in_frame = (px >= 0) & (px < w - 1) & (py >= 0) & (py < h - 1)
    
        # We need a 2D mask to place the calculated coordinates back into the map
        final_mask = np.zeros((pano_h, pano_w), dtype=bool)
        # This is a bit tricky: mask is already (pano_h, pano_w)
        # We further refine it with in_frame results
        temp_mask_indices = np.where(mask)
        final_mask_indices = (temp_mask_indices[0][in_frame], temp_mask_indices[1][in_frame])
    
        map_x[final_mask_indices] = px[in_frame]
        map_y[final_mask_indices] = py[in_frame]

        # 4. Use remap with 2D maps (This avoids the SHRT_MAX error)
        view_on_pano = cv2.remap(bgr, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
    
        # Update only the pixels that were actually mapped
        pano_mask = map_x != -1
        pano[pano_mask] = view_on_pano[pano_mask]

    return cv2.cvtColor(pano, cv2.COLOR_BGR2RGB)


# ==============================================================================
#  CNN DEDUP
# ==============================================================================

def extract_cnn_feature(pil_img, cnn_model):
    img = pil_img.resize((224,224)).convert("RGB")
    arr = preprocess_input(np.expand_dims(np.array(img,np.float32),0))
    return cnn_model.predict(arr, verbose=0).flatten()


def cnn_dedup(saved_crops, cnn_model, original_dir, duplicate_dir):
    os.makedirs(original_dir, exist_ok=True)
    os.makedirs(duplicate_dir, exist_ok=True)
    if len(saved_crops) < 2:
        for item in saved_crops:
            shutil.copy(item['path'], os.path.join(original_dir, os.path.basename(item['path'])))
        return

    print(f"  Extracting CNN features for {len(saved_crops)} crops...")
    feats = np.array([extract_cnn_feature(it['pil'], cnn_model) for it in saved_crops])
    labels = DBSCAN(eps=CNN_SIMILARITY_EPS, min_samples=2, metric='cosine').fit_predict(feats)

    cluster = defaultdict(list)
    for i,l in enumerate(labels): cluster[l].append(i)

    n_orig = n_dup = 0
    for lbl, idxs in cluster.items():
        if lbl == -1:
            for i in idxs:
                shutil.copy(saved_crops[i]['path'],
                            os.path.join(original_dir, os.path.basename(saved_crops[i]['path'])))
                n_orig += 1
        else:
            shutil.copy(saved_crops[idxs[0]]['path'],
                        os.path.join(original_dir, os.path.basename(saved_crops[idxs[0]]['path'])))
            n_orig += 1
            for i in idxs[1:]:
                shutil.copy(saved_crops[i]['path'],
                            os.path.join(duplicate_dir, os.path.basename(saved_crops[i]['path'])))
                n_dup += 1

    print(f"  CNN dedup → {n_orig} originals, {n_dup} duplicates.")


# ==============================================================================
#  RESULTS EXPORT
# ==============================================================================

def save_excel(records, path):
    df = pd.DataFrame(records)
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Buildings')
        ws = writer.sheets['Buildings']
        widths = {'A':6,'B':8,'C':12,'D':26,'E':14,'F':14,'G':12,
                  'H':12,'I':14,'J':14,'K':12,'L':35}
        for col,w in widths.items():
            if col in ws.column_dimensions:
                ws.column_dimensions[col].width = w
    print(f"  ✅ Excel: {path}")


def save_geojson(records, path):
    features = []
    for r in records:
        if r.get('Latitude') is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r['Longitude'], r['Latitude']]},
            "properties": {k: v for k,v in r.items() if k not in ('Latitude','Longitude')},
        })
    with open(path,'w') as f:
        json.dump({"type":"FeatureCollection","features":features}, f, indent=2)
    print(f"  ✅ GeoJSON: {path}  ({len(features)} buildings)")


# ==============================================================================
#  MAIN PIPELINE
# ==============================================================================

def process_spatial(spatial_interval_m=None, use_sequential=False, force_diagnose=False, active_angles=None):
    """
    Spatial-sampling pipeline with robust seeking.
    
    Args:
        spatial_interval_m: Distance between captures (metres)
        use_sequential: Force sequential frame loading (slow but 100% reliable)
        force_diagnose: Run diagnosis on videos before processing
        active_angles: List of angles to process (default: all 8 angles)
    """
    interval_m = spatial_interval_m if spatial_interval_m else SPATIAL_INTERVAL_M
    
    # Use provided active_angles or default to all
    if active_angles is None:
        active_angles = ACTIVE_ANGLES
    else:
        active_angles = active_angles
    
    print(f"\n{'='*70}")
    print(f"  ACTIVE ANGLES: {len(active_angles)} of {len(PERSPECTIVE_VIDEOS)} total")
    for angle in active_angles:
        print(f"    - {angle} ({PERSPECTIVE_YAWS[angle]}°)")
    print(f"{'='*70}\n")

    # ── Directories ────────────────────────────────────────────────────────────
    PANO_DIR      = os.path.join(BASE_OUTPUT_DIR, "panoramas")
    PANO_ANN_DIR  = os.path.join(BASE_OUTPUT_DIR, "panoramas_annotated")
    CROPPED_DIR   = os.path.join(BASE_OUTPUT_DIR, "cropped")
    ORIGINAL_DIR  = os.path.join(BASE_OUTPUT_DIR, "original")
    DUPLICATE_DIR = os.path.join(BASE_OUTPUT_DIR, "duplicate")
    EXCEL_PATH    = os.path.join(BASE_OUTPUT_DIR, "classification_results.xlsx")
    GEOJSON_PATH  = os.path.join(BASE_OUTPUT_DIR, "buildings.geojson")

    for d in [PANO_DIR, PANO_ANN_DIR, CROPPED_DIR, ORIGINAL_DIR, DUPLICATE_DIR]:
        os.makedirs(d, exist_ok=True)

    # ── GPS ────────────────────────────────────────────────────────────────────
    print("\n── Loading GPS track ──────────────────────────────────────────────")
    gps_track = load_gps_track(GPS_CSV_PATH)
    # In process_spatial(), after loading gps_track:
    print("\n🔍 GPS TRACK VERIFICATION:")
    print(f"  Number of points: {len(gps_track)}")
    if gps_track:
        print(f"  First 5 points:")
        for i in range(min(5, len(gps_track))):
            t, lat, lon, alt = gps_track[i]
            print(f"    [{i}] t={t:8.3f}s, lat={lat:.8f}, lon={lon:.8f}, alt={alt:.2f}")
        print(f"  Last point:")
        t, lat, lon, alt = gps_track[-1]
        print(f"    t={t:8.3f}s, lat={lat:.8f}, lon={lon:.8f}, alt={alt:.2f}")
    
        # Calculate expected FPS from GPS timestamps
        if len(gps_track) > 1:
            avg_dt = (gps_track[-1][0] - gps_track[0][0]) / len(gps_track)
            print(f"  Average time between GPS points: {avg_dt*1000:.1f}ms")
    else:
        print("  ❌ No GPS points loaded!")

    # ── Capture plan ───────────────────────────────────────────────────────────
    print("\n── Building spatial capture plan ──────────────────────────────────")
    capture_plan = build_spatial_capture_plan(gps_track, interval_m)
    print(f"  → {len(capture_plan)} panoramas to capture.")
    
    if not capture_plan:
        print("❌  No capture points generated. Exiting.")
        return

    # ── Open videos and diagnose (only active angles) ─────────────────────────
    print("\n── Opening perspective videos (active angles only) ─────────────────")
    caps = {}
    video_paths = {}
    
    for vname in active_angles:
        if vname not in PERSPECTIVE_VIDEOS:
            print(f"  ⚠️  {vname} is not a valid angle name. Skipping.")
            continue
            
        fname = PERSPECTIVE_VIDEOS[vname]
        fpath = os.path.join(VIDEO_DIR, fname)
        if os.path.exists(fpath):
            video_paths[vname] = fpath
            reader = RobustVideoReader(fpath, vname)
            if reader.open():
                caps[vname] = reader
                print(f"  ✅ [{vname:6s}] {fname} (fps={reader.fps:.2f})")
            else:
                print(f"  ❌ [{vname:6s}] Could not open {fname}")
        else:
            print(f"  ❌ [{vname:6s}] NOT FOUND — {fpath}")

    if not caps:
        print("❌  No videos opened. Exiting.")
        return

    # Get FPS from first video
    first_vname = list(caps.keys())[0]
    fps = caps[first_vname].fps
    print(f"  Video FPS: {fps:.2f}")

    # Optional: Run diagnosis
    if force_diagnose:
        print("\n── Running seeking diagnosis ─────────────────────────────────────")
        for vname, reader in caps.items():
            diagnose_video_seeking(video_paths[vname])
    
    # Decide frame extraction strategy
    if use_sequential:
        print("\n── Using sequential frame loading (reliable mode) ────────────────")
        sequential_loader = SequentialFrameLoader(video_paths, capture_plan, fps, active_angles)
        frames_by_capture = sequential_loader.load_all()
        
        if not frames_by_capture:
            print("❌  Failed to load frames sequentially")
            return
            
        # Process using pre-loaded frames
        all_records, saved_crops, building_id = process_with_frames(
            frames_by_capture, capture_plan, caps, PANO_DIR, PANO_ANN_DIR, 
            CROPPED_DIR, PANO_W=8192, PANO_H=4096, active_angles=active_angles
        )
        
    else:
        print("\n── Using adaptive seeking mode ───────────────────────────────────")
        # Process using on-demand seeking
        all_records, saved_crops, building_id = process_with_seeking(
            caps, capture_plan, fps, PANO_DIR, PANO_ANN_DIR, 
            CROPPED_DIR, PANO_W=8192, PANO_H=4096, active_angles=active_angles
        )

    # ── Release video captures ─────────────────────────────────────────────────
    for reader in caps.values():
        reader.close()
    
    if not all_records:
        print("\n⚠️  No buildings detected in any panorama.")
        return

    print(f"\n✅ Processing complete. {len(all_records)} total detections.")

    # ── Load models for classification (if not already loaded) ─────────────────
    print("\n── Loading models for final processing ─────────────────────────────")
    classifier, device = load_classification_model(CLASSIFICATION_MODEL_CHECKPOINT, NUM_CLASSES)
    cnn_model = load_cnn_model()

    # ── CNN second-pass dedup ──────────────────────────────────────────────────
    print("\n── CNN deduplication (second pass) ────────────────────────────────")
    cnn_dedup(saved_crops, cnn_model, ORIGINAL_DIR, DUPLICATE_DIR)

    # ── Re-classify originals & update records ─────────────────────────────────
    print("\n── Re-classifying originals & exporting ────────────────────────────")
    orig_fnames = set(os.listdir(ORIGINAL_DIR))

    final_records = []
    for rec in all_records:
        is_original = rec['Crop_file'] in orig_fnames
        rec['Is_Original'] = is_original

        if is_original:
            img_path = os.path.join(ORIGINAL_DIR, rec['Crop_file'])
            if os.path.exists(img_path):
                rec['Classification'] = classify_path(classifier, device, img_path, CLASS_NAMES)

        final_records.append(rec)

    # Save
    save_excel(final_records, EXCEL_PATH)
    save_geojson([r for r in final_records if r['Is_Original']], GEOJSON_PATH)

    # ── Summary ───────────────────────────────────────────────────────────────
    n_orig = sum(1 for r in final_records if r['Is_Original'])
    n_dup  = len(final_records) - n_orig
    total_route = (capture_plan[-1]['dist_m'] if capture_plan else 0)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                SPATIAL PIPELINE COMPLETE                     ║
╠══════════════════════════════════════════════════════════════╣
║  Active angles                : {len(active_angles)}
║  Spatial interval             : {interval_m} m
║  Total route length           : {total_route:.1f} m
║  Panoramas captured           : {len([r for r in all_records if r.get('Capture_IDX')])}
║  Total building detections    : {len(final_records)}
║  Unique buildings (originals) : {n_orig}
║  Duplicates removed           : {n_dup}
╠══════════════════════════════════════════════════════════════╣
║  OUTPUT STRUCTURE                                            ║
║  panoramas/            full 8K equirect panoramas            ║
║  panoramas_annotated/  4K thumbnails with bounding boxes     ║
║  cropped/              all building crops                    ║
║  original/             unique buildings (post CNN dedup)     ║
║  duplicate/            visual duplicates                     ║
║  classification_results.xlsx   georeferenced results         ║
║  buildings.geojson             ready for QGIS / Google Earth ║
╚══════════════════════════════════════════════════════════════╝
    """)


def process_with_frames(frames_by_capture, capture_plan, caps, 
                        PANO_DIR, PANO_ANN_DIR, CROPPED_DIR, PANO_W, PANO_H, active_angles):
    """Process using pre-loaded frames from sequential loader"""
    
    # Load all models
    print("\n── Loading models ─────────────────────────────────────────────────")
    detector = load_detector()
    classifier, device = load_classification_model(CLASSIFICATION_MODEL_CHECKPOINT, NUM_CLASSES)
    print("  All models ready.\n")
    
    all_records = []
    saved_crops = []
    building_id = 0
    
    for cap_info in capture_plan:
        cidx = cap_info['capture_idx']
        t_sec = cap_info['timestamp_sec']
        lat = cap_info['lat']
        lon = cap_info['lon']
        alt = cap_info['alt']
        dist = cap_info['dist_m']
        
        ts_str = format_timestamp(t_sec)
        
        print(f"\n  ── Capture #{cidx:04d} | dist={dist:.1f}m | "
              f"t={ts_str} | GPS: {lat},{lon} ──")
        
        # Get frames for this capture (only active angles)
        view_frames = {}
        for vname in active_angles:
            if vname in frames_by_capture and cidx in frames_by_capture[vname]:
                frame = frames_by_capture[vname][cidx]
                if frame is not None:
                    view_frames[vname] = frame
                else:
                    print(f"    ⚠️  [{vname}] No frame available")
        
        if not view_frames:
            print(f"    ⚠️  No frames retrieved — skipping capture #{cidx}.")
            continue
        
        # Process the capture
        result = process_single_capture(
            view_frames, cap_info, cidx, t_sec, lat, lon, alt, dist,
            detector, classifier, device,
            PANO_DIR, PANO_ANN_DIR, CROPPED_DIR, PANO_W, PANO_H,
            all_records, saved_crops, building_id
        )
        
        all_records, saved_crops, building_id = result
    
    return all_records, saved_crops, building_id


def process_with_seeking(caps, capture_plan, fps, 
                         PANO_DIR, PANO_ANN_DIR, CROPPED_DIR, PANO_W, PANO_H, active_angles):
    """Process using on-demand seeking"""
    
    # Load all models
    print("\n── Loading models ─────────────────────────────────────────────────")
    detector = load_detector()
    classifier, device = load_classification_model(CLASSIFICATION_MODEL_CHECKPOINT, NUM_CLASSES)
    print("  All models ready.\n")
    
    all_records = []
    saved_crops = []
    building_id = 0
    seek_stats = {'pts': 0, 'frame': 0, 'failed': 0}
    
    for cap_info in capture_plan:
        cidx = cap_info['capture_idx']
        t_sec = cap_info['timestamp_sec']
        lat = cap_info['lat']
        lon = cap_info['lon']
        alt = cap_info['alt']
        dist = cap_info['dist_m']
        
        ts_str = format_timestamp(t_sec)
        
        print(f"\n  ── Capture #{cidx:04d} | dist={dist:.1f}m | "
              f"t={ts_str} | GPS: {lat},{lon} ──")
        
        # Seek to timestamp in each video (only active angles)
        view_frames = {}
        for vname in active_angles:
            if vname in caps:
                frame, success, method = caps[vname].seek_and_read(t_sec)
                if success:
                    view_frames[vname] = frame
                    seek_stats[method] = seek_stats.get(method, 0) + 1
                else:
                    print(f"    ⚠️  [{vname}] seek failed at {t_sec:.2f}s")
                    seek_stats['failed'] += 1
            else:
                print(f"    ⚠️  [{vname}] not available in caps")
        
        if not view_frames:
            print(f"    ⚠️  No frames retrieved — skipping capture #{cidx}.")
            continue
        
        # Process the capture
        result = process_single_capture(
            view_frames, cap_info, cidx, t_sec, lat, lon, alt, dist,
            detector, classifier, device,
            PANO_DIR, PANO_ANN_DIR, CROPPED_DIR, PANO_W, PANO_H,
            all_records, saved_crops, building_id
        )
        
        all_records, saved_crops, building_id = result
    
    # Print seeking statistics
    print(f"\n  Seeking statistics: PTS={seek_stats['pts']}, Frame={seek_stats['frame']}, Failed={seek_stats['failed']}")
    
    return all_records, saved_crops, building_id


def process_single_capture(view_frames, cap_info, cidx, t_sec, lat, lon, alt, dist,
                          detector, classifier, device,
                          PANO_DIR, PANO_ANN_DIR, CROPPED_DIR, PANO_W, PANO_H,
                          all_records, saved_crops, building_id):
    """Process a single capture point"""
    
    ts_str = format_timestamp(t_sec)
    
    # ── Stitch & save panorama ─────────────────────────────────────────────
    pano_rgb = stitch_equirectangular(view_frames, PANO_W, PANO_H)
    pano_name = f"pano_{cidx:04d}_d{dist:.1f}m_t{t_sec:.2f}s.jpg"
    pano_path = os.path.join(PANO_DIR, pano_name)
    Image.fromarray(pano_rgb).save(pano_path, "JPEG", quality=95)
    
    # Check if panorama is not all zeros (bad stitch)
    if np.mean(pano_rgb) < 10:
        print(f"    ⚠️  Panorama appears blank/black - stitching may have failed")
    else:
        print(f"    💾 Panorama saved: {pano_name}")

    # ── Detection on every perspective view ────────────────────────────────
    per_view_dets = []
    for vname, bgr in view_frames.items():
        if bgr is None:
            continue
            
        yaw = PERSPECTIVE_YAWS[vname]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        raw = detect_buildings(rgb, detector)
        
        for det in raw:
            eq = box_to_equirect(det['box'], yaw, crop_w=w, crop_h=h)
            y1p = max(0, int(det['box'][0]*h))
            x1p = max(0, int(det['box'][1]*w))
            y2p = min(h, int(det['box'][2]*h))
            x2p = min(w, int(det['box'][3]*w))
            pil_crop = (Image.fromarray(rgb[y1p:y2p, x1p:x2p])
                        if y2p > y1p and x2p > x1p else None)
            per_view_dets.append({
                'view_name':    vname,
                'yaw_deg':      yaw,
                'crop_box':     det['box'],
                'equirect_box': eq,
                'score':        det['score'],
                'crop_img':     pil_crop,
            })

    fused = fuse_across_views(per_view_dets)
    print(f"    {len(per_view_dets)} raw detections → {len(fused)} fused")

    # ── Classify each fused detection & record ─────────────────────────────
    capture_dets_annotated = []
    for det in fused:
        if det['crop_img'] is None:
            continue

        pred = classify_pil(classifier, device, det['crop_img'], CLASS_NAMES)

        crop_fname = (f"building_{building_id:04d}"
                      f"_cap{cidx:04d}"
                      f"_d{dist:.1f}m"
                      f"_t{t_sec:.2f}s"
                      f"_{pred.replace(' ', '_')}.jpg")
        crop_path = os.path.join(CROPPED_DIR, crop_fname)
        det['crop_img'].save(crop_path, "JPEG", quality=95)
        saved_crops.append({'path': crop_path, 'pil': det['crop_img']})

        det['building_id'] = building_id
        det['class_name'] = pred
        capture_dets_annotated.append(det)

        record = {
            "Building_ID":      building_id,
            "Capture_IDX":      cidx,
            "Classification":   pred,
            "Confidence":       round(det['score'], 3),
            "Timestamp_sec":    t_sec,
            "Timestamp":        ts_str,
            "Distance_m":       dist,
            "Latitude":         lat,
            "Longitude":        lon,
            "Altitude_m":       alt,
            "Views_detected":   ', '.join(det.get('merged_views', [det['view_name']])),
            "Num_views":        len(det.get('merged_views', [det['view_name']])),
            "Panorama_file":    pano_name,
            "Crop_file":        crop_fname,
        }
        all_records.append(record)

        print(f"    ✅ Building #{building_id:04d} | {pred:25s} | "
              f"score={det['score']:.2f} | "
              f"views={det.get('merged_views', [det['view_name']])}")
        building_id += 1

    # ── Save annotated panorama (scaled to 4K) ─────────────────────────────
    scale = 0.5
    ann_w = int(PANO_W * scale)
    ann_h = int(PANO_H * scale)
    pano_small = cv2.resize(
        cv2.cvtColor(pano_rgb, cv2.COLOR_RGB2BGR), (ann_w, ann_h))

    for det in capture_dets_annotated:
        eq = det['equirect_box']
        x1 = int(eq[1]*ann_w)
        y1 = int(eq[0]*ann_h)
        x2 = int(eq[3]*ann_w)
        y2 = int(eq[2]*ann_h)
        cv2.rectangle(pano_small, (x1,y1), (x2,y2), (0,220,80), 3)
        label = f"#{det['building_id']} {det['class_name']} [{det['score']:.2f}]"
        cv2.putText(pano_small, label, (x1, max(y1-10,18)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,220,80), 2)

    info = (f"Cap #{cidx:04d} | {dist:.1f}m | {ts_str} | "
            f"{lat:.6f}, {lon:.6f}")
    cv2.putText(pano_small, info, (20, ann_h-20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,255), 2)

    ann_name = f"annotated_{cidx:04d}_d{dist:.1f}m.jpg"
    cv2.imwrite(os.path.join(PANO_ANN_DIR, ann_name), pano_small,
                [cv2.IMWRITE_JPEG_QUALITY, 90])
    
    return all_records, saved_crops, building_id


# ==============================================================================
# ── Entry point
# ==============================================================================

# Configuration - change these values as needed
RUN_INTERVAL_M = 15.0           # ← Change this for different spacing (metres)
USE_SEQUENTIAL_MODE = False     # ← Set to True if seeking still doesn't work (slower but 100% reliable)
RUN_DIAGNOSTICS = False         # ← Set to True to diagnose seeking issues first

# ── CHOOSE WHICH ANGLES TO USE ──────────────────────────────────────────────
# Edit this list to select which angles to process
# Options: 'front', 'fr45', 'right', 'br135', 'back', 'bl225', 'left', 'fl315'
# 
# Examples:
#   ALL 8 ANGLES (full coverage):
#   SELECTED_ANGLES = ['front', 'fr45', 'right', 'br135', 'back', 'bl225', 'left', 'fl315']
#
#   ONLY 4 CARDINAL DIRECTIONS (faster, less data):
#   SELECTED_ANGLES = ['front', 'right', 'back', 'left']
#
#   ONLY FRONT and BACK (minimal):
#   SELECTED_ANGLES = ['front', 'back']
#
#   ONLY 3 ANGLES (testing):
#   SELECTED_ANGLES = ['front', 'right', 'left']
#

# SELECTED_ANGLES = [
#     'front',    # 0 degrees
#     'fr45',     # 45 degrees
#     'right',    # 90 degrees
#     'br135',    # 135 degrees
#     'back',     # 180 degrees
#     'bl225',    # -135 degrees
#     'left',     # -90 degrees
#     'fl315',    # -45 degrees
# ]  # ← Modify this list to choose which angles to use
SELECTED_ANGLES = [
    'front',    # 0 degrees
    'fr45',     # 45 degrees
    # 'right',    # 90 degrees
    # 'br135',    # 135 degrees
    # 'back',     # 180 degrees
    # 'bl225',    # -135 degrees
    # 'left',     # -90 degrees
    'fl315',    # -45 degrees
]  # ← Modify this list to choose which angles to use


if __name__ == "__main__":
    import sys
    
    _in_jupyter = (
        "ipykernel" in sys.modules
        or "IPython" in sys.modules
        or hasattr(sys, "ps1")
    )
    
    if _in_jupyter:
        print(f"\n🗺️  Running in Jupyter — interval = {RUN_INTERVAL_M} m")
        print(f"   Active angles: {len(SELECTED_ANGLES)}")
        print(f"   Angles: {SELECTED_ANGLES}")
        print(f"   Sequential mode: {USE_SEQUENTIAL_MODE}")
        print(f"   Diagnostics: {RUN_DIAGNOSTICS}\n")
        
        if RUN_DIAGNOSTICS:
            # Run diagnosis first
            print("Running diagnostics mode...")
            test_video = os.path.join(VIDEO_DIR, "view_0_front.mp4")
            if os.path.exists(test_video):
                diagnose_video_seeking(test_video)
            print("\n" + "="*60)
            print("Diagnosis complete. Set RUN_DIAGNOSTICS = False and rerun to process.")
            print("="*60)
        else:
            process_spatial(
                spatial_interval_m=RUN_INTERVAL_M,
                use_sequential=USE_SEQUENTIAL_MODE,
                active_angles=SELECTED_ANGLES
            )
    else:
        import argparse
        parser = argparse.ArgumentParser(description="360° spatial-sampling building survey pipeline")
        parser.add_argument("--interval", type=float, default=SPATIAL_INTERVAL_M,
                          help=f"Capture every N metres (default: {SPATIAL_INTERVAL_M})")
        parser.add_argument("--sequential", action="store_true",
                          help="Use sequential frame loading (slower but 100% reliable)")
        parser.add_argument("--diagnose", action="store_true",
                          help="Run seeking diagnostics on videos")
        parser.add_argument("--angles", nargs="+", 
                          choices=['front', 'fr45', 'right', 'br135', 'back', 'bl225', 'left', 'fl315'],
                          default=['front', 'fr45', 'right', 'br135', 'back', 'bl225', 'left', 'fl315'],
                          help="Which perspective angles to process (default: all 8)")
        args = parser.parse_args()
        
        if args.diagnose:
            test_video = os.path.join(VIDEO_DIR, "view_0_front.mp4")
            if os.path.exists(test_video):
                diagnose_video_seeking(test_video)
        else:
            process_spatial(
                spatial_interval_m=args.interval,
                use_sequential=args.sequential,
                active_angles=args.angles
            )