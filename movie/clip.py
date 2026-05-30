"""Video clip generation for Movie Ads — Veo 3.x image-to-video.

Single 8s generation from scene image. Extension is not available for 9:16 vertical.
Intro/outro padding brings total to ~12-14s for TikTok/Reels.

Cost reference (8s per project):
  Veo 3.1 Lite  720p: $0.05/s → $0.40/project  (draft, fastest)
  Veo 3.1 Fast  720p: $0.10/s → $0.80/project  (good balance)
  Veo 3.1       1080p: $0.40/s → $3.20/project  (final render)

All Veo 3.x models generate native audio (dialogue, SFX, ambient).
"""

import asyncio
import time
from pathlib import Path

import httpx
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, log, output_path, output_url
import kol_manager

MODELS = {
    "veo-3.1-lite-generate-preview": "Veo 3.1 Lite — $0.80/project, 720p, nhanh nhất (draft)",
    "veo-3.1-fast-generate-preview": "Veo 3.1 Fast — $1.60/project, 720p (Recommended)",
    "veo-3.0-fast-generate-001": "Veo 3 Fast — $1.60/project, 720p",
    "veo-3.1-generate-preview": "Veo 3.1 — $6.40/project, 1080p (chất lượng cao)",
    "veo-3.0-generate-001": "Veo 3 — $6.40/project, 1080p",
}
DEFAULT_MODEL = "veo-3.1-fast-generate-preview"

SUPPORTS_REFERENCE_IMAGES = {"veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"}

POLL_INTERVAL = 15
MAX_POLL_TIME = 360


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


async def _poll_operation(client, op):
    """Poll a Veo operation until done or timeout."""
    start = time.time()
    while time.time() - start < MAX_POLL_TIME:
        await asyncio.sleep(POLL_INTERVAL)
        result = await asyncio.to_thread(client.operations.get, operation=op)
        if result.done:
            return result
    return None


async def _download_video(video_obj, out_file: Path) -> bool:
    """Download generated video to local file."""
    if not video_obj or not video_obj.video or not video_obj.video.uri:
        return False
    video_url = f"{video_obj.video.uri}&key={GEMINI_API_KEY}"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
        r = await http.get(video_url)
        if r.status_code != 200:
            return False
        out_file.write_bytes(r.content)
    return True


def _build_ref_images(kol_ids: list[str], product_images: list[str], model: str) -> list:
    """Build reference images list for Veo 3.1 models."""
    if model not in SUPPORTS_REFERENCE_IMAGES:
        return []
    ref_images = []
    if kol_ids:
        for kol_id in kol_ids:
            ref_paths = kol_manager.get_reference_paths(kol_id)
            if ref_paths:
                ref_bytes = Path(ref_paths[0]).read_bytes()
                ref_mime = "image/png" if ref_paths[0].endswith(".png") else "image/jpeg"
                ref_images.append(types.VideoGenerationReferenceImage(
                    image=types.Image(image_bytes=ref_bytes, mime_type=ref_mime),
                    reference_type="ASSET",
                ))
            if len(ref_images) >= 2:
                break
    if product_images and len(ref_images) < 3:
        for img_url in product_images[:1]:
            local_prod = str(Path(".") / img_url.lstrip("/"))
            if Path(local_prod).exists():
                prod_bytes = Path(local_prod).read_bytes()
                prod_mime = "image/png" if local_prod.endswith(".png") else "image/jpeg"
                ref_images.append(types.VideoGenerationReferenceImage(
                    image=types.Image(image_bytes=prod_bytes, mime_type=prod_mime),
                    reference_type="ASSET",
                ))
    return ref_images


