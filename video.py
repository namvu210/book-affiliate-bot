"""Generate TikTok/Reels video with animated bg, word-by-word highlight, and music."""

import math
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1080, 1920
MUSIC_DIR = Path(__file__).parent / "music"

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
    parts = re.split(r'(?<=[.!?。])\s+', text.strip())
    sentences = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) > 60:
            subs = re.split(r'(?<=[,;:\n])\s+|(?<=\s[-–])\s+', p)
            sentences.extend(s.strip() for s in subs if s.strip())
        else:
            sentences.append(p)
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


def _strip_emoji(text: str) -> str:
    return EMOJI_RE.sub('', text).strip()


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


def _load_image_fill(path: str) -> Image.Image:
    """Load image and resize to fill 9:16."""
    img = Image.open(path).convert("RGB")
    scale = max(WIDTH / img.width, HEIGHT / img.height)
    img = img.resize((int(img.width * scale * 1.3), int(img.height * scale * 1.3)), Image.LANCZOS)
    return img


def _crop_animated(img: Image.Image, progress: float) -> Image.Image:
    """Ken Burns: slow zoom + pan based on progress (0.0 to 1.0)."""
    # Zoom from 1.0x to 1.15x
    zoom = 1.0 + 0.15 * progress
    cw = int(WIDTH / zoom)
    ch = int(HEIGHT / zoom)
    # Pan: drift from center-left to center-right
    max_x = img.width - cw
    max_y = img.height - ch
    cx = int(max_x * (0.3 + 0.4 * progress))
    cy = int(max_y * (0.4 + 0.2 * math.sin(progress * math.pi)))
    cx = max(0, min(cx, max_x))
    cy = max(0, min(cy, max_y))
    return img.crop((cx, cy, cx + cw, cy + ch)).resize((WIDTH, HEIGHT), Image.LANCZOS)


