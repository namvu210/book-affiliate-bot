"""Backend batch orchestration — runs batch steps as background tasks."""

import asyncio
import json
import logging
from pathlib import Path

from batch_state import _save, _load, BATCH_DIR
from config import make_ts, output_path, output_url

log = logging.getLogger("batch_runner")

# Track running tasks
_running: dict[str, asyncio.Task] = {}


def get_job(batch_id: str) -> dict | None:
    return _load(batch_id)


def update_product_step(batch_id: str, idx: int, step: str, status: str, result=None, error=None):
    """Update a specific product's step status."""
    job = _load(batch_id)
    if not job or idx >= len(job["products"]):
        return
    product = job["products"][idx]
    if "steps" not in product:
        product["steps"] = {}
    product["steps"][step] = {"status": status}
    if result is not None:
        product["steps"][step]["result"] = result
    if error:
        product["steps"][step]["error"] = error
    _save(batch_id, job)


async def run_personas(batch_id: str):
    """Phase 1: Generate persona suggestions for all products."""
    from reviewer import suggest_personas
    job = _load(batch_id)
    job["status"] = "personas_running"
    _save(batch_id, job)

    for i, product in enumerate(job["products"]):
        if product.get("steps", {}).get("persona", {}).get("status") == "done":
            continue  # skip already done
        try:
            update_product_step(batch_id, i, "persona", "processing")
            personas = suggest_personas(product["title"])
            update_product_step(batch_id, i, "persona", "done", result=personas)
        except Exception as e:
            update_product_step(batch_id, i, "persona", "error", error=str(e))
            log.warning(f"Persona {i} failed: {e}")

    job = _load(batch_id)
    job["status"] = "personas_done"
    _save(batch_id, job)


async def run_reviews_and_assets(batch_id: str):
    """Phase 2: Generate reviews + audio + images for confirmed products."""
    job = _load(batch_id)
    job["status"] = "processing"
    _save(batch_id, job)

    sem = asyncio.Semaphore(2)  # max 2 concurrent

    async def process_one(i, product):
        async with sem:
            await _run_review(batch_id, i, product, job["settings"])
            await _run_audio(batch_id, i, product, job["settings"])
            await _run_ai_images(batch_id, i, product, job["settings"])

    tasks = []
    for i, product in enumerate(job["products"]):
        if not product.get("selected_persona"):
            continue  # user didn't confirm this product
        tasks.append(process_one(i, product))

    await asyncio.gather(*tasks, return_exceptions=True)

    job = _load(batch_id)
    job["status"] = "assets_done"
    _save(batch_id, job)


async def run_videos(batch_id: str):
    """Phase 3: Render videos for all ready products."""
    job = _load(batch_id)
    job["status"] = "videos_running"
    _save(batch_id, job)

    sem = asyncio.Semaphore(2)

    async def render_one(i, product):
        async with sem:
            await _run_video(batch_id, i, product, job["settings"])

    tasks = []
    for i, product in enumerate(job["products"]):
        steps = product.get("steps", {})
        has_audio = steps.get("audio", {}).get("status") == "done"
        has_images = steps.get("images", {}).get("status") == "done"
        if not has_audio or not has_images:
            continue
        if steps.get("video", {}).get("status") == "done":
            continue
        tasks.append(render_one(i, product))

    await asyncio.gather(*tasks, return_exceptions=True)

    # Auto-queue ad creatives if setting enabled
    job = _load(batch_id)
    if job.get("settings", {}).get("generate_ad_creative"):
        await run_ad_creatives(batch_id)
    else:
        job["status"] = "done"
        _save(batch_id, job)


async def run_ad_creatives(batch_id: str):
    """Phase 4: Generate 15s ad creative videos for products with AI images."""
    job = _load(batch_id)
    job["status"] = "ads_running"
    _save(batch_id, job)

    sem = asyncio.Semaphore(2)

    async def gen_one(i, product):
        async with sem:
            await _run_ad_creative(batch_id, i, product, job["settings"])

    tasks = []
    for i, product in enumerate(job["products"]):
        steps = product.get("steps", {})
        has_video = steps.get("video", {}).get("status") == "done"
        has_ai_imgs = steps.get("ai_images", {}).get("status") == "done"
        if not has_video or not has_ai_imgs:
            continue
        if steps.get("ad_creative", {}).get("status") == "done":
            continue
        tasks.append(gen_one(i, product))

    await asyncio.gather(*tasks, return_exceptions=True)

    job = _load(batch_id)
    job["status"] = "done"
    _save(batch_id, job)


