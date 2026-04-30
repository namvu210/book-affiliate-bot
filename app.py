"""Book Affiliate Bot - Phase 1: Extract & Review + Voice Narrative."""

import json
import os
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

app = FastAPI(title="Book Affiliate Bot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
templates = Jinja2Templates(directory="templates")


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "audiences": AUDIENCES, "default_voice_speed": DEFAULT_VOICE_SPEED})


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


@app.get("/api/models")
async def list_models():
    """List available Gemini models."""
    from google import genai
    from config import GEMINI_API_KEY
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models = []
        for m in client.models.list():
            models.append(m.name.replace("models/", ""))
        models = [m for m in models if m.startswith("gemini")]
        return {"models": sorted(models, reverse=True)}
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
    word_count_fb: int = Form(200),
    word_count_tk: int = Form(150),
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

    from pipeline import PipelineInput, process_product
    inp = PipelineInput(
        url=url, audience=audience, custom_audience=ca,
        affiliate_url=affiliate_url,
        word_count_fb=word_count_fb, word_count_tk=word_count_tk,
        image_urls=uploaded_paths or bm_imgs,
    )
    result = await process_product(inp)
    if result.error:
        raise HTTPException(500, result.error)
    return result.review_data


@app.post("/batch-personas")
async def batch_personas(
    urls: str = Form(...),
    voice_type: str = Form("elevenlabs"),
    voice_id: str = Form("T4jrQr9x0Y24833yKCWR"),
    word_count: int = Form(150),
):
    """Batch: suggest personas per product, generate reviews for each persona."""
    from pipeline import batch_with_personas
    url_list = [u.strip() for u in urls.split("\n") if u.strip().startswith("http")]
    if not url_list:
        raise HTTPException(400, "Nhập ít nhất 1 link Shopee")
    results = await batch_with_personas(url_list[:10], voice_type, voice_id, word_count)
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
async def upload_kol(file: UploadFile = File(...)):
    """Upload KOL reference photo for AI image generation."""
    from imagegen import save_kol_photo
    data = await file.read()
    save_kol_photo(data, file.filename)
    return {"status": "ok", "message": "✅ Đã lưu ảnh KOL!"}


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
    contents.append(f"Create a new lifestyle photo: {scene} Vietnamese setting. No face shown, crop above chin. TikTok product photography.")

    try:
        result = client.models.generate_content(
            model=EDIT_MODEL,
            contents=contents,
            config=gtypes.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        for part in result.candidates[0].content.parts:
            if part.inline_data:
                img_path = output_path(ts, "regen.png")
                Path(str(img_path)).write_bytes(part.inline_data.data)
                return {"image_url": output_url(ts, "regen.png")}
    except Exception as e:
        raise HTTPException(500, str(e))
    raise HTTPException(500, "No image generated")


@app.get("/api/kol-status")
async def kol_status():
    """Check if KOL reference photo exists."""
    from imagegen import get_kol_photo
    return {"has_kol": get_kol_photo() is not None}


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
        for f in media[:8]:
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
    return await render_video(inp)
