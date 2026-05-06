"""Product Affiliate Bot — Extract, Review, Voice & Video."""

import json
import logging, os
_log = logging.getLogger("app")
import subprocess
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import AUDIENCES, OUTPUT_DIR, UPLOAD_DIR, GEMINI_MODEL, make_ts, output_path, output_url, DEFAULT_VOICE_SPEED
from extractor import BookInfo, extract_from_pdf, extract_from_shopee, download_images
from reviewer import generate_review, generate_review_all_platforms
from tts import generate_audio
from video import generate_tiktok_video, extract_cover_from_pdf

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Product Affiliate Bot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
async def start_scheduler():
    import asyncio
    from scheduler import check_and_publish

    async def _scheduler_loop():
        while True:
            try:
                await check_and_publish()
            except Exception as e:
                _log.warning(f"Scheduler tick error: {e}")
            await asyncio.sleep(60)

    asyncio.create_task(_scheduler_loop())


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "audiences": AUDIENCES, "default_voice_speed": DEFAULT_VOICE_SPEED, "default_voice_id": os.getenv("ELEVENLABS_VOICE_ID", "")})


@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.get("/tiktok-demo", response_class=HTMLResponse)
async def tiktok_demo(request: Request):
    return templates.TemplateResponse("tiktok-demo.html", {"request": request})


@app.get("/api/elevenlabs-voices")
async def elevenlabs_voices():
    """List available ElevenLabs voices."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"voices": [], "error": "Cần ELEVENLABS_API_KEY trong .env"}
    try:
        from elevenlabs import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        resp = client.voices.get_all()
        voices = [{"id": v.voice_id, "name": v.name, "category": v.category or ""} for v in resp.voices]
        order = {"cloned": 0, "generated": 1, "professional": 2, "premade": 3}
        voices.sort(key=lambda v: (order.get(v["category"], 9), v["name"]))
        return {"voices": voices[:10]}
    except Exception as e:
        return {"voices": [], "error": str(e)[:200]}


@app.get("/api/set-model")
async def set_model(model: str = "gemini-2.5-flash-lite"):
    """Switch Gemini model at runtime."""
    import reviewer
    try:
        reviewer.set_model(model)
        return {"status": "ok", "model": model}
    except Exception as e:
        return {"error": str(e)[:200]}


@app.get("/api/set-image-model")
async def set_image_model(model: str = "gemini-2.5-flash-image"):
    """Switch image generation model at runtime."""
    from imagegen import set_image_model as _set
    _set(model)
    return {"status": "ok", "model": model}


@app.get("/api/models")
async def list_models():
    """List available Gemini models."""
    from google import genai
    from config import GEMINI_API_KEY, GEMINI_MODEL
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models = []
        for m in client.models.list():
            models.append(m.name.replace("models/", ""))
        models = [m for m in models if m.startswith("gemini")]
        return {"models": sorted(models, reverse=True), "current": GEMINI_MODEL}
    except Exception:
        return {"models": [
            "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
        ]}


@app.get("/api/music")
async def get_music(category: str = "", q: str = "", refresh: bool = False, source: str = "freesound"):
    """Search free music from Freesound or Jamendo."""
    from music import search_music
    return await search_music(category, q, refresh, source)


@app.post("/fetch-product-title")
async def fetch_product_title(request: Request):
    """Get product title from AffiPad when URL has no readable slug."""
    data = await request.json()
    url = data.get("url", "")
    api_key = os.getenv("AFFIPAD_API_KEY", "")
    if not api_key or not url:
        return {"title": ""}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("https://api.affipad.com/v1/product-info",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"url": url})
            d = resp.json()
            if d.get("success"):
                return {"title": d["data"]["productInfo"].get("name", "")}
    except Exception:
        pass
    return {"title": ""}


@app.post("/suggest-personas")
async def suggest_personas(title: str = Form(...)):
    """Use LLM to suggest 3 customer personas for a product."""
    from reviewer import generate_json
    prompt = f"""Dựa vào sản phẩm "{title}", gợi ý 3 nhóm khách hàng mục tiêu phù hợp nhất.

Trả về JSON array, mỗi phần tử có:
- "name": tên nhóm khách hàng (ngắn gọn, tiếng Việt)
- "tone": giọng văn phù hợp
- "focus": trọng tâm nội dung khi viết review

