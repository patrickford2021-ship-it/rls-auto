"""Smart cropping to the bottom half of a 9:16 Shorts frame (1080x960 by default).

Strategy:
  1. Scale the image so it fully covers the target box.
  2. Pick the crop window:
       a. If OpenCV is installed and finds faces, keep the faces in frame
          (with a little headroom above them).
       b. Otherwise slide the window over an edge-energy map and keep the
          busiest region, with a gentle bias towards the centre.
       c. If everything fails, plain centre crop.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

try:  # OpenCV is optional. Without it we fall back to the energy-based crop.
    import cv2  # type: ignore
except Exception:  # pragma: no cover - depends on the environment
    cv2 = None

Box = Tuple[int, int, int, int]  # x, y, w, h

# YuNet: small, accurate DNN face detector shipped with OpenCV >= 4.5.4 (and 5.x).
# The model file is fetched once into ./models and reused.
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
YUNET_FILE = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
# (Stored in Git LFS, so the "media" host serves the real file rather than a pointer.)
YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)

_haar_front = _haar_profile = None
_yunet = None
_yunet_failed = False


def _load_haar() -> bool:
    """Haar cascades ship inside opencv-python 4.x (removed in 5.x)."""
    global _haar_front, _haar_profile
    if cv2 is None or not hasattr(cv2, "CascadeClassifier"):
        return False
    if _haar_front is not None:
        return not _haar_front.empty()
    try:
        base = cv2.data.haarcascades
        _haar_front = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
        _haar_profile = cv2.CascadeClassifier(base + "haarcascade_profileface.xml")
        return not _haar_front.empty()
    except Exception:
        _haar_front = None
        return False


def _ensure_yunet_model() -> bool:
    if YUNET_FILE.is_file() and YUNET_FILE.stat().st_size > 100_000:
        return True
    try:
        import requests

        print("  Downloading face-detection model (one time, ~230 KB)...", end=" ", flush=True)
        resp = requests.get(YUNET_URL, timeout=30)
        resp.raise_for_status()
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        YUNET_FILE.write_bytes(resp.content)
        print("ok")
        return True
    except Exception as exc:
        print(f"failed ({exc.__class__.__name__}); using the built-in detector instead")
        return False


def _load_yunet():
    global _yunet, _yunet_failed
    if _yunet is not None or _yunet_failed:
        return _yunet
    if cv2 is None or not hasattr(cv2, "FaceDetectorYN"):
        _yunet_failed = True
        return None
    try:
        if not _ensure_yunet_model():
            raise RuntimeError("no model")
        _yunet = cv2.FaceDetectorYN.create(str(YUNET_FILE), "", (320, 320), score_threshold=0.7, nms_threshold=0.3)
    except Exception:
        _yunet_failed = True
        _yunet = None
    return _yunet


HAVE_OPENCV = cv2 is not None and (hasattr(cv2, "FaceDetectorYN") or hasattr(cv2, "CascadeClassifier"))


def crop_for_shorts(
    image: Image.Image,
    target: Tuple[int, int] = (1080, 960),
    use_faces: bool = True,
) -> Tuple[Image.Image, str]:
    """Return (cropped image, method used). Method is 'faces', 'energy' or 'center'."""
    tw, th = target
    rgb = image.convert("RGB")
    w, h = rgb.size

    scale = max(tw / w, th / h)
    new_w, new_h = max(tw, round(w * scale)), max(th, round(h * scale))
    scaled = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)

    method = "center"
    window: Optional[Box] = None

    if use_faces and HAVE_OPENCV:
        faces = detect_faces(scaled)
        if faces:
            window = _window_around_faces(faces, new_w, new_h, tw, th)
            method = "faces"

    if window is None:
        try:
            window = _window_by_energy(scaled, tw, th)
            method = "energy"
        except Exception:
            window = None

    if window is None:
        window = ((new_w - tw) // 2, (new_h - th) // 2, tw, th)
        method = "center"

    x, y, _, _ = window
    x = int(min(max(0, x), new_w - tw))
    y = int(min(max(0, y), new_h - th))
    return scaled.crop((x, y, x + tw, y + th)), method


# --------------------------------------------------------------------------- faces


def detect_faces(image: Image.Image) -> List[Box]:
    """Return face boxes in `image` coordinates. Empty list if none / no OpenCV."""
    if not HAVE_OPENCV:
        return []
    w, h = image.size
    # Detect on a smaller copy for speed, then scale the boxes back up.
    det_scale = min(1.0, 800 / max(w, h))
    small = image.resize((max(1, round(w * det_scale)), max(1, round(h * det_scale))), Image.Resampling.BILINEAR)
    rgb = np.ascontiguousarray(np.asarray(small))

    boxes: List[Box] = []
    try:
        boxes = _detect_yunet(rgb)
        if not boxes and _load_haar():
            boxes = _detect_haar(rgb)
    except Exception:
        boxes = []

    boxes = [(int(x / det_scale), int(y / det_scale), int(fw / det_scale), int(fh / det_scale)) for x, y, fw, fh in boxes]
    if not boxes:
        return []
    # Drop tiny detections (likely false positives) relative to the biggest face.
    biggest = max(b[2] * b[3] for b in boxes)
    return [b for b in boxes if b[2] * b[3] >= biggest * 0.2]


def _detect_yunet(rgb: np.ndarray) -> List[Box]:
    detector = _load_yunet()
    if detector is None:
        return []
    h, w = rgb.shape[:2]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    detector.setInputSize((w, h))
    _, faces = detector.detect(bgr)
    if faces is None:
        return []
    min_side = max(w, h) * 0.04
    out: List[Box] = []
    for face in faces:
        x, y, fw, fh = face[:4]
        if fw >= min_side and fh >= min_side:
            out.append((int(x), int(y), int(fw), int(fh)))
    return out


def _detect_haar(rgb: np.ndarray) -> List[Box]:
    gray = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    min_size = max(24, int(min(gray.shape) * 0.06))
    out: List[Box] = []
    for cascade in (_haar_front, _haar_profile):
        if cascade is None or cascade.empty():
            continue
        found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_size, min_size))
        for (x, y, fw, fh) in found:
            out.append((int(x), int(y), int(fw), int(fh)))
    return out


def _window_around_faces(faces: List[Box], img_w: int, img_h: int, tw: int, th: int) -> Box:
    x0 = min(f[0] for f in faces)
    y0 = min(f[1] for f in faces)
    x1 = max(f[0] + f[2] for f in faces)
    y1 = max(f[1] + f[3] for f in faces)
    face_h = y1 - y0

    cx = (x0 + x1) / 2
    # Place the faces around the upper third of the crop so bodies/shoulders show below.
    headroom = face_h * 0.6
    top = y0 - headroom
    # If the face group is taller than the frame allows, centre on it instead.
    if (y1 - y0) + headroom > th:
        top = (y0 + y1) / 2 - th / 2

    x = cx - tw / 2
    y = top
    x = min(max(0, x), img_w - tw)
    y = min(max(0, y), img_h - th)
    return int(x), int(y), tw, th


# -------------------------------------------------------------------------- energy


def _window_by_energy(image: Image.Image, tw: int, th: int) -> Box:
    """Find the busiest tw x th window using an edge map on a thumbnail."""
    img_w, img_h = image.size
    if img_w == tw and img_h == th:
        return 0, 0, tw, th

    thumb_scale = 160 / max(img_w, img_h)
    thumb = image.resize((max(2, round(img_w * thumb_scale)), max(2, round(img_h * thumb_scale))), Image.Resampling.BILINEAR)
    edges = np.asarray(thumb.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float64)

    # Mild centre bias: multiply energy by a wide gaussian centred on the image.
    hh, ww = edges.shape
    ys, xs = np.mgrid[0:hh, 0:ww]
    bias = np.exp(-(((xs - ww / 2) / (ww * 0.6)) ** 2 + ((ys - hh / 2) / (hh * 0.6)) ** 2))
    energy = edges * (0.6 + 0.4 * bias)

    win_w = max(1, min(ww, round(tw * thumb_scale)))
    win_h = max(1, min(hh, round(th * thumb_scale)))

    # Integral image for O(1) window sums.
    integral = np.zeros((hh + 1, ww + 1))
    integral[1:, 1:] = energy.cumsum(0).cumsum(1)
    sums = (
        integral[win_h:, win_w:]
        - integral[:-win_h, win_w:]
        - integral[win_h:, :-win_w]
        + integral[:-win_h, :-win_w]
    )
    by, bx = np.unravel_index(int(np.argmax(sums)), sums.shape)

    x = int(bx / thumb_scale)
    y = int(by / thumb_scale)
    x = min(max(0, x), img_w - tw)
    y = min(max(0, y), img_h - th)
    return x, y, tw, th