def _build_prompt(
    motion_prompt: str,
    dialogue: str | None,
    kol_ids: list[str] | None,
    screenplay_context: dict | None = None,
) -> str:
    """Build final prompt: enrich motion_prompt with screenplay context + dialogue.

    screenplay_context can contain: mood, cinematic_style.
    These are injected as style guidance so Veo understands the broader creative direction.
    Vietnamese atmosphere is added subtly only when the prompt doesn't specify a location.
    """
    parts = []

    # Style prefix from screenplay context
    if screenplay_context:
        style_hints = []
        if screenplay_context.get("cinematic_style"):
            style_hints.append(f"Cinematic style: {screenplay_context['cinematic_style']}")
        if screenplay_context.get("mood"):
            style_hints.append(f"Emotional arc: {screenplay_context['mood']}")
        if style_hints:
            parts.append(". ".join(style_hints) + ".")

    # Core motion prompt (should already be detailed from LLM)
    parts.append(motion_prompt)

    # Vietnamese atmosphere — only add if prompt doesn't already specify a clear location
    # The screenplay LLM is instructed to include Vietnamese settings, so this is a safety net
    prompt_lower = motion_prompt.lower()
    has_location = any(kw in prompt_lower for kw in [
        "vietnam", "vietnamese", "saigon", "hanoi", "hcmc",
        "studio", "garage", "alley", "rooftop", "café", "cafe",
        "street", "market", "park", "room", "apartment", "office",
        "beach", "forest", "field", "bridge", "temple",
    ])
    if not has_location:
        parts.append("Vietnamese urban setting, tropical warm atmosphere.")

    # Dialogue
    if dialogue:
        char_name = "The character"
        if kol_ids:
            profile = kol_manager.get_profile(kol_ids[0])
            if profile:
                char_name = profile["name"].split("—")[0].strip()
        parts.append(f'{char_name} says: "{dialogue}"')

    return "\n".join(parts)


async def generate_movie_clip(
    project_id: str,
    clip_number: int,
    scene_image_path: str,
    motion_prompt: str,
    dialogue: str | None = None,
    model: str = DEFAULT_MODEL,
    prev_clip_video: str | None = None,
    kol_ids: list[str] = None,
    product_images: list[str] = None,
    duration_seconds: int = 8,
    screenplay_context: dict | None = None,
) -> dict:
    """Generate an 8s video clip from scene image as first frame + motion prompt.

    Returns dict with video_url or error.
    """
    local_image = str(Path(".") / scene_image_path.lstrip("/"))
    if not Path(local_image).exists():
        return {"error": f"Scene image not found: {scene_image_path}"}

    prompt = _build_prompt(motion_prompt, dialogue, kol_ids, screenplay_context)

    out_dir = output_path(project_id, "video_clips")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"clip_{clip_number}.mp4"

    log.info(f"Generating movie clip {clip_number} for project {project_id} "
             f"(model={model}, dialogue={'yes' if dialogue else 'no'}, "
             f"prompt_len={len(prompt)})")

    try:
        img_bytes = Path(local_image).read_bytes()
        mime = "image/png" if local_image.endswith(".png") else "image/jpeg"
        img_input = types.Image(image_bytes=img_bytes, mime_type=mime)

        config_kwargs = dict(
            aspect_ratio="9:16",
            number_of_videos=1,
            duration_seconds=duration_seconds,
            person_generation="allow_adult",
        )

        ref_images = _build_ref_images(kol_ids or [], product_images or [], model)
        if ref_images:
            config_kwargs["reference_images"] = ref_images
            log.info(f"Clip {clip_number}: {len(ref_images)} reference images (KOL+product)")

        client = _get_client()
        try:
            op = await asyncio.to_thread(
                client.models.generate_videos,
                model=model,
                prompt=prompt,
                image=img_input,
                config=types.GenerateVideosConfig(**config_kwargs),
            )
        except Exception as first_err:
            if "400" in str(first_err) and ref_images:
                log.warning(f"Clip {clip_number}: 400 with reference_images, retrying without them")
                config_kwargs.pop("reference_images", None)
                op = await asyncio.to_thread(
                    client.models.generate_videos,
                    model=model,
                    prompt=prompt,
                    image=img_input,
                    config=types.GenerateVideosConfig(**config_kwargs),
                )
            else:
                raise
        log.info(f"Veo op submitted: {op.name}")

        result = await _poll_operation(client, op)
        if result is None:
            return {"error": f"Video generation timed out ({MAX_POLL_TIME}s). Thử lại sau."}
        if result.error:
            return {"error": str(result.error)}
        if not result.response or not result.response.generated_videos:
            return {"error": "Không có video trong response. Thử lại."}

        vid = result.response.generated_videos[0]
        if not await _download_video(vid, out_file):
            return {"error": "Download video failed. Thử lại."}

        url = f"{output_url(project_id, 'video_clips')}/clip_{clip_number}.mp4"
        log.info(f"Movie clip {clip_number} done: {url} ({out_file.stat().st_size} bytes)")
        return {"video_url": url, "clip_number": clip_number}

    except Exception as e:
        log.warning(f"Movie clip {clip_number} failed: {type(e).__name__}: {e}")
        return {"error": str(e)[:300]}



