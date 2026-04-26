"""Generate Reels/TikTok video with karaoke text over product image slideshow."""

import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1080, 1920
ACCENT = (233, 69, 96)
WHITE = (255, 255, 255)


EMOJI_FONT_PATH = str(Path(__file__).parent / "fonts" / "NotoEmoji.ttf")
EMOJI_RE = re.compile(
    r'[\U0001f000-\U0001ffff\U00002702-\U000027B0\U0000fe00-\U0000fe0f'
    r'\U0001fa00-\U0001faff\U00002600-\U000026FF\U0000200d\U00002640'
    r'\U00002642\U00002b50\U00002b55\U00002934-\U00002935'
    r'\U00002b05-\U00002b07\U0000231a-\U0000231b\U000023e9-\U000023fa'
    r'\U000025aa-\U000025fe\U00003030\U0000303d\U00003297\U00003299]+'
)


def _get_font(size: int, bold: bool = False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    if bold:
        paths.insert(0, "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
        paths.insert(1, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for w in words[1:]:
            test = current + " " + w
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                lines.append(current)
                current = w
        lines.append(current)
    return lines


def _split_sentences(text: str) -> list[str]:
    """Split text into short phrases that match natural speech pauses."""
    # First split on sentence endings
    parts = re.split(r'(?<=[.!?。])\s+', text.strip())
    sentences = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Split long segments on commas, colons, dashes, newlines
        if len(p) > 60:
            subs = re.split(r'(?<=[,;:\n])\s+|(?<=\s[-–])\s+', p)
            sentences.extend(s.strip() for s in subs if s.strip())
        else:
            sentences.append(p)
    # Further split any remaining long chunks
    final = []
    for s in sentences:
        if len(s) > 80:
            words = s.split()
            mid = len(words) // 2
            final.append(" ".join(words[:mid]))
            final.append(" ".join(words[mid:]))
        else:
            final.append(s)
    return final or [text]


def _draw_text_with_emoji(draw, xy, text, fill, font, font_size):
    """Draw text with color emoji using pilmoji."""
    try:
        from pilmoji import Pilmoji
        # pilmoji needs the actual Image, not ImageDraw
        # We draw onto the draw's image directly
        img = draw._image
        with Pilmoji(img) as pmj:
            pmj.text(xy, text, fill=fill, font=font)
    except ImportError:
        draw.text(xy, text, fill=fill, font=font)


def _get_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 30.0


def _extract_cover_from_pdf(pdf_path: str, out_path: str) -> str | None:
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3))
        pix.save(out_path)
        doc.close()
        return out_path
    except Exception:
        return None


def _make_bg_from_image(image_path: str) -> Image.Image:
    """Create blurred darkened 9:16 background from an image."""
    try:
        img = Image.open(image_path).convert("RGB")
        scale = max(WIDTH / img.width, HEIGHT / img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        left = (img.width - WIDTH) // 2
        top = (img.height - HEIGHT) // 2
        img = img.crop((left, top, left + WIDTH, top + HEIGHT))
        img = img.filter(ImageFilter.GaussianBlur(radius=25))
        dark = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        return Image.blend(img, dark, 0.45)
    except Exception:
        return Image.new("RGB", (WIDTH, HEIGHT), (15, 15, 35))


def _paste_inset(bg: Image.Image, image_path: str) -> Image.Image:
    """Paste sharp product image centered on top half."""
    img = bg.copy()
    try:
        inset = Image.open(image_path).convert("RGB")
        inset.thumbnail((800, 1200), Image.LANCZOS)
        x = (WIDTH - inset.width) // 2
        y = (HEIGHT - 300 - inset.height) // 2  # center above text area
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [(x - 5, y - 5), (x + inset.width + 5, y + inset.height + 5)],
            fill=WHITE,
        )
        img.paste(inset, (x, y))
    except Exception:
        pass
    return img


def _draw_karaoke(
    bg: Image.Image,
    sentences: list[str],
    active_idx: int,
) -> Image.Image:
    """Draw single active sentence at bottom of frame."""
    img = bg.copy().convert("RGBA")
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    font = _get_font(48, bold=True)
    pad = 60
    text_y = HEIGHT - 260

    text = sentences[active_idx] if active_idx < len(sentences) else ""
    lines = _wrap_text(text, font, WIDTH - pad * 2, odraw)[:3]
    block_h = len(lines) * 58 + 30

    # Dark pill behind text
    odraw.rounded_rectangle(
        [(pad - 20, text_y - 15), (WIDTH - pad + 20, text_y + block_h)],
        radius=20, fill=(0, 0, 0, 160),
    )

    # Composite the dark pill overlay first
    img = Image.alpha_composite(img, overlay)

    # Now draw text with color emoji directly on the composited image
    txt_img = img.convert("RGB")
    y = text_y
    for line in lines:
        # Shadow
        _draw_text_with_emoji(ImageDraw.Draw(txt_img), (pad + 2, y + 2), line,
                              fill=(0, 0, 0), font=font, font_size=48)
        # Main text
        _draw_text_with_emoji(ImageDraw.Draw(txt_img), (pad, y), line,
                              fill=(255, 255, 255), font=font, font_size=48)
        y += 58

    return txt_img


def generate_tiktok_video(
    audio_path: str,
    output_path: str,
    book_title: str = "",
    social_post: str = "",
    hook: str = "",
    key_points: list[str] | None = None,
    cta: str = "",
    cover_image_path: str | None = None,
    media_paths: list[str] | None = None,
) -> str:
    """Generate video with karaoke text over sliding product images."""
    duration = _get_duration(audio_path)

    all_text = ""
    if hook:
        all_text = hook + ". "
    all_text += social_post or ""
    if cta:
        all_text += " " + cta
    sentences = _split_sentences(all_text)

    # Proportional timing: longer sentences get more time
    word_counts = [max(1, len(s.split())) for s in sentences]
    total_words = sum(word_counts)
    sentence_durations = [(wc / total_words) * duration for wc in word_counts]

    # Determine image sources: uploaded media > PDF cover > fallback
    images = []
    if media_paths:
        images = [p for p in media_paths if Path(p).exists() and not p.endswith(".mp4")]
    if not images and cover_image_path and Path(cover_image_path).exists():
        images = [cover_image_path]

    # If we have multiple images, rotate them across sentences
    # Each image shows for (total_sentences / num_images) sentences
    if not images:
        images = [None]  # fallback dark bg

    # Pre-render backgrounds for each image
    bgs = []
    for img_path in images:
        if img_path:
            bg = _make_bg_from_image(img_path)
            bgs.append(_paste_inset(bg, img_path))
        else:
            bgs.append(Image.new("RGB", (WIDTH, HEIGHT), (15, 15, 35)))

    # Handle video files separately — splice them in later
    video_paths = [p for p in (media_paths or []) if p.endswith(".mp4") and Path(p).exists()]

    with tempfile.TemporaryDirectory() as tmpdir:
        concat_lines = []
        sentences_per_image = max(1, len(sentences) // len(bgs))

        for i, sent in enumerate(sentences):
            bg_idx = min(i // sentences_per_image, len(bgs) - 1)
            frame_path = f"{tmpdir}/frame_{i:04d}.png"
            frame = _draw_karaoke(bgs[bg_idx], sentences, i)
            frame.save(frame_path, quality=95)
            concat_lines.append(f"file '{frame_path}'")
            concat_lines.append(f"duration {sentence_durations[i]:.4f}")

        concat_lines.append(f"file '{tmpdir}/frame_{len(sentences)-1:04d}.png'")

        concat_file = f"{tmpdir}/concat.txt"
        Path(concat_file).write_text("\n".join(concat_lines))

        proc = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-i", audio_path,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                output_path,
            ],
            capture_output=True, timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[-800:]}")

    return output_path
