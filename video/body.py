"""Body-aware video effects using mediapipe segmentation and pose detection."""

import math
import os
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

_MODEL_DIR = Path("/tmp")
_SEG_MODEL = _MODEL_DIR / "selfie_segmenter.tflite"
_POSE_MODEL = _MODEL_DIR / "pose_landmarker_lite.task"

_SEG_URL = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite"
_POSE_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"

_segmenter = None
_pose_landmarker = None


def _ensure_model(path: Path, url: str):
    if not path.exists():
        urllib.request.urlretrieve(url, str(path))


def _get_segmenter():
    global _segmenter
    if _segmenter is None:
        import mediapipe as mp
        _ensure_model(_SEG_MODEL, _SEG_URL)
        options = mp.tasks.vision.ImageSegmenterOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(_SEG_MODEL)),
            output_confidence_masks=True,
        )
        _segmenter = mp.tasks.vision.ImageSegmenter.create_from_options(options)
    return _segmenter


def _get_pose_landmarker():
    global _pose_landmarker
    if _pose_landmarker is None:
        import mediapipe as mp
        _ensure_model(_POSE_MODEL, _POSE_URL)
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(_POSE_MODEL)),
            num_poses=1,
        )
        _pose_landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
    return _pose_landmarker


# Cache segmentation masks per image (keyed by id)
_mask_cache: dict[int, np.ndarray] = {}
_pose_cache: dict[int, list] = {}


def get_body_mask(pil_img: Image.Image) -> np.ndarray:
    """Get body segmentation mask (float32, 0-1) for a PIL image. Cached per image object."""
    img_id = id(pil_img)
    if img_id in _mask_cache:
        return _mask_cache[img_id]

    import mediapipe as mp
    segmenter = _get_segmenter()
    arr = np.array(pil_img.convert("RGB"))
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
    result = segmenter.segment(mp_image)

    if result.confidence_masks:
        mask = result.confidence_masks[0].numpy_view().squeeze()
    else:
        mask = np.zeros((pil_img.height, pil_img.width), dtype=np.float32)

    _mask_cache[img_id] = mask
    # Keep cache bounded
    if len(_mask_cache) > 30:
        oldest = next(iter(_mask_cache))
        del _mask_cache[oldest]
    return mask


def get_pose_landmarks(pil_img: Image.Image) -> list:
    """Get pose landmarks for a PIL image. Returns list of (x, y, visibility) tuples. Cached."""
    img_id = id(pil_img)
    if img_id in _pose_cache:
        return _pose_cache[img_id]

    import mediapipe as mp
    landmarker = _get_pose_landmarker()
    arr = np.array(pil_img.convert("RGB"))
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
    result = landmarker.detect(mp_image)

    landmarks = []
    if result.pose_landmarks and len(result.pose_landmarks) > 0:
        h, w = arr.shape[:2]
        for lm in result.pose_landmarks[0]:
            landmarks.append((lm.x * w, lm.y * h, lm.visibility))

    _pose_cache[img_id] = landmarks
    if len(_pose_cache) > 30:
        oldest = next(iter(_pose_cache))
        del _pose_cache[oldest]
    return landmarks


def apply_body_effect(src: Image.Image, effect: str, gp: float, size: tuple[int, int]) -> Image.Image:
    """Apply body-aware effect. src should be already cropped to target size."""
    from video.media import center_crop, crop_animated
    W, H = size

    bg = crop_animated(src, gp, size) if src.size != size else src
    mask = get_body_mask(bg)

    if effect == "aura":
        return _effect_aura(bg, mask, gp, W, H)
    elif effect == "contour":
        return _effect_contour(bg, mask, gp, W, H)
    elif effect == "wings":
        landmarks = get_pose_landmarks(bg)
        return _effect_wings(bg, mask, landmarks, gp, W, H)
    elif effect == "thermal_aura":
        return _effect_thermal_aura(bg, mask, gp, W, H)
    elif effect == "phantom":
        return _effect_phantom(bg, mask, gp, W, H)
    elif effect == "ghost":
        return _effect_ghost(bg, mask, gp, W, H)
    else:
        return bg


_aura_ring_cache: dict[int, np.ndarray] = {}


def _get_aura_ring(mask: np.ndarray) -> np.ndarray:
    """Pre-compute the aura ring shape from a mask. Cached per mask data."""
    key = id(mask)
    if key in _aura_ring_cache:
        return _aura_ring_cache[key]

    mask_uint8 = (mask * 255).astype(np.uint8)
    mask_pil = Image.fromarray(mask_uint8, "L")
    dilated = mask_pil.filter(ImageFilter.MaxFilter(size=15))
    glow = dilated.filter(ImageFilter.GaussianBlur(radius=25))
    glow_arr = np.array(glow, dtype=np.float32) / 255.0
    ring = np.clip(glow_arr - mask * 0.8, 0, 1)

    _aura_ring_cache[key] = ring
    if len(_aura_ring_cache) > 30:
        oldest = next(iter(_aura_ring_cache))
        del _aura_ring_cache[oldest]
    return ring