def _draw_word_highlight_frame(
    bg: Image.Image,
    sentence: str,
    word_progress: float,
    subtitle_style: str = "tiktok",
    highlight_color: str = "#FFD700",
) -> Image.Image:
    """Draw sentence at bottom with configurable style."""
    img = bg.copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    font = _get_font(52, bold=True)
    pad = 50

    clean = _strip_emoji(sentence)
    words = clean.split()
    if not words:
        return img

    lines = _wrap_text(clean, font, WIDTH - pad * 2, odraw)[:3]
    line_height = 68
    block_h = len(lines) * line_height + 30
    text_y = HEIGHT - block_h - 80

    # Parse highlight color
    hc = tuple(int(highlight_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    # Background style
    if subtitle_style == "news":
        odraw.rectangle([(0, text_y - 15), (WIDTH, text_y + block_h)], fill=(0, 0, 0, 200))
    elif subtitle_style != "minimal":
        odraw.rounded_rectangle([(pad - 20, text_y - 15), (WIDTH - pad + 20, text_y + block_h)], radius=24, fill=(0, 0, 0, 150))

    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    total_words = len(words)
    highlight_idx = int(word_progress * total_words)

    word_counter = 0
    y = text_y
    for line in lines:
        line_words = line.split()
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w = line_bbox[2] - line_bbox[0]
        x = (WIDTH - line_w) // 2

        for w in line_words:
            w_bbox = draw.textbbox((0, 0), w, font=font)
            w_w = w_bbox[2] - w_bbox[0]

            if word_counter <= highlight_idx:
                if subtitle_style == "tiktok":
                    for dx in [-2, -1, 0, 1, 2]:
                        for dy in [-2, -1, 0, 1, 2]:
                            if dx == 0 and dy == 0: continue
                            draw.text((x + dx, y + dy), w, fill=hc, font=font)
                    draw.text((x, y), w, fill=(255, 255, 255), font=font)
                elif subtitle_style == "karaoke":
                    draw.text((x, y), w, fill=hc, font=font)
                elif subtitle_style == "news":
                    draw.text((x, y), w, fill=(255, 255, 255), font=font)
                else:  # minimal
                    draw.text((x, y), w, fill=(255, 255, 255), font=font)
            else:
                if subtitle_style == "tiktok":
                    for dx in [-2, -1, 0, 1, 2]:
                        for dy in [-2, -1, 0, 1, 2]:
                            if dx == 0 and dy == 0: continue
                            draw.text((x + dx, y + dy), w, fill=(0, 0, 0), font=font)
                    draw.text((x, y), w, fill=(160, 160, 170), font=font)
                elif subtitle_style == "karaoke":
                    draw.text((x, y), w, fill=(180, 180, 180), font=font)
                elif subtitle_style == "news":
                    draw.text((x, y), w, fill=(200, 200, 200), font=font)
                else:
                    draw.text((x, y), w, fill=(200, 200, 200, 180), font=font)

            sp_bbox = draw.textbbox((0, 0), " ", font=font)
            x += w_w + (sp_bbox[2] - sp_bbox[0])
            word_counter += 1

        y += line_height

    return img.convert("RGB")


def _center_crop(src, w=None, h=None):
    """Crop center of src to WIDTHxHEIGHT."""
    w = w or WIDTH
    h = h or HEIGHT
    return src.crop(((src.width-w)//2, (src.height-h)//2, (src.width+w)//2, (src.height+h)//2)).resize((w, h), Image.LANCZOS)


def _apply_effect(src, effect, gp, lp, all_imgs, img_idx):
    """Apply image effect. gp=global progress 0-1, lp=local progress 0-1."""
    from PIL import ImageEnhance, ImageOps

    if effect == "ken_burns":
        return _crop_animated(src, gp)

    elif effect == "slide_lr":
        max_x = src.width - WIDTH
        x = int(max_x * gp)
        y = (src.height - HEIGHT) // 2
        return src.crop((x, y, x + WIDTH, y + HEIGHT))

    elif effect == "slide_ud":
        x = (src.width - WIDTH) // 2
        max_y = src.height - HEIGHT
        y = int(max_y * gp)
        return src.crop((x, y, x + WIDTH, y + HEIGHT))

    elif effect == "bounce_zoom":
        z = 1.0 + 0.1 * math.sin(gp * math.pi * 4)
        cw, ch = int(WIDTH / z), int(HEIGHT / z)
        cx = (src.width - cw) // 2
        cy = (src.height - ch) // 2
        return src.crop((cx, cy, cx + cw, cy + ch)).resize((WIDTH, HEIGHT), Image.LANCZOS)

    elif effect == "grayscale":
        bg = _crop_animated(src, gp)
        return ImageOps.grayscale(bg).convert("RGB")

    elif effect == "sepia":
        bg = _crop_animated(src, gp)
        gray = ImageOps.grayscale(bg)
        r = gray.point(lambda p: min(255, int(p * 1.2)))
        g = gray.point(lambda p: min(255, int(p * 1.0)))
        b = gray.point(lambda p: min(255, int(p * 0.8)))
        return Image.merge("RGB", (r, g, b))

    elif effect == "saturation":
        bg = _crop_animated(src, gp)
        return ImageEnhance.Color(bg).enhance(1.8)

    elif effect == "contrast":
        bg = _crop_animated(src, gp)
        return ImageEnhance.Contrast(bg).enhance(1.5)

    elif effect == "color_tint":
        bg = _crop_animated(src, gp)
        tint = Image.new("RGB", bg.size, (255, 200, 150))
        return Image.blend(bg, tint, 0.15)

    elif effect == "color_pop":
        bg = _crop_animated(src, gp)
        import colorsys
        gray = ImageOps.grayscale(bg)
        pixels = bg.load()
        gray_px = gray.load()
        result = bg.copy()
        rp = result.load()
        for y in range(bg.height):
            for x in range(bg.width):
                r, g, b = pixels[x, y]
                h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
                if not (0.95 < h or h < 0.1) or s < 0.4:  # keep red-ish, desaturate rest
                    rp[x, y] = (gray_px[x, y], gray_px[x, y], gray_px[x, y])
        return result

    elif effect == "vignette":
        bg = _crop_animated(src, gp)
        vig = Image.new("L", (WIDTH, HEIGHT), 0)
        d = ImageDraw.Draw(vig)
        for i in range(40):
            alpha = int(255 * (i / 40))
            margin = i * max(WIDTH, HEIGHT) // 80
            d.ellipse([(margin, margin), (WIDTH - margin, HEIGHT - margin)], fill=alpha)
        bg = bg.convert("RGB")
        vig_rgb = Image.merge("RGB", (vig, vig, vig))
        return Image.composite(bg, Image.new("RGB", bg.size, (0, 0, 0)), vig)

    elif effect == "soft_glow":
        bg = _crop_animated(src, gp)
        glow = bg.filter(ImageFilter.GaussianBlur(radius=15))
        return Image.blend(bg, glow, 0.3)

    elif effect == "mirror":
        bg = _crop_animated(src, gp)
        return ImageOps.mirror(bg)

    elif effect == "pixelate_reveal":
        bg = _crop_animated(src, gp)
        pix = max(1, int(32 * (1 - gp)))
        small = bg.resize((WIDTH // pix, HEIGHT // pix), Image.NEAREST)
        return small.resize((WIDTH, HEIGHT), Image.NEAREST)

    elif effect == "split_screen":
        half_w = WIDTH // 2
        idx2 = (img_idx + 1) % len(all_imgs)
        left = _center_crop(all_imgs[img_idx], half_w, HEIGHT)
        right = _center_crop(all_imgs[idx2], half_w, HEIGHT)
        combined = Image.new("RGB", (WIDTH, HEIGHT))
        combined.paste(left, (0, 0))
        combined.paste(right, (half_w, 0))
        return combined

    elif effect == "blur_bg":
        bg = _center_crop(src)
        return bg.filter(ImageFilter.GaussianBlur(radius=8))

    elif effect == "brightness":
        bg = _crop_animated(src, gp)
        return ImageEnhance.Brightness(bg).enhance(1.3)

    elif effect == "darken":
        bg = _crop_animated(src, gp)
        return ImageEnhance.Brightness(bg).enhance(0.7)

    else:  # none
        return _center_crop(src)


def _paste_logo(frame: Image.Image, logo_img: Image.Image, position: str) -> Image.Image:
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
    music_file: str | None = None,
    music_volume: float = 0.15,
    max_duration: int = 30,
    aspect_ratio: str = "9:16",
    img_transition: int = 3,
    logo_path: str | None = None,
    logo_position: str = "top-right",
    subtitle_style: str = "tiktok",
    highlight_color: str = "#FFD700",
    img_effect: str = "ken_burns",
    show_intro: bool = True,
    show_outro: bool = True,
    preview_only: bool = False,
    intro_bg_path: str | None = None,
    outro_bg_path: str | None = None,
) -> str:
    """Generate video with animated bg, word-by-word highlight, and optional music."""
    # Set dimensions based on aspect ratio
    ASPECT_MAP = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
    w, h = ASPECT_MAP.get(aspect_ratio, (1080, 1920))

    global WIDTH, HEIGHT
    WIDTH, HEIGHT = w, h

    duration = _get_duration(audio_path)
    # Cap audio to max_duration
    if duration and duration > max_duration:
        tmp_fast = audio_path + ".capped.mp3"
        tempo = duration / max_duration
        filters = []
        t = tempo
        while t > 2.0:
            filters.append("atempo=2.0")
            t /= 2.0
        filters.append(f"atempo={t:.4f}")
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-filter:a", ",".join(filters), tmp_fast],
            capture_output=True, timeout=30,
        )
        if Path(tmp_fast).exists():
            Path(tmp_fast).replace(audio_path)
        duration = _get_duration(audio_path) or max_duration

    fps = 10

    all_text = social_post or ""
    sentences = _split_sentences(all_text)

    # Proportional timing: use character count (better for Vietnamese than word count)
    char_counts = [max(1, len(s)) for s in sentences]
    total_chars = sum(char_counts)
    sentence_durations = [(cc / total_chars) * duration for cc in char_counts]

    # Load logo
    logo_img = None
    if logo_path and Path(logo_path).exists():
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            max_logo = WIDTH // 6
            logo_img.thumbnail((max_logo, max_logo), Image.LANCZOS)
        except Exception:
            logo_img = None

    # Load images
    images = []
    if media_paths:
        images = [p for p in media_paths if Path(p).exists() and not p.endswith(".mp4")]
    if not images and cover_image_path and Path(cover_image_path).exists():
        images = [cover_image_path]
    if not images:
        images = [None]

    # Pre-load full-size images for Ken Burns
    loaded_imgs = []
    for p in images:
        if p:
            try:
                loaded_imgs.append(_load_image_fill(p))
            except Exception:
                loaded_imgs.append(Image.new("RGB", (WIDTH * 2, HEIGHT * 2), (15, 15, 35)))
        else:
            loaded_imgs.append(Image.new("RGB", (WIDTH * 2, HEIGHT * 2), (15, 15, 35)))

    total_frames = int(duration * fps)

    # Intro/outro frames (2 seconds each)
    intro_frames = int(2 * fps) if show_intro and book_title else 0
    outro_frames = int(2 * fps) if show_outro and cta else 0
    content_frames = total_frames - intro_frames - outro_frames

    with tempfile.TemporaryDirectory() as tmpdir:
        frame_idx = 0

        # Intro slide
        if intro_frames > 0:
            if intro_bg_path and Path(intro_bg_path).exists():
                try:
                    ib = Image.open(intro_bg_path).convert("RGB")
                    scale = max(WIDTH / ib.width, HEIGHT / ib.height)
                    ib = ib.resize((int(ib.width * scale), int(ib.height * scale)), Image.LANCZOS)
                    left, top = (ib.width - WIDTH) // 2, (ib.height - HEIGHT) // 2
                    intro_img = ib.crop((left, top, left + WIDTH, top + HEIGHT))
                    from PIL import ImageEnhance
                    intro_img = ImageEnhance.Brightness(intro_img).enhance(0.5)
                except Exception:
                    intro_img = Image.new("RGB", (WIDTH, HEIGHT), (15, 15, 35))
            else:
                intro_img = Image.new("RGB", (WIDTH, HEIGHT), (15, 15, 35))
            d = ImageDraw.Draw(intro_img)
            tf = _get_font(60, bold=True)
            lines = _wrap_text(_strip_emoji(book_title), tf, WIDTH - 120, d)[:4]
            y = (HEIGHT - len(lines) * 76) // 2
            for line in lines:
                bbox = d.textbbox((0, 0), line, font=tf)
                d.text(((WIDTH - bbox[2] + bbox[0]) // 2, y), line, fill=(255, 255, 255), font=tf)
                y += 76
            if logo_img:
                intro_img = _paste_logo(intro_img, logo_img, logo_position)
            for _ in range(intro_frames):
                p = f"{tmpdir}/frame_{frame_idx:05d}.png"
                intro_img.save(p, quality=90)
                frame_idx += 1

        # Content frames
        int_frames = [max(1, round((cc / total_chars) * content_frames)) for cc in char_counts]
        diff = content_frames - sum(int_frames)
        if diff != 0 and int_frames:
            longest = max(range(len(int_frames)), key=lambda i: int_frames[i])
            int_frames[longest] += diff

        time_elapsed = 0.0
        for sent_idx, sentence in enumerate(sentences):
            sent_dur = sentence_durations[sent_idx]
            sent_frames = int_frames[sent_idx] if sent_idx < len(int_frames) else 1
            img_idx = int((time_elapsed) / img_transition) % len(loaded_imgs)

            for f in range(sent_frames):
                global_progress = min(1.0, (time_elapsed + f / fps) / duration)
                local_progress = f / sent_frames
                src = loaded_imgs[img_idx]
                bg = _apply_effect(src, img_effect, global_progress, local_progress, loaded_imgs, img_idx)

                word_prog = f / sent_frames
                frame = _draw_word_highlight_frame(bg, sentence, word_prog, subtitle_style, highlight_color)
                if logo_img:
                    frame = _paste_logo(frame, logo_img, logo_position)

                # Preview: save first content frame and return early
                if preview_only and frame_idx == intro_frames:
                    preview_path = output_path.replace(".mp4", "").rsplit("_", 1)[0] + "_preview.png"
                    frame.save(preview_path, quality=95)
                    return output_path

                frame_path = f"{tmpdir}/frame_{frame_idx:05d}.png"
                frame.save(frame_path, quality=90)
                frame_idx += 1

            time_elapsed += sent_dur

        # Outro slide
        if outro_frames > 0:
            if outro_bg_path and Path(outro_bg_path).exists():
                try:
                    ob = Image.open(outro_bg_path).convert("RGB")
                    scale = max(WIDTH / ob.width, HEIGHT / ob.height)
                    ob = ob.resize((int(ob.width * scale), int(ob.height * scale)), Image.LANCZOS)
                    left, top = (ob.width - WIDTH) // 2, (ob.height - HEIGHT) // 2
                    outro_img = ob.crop((left, top, left + WIDTH, top + HEIGHT))
                    from PIL import ImageEnhance
                    outro_img = ImageEnhance.Brightness(outro_img).enhance(0.5)
                except Exception:
                    outro_img = Image.new("RGB", (WIDTH, HEIGHT), (233, 69, 96))
            else:
                outro_img = Image.new("RGB", (WIDTH, HEIGHT), (233, 69, 96))
            d = ImageDraw.Draw(outro_img)
            tf = _get_font(48, bold=True)
            cta_clean = _strip_emoji(cta)
            lines = _wrap_text(cta_clean, tf, WIDTH - 120, d)[:4]
            y = (HEIGHT - len(lines) * 64) // 2
            for line in lines:
                bbox = d.textbbox((0, 0), line, font=tf)
                d.text(((WIDTH - bbox[2] + bbox[0]) // 2, y), line, fill=(255, 255, 255), font=tf)
                y += 64
            if logo_img:
                outro_img = _paste_logo(outro_img, logo_img, logo_position)
            for _ in range(outro_frames):
                p = f"{tmpdir}/frame_{frame_idx:05d}.png"
                outro_img.save(p, quality=90)
                frame_idx += 1

        # Build video from frames + audio
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", f"{tmpdir}/frame_%05d.png",
            "-i", audio_path,
        ]

        # Add background music if selected
        if music_file and Path(music_file).exists():
            cmd.extend(["-i", music_file])
            # Mix voice (louder) + music (quieter)
            cmd.extend([
                "-filter_complex",
                f"[1:a]volume=1.0[voice];[2:a]volume={music_volume:.2f}[music];[voice][music]amix=inputs=2:duration=shortest[a]",
                "-map", "0:v", "-map", "[a]",
            ])
        else:
            cmd.extend(["-map", "0:v", "-map", "1:a"])

        cmd.extend([
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ])

        proc = subprocess.run(cmd, capture_output=True, timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[-800:]}")

    return output_path


def list_music() -> list[dict]:
    """List available background music files."""
    MUSIC_DIR.mkdir(exist_ok=True)
    tracks = []
    for f in sorted(MUSIC_DIR.glob("*.mp3")):
        name = f.stem.replace("-", " ").replace("_", " ").title()
        tracks.append({"name": name, "file": str(f), "url": f"/music/{f.name}"})
    return tracks