# === Step implementations ===

async def _run_review(batch_id: str, idx: int, product: dict, settings: dict):
    """Generate review for a product."""
    from reviewer import generate_review
    from extractor import BookInfo
    import asyncio

    steps = product.get("steps", {})
    if steps.get("review", {}).get("status") == "done":
        return

    update_product_step(batch_id, idx, "review", "processing")
    try:
        book = BookInfo(
            title=product["title"], author="", description="",
            shopee_url=product.get("affiliate") or product.get("url", ""),
            source="shopee",
        )
        persona = product.get("selected_persona", {"name": "Khách hàng", "tone": "friendly", "focus": "quality"})
        wc = settings.get("word_count", 120)
        review = await asyncio.to_thread(generate_review, book, "custom", "facebook", persona, wc)
        # Strip audio tags from hook/cta
        import re
        for field in ("hook", "cta"):
            if review.get(field):
                review[field] = re.sub(r'\[[a-zA-Z_ ]+\]', '', review[field]).strip()
        update_product_step(batch_id, idx, "review", "done", result=review)
    except Exception as e:
        update_product_step(batch_id, idx, "review", "error", error=str(e))


async def _run_audio(batch_id: str, idx: int, product: dict, settings: dict):
    """Generate TTS audio."""
    from tts import generate_audio

    job = _load(batch_id)
    steps = job["products"][idx].get("steps", {})
    if steps.get("audio", {}).get("status") == "done":
        return

    review = steps.get("review", {}).get("result", {})
    text = review.get("social_post", "")
    cta = review.get("cta", "")
    if not text:
        update_product_step(batch_id, idx, "audio", "error", error="No review text")
        return
    if cta and cta not in text:
        text = text.rstrip() + " " + cta

    update_product_step(batch_id, idx, "audio", "processing")
    try:
        ts = make_ts()
        audio_path = str(output_path(ts, "facebook.mp3"))
        await generate_audio(
            text, audio_path,
            speed=settings.get("voice_speed", 140),
            voice_type=settings.get("voice_type", "elevenlabs"),
            elevenlabs_voice_id=settings.get("voice_id", ""),
            no_fallback=True,
        )
        audio_url = output_url(ts, "facebook.mp3")
        update_product_step(batch_id, idx, "audio", "done", result={"audio_url": audio_url})
    except Exception as e:
        update_product_step(batch_id, idx, "audio", "error", error=str(e)[:200])


async def _run_ai_images(batch_id: str, idx: int, product: dict, settings: dict):
    """Generate AI lifestyle images."""
    from imagegen import generate_lifestyle_images

    job = _load(batch_id)
    steps = job["products"][idx].get("steps", {})
    if steps.get("ai_images", {}).get("status") == "done":
        return

    image_paths = product.get("image_paths", [])
    # Save product images status
    update_product_step(batch_id, idx, "images", "done", result=image_paths)

    n = len(image_paths)
    if n < 5:
        update_product_step(batch_id, idx, "ai_images", "skipped", error=f"Only {n} images (<5)")
        return

    num_ai = 3 if n <= 7 else 2 if n <= 10 else 1
    update_product_step(batch_id, idx, "ai_images", "processing")
    try:
        ts = make_ts()
        persona = product.get("selected_persona", {"name": "Khách hàng", "focus": ""})
        ai_images = await generate_lifestyle_images(product["title"], persona, num_ai, ts, image_paths[:3])
        update_product_step(batch_id, idx, "ai_images", "done", result=ai_images)
    except Exception as e:
        update_product_step(batch_id, idx, "ai_images", "error", error=str(e)[:200])


