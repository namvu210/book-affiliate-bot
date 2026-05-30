"""Mock provider for testing — generates a static video from the input image."""

import asyncio
import subprocess
from pathlib import Path

from config import log
from videogen.provider import VideoGenProvider, VideoClipRequest, VideoClipResult


class MockProvider(VideoGenProvider):
    """Generates a simple zoompan video from the source image (no API calls)."""

    name = "mock"

    async def generate_clip(self, request: VideoClipRequest, output_path: str) -> VideoClipResult:
        """Create a ken-burns style clip from the image using ffmpeg."""
        if not Path(request.image_path).exists():
            return VideoClipResult(error=f"Image not found: {request.image_path}")

        dur = request.duration_s
        w, h = (1080, 1920) if request.aspect_ratio == "9:16" else (1080, 1080)
        # ffmpeg zoompan: slow zoom in over duration
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", request.image_path,
            "-vf", (
                f"scale=8000:-1,"
                f"zoompan=z='min(zoom+0.002,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={int(dur * 25)}:s={w}x{h}:fps=25"
            ),
            "-t", str(dur),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
            output_path,
        ]
        try:
            proc = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, timeout=60
            )
            if proc.returncode != 0:
                err = proc.stderr.decode()[-300:]
                log.warning(f"Mock clip failed: {err}")
                return VideoClipResult(error=err)
            log.info(f"Mock clip: {Path(output_path).name} ({dur}s)")
            return VideoClipResult(video_path=output_path, duration_s=dur)
        except Exception as e:
            return VideoClipResult(error=str(e))