PRODUCT_CLOSEUP_PROMPTS = [
    "Slow cinematic dolly around the product on a clean surface, soft studio lighting with subtle reflections, shallow depth of field, the product rotates slightly revealing details and texture, smooth professional movement",
    "Elegant slow orbit around the product, warm backlight creating a rim glow, camera pulls back slightly to reveal full product, studio setting with bokeh background",
    "Close-up product hero shot, camera slowly pushes in revealing fine details and craftsmanship, soft diffused lighting from above, gentle light shift from cool to warm",
]


async def generate_product_closeup(
    project_id: str,
    product_image_path: str,
    model: str = None,
    duration_seconds: int = 4,
    prompt_variant: int = 0,
    prompt_override: str = None,
) -> dict:
    """Generate a 4-6s product beauty/close-up shot from product image.

    Returns dict with video_url or error.
    """
    if model is None:
        model = DEFAULT_MODEL
    local_image = str(Path(".") / product_image_path.lstrip("/"))
    if not Path(local_image).exists():
        return {"error": f"Product image not found: {product_image_path}"}

    prompt = prompt_override or PRODUCT_CLOSEUP_PROMPTS[prompt_variant % len(PRODUCT_CLOSEUP_PROMPTS)]

    out_dir = output_path(project_id, "video_clips")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "product_closeup.mp4"

    log.info(f"Generating product close-up for project {project_id} "
             f"(model={model}, {duration_seconds}s, variant={prompt_variant})")

    try:
        img_bytes = Path(local_image).read_bytes()
        mime = "image/png" if local_image.endswith(".png") else "image/jpeg"
        img_input = types.Image(image_bytes=img_bytes, mime_type=mime)

        config_kwargs = dict(
            aspect_ratio="9:16",
            number_of_videos=1,
            duration_seconds=duration_seconds,
            person_generation="allow_adult",
        )

        client = _get_client()
        op = await asyncio.to_thread(
            client.models.generate_videos,
            model=model,
            prompt=prompt,
            image=img_input,
            config=types.GenerateVideosConfig(**config_kwargs),
        )
        log.info(f"Product close-up Veo op submitted: {op.name}")

        result = await _poll_operation(client, op)
        if result is None:
            return {"error": f"Product close-up timed out ({MAX_POLL_TIME}s). Thử lại sau."}
        if result.error:
            return {"error": str(result.error)}
        if not result.response or not result.response.generated_videos:
            return {"error": "Không có video trong response. Thử lại."}

        vid = result.response.generated_videos[0]
        if not await _download_video(vid, out_file):
            return {"error": "Download video failed. Thử lại."}

        url = f"{output_url(project_id, 'video_clips')}/product_closeup.mp4"
        log.info(f"Product close-up done: {url} ({out_file.stat().st_size} bytes)")
        return {"video_url": url, "duration_seconds": duration_seconds}

    except Exception as e:
        log.warning(f"Product close-up failed: {type(e).__name__}: {e}")
        return {"error": str(e)[:300]}


def get_available_models() -> dict:
    return MODELS
