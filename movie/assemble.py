"""Movie Ad assembly — intro + body video + outro + audio mix + marketing overlay."""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import log, output_path, output_url


W, H = 720, 1280
FPS = 24
INTRO_DURATION = 2.0
OUTRO_DURATION = 2.0


def _get_font(size: int, bold: bool = False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _make_intro_frame(scene_image_path: str, hook_text: str) -> Image.Image:
    """Dark blurred scene image + hook text."""
    bg = Image.open(scene_image_path).resize((W, H)).filter(ImageFilter.GaussianBlur(15))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 160))
    bg = bg.convert("RGBA")
    bg = Image.alpha_composite(bg, overlay).convert("RGB")

    d = ImageDraw.Draw(bg)
    font = _get_font(44, bold=True)

    lines = []
    words = hook_text.split()
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        bbox = d.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > W - 100:
            if line:
                lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    lines = lines[:3]

    text = "\n".join(lines)
    bbox = d.multiline_textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (W - tw) // 2, (H - th) // 2

    d.multiline_text((x + 2, y + 2), text, fill=(0, 0, 0), font=font, align="center")
    d.multiline_text((x, y), text, fill=(255, 255, 255), font=font, align="center")

    return bg


def _make_outro_frame(scene_image_path: str, cta_text: str) -> Image.Image:
    """Dark blurred scene image + CTA text."""
    bg = Image.open(scene_image_path).resize((W, H)).filter(ImageFilter.GaussianBlur(10))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 160))
    bg = bg.convert("RGBA")
    bg = Image.alpha_composite(bg, overlay).convert("RGB")

    d = ImageDraw.Draw(bg)
    font = _get_font(48, bold=True)

    bbox = d.textbbox((0, 0), cta_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (W - tw) // 2, (H - th) // 2

    d.text((x + 2, y + 2), cta_text, fill=(0, 0, 0), font=font)
    d.text((x, y), cta_text, fill=(255, 255, 255), font=font)

    return bg


def _image_to_video(image: Image.Image, duration: float, output_file: str):
    """Convert a PIL image to a video clip with silent audio track."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        image.save(f.name)
        tmp_img = f.name

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", tmp_img,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-c:a", "aac", "-shortest",
        output_file,
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=30)
    Path(tmp_img).unlink(missing_ok=True)


def _fmt_srt_time(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _generate_marketing_srt(overlay: dict, intro_duration: float, body_duration: float) -> str:
    """Generate SRT for marketing overlay text (hook → benefit → CTA)."""
    srt_lines = []
    idx = 1

    hook = overlay.get("hook_overlay", "")
    benefit = overlay.get("benefit_overlay", "")
    cta = overlay.get("cta_overlay", "")

    if hook:
        srt_lines.append(f"{idx}")
        srt_lines.append(f"{_fmt_srt_time(0)} --> {_fmt_srt_time(intro_duration)}")
        srt_lines.append(hook)
        srt_lines.append("")
        idx += 1

    if benefit:
        start = intro_duration + 1.0
        end = intro_duration + min(10.0, body_duration - 2.0)
        srt_lines.append(f"{idx}")
        srt_lines.append(f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}")
        srt_lines.append(benefit)
        srt_lines.append("")
        idx += 1

    if cta:
        start = intro_duration + body_duration
        end = start + OUTRO_DURATION
        srt_lines.append(f"{idx}")
        srt_lines.append(f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}")
        srt_lines.append(cta)
        srt_lines.append("")
        idx += 1

    return "\n".join(srt_lines)


def _get_video_duration(path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 8.0


async def assemble_movie(
    project_id: str,
    scene_image: str,
    segment_video_paths: list[str] = None,
    body_video_path: str = None,
    hook_text: str = "",
    cta_text: str = "Link mua o mo ta nhe!",
    music_path: str | None = None,
    music_volume: float = 0.25,
    keep_veo_audio: bool = True,
    marketing_overlay: dict = None,
) -> dict:
    """Assemble final movie: intro + segments (or single body) + outro + music.

    segment_video_paths: ordered list of segment video URLs (new format).
    body_video_path: single body video (legacy fallback).

    Returns dict with video_url or error.
    """
    local_scene = str(Path(".") / scene_image.lstrip("/"))
    if not Path(local_scene).exists():
        return {"error": f"Scene image not found: {local_scene}"}

    # Resolve segment videos
    local_segments = []
    if segment_video_paths:
        for vp in segment_video_paths:
            local = str(Path(".") / vp.lstrip("/"))
            if not Path(local).exists():
                return {"error": f"Segment video not found: {vp}"}
            local_segments.append(local)
    elif body_video_path:
        local_body = str(Path(".") / body_video_path.lstrip("/"))
        if not Path(local_body).exists():
            return {"error": f"Body video not found: {local_body}"}
        local_segments.append(local_body)
    else:
        return {"error": "Cần có segment videos hoặc body video."}

    body_duration = sum(_get_video_duration(s) for s in local_segments)
    out_dir = output_path(project_id, "final")
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        log.info(f"Assembling movie for project {project_id} "
                 f"({len(local_segments)} segments, body={body_duration:.1f}s)")

        # Generate intro/outro
        intro_frame = _make_intro_frame(local_scene, hook_text or "")
        intro_video = f"{tmpdir}/intro.mp4"
        _image_to_video(intro_frame, INTRO_DURATION, intro_video)

        outro_frame = _make_outro_frame(local_scene, cta_text)
        outro_video = f"{tmpdir}/outro.mp4"
        _image_to_video(outro_frame, OUTRO_DURATION, outro_video)

        # Re-encode segments to consistent format
        reencoded_segments = []
        for i, seg_path in enumerate(local_segments):
            out = f"{tmpdir}/seg_{i}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-i", seg_path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k", out,
            ], capture_output=True, check=True, timeout=120)
            reencoded_segments.append(out)

        # Concat: intro + segments + outro
        concat_file = f"{tmpdir}/concat.txt"
        with open(concat_file, "w") as f:
            f.write(f"file '{intro_video}'\n")
            for seg in reencoded_segments:
                f.write(f"file '{seg}'\n")
            f.write(f"file '{outro_video}'\n")

        out_file = str(out_dir / "movie.mp4")
        total_dur = INTRO_DURATION + body_duration + OUTRO_DURATION

        if music_path and Path(music_path).exists():
            concat_tmp = f"{tmpdir}/concat_raw.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k", concat_tmp,
            ], capture_output=True, check=True, timeout=120)

            veo_vol = "0.9" if keep_veo_audio else "0.0"
            filter_complex = (
                f"[0:a]volume={veo_vol}[voice];"
                f"[1:a]atrim=0:{total_dur:.1f},volume={music_volume:.2f}[music];"
                f"[voice][music]amix=inputs=2:duration=first:normalize=0[aout]"
            )
            subprocess.run([
                "ffmpeg", "-y", "-i", concat_tmp, "-i", music_path,
                "-filter_complex", filter_complex,
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                out_file,
            ], capture_output=True, check=True, timeout=120)
        else:
            if not keep_veo_audio:
                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-an", out_file,
                ], capture_output=True, check=True, timeout=120)
            else:
                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "128k", out_file,
                ], capture_output=True, check=True, timeout=120)

    if not Path(out_file).exists():
        return {"error": "Assembly failed — output file not created"}

    # Burn in marketing overlay
    if marketing_overlay:
        srt_content = _generate_marketing_srt(marketing_overlay, INTRO_DURATION, body_duration)
        if srt_content.strip():
            srt_file = str(out_dir / "marketing.srt")
            Path(srt_file).write_text(srt_content, encoding="utf-8")
            overlay_file = str(out_dir / "movie_overlay.mp4")
            srt_escaped = srt_file.replace(":", "\\:").replace("'", "\\'")
            cap_result = subprocess.run([
                "ffmpeg", "-y", "-i", out_file,
                "-vf", f"subtitles={srt_escaped}:force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Bold=1,Alignment=2,MarginV=80'",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "copy", overlay_file,
            ], capture_output=True, timeout=120)
            if cap_result.returncode == 0 and Path(overlay_file).exists():
                out_file = overlay_file
                log.info("Marketing overlay burned in")
            else:
                log.warning(f"Marketing overlay burn-in failed: {cap_result.stderr.decode()[-200:]}")

    filename = Path(out_file).name
    url = f"{output_url(project_id, 'final')}/{filename}"
    size_kb = Path(out_file).stat().st_size // 1024
    log.info(f"Movie assembled: {url} ({size_kb}KB, ~{total_dur:.0f}s)")
    return {"video_url": url, "duration": total_dur}