def _effect_aura(bg: Image.Image, mask: np.ndarray, gp: float, W: int, H: int) -> Image.Image:
    """Glowing colored aura around the body silhouette."""
    phase = gp * math.pi * 2
    r = int(128 + 127 * math.sin(phase))
    g = int(128 + 127 * math.sin(phase + 2.1))
    b = int(128 + 127 * math.sin(phase + 4.2))

    ring = _get_aura_ring(mask)

    pulse = 0.6 + 0.4 * math.sin(gp * math.pi * 4)

    bg_arr = np.array(bg, dtype=np.float32)
    glow_color = np.array([r, g, b], dtype=np.float32)
    ring_3d = (ring * pulse)[:, :, np.newaxis]
    result = bg_arr + ring_3d * glow_color * 0.8
    result = np.clip(result, 0, 255).astype(np.uint8)
    return Image.fromarray(result)


_contour_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _get_contour_edges(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pre-compute edge and glow arrays from mask. Cached."""
    key = id(mask)
    if key in _contour_cache:
        return _contour_cache[key]

    mask_uint8 = (mask * 255).astype(np.uint8)
    mask_pil = Image.fromarray(mask_uint8, "L")
    dilated = mask_pil.filter(ImageFilter.MaxFilter(size=5))
    eroded = mask_pil.filter(ImageFilter.MinFilter(size=5))
    edge = np.clip(np.array(dilated, dtype=np.int16) - np.array(eroded, dtype=np.int16), 0, 255).astype(np.uint8)
    edge_glow = np.array(Image.fromarray(edge, "L").filter(ImageFilter.GaussianBlur(radius=3)), dtype=np.uint8)

    _contour_cache[key] = (edge, edge_glow)
    if len(_contour_cache) > 30:
        oldest = next(iter(_contour_cache))
        del _contour_cache[oldest]
    return edge, edge_glow


def _effect_contour(bg: Image.Image, mask: np.ndarray, gp: float, W: int, H: int) -> Image.Image:
    """Animated glowing contour line around body edge."""
    edge, edge_glow = _get_contour_edges(mask)

    phase = gp * math.pi * 3
    r = int(128 + 127 * math.sin(phase))
    g = int(200 + 55 * math.sin(phase + 1.5))
    b = int(128 + 127 * math.sin(phase + 3.0))

    # Composite using numpy for speed
    bg_arr = np.array(bg, dtype=np.float32)
    edge_f = edge.astype(np.float32) / 255.0
    glow_f = edge_glow.astype(np.float32) / 255.0 * 0.5
    combined = np.clip(edge_f + glow_f, 0, 1)[:, :, np.newaxis]
    color = np.array([r, g, b], dtype=np.float32)
    result = bg_arr + combined * color
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def _effect_wings(bg: Image.Image, mask: np.ndarray, landmarks: list, gp: float, W: int, H: int) -> Image.Image:
    """Draw animated wings anchored to shoulders."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Shoulder landmarks: 11=left shoulder, 12=right shoulder
    if len(landmarks) < 13 or landmarks[11][2] < 0.3 or landmarks[12][2] < 0.3:
        # No visible shoulders — draw wings at default position
        l_shoulder = (W * 0.35, H * 0.35)
        r_shoulder = (W * 0.65, H * 0.35)
    else:
        l_shoulder = (landmarks[11][0], landmarks[11][1])
        r_shoulder = (landmarks[12][0], landmarks[12][1])

    # Wing animation (flapping)
    flap = math.sin(gp * math.pi * 3) * 0.3 + 0.7  # 0.4 to 1.0
    alpha_base = 160

    # Left wing (extends left and up from left shoulder)
    lx, ly = l_shoulder
    wing_w = int(W * 0.25 * flap)
    wing_h = int(H * 0.3)
    points_l = [
        (int(lx), int(ly)),
        (int(lx - wing_w), int(ly - wing_h * 0.6)),
        (int(lx - wing_w * 0.8), int(ly - wing_h * 0.2)),
        (int(lx - wing_w * 0.6), int(ly + wing_h * 0.3)),
        (int(lx), int(ly + wing_h * 0.2)),
    ]
    d.polygon(points_l, fill=(220, 220, 255, int(alpha_base * flap)))

    # Right wing (mirror)
    rx, ry = r_shoulder
    points_r = [
        (int(rx), int(ry)),
        (int(rx + wing_w), int(ry - wing_h * 0.6)),
        (int(rx + wing_w * 0.8), int(ry - wing_h * 0.2)),
        (int(rx + wing_w * 0.6), int(ry + wing_h * 0.3)),
        (int(rx), int(ry + wing_h * 0.2)),
    ]
    d.polygon(points_r, fill=(220, 220, 255, int(alpha_base * flap)))

    # Wing detail lines
    for pts in [points_l, points_r]:
        if len(pts) >= 3:
            d.line([pts[0], pts[1]], fill=(255, 255, 255, 100), width=2)
            d.line([pts[0], pts[2]], fill=(255, 255, 255, 80), width=1)

    # Soft glow around wings
    overlay_blurred = overlay.filter(ImageFilter.GaussianBlur(radius=8))
    combined = Image.alpha_composite(overlay_blurred, overlay)

    return Image.alpha_composite(bg.convert("RGBA"), combined).convert("RGB")


_thermal_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _get_thermal_rings(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pre-compute inner/outer thermal rings. Cached."""
    key = id(mask)
    if key in _thermal_cache:
        return _thermal_cache[key]

    mask_uint8 = (mask * 255).astype(np.uint8)
    mask_pil = Image.fromarray(mask_uint8, "L")
    arr1 = np.array(mask_pil.filter(ImageFilter.GaussianBlur(radius=15)), dtype=np.float32) / 255.0
    arr2 = np.array(mask_pil.filter(ImageFilter.GaussianBlur(radius=35)), dtype=np.float32) / 255.0
    inner = np.clip(arr1 - mask * 0.9, 0, 1)
    outer = np.clip(arr2 - arr1, 0, 1)

    _thermal_cache[key] = (inner, outer)
    if len(_thermal_cache) > 30:
        oldest = next(iter(_thermal_cache))
        del _thermal_cache[oldest]
    return inner, outer


def _effect_thermal_aura(bg: Image.Image, mask: np.ndarray, gp: float, W: int, H: int) -> Image.Image:
    """Heat-map style aura — warm colors close to body, cool farther out."""
    inner, outer = _get_thermal_rings(mask)

    pulse = 0.7 + 0.3 * math.sin(gp * math.pi * 4)
    bg_arr = np.array(bg, dtype=np.float32)
    bg_arr[:, :, 0] += inner * 200 * pulse
    bg_arr[:, :, 1] += inner * 80 * pulse
    bg_arr[:, :, 2] += outer * 180 * pulse
    bg_arr[:, :, 0] += outer * 60 * pulse

    return Image.fromarray(np.clip(bg_arr, 0, 255).astype(np.uint8))


def _effect_phantom(bg: Image.Image, mask: np.ndarray, gp: float, W: int, H: int) -> Image.Image:
    """Ghost duplicate offset from body — creates phantom/double effect."""
    # Create a semi-transparent shifted copy of the body
    bg_arr = np.array(bg, dtype=np.float32)
    mask_3d = mask[:, :, np.newaxis]

    # Extract body pixels
    body = bg_arr * mask_3d

    # Offset the body (shifts over time)
    dx = int(30 * math.sin(gp * math.pi * 2))
    dy = int(15 * math.cos(gp * math.pi * 2))

    phantom = np.zeros_like(bg_arr)
    # Shift body pixels
    if dy >= 0:
        if dx >= 0:
            phantom[dy:, dx:] = body[:H - dy, :W - dx]
        else:
            phantom[dy:, :W + dx] = body[:H - dy, -dx:]
    else:
        if dx >= 0:
            phantom[:H + dy, dx:] = body[-dy:, :W - dx]
        else:
            phantom[:H + dy, :W + dx] = body[-dy:, -dx:]

    # Tint the phantom blue/purple
    phantom[:, :, 0] *= 0.5
    phantom[:, :, 2] *= 1.3

    # Blend phantom behind
    result = bg_arr + phantom * 0.4
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def _effect_ghost(bg: Image.Image, mask: np.ndarray, gp: float, W: int, H: int) -> Image.Image:
    """Body fades in/out with ethereal transparency."""
    bg_arr = np.array(bg, dtype=np.float32)
    mask_3d = mask[:, :, np.newaxis]

    # Pulsing body transparency
    alpha = 0.3 + 0.5 * abs(math.sin(gp * math.pi * 2))

    # Create darkened background where body is
    darkened_bg = bg_arr * 0.4

    # Body with pulsing alpha
    body = bg_arr * mask_3d
    non_body = bg_arr * (1 - mask_3d)

    # Ghostly tint (slightly blue/white)
    body_tinted = body.copy()
    body_tinted[:, :, 2] = np.clip(body_tinted[:, :, 2] * 1.2, 0, 255)

    result = non_body + body_tinted * alpha + darkened_bg * mask_3d * (1 - alpha)
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def clear_cache():
    """Clear segmentation and pose caches (call between videos)."""
    _mask_cache.clear()
    _pose_cache.clear()
    _aura_ring_cache.clear()
    _contour_cache.clear()
    _thermal_cache.clear()
