"""Product review pipeline — reusable orchestration for single and batch generation."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from config import log, make_ts, output_path, output_url, OUTPUT_DIR, AFFIPAD_API_KEY, AFFIPAD_TOOL_ID, BITLY_API_KEY, SHORTIO_API_KEY, SHORTIO_DOMAIN
from extractor import BookInfo, extract_from_shopee, download_images
from reviewer import generate_review_all_platforms, generate_json
from tts import generate_audio

PERSONA_MODEL = "gemini-2.5-flash-lite"  # cheap model for persona suggestion
REVIEW_MODEL = ""  # empty = use default model from config


@dataclass
class PipelineInput:
    url: str
    audience: str = "phu-huynh-lop-5"
    custom_audience: dict | None = None
    affiliate_url: str = ""
    word_count_fb: int = 200
    word_count_tk: int = 150
    image_urls: list[str] = field(default_factory=list)
    voice_type: str = "elevenlabs"
    elevenlabs_voice_id: str = "T4jrQr9x0Y24833yKCWR"  # Thuý Hà V1
    platforms: list[str] = field(default_factory=lambda: ["facebook", "tiktok"])


@dataclass
class PipelineResult:
    ts: str
    review_data: dict
    product_images: list[str] = field(default_factory=list)
    review_json_path: str = ""
    error: str = ""


async def _shorten_url(client, long_url: str) -> str:
    """Shorten a URL using Short.io or Bitly."""
    # Try Short.io (1000 free/month)
    if SHORTIO_API_KEY and SHORTIO_DOMAIN:
        try:
            r = await client.post("https://api.short.io/links", headers={
                "Authorization": SHORTIO_API_KEY, "Content-Type": "application/json",
            }, json={"domain": SHORTIO_DOMAIN, "originalURL": long_url}, timeout=10)
            if r.status_code in (200, 201):
                return r.json().get("shortURL", "")
        except Exception as e:
            log.warning(f"shortio: Failed: {e}")
    # Try Bitly
    if BITLY_API_KEY:
        try:
            r = await client.post("https://api-ssl.bitly.com/v4/shorten", headers={
                "Authorization": f"Bearer {BITLY_API_KEY}", "Content-Type": "application/json",
            }, json={"long_url": long_url}, timeout=10)
            if r.status_code in (200, 201):
                return r.json().get("link", "")
        except Exception as e:
            log.warning(f"bitly: Failed: {e}")
    return ""


async def convert_to_affiliate_link(product_url: str) -> str:
    """Convert a Shopee product URL to a short affiliate link via AffiPad + TinyURL."""
    log.info(f"affipad: API_KEY: {'set' if AFFIPAD_API_KEY else 'MISSING'}, TOOL_ID: {'set' if AFFIPAD_TOOL_ID else 'MISSING'}")
    if not AFFIPAD_API_KEY or not AFFIPAD_TOOL_ID:
        return ""
    try:
        import httpx
        from urllib.parse import quote
        async with httpx.AsyncClient(timeout=15) as client:
            # Step 1: Get affiliate link from AffiPad
            resp = await client.post(
                "https://api.affipad.com/v1/fb-convert",
                headers={"Authorization": f"Bearer {AFFIPAD_API_KEY}", "Content-Type": "application/json"},
                json={"url": product_url, "toolId": AFFIPAD_TOOL_ID},
            )
            data = resp.json()
            if not data.get("success"):
                return ""
            results = data.get("data", {}).get("results", [])
            if not results:
                return ""
            long_link = results[0].get("link", "")
            if not long_link:
                return ""

            # Shorten link: try Short.io (1000 free/month), then Bitly, then raw
            if long_link:
                short = await _shorten_url(client, long_link)
                if short:
                    return short
            return long_link
    except Exception as e:
        log.warning(f"affipad:: {e}")
    return ""


async def process_product(inp: PipelineInput) -> PipelineResult:
    """Full pipeline — each step independent, partial results saved on failure."""
    ts = make_ts()
    result = {"book": {}, "audience": inp.audience, "audience_name": inp.custom_audience.get("name", "") if isinstance(inp.custom_audience, dict) else ""}
    images = []

    # Step 1: Extract product info
    try:
        book = await extract_from_shopee(inp.url)
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
            aff_link = await convert_to_affiliate_link(inp.url)
            if aff_link:
                book.shopee_url = aff_link
                result["book"]["shopee_url"] = aff_link
    except Exception as e:
        log.warning(f"Affiliate failed (continuing): {e}")

    # Step 3: Generate reviews — each platform independent
    for platform, wc in [("facebook", min(inp.word_count_fb, 300)), ("tiktok", min(inp.word_count_tk, 150))]:
        if platform not in inp.platforms:
            continue
        try:
            import asyncio
            from reviewer import generate_review
            review = await asyncio.to_thread(generate_review, book, inp.audience, platform, inp.custom_audience, wc)
            result[platform] = review
            log.info(f"{platform} review generated")
        except Exception as e:
            result[platform] = {"social_post": "", "review": f"Error: {e}", "hashtags": [], "hook": "", "key_points": [], "cta": ""}
            log.warning(f"{platform} review failed (continuing): {e}")

    # Step 4: Audio — each platform independent
    try:
        result = await _add_audio(result, ts, inp.voice_type, inp.elevenlabs_voice_id)
        log.info(f"Audio generated")
    except Exception as e:
        log.warning(f"Audio failed (continuing): {e}")

    # Step 5: Resolve images (non-blocking)
    try:
        images = await _resolve_images(inp.image_urls, book, ts)
        log.info(f"Images resolved: {len(images)}")
    except Exception as e:
        log.warning(f"Image resolve failed (continuing): {e}")

    # Step 6: AI images (non-blocking, separate from review)
    try:
        if len(images) < 12:
            from imagegen import generate_lifestyle_images, MAX_AI_IMAGES
            persona = inp.custom_audience or {"name": "Khách hàng phổ thông", "focus": "chất lượng sản phẩm"}
            num_ai = min(MAX_AI_IMAGES, 12 - len(images))
            ai_images = await generate_lifestyle_images(book.title, persona, num_ai, ts, images[:3] if images else [])
            images.extend(ai_images)
            log.info(f"AI images: {len(ai_images)} generated")
    except Exception as e:
        log.warning(f"AI image gen failed (continuing): {e}")

    # Shuffle: 1 AI image first, 1 AI image last, rest randomized in middle
    import random
    ai = [img for img in images if "ai_images" in img]
    real = [img for img in images if "ai_images" not in img]
    if len(ai) >= 2:
        first_ai = ai[0]
        last_ai = ai[-1]
        middle = real + ai[1:-1]
        random.shuffle(middle)
        images = [first_ai] + middle + [last_ai]
    elif len(ai) == 1:
        random.shuffle(real)
        images = [ai[0]] + real
    else:
        random.shuffle(images)

    result["product_images"] = images
    result["affiliate_link"] = book.shopee_url or ""

    # Save whatever we have
    out = output_path(ts, "review.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    return PipelineResult(ts=ts, review_data=result, product_images=images, review_json_path=str(out))


async def process_batch(inputs: list[PipelineInput]) -> list[PipelineResult]:
    """Process multiple products sequentially."""
    results = []
    for inp in inputs:
        results.append(await process_product(inp))
    return results


async def _add_audio(result: dict, ts: str, voice_type: str = "gtts", elevenlabs_voice_id: str = "") -> dict:
    """Generate voice narration for each platform's social_post."""
    for platform in ["facebook", "tiktok"]:
        data = result.get(platform)
        if not data:
            continue
        text = data.get("social_post", "")
        if not text:
            continue
        suffix = f"{platform}.mp3"
        audio_path = str(output_path(ts, suffix))
        await generate_audio(text, audio_path, voice_type=voice_type, elevenlabs_voice_id=elevenlabs_voice_id)
        data["audio_url"] = output_url(ts, suffix)
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


