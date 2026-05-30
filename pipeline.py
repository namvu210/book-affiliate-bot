"""Product review pipeline — reusable orchestration for single and batch generation."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from config import log, make_ts, output_path, output_url, OUTPUT_DIR
from extractor import BookInfo, extract_from_shopee, download_images
from reviewer import generate_json
from tts import generate_audio
from affiliate import get_affiliate_link

PERSONA_MODEL = "gemini-2.5-flash-lite"  # cheap model for persona suggestion
REVIEW_MODEL = ""  # empty = use default model from config


@dataclass
class PipelineInput:
    url: str
    audience: str = "phu-huynh-lop-5"
    custom_audience: dict | None = None
    affiliate_url: str = ""
    word_count_fb: int = 150
    word_count_tk: int = 120
    image_urls: list[str] = field(default_factory=list)
    voice_type: str = "edge"
    elevenlabs_voice_id: str = "T4jrQr9x0Y24833yKCWR"
    voice_speed: int = 140
    platforms: list[str] = field(default_factory=lambda: ["facebook", "tiktok"])
    scraped_reviews: list[dict] = field(default_factory=list)
    scraped_rating: float | None = None
    scraped_rating_count: int = 0
    scraped_sold_count: int = 0
    scraped_description: str = ""
    scraped_price: str = ""
    style_id: str = "auto"


@dataclass
class PipelineResult:
    ts: str
    review_data: dict
    product_images: list[str] = field(default_factory=list)
    review_json_path: str = ""
    error: str = ""


async def process_product(inp: PipelineInput) -> PipelineResult:
    """Full pipeline — each step independent, partial results saved on failure."""
    ts = make_ts()
    result = {"book": {}, "audience": inp.audience, "audience_name": inp.custom_audience.get("name", "") if isinstance(inp.custom_audience, dict) else ""}
    images = []

    # Step 1: Extract product info
    try:
        book = await extract_from_shopee(inp.url)
        # Enrich with scraped data from extension
        if inp.scraped_rating and not book.rating:
            book.rating = inp.scraped_rating
        if inp.scraped_rating_count and not book.rating_count:
            book.rating_count = inp.scraped_rating_count
        if inp.scraped_sold_count and not book.sold_count:
            book.sold_count = inp.scraped_sold_count
        if inp.scraped_reviews and not book.reviews:
            book.reviews = inp.scraped_reviews
        if inp.scraped_description and not book.description:
            book.description = inp.scraped_description
        if inp.scraped_price and not book.price:
            book.price = inp.scraped_price
        result["book"] = {
            "title": book.title, "author": book.author, "price": book.price,
            "shopee_url": book.shopee_url, "source": book.source,
        }
    except Exception as e:
        log.error(f"Extract failed: {e}")
        return PipelineResult(ts=ts, review_data=result, error=f"Extract failed: {e}")

    # Step 2: Affiliate link (non-blocking)
    try:
        if inp.affiliate_url:
            book.shopee_url = inp.affiliate_url
            result["book"]["shopee_url"] = inp.affiliate_url
        else:
            aff_link = await get_affiliate_link(inp.url)
            if aff_link:
                book.shopee_url = aff_link
                result["book"]["shopee_url"] = aff_link
    except Exception as e:
        log.warning(f"Affiliate failed (continuing): {e}")

    # Step 3: Generate ONE review (used for video + all platforms)
    import asyncio
    from reviewer import generate_review
    _fallback = {"social_post": "", "review": "", "hashtags": [], "hook": "", "key_points": [], "cta": ""}
    try:
        review = await asyncio.to_thread(generate_review, book, inp.audience, "facebook", inp.custom_audience, inp.word_count_fb, inp.style_id)
        log.info(f"Review generated ({len(review.get('social_post',''))} chars)")
    except Exception as e:
        review = {**_fallback, "review": f"Error: {e}"}
        log.warning(f"Review failed: {e}")
    # Share same review data across all platforms
    for platform in inp.platforms:
        result[platform] = dict(review)

    # Step 4: Audio — skipped, user generates manually via "Tạo giọng nói"

    # Step 5: Resolve images (non-blocking)
    try:
        images = await _resolve_images(inp.image_urls, book, ts)
        log.info(f"Images resolved: {len(images)}")
    except Exception as e:
        log.warning(f"Image resolve failed (continuing): {e}")

    # Step 6: AI images — only if user provided 5-14 images (sweet spot for mixing)
    try:
        if 5 <= len(images) <= 14:
            from imagegen import generate_lifestyle_images, MAX_AI_IMAGES
            persona = inp.custom_audience or {"name": "Khách hàng phổ thông", "focus": "chất lượng sản phẩm"}
            num_ai = 3 if len(images) <= 7 else 2 if len(images) <= 10 else 1
            ai_images = await generate_lifestyle_images(book.title, persona, num_ai, ts, images[:3] if images else [])
            images.extend(ai_images)
            log.info(f"AI images: {len(ai_images)} generated (real={len(images)-len(ai_images)})")
        else:
            log.info(f"AI images skipped: {len(images)} real images (need 5-14)")
    except Exception as e:
        log.warning(f"AI image gen failed (continuing): {e}")

    # Order: AI first + AI last (eye-catching), real images keep user order in middle
    ai = [img for img in images if "ai_images" in img]
    real = [img for img in images if "ai_images" not in img]
    if len(ai) >= 2:
        images = [ai[0]] + real + ai[1:-1] + [ai[-1]]
    elif len(ai) == 1:
        images = [ai[0]] + real
    # else: keep real images in original order

    images = images[:16]

    result["product_images"] = images
    result["affiliate_link"] = book.shopee_url or ""

    # Save whatever we have
    out = output_path(ts, "review.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    return PipelineResult(ts=ts, review_data=result, product_images=images, review_json_path=str(out))


async def process_batch(inputs: list[PipelineInput]) -> list[PipelineResult]:
    """Process multiple products sequentially."""
    from music import reset_batch_music
    reset_batch_music()
    results = []
    for inp in inputs:
        results.append(await process_product(inp))
    return results


async def _add_audio(result: dict, ts: str, voice_type: str = "edge", elevenlabs_voice_id: str = "", edge_voice: str = "vi-VN-HoaiMyNeural", speed: int = 175) -> dict:
    """Generate ONE voice narration, shared across all platforms."""
    # Find the first platform with content
    text = ""
    cta = ""
    for platform in ["facebook", "tiktok", "youtube"]:
        data = result.get(platform)
        if data and data.get("social_post"):
            text = data["social_post"]
            cta = data.get("cta", "").strip()
            break
    if not text:
        return result
    if cta and cta not in text:
        text = text.rstrip() + " " + cta
    audio_path = str(output_path(ts, "audio.mp3"))
    try:
        await generate_audio(text, audio_path, speed=speed, voice_type=voice_type, elevenlabs_voice_id=elevenlabs_voice_id, edge_voice=edge_voice)
        audio_url = output_url(ts, "audio.mp3")
        for platform in ["facebook", "tiktok", "youtube"]:
            if result.get(platform):
                result[platform]["audio_url"] = audio_url
    except Exception as e:
        log.warning(f"Audio failed: {e}")
    return result


async def _resolve_images(image_urls: list[str], book: BookInfo, ts: str) -> list[str]:
    """Resolve product images — download CDN URLs or use local paths."""
    if image_urls:
        # Check if these are already local paths or need downloading
        remote = [u for u in image_urls if u.startswith("http")]
        if remote:
            img_dir = str(output_path(ts, "images"))
            local = await download_images(remote, img_dir)
            return [f"{output_url(ts, 'images')}/{Path(p).name}" for p in local]
        return image_urls  # already local
    if book.image_urls:
        img_dir = str(output_path(ts, "images"))
        local = await download_images(book.image_urls, img_dir)
        return [f"{output_url(ts, 'images')}/{Path(p).name}" for p in local]
    return []


def suggest_personas_for_product(title: str) -> list[dict]:
    """Use cheap LLM to suggest 3 target customer personas for a product."""
    prompt = f"""Dựa vào sản phẩm "{title}", gợi ý 2 nhóm khách hàng mục tiêu KHÁC NHAU phù hợp nhất.

