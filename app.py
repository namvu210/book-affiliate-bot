"""Book Affiliate Bot - Phase 1: Extract & Review + Voice Narrative."""

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import AUDIENCES, OUTPUT_DIR, UPLOAD_DIR, GEMINI_MODEL
from extractor import BookInfo, extract_from_pdf, extract_from_shopee, download_images
from reviewer import generate_review, generate_review_all_platforms
from tts import generate_audio
from video import generate_tiktok_video, _extract_cover_from_pdf

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Book Affiliate Bot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
templates = Jinja2Templates(directory="templates")


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "audiences": AUDIENCES})


@app.post("/suggest-personas")
async def suggest_personas(title: str = Form(...)):
    """Use LLM to suggest 3 customer personas for a product."""
    from reviewer import _get_model
    import google.generativeai as genai
    resp = _get_model().generate_content(
        f"""Dựa vào sản phẩm "{title}", gợi ý 3 nhóm khách hàng mục tiêu phù hợp nhất.

Trả về JSON array, mỗi phần tử có:
- "name": tên nhóm khách hàng (ngắn gọn, tiếng Việt)
- "tone": giọng văn phù hợp
- "focus": trọng tâm nội dung khi viết review

CHỈ trả về JSON array, không giải thích.""",
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=500,
            response_mime_type="application/json",
        ),
    )
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(text)
        personas = parsed if isinstance(parsed, list) else parsed.get("personas", [])
    except json.JSONDecodeError:
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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    image_urls = data.get("images", [])
    video_urls = data.get("videos", [])
    all_media = image_urls + video_urls
    local_images = []
    if all_media:
        img_dir = str(Path(OUTPUT_DIR) / f"{ts}_images")
        local_images = await download_images(all_media, img_dir)

    result = {
        "title": data.get("title", ""),
        "price": data.get("price", ""),
        "description": data.get("description", ""),
        "rating": data.get("rating"),
        "rating_count": data.get("rating_count", 0),
        "reviews": data.get("reviews", []),
        "product_images": [f"/output/{ts}_images/{Path(p).name}" for p in local_images],
        "product_images_original": all_media,
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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    result = {
        "title": book.title,
        "price": book.price,
        "rating": book.rating,
        "rating_count": book.rating_count,
    }

    if book.image_urls:
        img_dir = str(Path(OUTPUT_DIR) / f"{ts}_images")
        local = await download_images(book.image_urls, img_dir)
        result["product_images"] = [f"/output/{ts}_images/{Path(p).name}" for p in local]

    return result


async def _add_audio(result: dict, ts: str) -> dict:
    """Generate voice narration for each platform's social_post."""
    for platform in ["facebook", "tiktok"]:
        data = result.get(platform)
        if not data:
            continue
        text = data.get("social_post", "")
        if not text:
            continue
        filename = f"{ts}_{platform}.mp3"
        audio_path = str(Path(OUTPUT_DIR) / filename)
        await generate_audio(text, audio_path)
        data["audio_url"] = f"/output/{filename}"
    return result


@app.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    audience: str = Form("phu-huynh-lop-5"),
    custom_audience: str = Form(""),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Chỉ hỗ trợ file PDF")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = Path(UPLOAD_DIR) / f"{ts}_{file.filename}"
    content = await file.read()
    save_path.write_bytes(content)

    book = extract_from_pdf(str(save_path))
    ca = json.loads(custom_audience) if custom_audience else None
    result = generate_review_all_platforms(book, audience, ca)
    result = await _add_audio(result, ts)

    out_path = Path(OUTPUT_DIR) / f"{ts}_review.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    result["_pdf_path"] = str(save_path)
    return result


@app.post("/from-url")
async def from_url(
    url: str = Form(...),
    audience: str = Form("phu-huynh-lop-5"),
    custom_audience: str = Form(""),
    affiliate_url: str = Form(""),
    media: list[UploadFile] = File(default=[]),
):
    if "shopee" not in url:
        raise HTTPException(400, "Hiện chỉ hỗ trợ link Shopee")

    book = await extract_from_shopee(url)
    if affiliate_url:
        book.shopee_url = affiliate_url
    ca = json.loads(custom_audience) if custom_audience else None
    result = generate_review_all_platforms(book, audience, ca)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = await _add_audio(result, ts)

    # Save uploaded media files
    uploaded_paths = []
    if media and media[0].filename:
        img_dir = Path(OUTPUT_DIR) / f"{ts}_images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(media):
            ext = Path(f.filename).suffix or ".jpg"
            save_to = img_dir / f"product_{i}{ext}"
            save_to.write_bytes(await f.read())
            uploaded_paths.append(f"/output/{ts}_images/product_{i}{ext}")

    # Use uploaded images, or fall back to extracted ones
    if uploaded_paths:
        result["product_images"] = uploaded_paths
    elif book.image_urls:
        img_dir = str(Path(OUTPUT_DIR) / f"{ts}_images")
        local_images = await download_images(book.image_urls, img_dir)
        result["product_images"] = [f"/output/{ts}_images/{Path(p).name}" for p in local_images]

    out_path = Path(OUTPUT_DIR) / f"{ts}_review.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    text = result.get("social_post", result.get("review", ""))
    if text:
        filename = f"{ts}_{platform}.mp3"
        await generate_audio(text, str(Path(OUTPUT_DIR) / filename))
        result["audio_url"] = f"/output/{filename}"

    return result



@app.post("/generate-speech")
async def generate_speech(
    text: str = Form(...),
    platform: str = Form("tiktok"),
):
    """Generate speech audio from edited text."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{platform}.mp3"
    audio_path = str(Path(OUTPUT_DIR) / filename)
    await generate_audio(text, audio_path)
    return {"audio_url": f"/output/{filename}"}

@app.post("/generate-video")
async def generate_video(
    review_json: str = Form(...),
    pdf_path: str = Form(""),
    platform: str = Form("tiktok"),
    selected_images: str = Form("[]"),
    media: list[UploadFile] = File(default=[]),
):
    """Generate Reels/TikTok video with karaoke text over product images."""
    data = json.loads(review_json)
    platform_data = data.get(platform, data.get("tiktok", {}))
    book = data.get("book", {})
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Resolve selected images to local paths
    media_paths = []
    for img_url in json.loads(selected_images)[:4]:
        local = str(Path(".") / img_url.lstrip("/"))
        if Path(local).exists():
            media_paths.append(local)

    # Add uploaded files
    if media and media[0].filename:
        media_dir = Path(OUTPUT_DIR) / f"{ts}_video_media"
        media_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(media[:4]):
            ext = Path(f.filename).suffix or ".jpg"
            p = media_dir / f"media_{i}{ext}"
            p.write_bytes(await f.read())
            media_paths.append(str(p))

    media_paths = media_paths[:4]

    # Fallback: product_images from review data
    if not media_paths and data.get("product_images"):
        for img_url in data["product_images"][:4]:
            local = str(Path(".") / img_url.lstrip("/"))
            if Path(local).exists():
                media_paths.append(local)

    # Fallback: PDF cover
    cover_path = None
    if not media_paths and pdf_path and Path(pdf_path).exists():
        cover_path = str(Path(OUTPUT_DIR) / f"{ts}_cover.png")
        cover_path = _extract_cover_from_pdf(pdf_path, cover_path)

    # Audio
    audio_url = platform_data.get("audio_url", "")
    if audio_url:
        audio_path = str(Path(OUTPUT_DIR) / audio_url.split("/")[-1])
    else:
        audio_path = str(Path(OUTPUT_DIR) / f"{ts}_{platform}.mp3")
        await generate_audio(platform_data.get("social_post", ""), audio_path)

    # Generate video
    video_path = str(Path(OUTPUT_DIR) / f"{ts}_{platform}.mp4")
    generate_tiktok_video(
        audio_path=audio_path,
        output_path=video_path,
        book_title=book.get("title", ""),
        social_post=platform_data.get("social_post", ""),
        hook=platform_data.get("hook", ""),
        key_points=platform_data.get("key_points", []),
        cta=platform_data.get("cta", ""),
        cover_image_path=cover_path,
        media_paths=media_paths,
    )

    if cover_path and Path(cover_path).exists():
        Path(cover_path).unlink(missing_ok=True)

    return {"video_url": f"/output/{ts}_{platform}.mp4"}
