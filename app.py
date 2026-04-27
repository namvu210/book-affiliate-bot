"""Book Affiliate Bot - Phase 1: Extract & Review + Voice Narrative."""

import json
import os
import subprocess
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
        return {"voices": voices}
    except Exception as e:
        return {"voices": [], "error": str(e)[:200]}


@app.get("/api/set-model")
async def set_model(model: str = "gemini-2.5-flash-lite"):
    """Switch Gemini model at runtime."""
    import google.generativeai as genai
    import reviewer
    try:
        reviewer._model = genai.GenerativeModel(model)
        return {"status": "ok", "model": model}
    except Exception as e:
        return {"error": str(e)[:200]}


@app.get("/api/models")
async def list_models():
    """List available Gemini models."""
    import google.generativeai as genai
    from config import GEMINI_API_KEY
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        models = []
        for m in genai.list_models():
            methods = [s.name for s in m.supported_generation_methods]
            if "generateContent" in methods:
                models.append(m.name.replace("models/", ""))
        # Filter to gemini models only, sort newest first
        models = [m for m in models if m.startswith("gemini")]
        return {"models": sorted(models, reverse=True)}
    except Exception:
        # Fallback: known models
        return {"models": [
            "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
        ]}


@app.get("/api/music")

async def get_music(category: str = "", q: str = "", refresh: bool = False, source: str = "freesound"):
    """Search free music from Freesound or Jamendo."""
    import httpx as hx
    import random

    categories = ["happy", "sad", "calm", "energetic", "acoustic", "piano", "lofi", "jazz", "pop", "cinematic", "corporate", "ambient"]
    search = q or category or "background music"

    if source == "jamendo":
        return await _search_jamendo(search, categories, refresh)
    return await _search_freesound(search, categories, refresh)


async def _search_freesound(search, categories, refresh):
    import httpx as hx, random
    api_key = os.getenv("FREESOUND_API_KEY", "")
    if not api_key:
        return {"tracks": [], "categories": categories, "error": "Cần FREESOUND_API_KEY"}
    try:
        async with hx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://freesound.org/apiv2/search/text/", params={
                "token": api_key,
                "query": search,
                "filter": "duration:[15 TO 120]",
                "fields": "id,name,duration,previews,tags",
                "page_size": "20",
                "sort": "rating_desc" if not refresh else "score",
            })
            data = resp.json()
            tracks = []
            for r in data.get("results", []):
                url = r.get("previews", {}).get("preview-hq-mp3", "")
                if url:
                    tags = r.get("tags", [])[:3]
                    tracks.append({"name": r["name"], "url": url, "duration": round(r.get("duration", 0)), "category": tags[0] if tags else ""})
            if refresh:
                random.shuffle(tracks)
            return {"tracks": tracks, "categories": categories, "source": "freesound"}
    except Exception as e:
        return {"tracks": [], "categories": categories, "error": str(e)[:100]}


