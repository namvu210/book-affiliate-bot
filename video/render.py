"""Video rendering pipeline — hybrid PIL effects + ffmpeg animation."""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from config import strip_emoji, get_audio_duration
from video.text import get_font, wrap_text, split_sentences
from video.media import load_image_fill, extract_video_frames, paste_logo
from video.effects import apply_effect, draw_word_highlight_frame

MUSIC_DIR = Path(__file__).parent.parent / "music"

# Effects that ffmpeg zoompan can handle natively (no per-frame PIL needed)
_FFMPEG_MOTION = {"ken_burns", "slide_lr", "slide_ud", "zoom_center", "bounce_zoom", "none"}
# Style effects that can be applied once to a static image
_STATIC_STYLES = {"grayscale", "sepia", "saturation", "contrast", "color_tint",
                  "color_pop", "vignette", "soft_glow", "mirror", "brightness",
                  "darken", "blur_bg", "none"}


def _can_use_ffmpeg_pipeline(img_effect: str, img_style: str) -> bool:
    """Check if this effect combo can use the fast ffmpeg path."""
    return img_effect in _FFMPEG_MOTION and img_style in _STATIC_STYLES


def generate_srt(text: str, audio_path: str, srt_path: str, intro_offset: float = 0.0):
    """Generate SRT subtitle file from text, timed to audio duration."""
    dur = get_audio_duration(audio_path) or 30
    sentences = split_sentences(text)
    char_counts = [max(1, len(s)) for s in sentences]
    total_chars = sum(char_counts)
    with open(srt_path, "w") as f:
        t = intro_offset
        for i, s in enumerate(sentences):
            sd = (char_counts[i] / total_chars) * dur
            h1, m1, s1 = int(t // 3600), int(t % 3600 // 60), t % 60
            t2 = t + sd
            h2, m2, s2 = int(t2 // 3600), int(t2 % 3600 // 60), t2 % 60
            f.write(f"{i+1}\n{h1:02d}:{m1:02d}:{s1:06.3f} --> {h2:02d}:{m2:02d}:{s2:06.3f}\n{s}\n\n")
            t = t2


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
    aspect_ratio: str = "9:16",
    logo_path: str | None = None,
    logo_position: str = "top-right",
    subtitle_style: str = "tiktok",
    highlight_color: str = "#FFD700",
    img_effect: str = "ken_burns",
    img_style: str = "none",
    zoom_ratio: float = 0.15,
    show_intro: bool = True,
    show_outro: bool = True,
    preview_only: bool = False,
    intro_bg_path: str | None = None,
    outro_bg_path: str | None = None,
    persona_name: str = "",
) -> str:
    """Generate video with animated bg, word-by-word highlight, and optional music."""
    ASPECT_MAP = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
    size = ASPECT_MAP.get(aspect_ratio, (1080, 1920))
    W, H = size
    duration = get_audio_duration(audio_path) or 30.0
    fps = 24

    sentences = split_sentences(social_post or "")
    char_counts = [max(1, len(s)) for s in sentences]
    total_chars = sum(char_counts)
    subtitle_duration = duration * 0.95
    sentence_durations = [(cc / total_chars) * subtitle_duration for cc in char_counts]

    # Load logo
    logo_img = None
    if logo_path and Path(logo_path).exists():
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_img.thumbnail((W // 6, W // 6), Image.LANCZOS)
        except Exception:
            logo_img = None

    # Load images
    images = []
    if media_paths:
        for p in media_paths:
            if not Path(p).exists():
                continue
            if p.endswith(".mp4"):
                images.extend(extract_video_frames(p))
            else:
                images.append(p)
    if not images and cover_image_path and Path(cover_image_path).exists():
        images = [cover_image_path]
    if not images:
        images = [None]

    loaded_imgs = []
    for p in images:
        if p:
            try:
                loaded_imgs.append(load_image_fill(p, size))
            except Exception:
                loaded_imgs.append(Image.new("RGB", (W * 2, H * 2), (15, 15, 35)))
        else:
            loaded_imgs.append(Image.new("RGB", (W * 2, H * 2), (15, 15, 35)))

    with tempfile.TemporaryDirectory() as tmpdir:
        return _render_pil_pipeline(
            tmpdir, output_path, audio_path, music_file, music_volume,
            loaded_imgs, sentences, sentence_durations, char_counts, total_chars,
            duration, fps, size, img_effect, img_style, zoom_ratio,
            subtitle_style, highlight_color, logo_img, logo_position,
            book_title, cta, show_intro, show_outro, intro_bg_path, outro_bg_path, persona_name,
            preview_only, hook,
        )


def _render_pil_pipeline(
    tmpdir, output_path, audio_path, music_file, music_volume,
    loaded_imgs, sentences, sentence_durations, char_counts, total_chars,
    duration, fps, size, img_effect, img_style, zoom_ratio,
    subtitle_style, highlight_color, logo_img, logo_position,
    book_title, cta, show_intro, show_outro, intro_bg_path, outro_bg_path, persona_name="",
    preview_only=False, hook="",
) -> str:
    """PIL frame-by-frame pipeline — pipes frames directly to ffmpeg (no temp files)."""
    W, H = size
    intro_frames = int(2 * fps) if show_intro and book_title else 0
    outro_frames = int(2 * fps) if show_outro and cta else 0
    content_frames = int(duration * fps)

    # For preview, just render one frame and return
    if preview_only:
        if loaded_imgs:
            src = loaded_imgs[0]
            bg = apply_effect(src, img_effect, 0.0, 0.0, loaded_imgs, 0, size, zoom_ratio)
            if img_style != "none":
                bg = apply_effect(bg, img_style, 0.0, 0.0, loaded_imgs, 0, size, zoom_ratio)
            if sentences:
                bg = draw_word_highlight_frame(bg, sentences[0], 0.5, size, subtitle_style, highlight_color)
            if logo_img:
                bg = paste_logo(bg, logo_img, logo_position)
            preview_path = output_path.replace(".mp4", "").rsplit("_", 1)[0] + "_preview.png"
            bg.save(preview_path, quality=95)
        return output_path

    # Build raw video via pipe, then mux with audio
    raw_video = f"{tmpdir}/raw.mp4"
    ffmpeg_proc = subprocess.Popen([
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
        raw_video,
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    # Intro
    if intro_frames > 0:
        first_bg = None
        if loaded_imgs:
            p = f"{tmpdir}/intro_bg.png"
            loaded_imgs[0].save(p, quality=95)
            first_bg = p
        intro_img = _make_slide(first_bg or intro_bg_path, W, H, (15, 15, 35))
        d = ImageDraw.Draw(intro_img)
        # Hook as main text (bold, attention-grabbing)
        intro_text = hook or book_title
        tf = get_font(56, bold=True)
        main_lines = wrap_text(strip_emoji(intro_text), tf, W - 120, d)[:3]
        # Product title as subtitle (if hook is used, show title below)
        sub_lines = []
        if hook and book_title:
            sf = get_font(32)
            sub_lines = wrap_text(strip_emoji(book_title), sf, W - 120, d)[:2]
        elif persona_name:
            sf = get_font(36)
            sub_lines = wrap_text(strip_emoji(persona_name), sf, W - 120, d)[:2]
        total_h = len(main_lines) * 72 + (len(sub_lines) * 44 + 16 if sub_lines else 0)
        y = (H - total_h) // 2
        for line in main_lines:
            bbox = d.textbbox((0, 0), line, font=tf)
            d.text(((W - bbox[2] + bbox[0]) // 2, y), line, fill=(255, 255, 255), font=tf)
            y += 72
        if sub_lines:
            sf = get_font(32) if hook else get_font(36)
            y += 16
            for line in sub_lines:
                bbox = d.textbbox((0, 0), line, font=sf)
                d.text(((W - bbox[2] + bbox[0]) // 2, y), line, fill=(255, 220, 100), font=sf)
                y += 44
        if logo_img:
            intro_img = paste_logo(intro_img, logo_img, logo_position)
        raw = intro_img.convert("RGB").tobytes()
        for _ in range(intro_frames):
            ffmpeg_proc.stdin.write(raw)

    # Content
    int_frames = [max(1, round((cc / total_chars) * content_frames)) for cc in char_counts]
    diff = content_frames - sum(int_frames)
    if diff != 0 and int_frames:
        int_frames[max(range(len(int_frames)), key=lambda i: int_frames[i])] += diff

    time_elapsed = 0.0
    use_cache = img_effect == "none" and img_style in ("none", "")
    prev_cache_key = None
    prev_frame_bytes = None
    for sent_idx, sentence in enumerate(sentences):
        sent_frames = int_frames[sent_idx] if sent_idx < len(int_frames) else 1
        img_idx = min(int(time_elapsed / (duration / len(loaded_imgs))), len(loaded_imgs) - 1)

        for f in range(sent_frames):
            gp = min(1.0, (time_elapsed + f / fps) / duration)
            lp = f / sent_frames
            wp = f / max(1, sent_frames - 1)
            clean_words = strip_emoji(sentence).split()
            hi = int(wp * len(clean_words)) if clean_words else 0
            cache_key = (sent_idx, img_idx, hi)

            if use_cache and cache_key == prev_cache_key and prev_frame_bytes:
                ffmpeg_proc.stdin.write(prev_frame_bytes)
            else:
                src = loaded_imgs[img_idx]
                bg = apply_effect(src, img_effect, gp, lp, loaded_imgs, img_idx, size, zoom_ratio)
                if img_style != "none":
                    bg = apply_effect(bg, img_style, gp, lp, loaded_imgs, img_idx, size, zoom_ratio)
                frame = draw_word_highlight_frame(bg, sentence, wp, size, subtitle_style, highlight_color)
                if logo_img:
                    frame = paste_logo(frame, logo_img, logo_position)
                if frame.size != (W, H):
                    frame = frame.resize((W, H), Image.LANCZOS)
                if frame.mode != "RGB":
                    frame = frame.convert("RGB")
                prev_frame_bytes = frame.tobytes()
                prev_cache_key = cache_key
                ffmpeg_proc.stdin.write(prev_frame_bytes)
        time_elapsed += sentence_durations[sent_idx]

    # Outro
    if outro_frames > 0:
        last_bg = None
        if loaded_imgs:
            p = f"{tmpdir}/outro_bg.png"
            loaded_imgs[-1].save(p, quality=95)
            last_bg = p
        outro_img = _make_slide(last_bg or outro_bg_path, W, H, (233, 69, 96))
        d = ImageDraw.Draw(outro_img)
        tf = get_font(48, bold=True)
        lines = wrap_text(strip_emoji(cta), tf, W - 120, d)[:4]
        y = (H - len(lines) * 64) // 2
        for line in lines:
            bbox = d.textbbox((0, 0), line, font=tf)
            d.text(((W - bbox[2] + bbox[0]) // 2, y), line, fill=(255, 255, 255), font=tf)
            y += 64
        if logo_img:
            outro_img = paste_logo(outro_img, logo_img, logo_position)
        raw = outro_img.convert("RGB").tobytes()
        for _ in range(outro_frames):
            ffmpeg_proc.stdin.write(raw)

    ffmpeg_proc.stdin.close()
    _, stderr = ffmpeg_proc.communicate(timeout=300)
    if ffmpeg_proc.returncode != 0:
        raise RuntimeError(f"ffmpeg pipe failed: {stderr.decode()[-800:]}")

    # Mux with audio
    intro_delay_ms = int((intro_frames / fps) * 1000) if intro_frames > 0 else 0
    cmd = ["ffmpeg", "-y", "-i", raw_video, "-i", audio_path]
    if music_file and Path(music_file).exists():
        cmd.extend(["-i", music_file])
        vf = f"[1:a]adelay={intro_delay_ms}|{intro_delay_ms},volume=1.0[voice]" if intro_delay_ms else "[1:a]volume=1.0[voice]"
        cmd.extend(["-filter_complex", f"{vf};[2:a]volume={music_volume:.2f}[music];[voice][music]amix=inputs=2:duration=shortest[a]", "-map", "0:v", "-map", "[a]"])
    elif intro_delay_ms:
        cmd.extend(["-filter_complex", f"[1:a]adelay={intro_delay_ms}|{intro_delay_ms}[a]", "-map", "0:v", "-map", "[a]"])
    else:
        cmd.extend(["-map", "0:v", "-map", "1:a"])
    cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", output_path])
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed: {proc.stderr.decode()[-800:]}")
    return output_path



def _generate_timed_srt(sentences, sentence_durations, srt_path, intro_offset=0.0):
    """Generate SRT with timing from sentence durations."""
    with open(srt_path, "w") as f:
        t = intro_offset
        for i, s in enumerate(sentences):
            sd = sentence_durations[i] if i < len(sentence_durations) else 2.0
            h1, m1, s1 = int(t // 3600), int(t % 3600 // 60), t % 60
            t2 = t + sd
            h2, m2, s2 = int(t2 // 3600), int(t2 % 3600 // 60), t2 % 60
            f.write(f"{i+1}\n{h1:02d}:{m1:02d}:{s1:06.3f} --> {h2:02d}:{m2:02d}:{s2:06.3f}\n{s}\n\n")
            t = t2


def _build_drawtext_filters(sentences, sentence_durations, w, h, intro_offset, highlight_color):
    """Build ffmpeg drawtext filter chain for timed subtitles."""
    font_path = ""
    for p in ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(p).exists():
            font_path = p
            break
    if not font_path:
        return ""

    hc = highlight_color.lstrip('#')
    r, g, b = int(hc[0:2], 16), int(hc[2:4], 16), int(hc[4:6], 16)
    color = f"0x{r:02x}{g:02x}{b:02x}"

    parts = []
    t = intro_offset
    escaped_font = font_path.replace(":", "\\\\:")
    for i, s in enumerate(sentences):
        sd = sentence_durations[i] if i < len(sentence_durations) else 2.0
        # Escape special chars for ffmpeg drawtext
        text = strip_emoji(s).replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
        if not text.strip():
            t += sd
            continue
        parts.append(
            f"drawtext=fontfile='{escaped_font}':text='{text}'"
            f":fontsize=42:fontcolor=white:borderw=3:bordercolor=black"
            f":x=(w-text_w)/2:y=h-100"
            f":enable='between(t,{t:.3f},{t + sd:.3f})'"
        )
        t += sd

    return ",".join(parts) if parts else ""


def _make_slide(bg_path: str | None, w: int, h: int, default_color: tuple) -> Image.Image:
    """Create a slide background from an image or solid color."""
    if bg_path and Path(bg_path).exists():
        try:
            from PIL import ImageEnhance
            ib = Image.open(bg_path).convert("RGB")
            scale = max(w / ib.width, h / ib.height)
            ib = ib.resize((int(ib.width * scale), int(ib.height * scale)), Image.LANCZOS)
            left, top = (ib.width - w) // 2, (ib.height - h) // 2
            img = ib.crop((left, top, left + w, top + h))
            return ImageEnhance.Brightness(img).enhance(0.5)
        except Exception:
            pass
    return Image.new("RGB", (w, h), default_color)


def list_music() -> list[dict]:
    """List available background music files."""
    MUSIC_DIR.mkdir(exist_ok=True)
    tracks = []
    for f in sorted(MUSIC_DIR.glob("*.mp3")):
        name = f.stem.replace("-", " ").replace("_", " ").title()
        tracks.append({"name": name, "file": str(f), "url": f"/music/{f.name}"})
    return tracks
