"""Video preparation: resolve assets and render."""

from dataclasses import dataclass, field
from pathlib import Path

import httpx

from config import log, make_ts, output_path, output_url, OUTPUT_DIR
from music import get_background_music
from tts import generate_audio


@dataclass
class VideoInput:
    review_data: dict
    platform: str = "tiktok"
    selected_images: list[str] = field(default_factory=list)
    uploaded_media: list[tuple[str, bytes]] = field(default_factory=list)
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
        for img_url in data["product_images"][:16]:
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
        local_music = get_background_music(book.get("title", ""))

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

    # Render — check we have content
    if not platform_data.get("social_post", "").strip():
        return {"error": "Không có nội dung review để tạo video"}
    if not audio_path or not Path(audio_path).exists():
        return {"error": "Không có audio để tạo video"}
    video_path = str(output_path(ts, f"{inp.platform}.mp4"))
    generate_tiktok_video(
        audio_path=audio_path, output_path=video_path,
        book_title=book.get("title", ""),
        social_post=platform_data.get("social_post", ""),
        hook=platform_data.get("hook", ""),
        key_points=platform_data.get("key_points", []),
        cta=platform_data.get("cta", "") or "🛒 Link mua ở mô tả nhé!",
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
