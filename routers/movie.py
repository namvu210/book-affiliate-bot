"""Movie Ad Generator routes."""

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from typing import List

import kol_manager
from movie import project as movie_project
from movie.screenplay import generate_screenplay, get_story_styles, get_cinematic_styles
from movie.scene_image import generate_scene_image
from movie.clip import generate_movie_clip, generate_product_closeup, get_available_models as get_clip_models
from movie.assemble import assemble_movie

router = APIRouter(prefix="/api/movie", tags=["movie"])


# --- KOL Management ---

@router.get("/kol/")
async def list_kols():
    return {"profiles": kol_manager.list_profiles()}


@router.post("/kol/")
async def create_kol(
    name: str = Form(...),
    description: str = Form(""),
    images: List[UploadFile] = File(...),
):
    if len(images) < 1:
        raise HTTPException(400, "Cần ít nhất 1 ảnh reference")
    if len(images) > 8:
        raise HTTPException(400, "Tối đa 8 ảnh reference")

    image_bytes = []
    for img in images:
        data = await img.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(400, f"Ảnh {img.filename} quá lớn (>10MB)")
        image_bytes.append(data)

    profile = kol_manager.create_profile(name, description, image_bytes)
    return profile


@router.delete("/kol/{kol_id}")
async def delete_kol(kol_id: str):
    if not kol_manager.delete_profile(kol_id):
        raise HTTPException(404, "KOL not found")
    return {"ok": True}


@router.get("/kol/{kol_id}")
async def get_kol(kol_id: str):
    profile = kol_manager.get_profile(kol_id)
    if not profile:
        raise HTTPException(404, "KOL not found")
    return profile


@router.get("/kol/{kol_id}/images")
async def get_kol_images(kol_id: str):
    profile = kol_manager.get_profile(kol_id)
    if not profile:
        raise HTTPException(404, "KOL not found")
    return {"images": profile["turnaround_images"]}


# --- Product Image Upload ---

@router.post("/upload-product-images")
async def upload_product_images(images: List[UploadFile] = File(...)):
    """Upload local product images, returns URLs."""
    from config import make_ts, output_path, output_url
    from pathlib import Path
    from PIL import Image as PILImage
    import io

    ts = make_ts()
    img_dir = output_path(ts, "images")
    img_dir.mkdir(parents=True, exist_ok=True)

    urls = []
    for i, img in enumerate(images[:6]):
        data = await img.read()
        pil_img = PILImage.open(io.BytesIO(data)).convert("RGB")
        if max(pil_img.size) > 1536:
            pil_img.thumbnail((1536, 1536), PILImage.LANCZOS)
        out_path = img_dir / f"{i}.jpg"
        pil_img.save(out_path, "JPEG", quality=90)
        urls.append(f"{output_url(ts, 'images')}/{i}.jpg")

    return {"image_urls": urls}


# --- Project Management ---

@router.post("/project/create")
async def create_project(request: Request):
    body = await request.json()
    product_title = body.get("product_title", "")
    if not product_title:
        raise HTTPException(400, "Cần nhập tên sản phẩm")
    kol_ids = body.get("kol_ids", [])
    if not kol_ids:
        raise HTTPException(400, "Cần chọn ít nhất 1 KOL")

    # Download external images (https://) to local output dir
    product_images = body.get("product_images", [])
    if product_images and any(img.startswith("http") for img in product_images):
        from config import make_ts, output_path, output_url
        from extractor import download_images
        ts = make_ts()
        img_dir = str(output_path(ts, "images"))
        external = [img for img in product_images if img.startswith("http")]
        local_paths = await download_images(external[:6], img_dir)
        from pathlib import Path
        product_images = [f"{output_url(ts, 'images')}/{Path(p).name}" for p in local_paths]

    project = movie_project.create_project(
        product_title=product_title,
        kol_ids=kol_ids,
        product_url=body.get("product_url", ""),
        product_images=product_images,
        affiliate_link=body.get("affiliate_link", ""),
    )
    return project


@router.get("/project/{project_id}")
async def get_project(project_id: str):
    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("/projects/")