CHỈ trả về JSON array, không giải thích."""
    try:
        parsed = generate_json(prompt, max_tokens=500)
        personas = parsed if isinstance(parsed, list) else parsed.get("personas", [])
    except Exception:
        personas = []
    return {"personas": personas}


@app.post("/receive-shopee-data")
async def receive_shopee_data(request: Request):
    """Receive product data sent from bookmarklet running on Shopee page."""
    data = await request.json()
    return await _process_shopee_data(data)


@app.get("/receive-shopee-data")
async def receive_shopee_data_get(data: str = ""):
    """GET fallback for bookmarklet (data as query param)."""
    if data:
        result = await _process_shopee_data(json.loads(data))
        return HTMLResponse("<html><body><script>window.close()</script>OK — bạn có thể đóng tab này.</body></html>")
    return {"error": "No data"}


async def _process_shopee_data(data: dict):
    ts = make_ts()

    image_urls = data.get("images", [])
    video_urls = data.get("videos", [])
    all_media = image_urls + video_urls
    local_images = []
    if all_media:
        img_dir = str(output_path(ts, "images"))
        local_images = await download_images(all_media, img_dir)

    result = {
        "title": data.get("title", ""),
        "price": data.get("price", ""),
        "description": data.get("description", ""),
        "rating": data.get("rating"),
        "rating_count": data.get("rating_count", 0),
        "reviews": data.get("reviews", []),
        "product_images": [f"{output_url(ts, 'images')}/{Path(p).name}" for p in local_images],
        "product_images_original": all_media,
        "url": data.get("url", ""),
    }

    app.state.last_shopee_data = result
    return result


@app.get("/poll-shopee-data")
async def poll_shopee_data():
    """Poll for bookmarklet data."""
    data = getattr(app.state, "last_shopee_data", None)
    if data:
        app.state.last_shopee_data = None  # consume once
        return {"ready": True, "data": data}
    return {"ready": False}


@app.post("/fetch-images")
async def fetch_images(url: str = Form(...)):
    """Fetch product images/videos from Shopee URL without generating review."""
    if "shopee" not in url:
        raise HTTPException(400, "Chỉ hỗ trợ link Shopee")

    book = await extract_from_shopee(url)
    ts = make_ts()

    result = {
        "title": book.title,
        "price": book.price,
        "rating": book.rating,
        "rating_count": book.rating_count,
    }

    if book.image_urls:
        img_dir = str(output_path(ts, "images"))
        local = await download_images(book.image_urls, img_dir)
        result["product_images"] = [f"{output_url(ts, 'images')}/{Path(p).name}" for p in local]

    return result


@app.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    audience: str = Form("phu-huynh-lop-5"),
    custom_audience: str = Form(""),
    word_count: int = Form(150),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Chỉ hỗ trợ file PDF")

    ts = make_ts()
    save_path = Path(UPLOAD_DIR) / f"{ts}_{file.filename}"
    content = await file.read()
    save_path.write_bytes(content)

    book = extract_from_pdf(str(save_path))
    ca = json.loads(custom_audience) if custom_audience else None
    result = generate_review_all_platforms(book, audience, ca, min(word_count, 200))

    from pipeline import _add_audio
    result = await _add_audio(result, ts)

    out_path = output_path(ts, "review.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    result["_pdf_path"] = str(save_path)
    return result


@app.post("/from-url")
async def from_url(
    url: str = Form(...),
    audience: str = Form("phu-huynh-lop-5"),
    custom_audience: str = Form(""),
    affiliate_url: str = Form(""),
    word_count_fb: int = Form(150),
    word_count_tk: int = Form(120),
    platforms: str = Form("facebook,tiktok"),
    bookmarklet_images: str = Form("[]"),
    media: list[UploadFile] = File(default=[]),
):
    if "shopee" not in url:
        raise HTTPException(400, "Hiện chỉ hỗ trợ link Shopee")

    ca = json.loads(custom_audience) if custom_audience else None
    bm_imgs = json.loads(bookmarklet_images)

    # Handle uploaded media files
    uploaded_paths = []
    if media and media[0].filename:
        ts_upload = make_ts()
        img_dir = output_path(ts_upload, "images")
        img_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(media):
            ext = Path(f.filename).suffix or ".jpg"
            save_to = img_dir / f"product_{i}{ext}"
            save_to.write_bytes(await f.read())
            uploaded_paths.append(f"{output_url(ts_upload, 'images')}/product_{i}{ext}")

    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
    from pipeline import PipelineInput, process_product
    inp = PipelineInput(
        url=url, audience=audience, custom_audience=ca,
        affiliate_url=affiliate_url,
        word_count_fb=word_count_fb, word_count_tk=word_count_tk,
        image_urls=uploaded_paths or bm_imgs,
        platforms=platform_list,
    )
    result = await process_product(inp)
    if result.error:
        raise HTTPException(500, result.error)
    return result.review_data


@app.post("/batch-review")
async def batch_review(
    url: str = Form(...),
    audience: str = Form("custom"),
    custom_audience: str = Form(""),
    affiliate_url: str = Form(""),
    word_count_fb: int = Form(150),
    word_count_tk: int = Form(120),
    platforms: str = Form("facebook,tiktok"),
):
    """Step 2a: Generate review text only (no audio, no images)."""
    import asyncio
    from extractor import extract_from_shopee
    from reviewer import generate_review
    from affiliate import get_affiliate_link

    ca = json.loads(custom_audience) if custom_audience else None
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    book = await extract_from_shopee(url)
    if affiliate_url:
        book.shopee_url = affiliate_url
    else:
        aff = await get_affiliate_link(url)
        if aff:
            book.shopee_url = aff

    # Generate reviews in parallel
    review_tasks = []
    review_platforms = []
    for platform, wc in [("facebook", min(word_count_fb, 300)), ("tiktok", min(word_count_tk, 150))]:
        if platform not in platform_list:
            continue
        review_tasks.append(asyncio.to_thread(generate_review, book, audience, platform, ca, wc))
        review_platforms.append(platform)

    result = {"book": {"title": book.title, "author": book.author, "price": book.price, "shopee_url": book.shopee_url, "source": book.source}}
    _fallback = {"social_post": "", "review": "", "hashtags": [], "hook": "", "key_points": [], "cta": ""}
    for platform, outcome in zip(review_platforms, await asyncio.gather(*review_tasks, return_exceptions=True)):
        if isinstance(outcome, Exception):
            result[platform] = {**_fallback, "review": f"Error: {outcome}"}
        else:
            result[platform] = outcome

    result["affiliate_link"] = book.shopee_url or ""
    result["audience_name"] = ca.get("name", "") if ca else ""
    return result


@app.post("/batch-assets")
async def batch_assets(
    review_json: str = Form(...),
    url: str = Form(""),
    platforms: str = Form("facebook,tiktok"),
    voice_type: str = Form("edge"),
    voice_id: str = Form(""),
    edge_voice: str = Form("vi-VN-HoaiMyNeural"),
    voice_speed: str = Form("75"),
    media: list[UploadFile] = File(default=[]),
):
    """Step 2b: Generate audio + images + AI images from existing review data."""
    from tts import generate_audio
    from extractor import download_images, extract_from_shopee

    data = json.loads(review_json)
    ts = make_ts()
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    # Audio — parallel per platform
    import asyncio
    audio_tasks = []
    audio_platforms = []
    for platform in platform_list:
        pdata = data.get(platform)
        if not pdata or not pdata.get("social_post"):
            continue
        text = pdata["social_post"]
        cta = pdata.get("cta", "").strip()
        if cta and cta not in text:
            text = text.rstrip() + " " + cta
        audio_path = str(output_path(ts, f"{platform}.mp3"))
        audio_tasks.append(generate_audio(text, audio_path, voice_type=voice_type, elevenlabs_voice_id=voice_id, edge_voice=edge_voice))
        audio_platforms.append(platform)

    for platform, outcome in zip(audio_platforms, await asyncio.gather(*audio_tasks, return_exceptions=True)):
        if isinstance(outcome, Exception):
            _log.warning(f"Audio {platform} failed: {outcome}")
        else:
            data[platform]["audio_url"] = output_url(ts, f"{platform}.mp3")

    # Images — from uploaded media
    images = []
    if media and media[0].filename:
        img_dir = output_path(ts, "images")
        img_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(media):
            ext = Path(f.filename).suffix or ".jpg"
            save_to = img_dir / f"product_{i}{ext}"
            save_to.write_bytes(await f.read())
            images.append(f"{output_url(ts, 'images')}/product_{i}{ext}")

    # If no uploaded images, try extracting from URL
    if not images and url:
        book = await extract_from_shopee(url)
        if book.image_urls:
            img_dir = str(output_path(ts, "images"))
            local = await download_images(book.image_urls, img_dir)
            images = [f"{output_url(ts, 'images')}/{Path(p).name}" for p in local]

    # AI images
    if 5 <= len(images) <= 14:
        try:
            from imagegen import generate_lifestyle_images
            persona = {"name": data.get("audience_name", "Khách hàng"), "focus": ""}
            num_ai = 4 if len(images) <= 7 else 3 if len(images) <= 10 else 2
            ai_images = await generate_lifestyle_images(data["book"]["title"], persona, num_ai, ts, images[:3])
            images.extend(ai_images)
        except Exception as e:
            _log.warning(f"AI images failed: {e}")

    # Order: AI first/last, real in middle
    ai = [img for img in images if "ai_images" in img]
    real = [img for img in images if "ai_images" not in img]
    if len(ai) >= 2:
        images = [ai[0]] + real + ai[1:-1] + [ai[-1]]
    elif len(ai) == 1:
        images = [ai[0]] + real
    images = images[:16]

    data["product_images"] = images

    # Save review json
    out = output_path(ts, "review.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    return data


@app.get("/api/history")
async def get_history(platform: str = "", days: int = 90):
    """Return publish history, optionally filtered by platform and date range."""
    from history import HISTORY_FILE, FIELDS
    import csv
    from datetime import datetime, timedelta
    if not HISTORY_FILE.exists():
        return {"records": []}
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    records = []
    with open(HISTORY_FILE, 'r', newline='') as f:
        for row in csv.DictReader(f):
            if row.get('published_at', '') < cutoff:
                continue
            if platform and row.get('platform') != platform:
                continue
            records.append(row)
    records.reverse()  # newest first
    return {"records": records}


@app.post("/publish")
async def publish_content(
    review_json: str = Form(...),
    video_url: str = Form(""),
    platforms: str = Form("facebook"),
    page_id: str = Form(""),
    force: str = Form("0"),
):
    """Publish video + caption to social platforms."""
    from poster import publish, build_post_request
    from history import check_duplicate, record_publish
    try:
        data = json.loads(review_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid review JSON")
    if not isinstance(data, dict):
        raise HTTPException(400, "review_json must be a JSON object")
    valid_platforms = {"facebook", "tiktok", "youtube"}
    platform_list = [p.strip() for p in platforms.split(",") if p.strip() in valid_platforms]
    if not platform_list:
        raise HTTPException(400, f"No valid platform. Choose from: {', '.join(valid_platforms)}")

    # Duplicate check
    book = data.get("book", {})
    product_url = book.get("shopee_url", "")
    if product_url and force != "1":
        warnings = []
        for plat in platform_list:
            prev = check_duplicate(product_url, plat)
            if prev:
                warnings.append(f"{plat}: đã đăng ngày {prev['published_at'][:10]}")
        if warnings:
            return {"duplicate_warning": True, "warnings": warnings, "message": "Sản phẩm đã được đăng trước đó. Đăng lại?"}

    req = build_post_request(data, video_url, platform_list[0])
    req.platforms = platform_list
    req.page_id = page_id
    results = await publish(req)

    # Record successful publishes
    product_images = data.get("product_images", [])
    ai_imgs = [p for p in product_images if "ai_images" in p]
    real_imgs = [p for p in product_images if "ai_images" not in p]
    for r in results:
        if r.success:
            plat_data = data.get(r.platform, {})
            record_publish(
                product_url, book.get("shopee_url", ""), r.platform, book.get("title", ""),
                persona=data.get("audience_name", ""),
                hook=plat_data.get("hook", ""),
                cta=plat_data.get("cta", ""),
                review_text=plat_data.get("social_post", ""),
                images=real_imgs, ai_images=ai_imgs, video_path=video_url,
            )

    return {"results": [{"platform": r.platform, "success": r.success, "message": r.message, "post_id": r.post_id} for r in results]}


@app.post("/schedule")
async def schedule_post(
    review_json: str = Form(...),
    video_url: str = Form(""),
    platform: str = Form("facebook"),
    page_id: str = Form(""),
    slot: str = Form(""),
):
    """Schedule a video for auto-posting at optimal time."""
    from scheduler import add_job, get_slots
    data = json.loads(review_json)
    job = add_job(data, video_url, platform, page_id, slot)
    return {"status": "ok", "job_id": job["id"], "slot": job["slot"], "slots": get_slots()}


@app.get("/api/schedule")
async def get_schedule():
    """List all scheduled and recent jobs."""
    from scheduler import get_all, get_slots
    jobs = get_all()
    return {"jobs": jobs, "slots": get_slots()}


@app.post("/api/schedule/cancel")
async def cancel_scheduled(job_id: str = Form(...)):
    """Cancel a pending scheduled job."""
    from scheduler import cancel_job
    if cancel_job(job_id):
        return {"status": "ok"}
    return {"status": "error", "message": "Job not found or already published"}


@app.post("/api/schedule/slots")
async def update_slots(slot: str = Form(...)):
    """Set custom posting time slot (HH:MM). Added to the 4 fixed slots."""
    from scheduler import set_custom_slot, get_slots
    set_custom_slot(slot.strip())
    return {"status": "ok", "slots": get_slots()}


@app.post("/api/schedule/reschedule")
async def reschedule(job_id: str = Form(...), slot: str = Form(...)):
    """Reschedule a missed/pending job to a new slot."""
    from scheduler import reschedule_job
    if reschedule_job(job_id, slot):
        return {"status": "ok"}
    return {"status": "error", "message": "Job not found"}


@app.post("/api/schedule/publish-now")
async def publish_scheduled_now(job_id: str = Form(...)):
    """Immediately publish a scheduled/missed job."""
    from scheduler import _load_schedule, _mark_done, _mark_failed
    from poster import publish, build_post_request
    jobs = _load_schedule()
    job = next((j for j in jobs if j["id"] == job_id and j["status"] == "pending"), None)
    if not job:
        return {"status": "error", "message": "Job not found"}
    try:
        data = job["review_data"]
        req = build_post_request(data, job["video_url"], job["platform"])
        req.platforms = [job["platform"]]
        req.page_id = job.get("page_id", "")
        results = await publish(req)
        if results and results[0].success:
            _mark_done(job["id"])
            return {"status": "ok", "message": results[0].message}
        else:
            msg = results[0].message if results else "Unknown error"
            _mark_failed(job["id"], msg)
            return {"status": "error", "message": msg}
    except Exception as e:
        _mark_failed(job["id"], str(e))
        return {"status": "error", "message": str(e)}


@app.post("/import-excel")
async def import_excel(file: UploadFile):
    """Parse Excel file with product URLs and affiliate links."""
    from importer import parse_product_excel
    data = await file.read()
    products = parse_product_excel(data)
    if not products:
        raise HTTPException(400, "Không tìm thấy sản phẩm trong file Excel")
    # Enrich unreadable titles via AffiPad
    import httpx
    api_key = os.getenv("AFFIPAD_API_KEY", "")
    if api_key:
        async with httpx.AsyncClient(timeout=10) as client:
            for p in products:
                if p["title"].startswith("product/") or len(p["title"]) < 5:
                    try:
                        resp = await client.post("https://api.affipad.com/v1/product-info",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={"url": p["url"]})
                        info = resp.json()
                        if info.get("success"):
                            p["title"] = info["data"]["productInfo"].get("name", p["title"])
                    except Exception:
                        pass
    return {"products": products}


@app.post("/upload-video")
async def upload_video(video: UploadFile):
    """Save an uploaded video file and return its path for publishing."""
    from config import make_ts, OUTPUT_DIR
    ts = make_ts()
    dest = Path(OUTPUT_DIR) / f"{ts}_upload.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await video.read())
    return {"video_url": f"/output/{ts}_upload.mp4", "path": str(dest)}


@app.post("/batch-personas")
async def batch_personas(
    urls: str = Form(...),
    affiliate_urls: str = Form("{}"),
    voice_type: str = Form("elevenlabs"),
    voice_id: str = Form("T4jrQr9x0Y24833yKCWR"),
    word_count: int = Form(150),
    word_count_fb: int = Form(200),
):
    """Batch: suggest personas per product, generate reviews for each persona."""
    from pipeline import batch_with_personas
    url_list = [u.strip() for u in urls.split("\n") if u.strip().startswith("http")]
    if not url_list:
        raise HTTPException(400, "Nhập ít nhất 1 link Shopee")
    aff_map = json.loads(affiliate_urls) if affiliate_urls else {}
    results = await batch_with_personas(url_list[:10], voice_type, voice_id, word_count, aff_map, word_count_fb)
    return {"results": [
        {
            "url": r.url,
            "title": r.title,
            "error": r.error,
            "personas": r.personas,
            "reviews": [
                {"persona": r.personas[i] if i < len(r.personas) else {},
                 "data": rv.review_data, "error": rv.error}
                for i, rv in enumerate(r.reviews)
            ],
        } for r in results
    ]}


@app.post("/preview")
async def preview_review(
    title: str = Form(...),
    author: str = Form(""),
    description: str = Form(""),
    audience: str = Form("phu-huynh-lop-5"),
    platform: str = Form("facebook"),
):
    """Quick preview: manually enter book info, get a review for one platform."""
    book = BookInfo(
        title=title,
        author=author or "Không rõ tác giả",
        description=description,
    )
    result = generate_review(book, audience, platform)

    # Generate audio for preview too
    ts = make_ts()
    text = result.get("social_post", result.get("review", ""))
    if text:
        suffix = f"{platform}.mp3"
        await generate_audio(text, str(output_path(ts, suffix)))
        result["audio_url"] = output_url(ts, suffix)

    return result



@app.post("/generate-speech")
async def generate_speech(
    text: str = Form(...),
    platform: str = Form("tiktok"),
    voice_type: str = Form("gtts"),
    elevenlabs_voice_id: str = Form(""),
    speed: int = Form(125),
):
    """Generate speech audio from edited text."""
    ts = make_ts()
    suffix = f"{platform}.mp3"
    audio_path = str(output_path(ts, suffix))
    await generate_audio(text, audio_path, speed=speed, voice_type=voice_type, elevenlabs_voice_id=elevenlabs_voice_id)
    return {"audio_url": output_url(ts, suffix)}


@app.post("/upload-voice")
async def upload_voice(file: UploadFile = File(...), ref_text: str = Form("")):
    """Upload voice sample for cloning."""
    from tts import save_voice_sample, VOICE_DIR
    data = await file.read()
    save_voice_sample(data, file.filename)
    # Save ref_text
    if ref_text.strip():
        (VOICE_DIR / "ref_text.txt").write_text(ref_text.strip())
    return {"status": "ok", "message": "✅ Đã lưu mẫu giọng nói!"}


@app.get("/api/voice-status")
async def voice_status():
    """Check if voice sample exists."""
    from tts import get_voice_sample
    return {"has_voice": get_voice_sample() is not None}


@app.post("/upload-kol")
async def upload_kol(file: UploadFile = File(...), slot: int = Form(1)):
    """Upload KOL reference photo (slot 1=front, 2=side angle)."""
    from imagegen import save_kol_photo, get_kol_photos
    data = await file.read()
    save_kol_photo(data, file.filename, slot=min(max(slot, 1), 2))
    count = len(get_kol_photos())
    return {"status": "ok", "count": count, "message": f"✅ Đã lưu ảnh KOL #{slot}! ({count}/2)"}


@app.post("/regen-review")
async def regen_review(
    platform: str = Form(...),
    title: str = Form(""),
    author: str = Form(""),
    description: str = Form(""),
    shopee_url: str = Form(""),
    audience: str = Form("phu-huynh-lop-5"),
    custom_audience: str = Form(""),
    word_count: int = Form(150),
):
    """Regenerate review for a single platform."""
    from reviewer import generate_review
    ca = json.loads(custom_audience) if custom_audience else None
    book = BookInfo(title=title, author=author or "Không rõ tác giả", description=description, shopee_url=shopee_url)
    result = generate_review(book, audience, platform, ca, word_count)
    return result


@app.post("/generate-ai-images")
async def generate_ai_images_endpoint(
    title: str = Form(...),
    persona_name: str = Form("Khách hàng"),
    persona_focus: str = Form("chất lượng sản phẩm"),
    product_images: str = Form("[]"),
):
    """Generate AI lifestyle images independently — retryable without regenerating reviews."""
    from imagegen import generate_lifestyle_images, MAX_AI_IMAGES
    ts = make_ts()
    imgs = json.loads(product_images)
    persona = {"name": persona_name, "focus": persona_focus}
    ai_images = await generate_lifestyle_images(title, persona, MAX_AI_IMAGES, ts, imgs[:3])
    return {"ai_images": ai_images}


@app.post("/regenerate-image")
async def regenerate_image(
    scene: str = Form(...),
    product_image: str = Form(""),
):
    """Regenerate a single AI lifestyle image."""
    from imagegen import get_kol_photo, EDIT_MODEL
    from google import genai
    from google.genai import types as gtypes
    from PIL import Image as PILImage

    ts = make_ts()
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

    contents = []
    kol_path = get_kol_photo()
    if kol_path:
        try:
            contents.append(PILImage.open(kol_path))
            contents.append("Above: KOL reference. Match this person.")
        except Exception:
            pass
    if product_image:
        local = str(Path(".") / product_image.lstrip("/"))
        if Path(local).exists():
            try:
                contents.append(PILImage.open(local))
                contents.append("Above: Real product. Keep appearance identical.")
            except Exception:
                pass
    contents.append(f"Create a new lifestyle photo: {scene} The product must look exactly like the reference photo.")

    try:
        result = client.models.generate_content(
            model=EDIT_MODEL,
            contents=contents,
            config=gtypes.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        candidates = result.candidates or []
        if not candidates:
            _log.warning(f"regen: No candidates returned. Prompt filter: {getattr(result, 'prompt_feedback', 'none')}")
            raise HTTPException(500, "Gemini blocked or returned no image — try a different product")
        for part in (candidates[0].content.parts if candidates[0].content else []):
            if part.inline_data:
                img_path = output_path(ts, "regen.png")
                Path(str(img_path)).write_bytes(part.inline_data.data)
                return {"image_url": output_url(ts, "regen.png")}
        _log.warning(f"regen: Candidates returned but no image data. Finish reason: {getattr(candidates[0], 'finish_reason', 'unknown')}")
        raise HTTPException(500, "Gemini returned no image — try again")
    except HTTPException:
        raise
    except Exception as e:
        _log.warning(f"regen: Error: {type(e).__name__}: {e}")
        raise HTTPException(500, str(e))
    raise HTTPException(500, "No image generated")


@app.get("/api/kol-status")
async def kol_status():
    """Check KOL reference photos status."""
    from imagegen import get_kol_photos
    photos = get_kol_photos()
    return {"has_kol": len(photos) > 0, "count": len(photos)}


@app.get("/api/facebook-pages")
async def facebook_pages():
    """List connected Facebook pages."""
    from auth import get_facebook_pages
    pages = get_facebook_pages()
    return {"pages": [{"page_id": p["page_id"], "name": p["display_name"]} for p in pages]}


# === Platform OAuth ===

@app.get("/api/platforms")
async def platform_status():
    """Check which social platforms are connected."""
    from auth import get_platform_status
    return get_platform_status()


@app.get("/connect/{platform}")
async def connect_platform(platform: str, request: Request):
    """Redirect to OAuth login for a platform."""
    from auth import tiktok_auth_url, youtube_auth_url, facebook_auth_url
    if platform == "tiktok":
        origin = f"{request.url.scheme}://{request.url.netloc}"
        url = tiktok_auth_url(server_origin=origin)
    else:
        urls = {"youtube": youtube_auth_url, "facebook": facebook_auth_url}
        fn = urls.get(platform)
        if not fn:
            raise HTTPException(400, f"Unknown platform: {platform}")
        url = fn()
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)


@app.get("/callback/{platform}")
async def oauth_callback(platform: str, code: str = ""):
    """Handle OAuth callback from platforms."""
    if not code:
        return HTMLResponse("<html><body><h2>❌ Lỗi: không nhận được mã xác thực</h2></body></html>")
    from auth import tiktok_exchange_code, youtube_exchange_code, facebook_exchange_code, save_platform_token
    exchangers = {"tiktok": tiktok_exchange_code, "youtube": youtube_exchange_code, "facebook": facebook_exchange_code}
    fn = exchangers.get(platform)
    if not fn:
        return HTMLResponse(f"<html><body><h2>❌ Unknown platform: {platform}</h2></body></html>")
    token_data = await fn(code)
    if token_data and token_data.get("access_token"):
        save_platform_token(platform, token_data)
        name = token_data.get("display_name", platform)
        return HTMLResponse(f"<html><body><h2>✅ Đã kết nối {name}!</h2><p>Bạn có thể đóng tab này.</p><script>window.close()</script></body></html>")
    return HTMLResponse("<html><body><h2>❌ Kết nối thất bại. Thử lại.</h2></body></html>")


@app.post("/disconnect/{platform}")
async def disconnect(platform: str):
    """Disconnect a platform."""
    from auth import disconnect_platform
    disconnect_platform(platform)
    return {"status": "ok"}


@app.get("/api/settings")
async def get_settings():
    """Return which credentials are configured (not the values)."""
    keys = ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET",
            "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
            "FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET",
            "ELEVENLABS_API_KEY", "AFFIPAD_API_KEY", "BITLY_API_KEY", "GEMINI_API_KEY"]
    return {k: bool(os.getenv(k, "")) for k in keys}


@app.post("/api/settings")
async def save_settings(request: Request):
    """Save credentials to .env file."""
    data = await request.json()
    env_path = Path(".env")
    existing = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
    # Update with new values (only non-empty)
    for k, v in data.items():
        if v and v.strip():
            existing[k] = v.strip()
    env_path.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")
    return {"status": "ok", "message": "✅ Đã lưu. Khởi động lại server để áp dụng."}


# === Template System ===
TEMPLATE_DIR = Path("templates_video")
TEMPLATE_DIR.mkdir(exist_ok=True)


@app.get("/api/templates")
async def list_templates():
    templates = []
    for f in sorted(TEMPLATE_DIR.glob("*.json")):
        templates.append({"name": f.stem, "file": f.name})
    return {"templates": templates}


@app.post("/api/templates")
async def save_template(name: str = Form(...), config: str = Form(...)):
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
    (TEMPLATE_DIR / f"{safe_name}.json").write_text(config)
    return {"status": "ok", "name": safe_name}


@app.get("/api/templates/{name}")
async def load_template(name: str):
    f = TEMPLATE_DIR / f"{name}.json"
    if not f.exists():
        raise HTTPException(404, "Template không tồn tại")
    return json.loads(f.read_text())


@app.delete("/api/templates/{name}")
async def delete_template(name: str):
    f = TEMPLATE_DIR / f"{name}.json"
    f.unlink(missing_ok=True)
    return {"status": "ok"}


# === Auto-cut product video ===
@app.post("/auto-cut-video")
async def auto_cut_video(
    video: UploadFile = File(...),
    max_duration: int = Form(30),
):
    """Auto-trim uploaded video to max_duration, extract best segment."""
    ts = make_ts()
    input_path = str(output_path(ts, "raw.mp4"))
    Path(input_path).write_bytes(await video.read())

    # Get video duration
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", input_path],
        capture_output=True, text=True, timeout=10,
    )
    total_dur = float(probe.stdout.strip()) if probe.stdout.strip() else 0

    cut_path = str(output_path(ts, "cut.mp4"))

    if total_dur <= max_duration:
        # Already short enough, just copy
        Path(input_path).rename(cut_path)
    else:
        # Take middle segment for best content
        start = max(0, (total_dur - max_duration) / 2)
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start), "-i", input_path,
             "-t", str(max_duration), "-c:v", "libx264", "-c:a", "aac",
             "-vf", f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
             cut_path],
            capture_output=True, timeout=120,
        )
        Path(input_path).unlink(missing_ok=True)

    return {
        "video_url": output_url(ts, "cut.mp4"),
        "original_duration": round(total_dur, 1),
        "cut_duration": min(total_dur, max_duration),
    }


@app.post("/generate-video")
async def generate_video(
    review_json: str = Form(...),
    pdf_path: str = Form(""),
    platform: str = Form("tiktok"),
    selected_images: str = Form("[]"),
    music_file: str = Form(""),
    music_volume: int = Form(15),
    aspect_ratio: str = Form("9:16"),
    voice_speed: int = Form(75),
    logo_position: str = Form("top-right"),
    logo_text: str = Form(""),
    logo: UploadFile = File(default=None),
    subtitle_style: str = Form("tiktok"),
    highlight_color: str = Form("#FFD700"),
    img_effect: str = Form("ken_burns"),
    img_style: str = Form("none"),
    zoom_ratio: int = Form(15),
    show_intro: str = Form("1"),
    show_outro: str = Form("1"),
    preview_only: str = Form("0"),
    intro_bg_url: str = Form(""),
    outro_bg_url: str = Form(""),
    music_upload: UploadFile = File(default=None),
    media: list[UploadFile] = File(default=[]),
):
    """Generate Reels/TikTok video with karaoke text over product images."""
    from pipeline import VideoInput, render_video

    # Read uploaded files into bytes (can't pass UploadFile to pipeline)
    uploaded_media = []
    if media and media[0].filename:
        for f in media[:16]:
            uploaded_media.append((f.filename, await f.read()))

    inp = VideoInput(
        review_data=json.loads(review_json),
        platform=platform,
        selected_images=json.loads(selected_images),
        uploaded_media=uploaded_media,
        music_url=music_file,
        music_data=(await music_upload.read()) if music_upload and music_upload.filename else None,
        music_volume=music_volume,
        aspect_ratio=aspect_ratio,
        voice_speed=voice_speed,
        logo_data=(await logo.read()) if logo and logo.filename else None,
        logo_text=logo_text,
        logo_position=logo_position,
        subtitle_style=subtitle_style,
        highlight_color=highlight_color,
        img_effect=img_effect,
        img_style=img_style,
        zoom_ratio=zoom_ratio,
        show_intro=show_intro == "1",
        show_outro=show_outro == "1",
        preview_only=preview_only == "1",
        intro_bg_url=intro_bg_url,
        outro_bg_url=outro_bg_url,
        pdf_path=pdf_path,
    )
    result = await render_video(inp)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result
