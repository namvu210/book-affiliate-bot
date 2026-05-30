"""Kling AI provider — image-to-video generation via API."""

import asyncio
import os
import time
from pathlib import Path

import httpx

from config import log
from videogen.provider import VideoGenProvider, VideoClipRequest, VideoClipResult

# Requires: KLING_API_KEY env var
API_BASE = "https://api.klingai.com/v1"
POLL_INTERVAL = 5
MAX_POLL_TIME = 180


class KlingProvider(VideoGenProvider):
    """Kling 1.6 image-to-video."""

    name = "kling"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("KLING_API_KEY", "")

    async def generate_clip(self, request: VideoClipRequest, output_path: str) -> VideoClipResult:
        """Submit image-to-video and poll for completion."""
        if not self.api_key:
            return VideoClipResult(error="KLING_API_KEY not set")

        try:
            import base64
            image_b64 = base64.b64encode(Path(request.image_path).read_bytes()).decode()

            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

            # Submit generation task
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{API_BASE}/images/generations/image2video",
                    headers=headers,
                    json={
                        "image": image_b64,
                        "prompt": request.motion_prompt,
                        "duration": str(int(request.duration_s)),
                        "aspect_ratio": request.aspect_ratio,
                    },
                )
                resp.raise_for_status()
                task_id = resp.json().get("data", {}).get("task_id")

            if not task_id:
                return VideoClipResult(error="No task_id in response")

            # Poll for result
            start = time.time()
            async with httpx.AsyncClient(timeout=30) as client:
                while time.time() - start < MAX_POLL_TIME:
                    await asyncio.sleep(POLL_INTERVAL)
                    resp = await client.get(
                        f"{API_BASE}/images/generations/{task_id}",
                        headers=headers,
                    )
                    data = resp.json().get("data", {})
                    status = data.get("status", "")

                    if status == "completed":
                        video_url = data.get("output", {}).get("video_url", "")
                        if video_url:
                            dl = await client.get(video_url)
                            Path(output_path).write_bytes(dl.content)
                            log.info(f"Kling clip: {Path(output_path).name} ({request.duration_s}s)")
                            return VideoClipResult(video_path=output_path, duration_s=request.duration_s)
                        return VideoClipResult(error="No video_url in completed task")
                    elif status == "failed":
                        return VideoClipResult(error=f"Kling task failed: {data.get('error', 'unknown')}")

            return VideoClipResult(error="Kling generation timed out")

        except Exception as e:
            log.warning(f"Kling generation failed: {e}")
            return VideoClipResult(error=str(e)[:200])