async def list_projects():
    return {"projects": movie_project.list_projects()}


# --- Screenplay ---

@router.get("/story-styles")
async def list_story_styles():
    return {"styles": get_story_styles()}


@router.get("/cinematic-styles")
async def list_cinematic_styles():
    return {"styles": get_cinematic_styles()}


@router.post("/project/{project_id}/screenplay")
async def gen_screenplay(project_id: str, request: Request):
    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    body = await request.json()
    story_style = body.get("story_style", "auto")
    cinematic_style = body.get("cinematic_style", "auto")
    product_description = body.get("product_description", "")

    try:
        screenplay = generate_screenplay(
            product_title=project["product_title"],
            product_description=product_description,
            kol_ids=project["kol_ids"],
            story_style=story_style,
            cinematic_style=cinematic_style,
            product_images=project.get("product_images", []),
        )
    except Exception as e:
        raise HTTPException(500, f"Lỗi tạo kịch bản: {e}")

    movie_project.update_project(project_id, {"screenplay": screenplay, "status": "screenplay_done"})
    return screenplay


@router.put("/project/{project_id}/screenplay")
async def edit_screenplay(project_id: str, request: Request):
    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    screenplay = await request.json()
    movie_project.update_project(project_id, {"screenplay": screenplay})
    return screenplay


# --- Scene Image ---

@router.post("/project/{project_id}/scene-image")
async def gen_scene_image(project_id: str):
    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    screenplay = project.get("screenplay")
    if not screenplay:
        raise HTTPException(400, "Chưa có kịch bản. Tạo kịch bản trước.")

    key_frame = screenplay.get("key_frame_description", "")
    if not key_frame:
        raise HTTPException(400, "Kịch bản chưa có key_frame_description")

    cinematic_style = screenplay.get("cinematic_style", "")

    url = await generate_scene_image(
        project_id=project_id,
        clip_number=1,
        key_frame_description=key_frame,
        kol_ids=project.get("kol_ids", []),
        product_images=project.get("product_images", []),
        cinematic_style=cinematic_style,
    )

    if not url:
        raise HTTPException(500, "Không tạo được ảnh. Thử lại hoặc chỉnh key_frame_description.")

    movie_project.update_project(project_id, {"scene_image": url})
    return {"image_url": url}


@router.post("/project/{project_id}/scene-image/regen")
async def regen_scene_image(project_id: str):
    return await gen_scene_image(project_id)


# --- Video Clip Generation ---

@router.get("/clip-models")
async def list_clip_models():
    return get_clip_models()


@router.post("/project/{project_id}/generate-segment/{seg_index}")
async def gen_segment(project_id: str, seg_index: int, model: str = ""):
    """Generate a single segment video. Uses scene image for first story, product image for closeup, extends from previous if adjacent story."""
    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    screenplay = project.get("screenplay")
    if not screenplay:
        raise HTTPException(400, "Chưa có kịch bản.")

    segments = screenplay.get("segments", [])
    if seg_index < 0 or seg_index >= len(segments):
        raise HTTPException(400, f"Segment index {seg_index} không hợp lệ (có {len(segments)} segments).")

    scene_image = project.get("scene_image")
    if not scene_image:
        raise HTTPException(400, "Cần tạo scene image trước.")

    seg = segments[seg_index]
    seg_type = seg.get("type", "story")
    duration = max(4, min(8, seg.get("duration", 8)))
    prompt = seg.get("prompt", "")

    if not prompt:
        raise HTTPException(400, f"Segment {seg_index} chưa có prompt.")

    # Build screenplay context for prompt enrichment
    sp_context = {
        "mood": screenplay.get("mood", ""),
        "cinematic_style": screenplay.get("cinematic_style", ""),
    }

    # Single segment: always generate from scene image (extension only works in chain mode)
    segment_videos = project.get("segment_videos", {})

    if seg_type == "closeup":
        product_images = project.get("product_images", [])
        if not product_images:
            raise HTTPException(400, "Cần có ảnh sản phẩm cho closeup segment.")
        result = await generate_product_closeup(
            project_id=project_id,
            product_image_path=product_images[0],
            model=model or None,
            duration_seconds=duration,
            prompt_override=prompt,
        )
    else:
        dialogue = seg.get("dialogue")
        kwargs = dict(
            project_id=project_id,
            clip_number=seg_index,
            scene_image_path=scene_image,
            motion_prompt=prompt,
            dialogue=dialogue,
            kol_ids=project.get("kol_ids", []),
            product_images=project.get("product_images", []),
            duration_seconds=duration,
            screenplay_context=sp_context,
        )
        if model:
            kwargs["model"] = model
        result = await generate_movie_clip(**kwargs)

    if result.get("error"):
        raise HTTPException(500, result["error"])

    segment_videos[str(seg_index)] = result["video_url"]
    movie_project.update_project(project_id, {"segment_videos": segment_videos})
    return {"segment_index": seg_index, **result}


