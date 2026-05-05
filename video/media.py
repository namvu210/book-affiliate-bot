"""Image and video media processing."""

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from config import get_audio_duration


def extract_cover_from_pdf(pdf_path: str, out_path: str) -> str | None:
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3))
        pix.save(out_path)
        doc.close()
        return out_path
    except Exception:
        return None


def load_image_fill(path: str, size: tuple[int, int]) -> Image.Image:
    """Load image with blurred background fill — no content lost."""
    W, H = size
    img = Image.open(path).convert("RGB")
    tw = int(W * 1.2)
    th = int(H * 1.2)
    bg_scale = max(tw / img.width, th / img.height)
    bg = img.resize((int(img.width * bg_scale), int(img.height * bg_scale)), Image.LANCZOS)
    left = (bg.width - tw) // 2
    top = (bg.height - th) // 2
    bg = bg.crop((left, top, left + tw, top + th))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
    dark = Image.new("RGB", (tw, th), (0, 0, 0))
    bg = Image.blend(bg, dark, 0.3)
    fit_scale = min(W / img.width, H / img.height) * 0.85
    sharp_w = int(img.width * fit_scale)
    sharp_h = int(img.height * fit_scale)
    sharp = img.resize((sharp_w, sharp_h), Image.LANCZOS)
    x = (tw - sharp_w) // 2
    y = (th - sharp_h) // 2
    shadow = Image.new("RGBA", (sharp_w + 16, sharp_h + 16), (0, 0, 0, 80))
    bg.paste(shadow.convert("RGB"), (x + 8, y + 8), shadow)
    bg.paste(sharp, (x, y))
    return bg


def crop_animated(img: Image.Image, progress: float, size: tuple[int, int], zoom_ratio: float = 0.15) -> Image.Image:
    """Ken Burns: slow zoom + pan based on progress (0.0 to 1.0)."""
    W, H = size
    zoom = 1.0 + zoom_ratio * progress
    cw = int(W / zoom)
    ch = int(H / zoom)
    max_x = img.width - cw
    max_y = img.height - ch
    cx = int(max_x * (0.3 + 0.4 * progress))
    cy = int(max_y * (0.4 + 0.2 * math.sin(progress * math.pi)))
    cx = max(0, min(cx, max_x))
    cy = max(0, min(cy, max_y))
    return img.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.LANCZOS)


def center_crop(src, w, h):
    """Crop center of src to target size."""
    if src.width < w or src.height < h:
        src = src.resize((max(w, src.width), max(h, src.height)), Image.LANCZOS)
    return src.crop(((src.width - w) // 2, (src.height - h) // 2, (src.width + w) // 2, (src.height + h) // 2))


def extract_video_frames(video_path: str, max_frames: int = 4) -> list[str]:
    """Extract evenly-spaced frames from a video file as JPEGs."""
    import tempfile
    out_dir = tempfile.mkdtemp()
    dur = get_audio_duration(video_path) or 10
    interval = max(1, dur / (max_frames + 1))
    paths = []
    for i in range(max_frames):
        t = interval * (i + 1)
        out = f"{out_dir}/frame_{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", video_path,
             "-frames:v", "1", "-q:v", "2", out],
            capture_output=True, timeout=15,
        )
        if Path(out).exists():
            paths.append(out)
    return paths


def text_to_logo(text: str, font_size: int = 36, color: str = "#FFFFFF", opacity: int = 180) -> Image.Image:
    """Render text as a transparent RGBA logo image. opacity: 0-255."""
    from video.text import get_font
    font = get_font(font_size, bold=True)
    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(dummy)
    bbox = d.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0] + 20, bbox[3] - bbox[1] + 12
    # Render with transparency
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Parse color
    c = color.lstrip('#')
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    # Shadow
    d.text((11, 7), text, fill=(0, 0, 0, opacity // 2), font=font)
    # Main text with opacity
    d.text((10, 6), text, fill=(r, g, b, opacity), font=font)
    return img


def paste_logo(frame: Image.Image, logo_img: Image.Image, position: str) -> Image.Image:
    """Paste logo onto frame at specified corner."""
    margin = 30
    positions = {
        "top-left": (margin, margin),
        "top-right": (frame.width - logo_img.width - margin, margin),
        "bottom-left": (margin, frame.height - logo_img.height - margin),
        "bottom-right": (frame.width - logo_img.width - margin, frame.height - logo_img.height - margin),
    }
    x, y = positions.get(position, positions["top-right"])
    frame = frame.convert("RGBA")
    frame.paste(logo_img, (x, y), logo_img if logo_img.mode == "RGBA" else None)
    return frame.convert("RGB")