async def _run_video(batch_id: str, idx: int, product: dict, settings: dict):
    """Render video for a product."""
    from video.prepare import VideoInput, render_video

    job = _load(batch_id)
    steps = job["products"][idx].get("steps", {})
    review = steps.get("review", {}).get("result", {})
    audio_url = steps.get("audio", {}).get("result", {}).get("audio_url", "")
    images = steps.get("images", {}).get("result", [])
    ai_images = steps.get("ai_images", {}).get("result", [])

    if not audio_url or not review:
        update_product_step(batch_id, idx, "video", "error", error="Missing audio or review")
        return

    # Combine images: AI first/last, product in middle
    all_imgs = []
    if ai_images:
        all_imgs = [ai_images[0]] + images + ai_images[1:]
    else:
        all_imgs = images

    # Build review data structure expected by render_video
    review_data = {
        "book": {"title": product["title"], "shopee_url": product.get("url", "")},
        "facebook": {**review, "audio_url": audio_url},
        "affiliate_link": product.get("affiliate", ""),
        "audience_name": product.get("selected_persona", {}).get("name", ""),
        "product_images": all_imgs,
    }

    update_product_step(batch_id, idx, "video", "processing")
    try:
        from video.prepare import pick_effect_combo
        effect, style = pick_effect_combo(seed=hash(f"{batch_id}_{idx}"))
        inp = VideoInput(
            review_data=review_data,
            platform="facebook",
            selected_images=all_imgs,
            music_volume=15,
            aspect_ratio="9:16",
            voice_speed=settings.get("voice_speed", 140),
            subtitle_style="tiktok",
            img_effect=effect,
            img_style=style,
            show_intro=True,
            show_outro=True,
        )
        result = await render_video(inp)
        if result.get("error"):
            update_product_step(batch_id, idx, "video", "error", error=result["error"])
        else:
            update_product_step(batch_id, idx, "video", "done", result=result)
    except Exception as e:
        update_product_step(batch_id, idx, "video", "error", error=str(e)[:200])


async def _run_ad_creative(batch_id: str, idx: int, product: dict, settings: dict):
    """Generate 15s ad creative video for a product."""
    from videogen import generate_ad_creative
    from reviewer import generate_review
    from extractor import BookInfo

    job = _load(batch_id)
    steps = job["products"][idx].get("steps", {})
    ai_images = steps.get("ai_images", {}).get("result", [])
    review = steps.get("review", {}).get("result", {})

    if not ai_images:
        update_product_step(batch_id, idx, "ad_creative", "skipped", error="No AI images")
        return

    update_product_step(batch_id, idx, "ad_creative", "processing")
    try:
        # Generate short ad script (~60 words) via Gemini
        book = BookInfo(
            title=product["title"], author="", description="",
            shopee_url=product.get("affiliate") or product.get("url", ""),
            source="shopee",
        )
        persona = product.get("selected_persona", {"name": "Khách hàng", "tone": "friendly", "focus": "quality"})
        import asyncio
        ad_review = await asyncio.to_thread(generate_review, book, "custom", "tiktok", persona, 60)
        ad_script = ad_review.get("social_post", "")
        if not ad_script:
            update_product_step(batch_id, idx, "ad_creative", "error", error="Empty ad script")
            return

        # Resolve AI image URLs to local paths
        img_paths = []
        from pathlib import Path
        for img_url in ai_images:
            local = str(Path(".") / img_url.lstrip("/"))
            if Path(local).exists():
                img_paths.append(local)

        result = await generate_ad_creative(
            product_title=product["title"],
            ad_script=ad_script,
            ai_image_paths=img_paths,
            persona_name=persona.get("name", ""),
            voice_speed=settings.get("voice_speed", 140),
            voice_type=settings.get("voice_type", "elevenlabs"),
            voice_id=settings.get("voice_id", ""),
            music_volume=0.20,
        )
        if result.get("error"):
            update_product_step(batch_id, idx, "ad_creative", "error", error=result["error"])
        else:
            update_product_step(batch_id, idx, "ad_creative", "done", result=result)
    except Exception as e:
        update_product_step(batch_id, idx, "ad_creative", "error", error=str(e)[:200])


async def retry_step(batch_id: str, idx: int, step: str):
    """Retry a specific step for a product."""
    job = _load(batch_id)
    if not job or idx >= len(job["products"]):
        return
    product = job["products"][idx]
    settings = job.get("settings", {})

    if step == "persona":
        await run_personas(batch_id)  # re-runs all pending
    elif step == "review":
        await _run_review(batch_id, idx, product, settings)
    elif step == "audio":
        await _run_audio(batch_id, idx, product, settings)
    elif step == "ai_images":
        await _run_ai_images(batch_id, idx, product, settings)
    elif step == "video":
        await _run_video(batch_id, idx, product, settings)
    elif step == "ad_creative":
        await _run_ad_creative(batch_id, idx, product, settings)