async def _search_jamendo(search, categories, refresh):
    import httpx as hx, random
    client_id = os.getenv("JAMENDO_CLIENT_ID", "")
    if not client_id:
        return {"tracks": [], "categories": categories, "error": "Cần JAMENDO_CLIENT_ID"}
    try:
        async with hx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.jamendo.com/v3.0/tracks/", params={
                "client_id": client_id,
                "format": "json",
                "limit": "20",
                "search": search,
                "audioformat": "mp32",
                "order": "popularity_total" if not refresh else "relevance",
                "duration_between": "15_120",
            })
            data = resp.json()
            tracks = []
            for r in data.get("results", []):
                url = r.get("audio", "")
                if url:
                    tracks.append({"name": r["name"], "url": url, "duration": r.get("duration", 0), "category": r.get("genre", "")})
            if refresh:
                random.shuffle(tracks)
            return {"tracks": tracks, "categories": categories, "source": "jamendo"}
    except Exception as e:
        return {"tracks": [], "categories": categories, "error": str(e)[:100]}


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
    word_count: int = Form(150),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Chỉ hỗ trợ file PDF")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = Path(UPLOAD_DIR) / f"{ts}_{file.filename}"
    content = await file.read()
    save_path.write_bytes(content)

    book = extract_from_pdf(str(save_path))
    ca = json.loads(custom_audience) if custom_audience else None
    result = generate_review_all_platforms(book, audience, ca, min(word_count, 200))
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
    word_count_fb: int = Form(150),
    word_count_tk: int = Form(80),
    media: list[UploadFile] = File(default=[]),
):
    if "shopee" not in url:
        raise HTTPException(400, "Hiện chỉ hỗ trợ link Shopee")

    book = await extract_from_shopee(url)
    if affiliate_url:
        book.shopee_url = affiliate_url
    ca = json.loads(custom_audience) if custom_audience else None
    result = generate_review_all_platforms(book, audience, ca, min(word_count_fb, 300), min(word_count_tk, 150))

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
    voice_type: str = Form("gtts"),
    elevenlabs_voice_id: str = Form(""),
):
    """Generate speech audio from edited text."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{platform}.mp3"
    audio_path = str(Path(OUTPUT_DIR) / filename)
    await generate_audio(text, audio_path, voice_type=voice_type, elevenlabs_voice_id=elevenlabs_voice_id)
    return {"audio_url": f"/output/{filename}"}


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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_path = str(Path(OUTPUT_DIR) / f"{ts}_raw.mp4")
    Path(input_path).write_bytes(await video.read())

    # Get video duration
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", input_path],
        capture_output=True, text=True, timeout=10,
    )
    total_dur = float(probe.stdout.strip()) if probe.stdout.strip() else 0

    output_path = str(Path(OUTPUT_DIR) / f"{ts}_cut.mp4")

    if total_dur <= max_duration:
        # Already short enough, just copy
        Path(input_path).rename(output_path)
    else:
        # Take middle segment for best content
        start = max(0, (total_dur - max_duration) / 2)
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start), "-i", input_path,
             "-t", str(max_duration), "-c:v", "libx264", "-c:a", "aac",
             "-vf", f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
             output_path],
            capture_output=True, timeout=120,
        )
        Path(input_path).unlink(missing_ok=True)

    return {
        "video_url": f"/output/{ts}_cut.mp4",
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
    max_duration: int = Form(30),
    aspect_ratio: str = Form("9:16"),
    voice_speed: int = Form(75),
    img_transition: int = Form(3),
    logo_position: str = Form("top-right"),
    logo: UploadFile = File(default=None),
    subtitle_style: str = Form("tiktok"),
    highlight_color: str = Form("#FFD700"),
    img_effect: str = Form("ken_burns"),
    zoom_ratio: int = Form(15),
    show_intro: str = Form("1"),
    show_outro: str = Form("1"),
    preview_only: str = Form("0"),
    intro_bg: UploadFile = File(default=None),
    outro_bg: UploadFile = File(default=None),
    music_upload: UploadFile = File(default=None),
    media: list[UploadFile] = File(default=[]),
):
    """Generate Reels/TikTok video with karaoke text over product images."""
    data = json.loads(review_json)
    platform_data = data.get(platform, data.get("tiktok", {}))
    book = data.get("book", {})
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Resolve selected images to local paths
    media_paths = []
    for img_url in json.loads(selected_images)[:8]:
        local = str(Path(".") / img_url.lstrip("/"))
        if Path(local).exists():
            media_paths.append(local)

    # Add uploaded files
    if media and media[0].filename:
        media_dir = Path(OUTPUT_DIR) / f"{ts}_video_media"
        media_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(media[:8]):
            ext = Path(f.filename).suffix or ".jpg"
            p = media_dir / f"media_{i}{ext}"
            p.write_bytes(await f.read())
            media_paths.append(str(p))

    media_paths = media_paths[:8]

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
        await generate_audio(platform_data.get("social_post", ""), audio_path, rate=f"+{voice_speed}%")

    # Download/save music
    local_music = None
    if music_upload and music_upload.filename:
        local_music = str(Path(OUTPUT_DIR) / f"{ts}_music.mp3")
        Path(local_music).write_bytes(await music_upload.read())
    elif music_file and music_file.startswith("http"):
        import httpx as hx
        local_music = str(Path(OUTPUT_DIR) / f"{ts}_music.mp3")
        r = hx.get(music_file, timeout=30, follow_redirects=True)
        if r.status_code == 200:
            Path(local_music).write_bytes(r.content)
        else:
            local_music = None
    elif music_file:
        local_music = music_file

    # Save logo if uploaded
    logo_path = None
    if logo and logo.filename:
        logo_path = str(Path(OUTPUT_DIR) / f"{ts}_logo.png")
        Path(logo_path).write_bytes(await logo.read())

    # Save intro/outro backgrounds
    intro_bg_path = None
    if intro_bg and intro_bg.filename:
        intro_bg_path = str(Path(OUTPUT_DIR) / f"{ts}_intro_bg.png")
        Path(intro_bg_path).write_bytes(await intro_bg.read())
    outro_bg_path = None
    if outro_bg and outro_bg.filename:
        outro_bg_path = str(Path(OUTPUT_DIR) / f"{ts}_outro_bg.png")
        Path(outro_bg_path).write_bytes(await outro_bg.read())

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
        music_file=local_music,
        music_volume=max(0, min(50, music_volume)) / 100,
        max_duration=max(15, min(60, max_duration)),
        aspect_ratio=aspect_ratio,
        img_transition=max(1, min(10, img_transition)),
        logo_path=logo_path,
        logo_position=logo_position,
        subtitle_style=subtitle_style,
        highlight_color=highlight_color,
        img_effect=img_effect,
        zoom_ratio=max(5, min(100, zoom_ratio)) / 100,
        show_intro=show_intro == "1",
        show_outro=show_outro == "1",
        preview_only=preview_only == "1",
        intro_bg_path=intro_bg_path,
        outro_bg_path=outro_bg_path,
    )

    # Cleanup
    if local_music and local_music.startswith(str(OUTPUT_DIR)):
        Path(local_music).unlink(missing_ok=True)
    if cover_path and Path(cover_path).exists():
        Path(cover_path).unlink(missing_ok=True)
    if logo_path and Path(logo_path).exists():
        Path(logo_path).unlink(missing_ok=True)
    if intro_bg_path and Path(intro_bg_path).exists():
        Path(intro_bg_path).unlink(missing_ok=True)
    if outro_bg_path and Path(outro_bg_path).exists():
        Path(outro_bg_path).unlink(missing_ok=True)

    if preview_only == "1":
        preview_img = str(Path(OUTPUT_DIR) / f"{ts}_preview.png")
        return {"preview_url": f"/output/{ts}_preview.png"} if Path(preview_img).exists() else {"preview_url": f"/output/{ts}_{platform}.mp4"}

    # Generate SRT
    from video import _split_sentences, _get_duration as vid_duration
    srt_path = str(Path(OUTPUT_DIR) / f"{ts}_{platform}.srt")
    text = platform_data.get("social_post", "")
    dur = vid_duration(audio_path) or 30
    sentences = _split_sentences(text)
    char_counts = [max(1, len(s)) for s in sentences]
    total_chars = sum(char_counts)
    with open(srt_path, "w") as f:
        t = 0.0
        for i, s in enumerate(sentences):
            sd = (char_counts[i] / total_chars) * dur
            h1, m1, s1 = int(t//3600), int(t%3600//60), t%60
            t2 = t + sd
            h2, m2, s2 = int(t2//3600), int(t2%3600//60), t2%60
            f.write(f"{i+1}\n{h1:02d}:{m1:02d}:{s1:06.3f} --> {h2:02d}:{m2:02d}:{s2:06.3f}\n{s}\n\n")
            t = t2

    return {"video_url": f"/output/{ts}_{platform}.mp4", "srt_url": f"/output/{ts}_{platform}.srt"}