@router.post("/project/{project_id}/generate-video")
async def gen_video(project_id: str, model: str = ""):
    """Generate single 8s video clip from scene image."""
    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    screenplay = project.get("screenplay")
    if not screenplay:
        raise HTTPException(400, "Chưa có kịch bản.")

    scene_image = project.get("scene_image")
    if not scene_image:
        raise HTTPException(400, "Cần tạo scene image trước.")

    from movie.clip import DEFAULT_MODEL
    use_model = model or DEFAULT_MODEL

    # Combine all segment prompts into one motion prompt
    segments = screenplay.get("segments", [])
    prompt_parts = [s.get("prompt", "") for s in segments if s.get("prompt")]
    combined_prompt = " ".join(prompt_parts) if prompt_parts else ""
    dialogue = next((s.get("dialogue") for s in segments if s.get("dialogue")), None)

    sp_context = {
        "mood": screenplay.get("mood", ""),
        "cinematic_style": screenplay.get("cinematic_style", ""),
    }

    result = await generate_movie_clip(
        project_id=project_id,
        clip_number=0,
        scene_image_path=scene_image,
        motion_prompt=combined_prompt,
        dialogue=dialogue,
        model=use_model,
        kol_ids=project.get("kol_ids", []),
        product_images=project.get("product_images", []),
        duration_seconds=8,
        screenplay_context=sp_context,
    )

    if result.get("error"):
        raise HTTPException(500, result["error"])

    movie_project.update_project(project_id, {
        "video_clip": result["video_url"],
        "segment_videos": {"0": result["video_url"]},
    })
    return result


# --- Assembly ---

@router.get("/music-categories")
async def list_music_categories():
    """List available music categories from local library."""
    from pathlib import Path
    music_dir = Path("music")
    if not music_dir.exists():
        return {}
    files = list(music_dir.glob("*.mp3"))
    categories = {}
    for f in files:
        cat = f.stem.rsplit("_", 1)[0]
        categories.setdefault(cat, []).append(str(f))
    return {cat: len(tracks) for cat, tracks in sorted(categories.items())}


@router.get("/music/{category}")
async def list_music_tracks(category: str):
    """List tracks in a category."""
    from pathlib import Path
    music_dir = Path("music")
    tracks = sorted(music_dir.glob(f"{category}_*.mp3"))
    return [{"path": str(t), "name": t.stem} for t in tracks[:20]]