Mỗi nhóm phải có góc nhìn và nhu cầu khác biệt rõ ràng.

Trả về JSON array, mỗi phần tử có:
- "name": tên nhóm khách hàng (ngắn gọn, tiếng Việt)
- "tone": giọng văn phù hợp khi viết review cho nhóm này
- "focus": trọng tâm nội dung khi viết review cho nhóm này

CHỈ trả về JSON array, không giải thích."""
    try:
        result = generate_json(prompt, max_tokens=500, model=PERSONA_MODEL)
        return result if isinstance(result, list) else []
    except Exception as e:
        log.warning(f"persona-suggest: Failed for '{title[:40]}': {e}")
        return []


@dataclass
class BatchPersonaResult:
    url: str
    title: str
    personas: list[dict] = field(default_factory=list)
    reviews: list[PipelineResult] = field(default_factory=list)
    error: str = ""


async def batch_with_personas(urls: list[str], voice_type: str = "elevenlabs", voice_id: str = "", word_count: int = 150, affiliate_map: dict = None, word_count_fb: int = 200) -> list[BatchPersonaResult]:
    """For each URL: suggest 2 personas, then generate a review for each persona."""
    import asyncio
    from music import reset_batch_music
    reset_batch_music()
    affiliate_map = affiliate_map or {}
    results = []
    for url in urls:
        try:
            book = await extract_from_shopee(url)
            title = book.title or url.split("-i.")[0].split("shopee.vn/")[-1].replace("-", " ")

            personas = await asyncio.to_thread(suggest_personas_for_product, title)
            if not personas:
                personas = [{"name": "Khách hàng phổ thông", "tone": "thân thiện", "focus": "chất lượng sản phẩm"}]

            reviews = []
            for persona in personas[:2]:
                inp = PipelineInput(url=url, custom_audience=persona, word_count_tk=word_count,
                                    word_count_fb=word_count_fb,
                                    voice_type=voice_type, elevenlabs_voice_id=voice_id,
                                    affiliate_url=affiliate_map.get(url, ""))
                r = await process_product(inp)
                reviews.append(r)

            results.append(BatchPersonaResult(url=url, title=title, personas=personas[:2], reviews=reviews))
        except Exception as e:
            results.append(BatchPersonaResult(url=url, title=url, error=str(e)))
    return results


# Re-export from video package for backward compatibility
from video.prepare import VideoInput, render_video
