"""Asset generation routes — TTS, images, video, auto-cut."""

import json
import logging
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from config import make_ts, output_path, output_url

router = APIRouter()
_log = logging.getLogger("assets")


@router.post("/batch-assets")
async def batch_assets(
    review_json: str = Form(...),
    url: str = Form(""),
    platforms: str = Form("facebook,tiktok"),
    voice_type: str = Form("edge"),
    voice_id: str = Form(""),
    edge_voice: str = Form("vi-VN-HoaiMyNeural"),
    voice_speed: int = Form(140),
    media: list[UploadFile] = File(default=[]),
):
    """Step 2b: Generate audio + images + AI images from existing review data."""
    from tts import generate_audio
    from extractor import download_images, extract_from_shopee

    data = json.loads(review_json)
    ts = make_ts()
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    # Audio — ONE audio shared across all platforms
    text = ""
    for platform in platform_list:
        pdata = data.get(platform)
        if pdata and pdata.get("social_post"):
            text = pdata["social_post"]
            cta = pdata.get("cta", "").strip()
            if cta and cta not in text:
                text = text.rstrip() + " " + cta
            break
    if text:
        audio_path = str(output_path(ts, "audio.mp3"))
        try:
            await generate_audio(text, audio_path, speed=voice_speed, voice_type=voice_type, elevenlabs_voice_id=voice_id, edge_voice=edge_voice, no_fallback=True)
            audio_url = output_url(ts, "audio.mp3")
            for platform in platform_list:
                if data.get(platform):
                    data[platform]["audio_url"] = audio_url
        except Exception as e:
            _log.warning(f"Audio failed: {e}")

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
    ai_expected = 0
    ai_generated = 0
    if 5 <= len(images) <= 14:
        try:
            from imagegen import generate_lifestyle_images
            persona = {"name": data.get("audience_name", "Khách hàng"), "focus": ""}
            ai_expected = 3 if len(images) <= 7 else 2 if len(images) <= 10 else 1
            ai_images = await generate_lifestyle_images(data["book"]["title"], persona, ai_expected, ts, images[:3])
            ai_generated = len(ai_images)
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
    data["_ai_status"] = {"expected": ai_expected, "generated": ai_generated, "real_images": len(real)}

    out = output_path(ts, "review.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    return data


@router.post("/generate-speech")
async def generate_speech(
    text: str = Form(...),
    platform: str = Form("tiktok"),
    voice_type: str = Form("edge"),
    elevenlabs_voice_id: str = Form(""),
    edge_voice: str = Form("vi-VN-HoaiMyNeural"),
    speed: int = Form(125),
):
    """Generate speech audio from edited text."""
    from tts import generate_audio
    from config import log
    log.info(f"generate-speech: voice_type={voice_type}, speed={speed}, edge_voice={edge_voice}")
    ts = make_ts()
    suffix = f"{platform}.mp3"
    audio_path = str(output_path(ts, suffix))
    await generate_audio(text, audio_path, speed=speed, voice_type=voice_type, elevenlabs_voice_id=elevenlabs_voice_id, edge_voice=edge_voice)
    return {"audio_url": output_url(ts, suffix)}


@router.post("/upload-voice")
async def upload_voice(file: UploadFile = File(...), ref_text: str = Form("")):
    """Upload voice sample for cloning."""
    from tts import save_voice_sample, VOICE_DIR
    data = await file.read()
    save_voice_sample(data, file.filename)
    if ref_text.strip():
        (VOICE_DIR / "ref_text.txt").write_text(ref_text.strip())
    return {"status": "ok", "message": "✅ Đã lưu mẫu giọng nói!"}


@router.get("/api/voice-status")
async def voice_status():
    """Check if voice sample exists."""
    from tts import get_voice_sample
    return {"has_voice": get_voice_sample() is not None}


@router.post("/upload-kol")
async def upload_kol(file: UploadFile = File(...), slot: int = Form(1)):
    """Upload KOL reference photo (slot 1=front, 2=side angle)."""
    from imagegen import save_kol_photo, get_kol_photos
    data = await file.read()
    save_kol_photo(data, file.filename, slot=min(max(slot, 1), 2))
    count = len(get_kol_photos())
    return {"status": "ok", "count": count, "message": f"✅ Đã lưu ảnh KOL #{slot}! ({count}/2)"}


@router.get("/api/kol-status")
async def kol_status():
    """Check KOL reference photos status."""
    from imagegen import get_kol_photos
    photos = get_kol_photos()
    return {"has_kol": len(photos) > 0, "count": len(photos)}


@router.post("/generate-ai-images")
async def generate_ai_images_endpoint(
    title: str = Form(...),
    persona_name: str = Form("Khách hàng"),
    persona_focus: str = Form("chất lượng sản phẩm"),
    product_images: str = Form("[]"),
    media: list[UploadFile] = File(default=[]),
):
    """Generate AI lifestyle images independently."""
    from pathlib import Path
    from imagegen import generate_lifestyle_images
    ts = make_ts()
    imgs = json.loads(product_images)
    # Save uploaded images and add their URLs to the list
    if media and media[0].filename:
        img_dir = output_path(ts, "images")
        img_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(media):
            if not f.content_type or not f.content_type.startswith("image/"):
                continue
            ext = Path(f.filename).suffix or ".jpg"
            save_to = img_dir / f"upload_{i}{ext}"
            save_to.write_bytes(await f.read())
            imgs.append(f"{output_url(ts, 'images')}/upload_{i}{ext}")
    num_ai = 3 if len(imgs) <= 7 else 2 if len(imgs) <= 10 else 1
    persona = {"name": persona_name, "focus": persona_focus}
    ai_images = await generate_lifestyle_images(title, persona, num_ai, ts, imgs[:3])
    return {"ai_images": ai_images}


@router.post("/regenerate-image")
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
            contents.append(
                "PERSON REFERENCE — FACE AND BODY ONLY:\n"
                "- COPY: face shape, skin tone, hair style, body type, approximate age\n"
                "- NEVER COPY: clothing, accessories, background, pose, lighting from this photo\n"
                "- The person must wear clothing appropriate to the scene described below"
            )
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
    contents.append(
        f"Create a new lifestyle photo: {scene}\n\n"
        f"The product must look exactly like the reference photo.\n"
        f"Generate a COMPLETELY NEW scene — new background, new outfit, new pose, new lighting.\n"
        f"Do NOT reproduce or imitate the reference person's photo."
    )

    try:
        result = client.models.generate_content(
            model=EDIT_MODEL,
            contents=contents,
            config=gtypes.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=gtypes.ImageConfig(aspect_ratio="9:16"),
            ),
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


@router.post("/generate-video")
async def generate_video(
    review_json: str = Form(...),
    pdf_path: str = Form(""),
    platform: str = Form("tiktok"),
    selected_images: str = Form("[]"),
    music_file: str = Form(""),
    music_volume: int = Form(15),
    aspect_ratio: str = Form("9:16"),
    voice_speed: int = Form(140),
    voice_type: str = Form("edge"),
    voice_id: str = Form(""),
    logo_position: str = Form("top-right"),
    logo_text: str = Form(""),
    logo: UploadFile = File(default=None),
    subtitle_style: str = Form("tiktok"),
    highlight_color: str = Form("#FFD700"),
    img_effect: str = Form("random"),
    img_transition: str = Form(""),
    img_style: str = Form("random"),
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
        voice_type=voice_type,
        elevenlabs_voice_id=voice_id,
        logo_data=(await logo.read()) if logo and logo.filename else None,
        logo_text=logo_text,
        logo_position=logo_position,
        subtitle_style=subtitle_style,
        highlight_color=highlight_color,
        img_effect=img_effect,
        img_transition=img_transition,
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


@router.post("/upload-video")
async def upload_video(video: UploadFile):
    """Save an uploaded video file and return its path for publishing."""
    from config import OUTPUT_DIR
    ts = make_ts()
    dest = Path(OUTPUT_DIR) / f"{ts}_upload.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await video.read())
    return {"video_url": f"/output/{ts}_upload.mp4", "path": str(dest)}


@router.post("/auto-cut-video")
async def auto_cut_video(
    video: UploadFile = File(...),
    max_duration: int = Form(30),
):
    """Auto-trim uploaded video to max_duration, extract best segment."""
    ts = make_ts()
    input_path = str(output_path(ts, "raw.mp4"))
    Path(input_path).write_bytes(await video.read())

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", input_path],
        capture_output=True, text=True, timeout=10,
    )
    total_dur = float(probe.stdout.strip()) if probe.stdout.strip() else 0

    cut_path = str(output_path(ts, "cut.mp4"))

    if total_dur <= max_duration:
        Path(input_path).rename(cut_path)
    else:
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