@router.post("/project/{project_id}/assemble")
async def assemble_project(project_id: str, request: Request):
    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    scene_image = project.get("scene_image")
    if not scene_image:
        raise HTTPException(400, "Cần tạo scene image trước (bước 4).")

    # Resolve video sources: prefer segment_videos, fall back to legacy single body
    segment_videos = project.get("segment_videos", {})
    screenplay = project.get("screenplay", {})
    segments = screenplay.get("segments", [])

    segment_video_paths = None
    body_video_path = None

    if segment_videos and len(segment_videos) == len(segments):
        # New format: ordered segment videos
        segment_video_paths = [segment_videos[str(i)] for i in range(len(segments))]
    else:
        # Legacy fallback
        body_video_path = project.get("extended_video") or project.get("video_clip")
        if not body_video_path:
            raise HTTPException(400, "Cần tạo video trước (bước 5).")

    # Parse options from request body
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    cta_text = body.get("cta", "Link mua o mo ta nhe!")
    music_path = body.get("music_path", "")
    music_volume = float(body.get("music_volume", 0.25))
    keep_veo_audio = body.get("keep_veo_audio", True)

    # Hook from screenplay
    hook_text = body.get("hook", screenplay.get("story_hook", ""))

    # Marketing overlay: from request body or fall back to screenplay
    marketing_overlay = body.get("marketing_overlay")
    if marketing_overlay is None:
        marketing_overlay = screenplay.get("marketing_overlay")

    result = await assemble_movie(
        project_id=project_id,
        scene_image=scene_image,
        segment_video_paths=segment_video_paths,
        body_video_path=body_video_path,
        hook_text=hook_text,
        cta_text=cta_text,
        music_path=music_path if music_path else None,
        music_volume=music_volume,
        keep_veo_audio=keep_veo_audio,
        marketing_overlay=marketing_overlay,
    )

    if result.get("error"):
        raise HTTPException(500, result["error"])

    movie_project.update_project(project_id, {
        "final_video": result["video_url"],
        "status": "complete",
    })

    return result


@router.post("/project/{project_id}/publish")
async def publish_movie(project_id: str, request: Request):
    """Publish assembled movie to social platforms."""
    from poster import publish, PostRequest
    from pathlib import Path

    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    final_video = project.get("final_video")
    if not final_video:
        raise HTTPException(400, "Chưa xuất video (bước 6).")

    video_path = str(Path(".") / final_video.lstrip("/"))
    if not Path(video_path).exists():
        raise HTTPException(400, "Video file not found. Xuất lại.")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    platforms = body.get("platforms", ["tiktok"])
    caption = body.get("caption", "")
    hashtags = body.get("hashtags", [])
    affiliate_link = body.get("affiliate_link", project.get("affiliate_link", ""))

    # Thumbnail from scene image
    scene_image = project.get("scene_image", "")
    thumbnail = ""
    if scene_image:
        local_thumb = str(Path(".") / scene_image.lstrip("/"))
        if Path(local_thumb).exists():
            thumbnail = local_thumb

    req = PostRequest(
        video_path=video_path,
        caption=caption,
        hashtags=hashtags,
        title=project.get("product_title", ""),
        affiliate_link=affiliate_link,
        thumbnail_path=thumbnail,
        platforms=platforms,
    )

    results = await publish(req)
    output = []
    for r in results:
        output.append({
            "platform": r.platform,
            "success": r.success,
            "message": r.message,
            "post_id": r.post_id,
        })

    movie_project.update_project(project_id, {"status": "published"})
    return {"results": output}


@router.post("/project/{project_id}/schedule")
async def schedule_movie(project_id: str, request: Request):
    """Schedule movie for publishing at a specific time slot."""
    from scheduler import add_job, get_slots

    project = movie_project.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    final_video = project.get("final_video")
    if not final_video:
        raise HTTPException(400, "Chưa xuất video (bước 6).")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    slot = body.get("slot", "")
    platforms = body.get("platforms", ["tiktok"])
    caption = body.get("caption", "")
    hashtags = body.get("hashtags", [])
    affiliate_link = body.get("affiliate_link", "")

    # Build review_data-compatible dict for the scheduler
    review_data = {
        "book": {
            "title": project.get("product_title", ""),
            "shopee_url": affiliate_link,
        },
        "product_images": project.get("product_images", []),
        "affiliate_link": affiliate_link,
    }
    # Add platform-specific data
    platform_key = platforms[0] if platforms else "tiktok"
    review_data[platform_key] = {
        "social_post": caption,
        "hashtags": hashtags,
    }

    platform_str = ",".join(platforms) if len(platforms) > 1 else platforms[0]
    job = add_job(review_data, final_video, platform_str, slot=slot)

    movie_project.update_project(project_id, {"status": "scheduled"})
    return {"job_id": job["id"], "slot": job["slot"], "status": "scheduled"}
