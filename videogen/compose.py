"""Compose: stitch video clips + TTS + text overlay + music into final ad creative."""

import asyncio
import subprocess
import tempfile
from pathlib import Path

from config import log, make_ts, output_path, output_url, get_audio_duration
from music import get_background_music
from tts import generate_audio
from videogen.provider import VideoClipRequest, get_provider
from videogen.storyboard import generate_storyboard


async def generate_ad_creative(
    product_title: str,
    ad_script: str,
    ai_image_paths: list[str],
    persona_name: str = "",
    voice_speed: int = 140,
    voice_type: str = "elevenlabs",
    voice_id: str = "",
    music_volume: float = 0.20,
    aspect_ratio: str = "9:16",
) -> dict:
    """Generate a 15s ad creative video.

    Returns {"video_url": str, "duration": float} or {"error": str}.
    """
    if not ai_image_paths:
        return {"error": "No AI images available for ad creative"}
    if not ad_script.strip():
        return {"error": "No ad script provided"}

    ts = make_ts()
    provider = get_provider()

    # 1. Generate storyboard (scene splits + motion prompts)
    num_clips = min(len(ai_image_paths), 4)
    storyboard = await asyncio.to_thread(
        generate_storyboard, ad_script, product_title, persona_name, num_clips
    )
    if not storyboard:
        return {"error": "Storyboard generation failed"}

    # 2. Generate TTS audio for the full script
    audio_path = str(output_path(ts, "ad_audio.mp3"))
    await generate_audio(
        ad_script, audio_path,
        speed=voice_speed,
        voice_type=voice_type,
        elevenlabs_voice_id=voice_id,
        no_fallback=True,
    )
    if not Path(audio_path).exists():
        return {"error": "TTS generation failed"}

    audio_dur = get_audio_duration(audio_path) or 15.0
    # Adjust storyboard durations to match actual audio
    total_story_dur = sum(s["duration_s"] for s in storyboard)
    if total_story_dur > 0:
        scale = audio_dur / total_story_dur
        for s in storyboard:
            s["duration_s"] = round(s["duration_s"] * scale, 1)

    # 3. Generate video clips (image-to-video)
    clip_dir = output_path(ts, "ad_clips").resolve()
    clip_dir.mkdir(parents=True, exist_ok=True)

    requests = []
    for i, scene in enumerate(storyboard):
        img_idx = i % len(ai_image_paths)
        img_path = ai_image_paths[img_idx]
        # Resolve relative paths
        local = str(Path(".") / img_path.lstrip("/"))
        if not Path(local).exists():
            local = img_path
        requests.append(VideoClipRequest(
            image_path=str(Path(local).resolve()),
            motion_prompt=scene["motion"],
            duration_s=scene["duration_s"],
            aspect_ratio=aspect_ratio,
        ))

    results = await provider.generate_clips(requests, str(clip_dir))

    # Collect successful clips
    clip_paths = []
    for r in results:
        if r.video_path and Path(r.video_path).exists():
            clip_paths.append(r.video_path)
        elif r.error:
            log.warning(f"Clip failed: {r.error}")

    if not clip_paths:
        return {"error": "All video clip generations failed"}

    # 4. Stitch clips + audio + music
    video_path = str(output_path(ts, "ad_creative.mp4"))
    music_path = get_background_music(product_title)

    await asyncio.to_thread(
        _stitch_final, clip_paths, audio_path, music_path, music_volume, video_path
    )

    if not Path(video_path).exists():
        return {"error": "Final video composition failed"}

    log.info(f"Ad creative done: {video_path} ({len(clip_paths)} clips, {audio_dur:.1f}s)")
    return {
        "video_url": output_url(ts, "ad_creative.mp4"),
        "duration": audio_dur,
        "clips_generated": len(clip_paths),
        "clips_requested": len(requests),
    }


def _stitch_final(
    clip_paths: list[str],
    audio_path: str,
    music_path: str | None,
    music_volume: float,
    output: str,
):
    """Concatenate clips, overlay audio + background music."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for cp in clip_paths:
            f.write(f"file '{Path(cp).resolve()}'\n")
        concat_list = f.name

    try:
        # Concat clips
        concat_path = output.replace(".mp4", "_concat.mp4")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
            concat_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"Concat failed: {proc.stderr.decode()[-300:]}")

        # Mux with audio + music
        audio_dur = get_audio_duration(audio_path) or 15.0
        cmd = ["ffmpeg", "-y", "-i", concat_path, "-i", audio_path]

        if music_path and Path(music_path).exists():
            cmd.extend(["-i", music_path])
            cmd.extend([
                "-filter_complex",
                f"[1:a]volume=1.0[voice];"
                f"[2:a]volume={music_volume:.2f},aloop=loop=-1:size=2e+09,"
                f"atrim=0:{audio_dur:.3f}[music];"
                f"[voice][music]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]",
            ])
        else:
            cmd.extend(["-map", "0:v", "-map", "1:a"])

        cmd.extend([
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", str(audio_dur),
            output,
        ])
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"Mux failed: {proc.stderr.decode()[-300:]}")
    finally:
        Path(concat_list).unlink(missing_ok=True)
        Path(output.replace(".mp4", "_concat.mp4")).unlink(missing_ok=True)