def _get_default_music(product_title: str = "", persona_name: str = "") -> str | None:
    """Get background music — LLM picks genre, then fetch from Freesound and cache."""
    import random, os
    music_dir = Path(__file__).parent / "music"
    music_dir.mkdir(exist_ok=True)

    # Pick genre by keyword matching
    genre = "lofi"
    if product_title:
        t = product_title.lower()
        if any(w in t for w in ["trẻ em", "bé", "mầm non", "thiếu nhi", "đồ chơi"]):
            genre = "happy"
        elif any(w in t for w in ["sách", "book", "học", "giáo dục"]):
            genre = "acoustic"
        elif any(w in t for w in ["thời trang", "áo", "quần", "váy", "giày"]):
            genre = "lofi"
        elif any(w in t for w in ["công nghệ", "laptop", "điện thoại", "tai nghe"]):
            genre = "corporate"
        elif any(w in t for w in ["mỹ phẩm", "skincare", "serum", "kem"]):
            genre = "piano"

    # Check cache for this genre
    cached = list(music_dir.glob(f"{genre}_*.mp3"))
    if cached:
        return str(random.choice(cached))

    # Fetch from Freesound
    try:
        import httpx
        api_key = os.getenv("FREESOUND_API_KEY", "")
        if not api_key:
            return None
        r = httpx.get("https://freesound.org/apiv2/search/text/", params={
            "token": api_key, "query": f"{genre} background",
            "filter": "duration:[15 TO 60]",
            "fields": "id,name,previews", "page_size": "5", "sort": "rating_desc",
        }, timeout=10)
        results = r.json().get("results", [])
        if results:
            url = random.choice(results).get("previews", {}).get("preview-hq-mp3", "")
            if url:
                audio = httpx.get(url, timeout=15, follow_redirects=True)
                if audio.status_code == 200:
                    cached_path = music_dir / f"{genre}_{random.randint(1000,9999)}.mp3"
                    cached_path.write_bytes(audio.content)
                    return str(cached_path)
    except Exception:
        pass
    return None


