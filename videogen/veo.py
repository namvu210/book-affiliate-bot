"""Veo 3 provider via Google AI Studio (google-genai SDK)."""

import asyncio
import time
from pathlib import Path

import httpx
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, log
from videogen.provider import VideoGenProvider, VideoClipRequest, VideoClipResult

POLL_INTERVAL = 15
MAX_POLL_TIME = 300


class VeoProvider(VideoGenProvider):
    """Veo 3 image-to-video via Google AI Studio API."""

    name = "veo3"

    def __init__(self, model: str = "veo-3.0-generate-001", api_key: str = ""):
        self.model = model
        self.api_key = api_key or GEMINI_API_KEY
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate_clip(self, request: VideoClipRequest, output_path: str) -> VideoClipResult:
        """Generate a video clip from image + motion prompt."""
        if not Path(request.image_path).exists():
            return VideoClipResult(error=f"Image not found: {request.image_path}")

        try:
            img_bytes = Path(request.image_path).read_bytes()
            mime = "image/png" if request.image_path.endswith(".png") else "image/jpeg"
            img_input = types.Image(image_bytes=img_bytes, mime_type=mime)

            # Submit async operation
            op = await asyncio.to_thread(
                self.client.models.generate_videos,
                model=self.model,
                prompt=request.motion_prompt,
                image=img_input,
                config=types.GenerateVideosConfig(
                    aspectRatio=request.aspect_ratio.replace(":", ":"),
                    numberOfVideos=1,
                ),
            )
            log.info(f"Veo op submitted: {op.name}")

            # Poll for completion
            start = time.time()
            while time.time() - start < MAX_POLL_TIME:
                await asyncio.sleep(POLL_INTERVAL)
                result = await asyncio.to_thread(self.client.operations.get, operation=op)
                if result.done:
                    break
            else:
                return VideoClipResult(error=f"Veo generation timed out after {MAX_POLL_TIME}s")

            if result.error:
                return VideoClipResult(error=str(result.error))

            if not result.response or not result.response.generated_videos:
                return VideoClipResult(error="No video in Veo response")

            vid = result.response.generated_videos[0]
            if not vid.video or not vid.video.uri:
                return VideoClipResult(error="No video URI in response")

            # Download video
            video_url = f"{vid.video.uri}&key={self.api_key}"
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
                r = await http.get(video_url)
                if r.status_code != 200:
                    return VideoClipResult(error=f"Download failed: HTTP {r.status_code}")
                Path(output_path).write_bytes(r.content)

            log.info(f"Veo clip done: {Path(output_path).name} ({len(r.content)} bytes)")
            return VideoClipResult(video_path=output_path, duration_s=request.duration_s)

        except Exception as e:
            log.warning(f"Veo generation failed: {e}")
            return VideoClipResult(error=str(e)[:200])

    async def generate_clips(self, requests: list[VideoClipRequest], output_dir: str) -> list[VideoClipResult]:
        """Generate clips in parallel (Veo handles concurrency server-side)."""
        tasks = []
        for i, req in enumerate(requests):
            out = str(Path(output_dir) / f"clip_{i}.mp4")
            tasks.append(self.generate_clip(req, out))
        return await asyncio.gather(*tasks)