@dataclass
class VideoInput:
    review_data: dict
    platform: str = "tiktok"
    selected_images: list[str] = field(default_factory=list)
    uploaded_media: list[tuple[str, bytes]] = field(default_factory=list)  # (filename, data)
    music_url: str = ""
    music_data: bytes | None = None
    music_volume: int = 15
    aspect_ratio: str = "9:16"
    voice_speed: int = 75
    logo_data: bytes | None = None
    logo_position: str = "top-right"
    subtitle_style: str = "tiktok"
    highlight_color: str = "#FFD700"
    img_effect: str = "ken_burns"
    img_style: str = "none"
    zoom_ratio: int = 15
    show_intro: bool = True
    show_outro: bool = True
    preview_only: bool = False
    intro_bg_url: str = ""
    outro_bg_url: str = ""
    pdf_path: str = ""


async def render_video(inp: VideoInput) -> dict:
    """Prepare assets and render video. Returns {"video_url", "srt_url"} or {"preview_url"}."""
    from video import generate_tiktok_video, generate_srt, extract_cover_from_pdf
    import httpx

    data = inp.review_data
    platform_data = data.get(inp.platform, data.get("tiktok", {}))
    book = data.get("book", {})
    ts = make_ts()

    # Resolve selected images to local paths
    media_paths = []
    for img_url in inp.selected_images[:16]:
        local = str(Path(".") / img_url.lstrip("/"))
        if Path(local).exists():
            media_paths.append(local)

    # Add uploaded files
    if inp.uploaded_media:
        media_dir = output_path(ts, "video_media")
        media_dir.mkdir(parents=True, exist_ok=True)
        for i, (filename, file_data) in enumerate(inp.uploaded_media[:16]):
            ext = Path(filename).suffix or ".jpg"
            p = media_dir / f"media_{i}{ext}"
            p.write_bytes(file_data)
            media_paths.append(str(p))

    media_paths = media_paths[:16]

    # Fallback: product_images from review data
    if not media_paths and data.get("product_images"):
        for img_url in data["product_images"][:4]:
            local = str(Path(".") / img_url.lstrip("/"))
            if Path(local).exists():
                media_paths.append(local)

    # Fallback: PDF cover
    cover_path = None
    if not media_paths and inp.pdf_path and Path(inp.pdf_path).exists():
        cover_path = str(output_path(ts, "cover.png"))
        cover_path = extract_cover_from_pdf(inp.pdf_path, cover_path)

    # Audio
    audio_url = platform_data.get("audio_url", "")
    if audio_url:
        audio_path = str(Path(OUTPUT_DIR) / audio_url.split("/")[-1])
    else:
        audio_path = str(output_path(ts, f"{inp.platform}.mp3"))
        await generate_audio(platform_data.get("social_post", ""), audio_path, speed=100 + inp.voice_speed)

    # Music — auto-fetch if none selected
    local_music = None
    if inp.music_data:
        local_music = str(output_path(ts, "music.mp3"))
        Path(local_music).write_bytes(inp.music_data)
    elif inp.music_url and inp.music_url.startswith("http"):
        local_music = str(output_path(ts, "music.mp3"))
        r = httpx.get(inp.music_url, timeout=30, follow_redirects=True)
        if r.status_code == 200:
            Path(local_music).write_bytes(r.content)
        else:
            local_music = None
    elif inp.music_url:
        local_music = inp.music_url
    if not local_music:
        local_music = _get_default_music(book.get("title", ""), platform_data.get("social_post", "")[:50])

    # Logo
    logo_path = None
    if inp.logo_data:
        logo_path = str(output_path(ts, "logo.png"))
        Path(logo_path).write_bytes(inp.logo_data)

    # Intro/outro backgrounds
    intro_bg_path = None
    if inp.intro_bg_url:
        local = str(Path(".") / inp.intro_bg_url.lstrip("/"))
        if Path(local).exists():
            intro_bg_path = local
    outro_bg_path = None
    if inp.outro_bg_url:
        local = str(Path(".") / inp.outro_bg_url.lstrip("/"))
        if Path(local).exists():
            outro_bg_path = local

    # Render
    video_path = str(output_path(ts, f"{inp.platform}.mp4"))
    generate_tiktok_video(
        audio_path=audio_path, output_path=video_path,
        book_title=book.get("title", ""),
        social_post=platform_data.get("social_post", ""),
        hook=platform_data.get("hook", ""),
        key_points=platform_data.get("key_points", []),
        cta=platform_data.get("cta", ""),
        cover_image_path=cover_path, media_paths=media_paths,
        music_file=local_music,
        music_volume=max(0, min(50, inp.music_volume)) / 100,
        aspect_ratio=inp.aspect_ratio,
        logo_path=logo_path, logo_position=inp.logo_position,
        subtitle_style=inp.subtitle_style, highlight_color=inp.highlight_color,
        img_effect=inp.img_effect, img_style=inp.img_style,
        zoom_ratio=max(5, min(100, inp.zoom_ratio)) / 100,
        show_intro=inp.show_intro, show_outro=inp.show_outro,
        preview_only=inp.preview_only,
        intro_bg_path=intro_bg_path, outro_bg_path=outro_bg_path,
        persona_name=data.get("audience_name", ""),
    )

    # Cleanup temp files
    if local_music and ts in str(local_music):
        Path(local_music).unlink(missing_ok=True)
    if cover_path and Path(cover_path).exists():
        Path(cover_path).unlink(missing_ok=True)
    if logo_path and Path(logo_path).exists():
        Path(logo_path).unlink(missing_ok=True)

    if inp.preview_only:
        preview_img = str(output_path(ts, "preview.png"))
        return {"preview_url": output_url(ts, "preview.png")} if Path(preview_img).exists() else {"preview_url": output_url(ts, f"{inp.platform}.mp4")}

    # SRT
    srt_path = str(output_path(ts, f"{inp.platform}.srt"))
    intro_offset = 2.0 if inp.show_intro and book.get("title") else 0.0
    generate_srt(platform_data.get("social_post", ""), audio_path, srt_path, intro_offset)

    return {"video_url": output_url(ts, f"{inp.platform}.mp4"), "srt_url": output_url(ts, f"{inp.platform}.srt")}
