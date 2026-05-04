"""Post content to social platforms."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from auth import get_access_token, _load_tokens
from config import OUTPUT_DIR, log


@dataclass
class PostRequest:
    video_path: str
    caption: str
    hashtags: list[str] = field(default_factory=list)
    title: str = ""
    affiliate_link: str = ""
    thumbnail_path: str = ""
    platforms: list[str] = field(default_factory=lambda: ["facebook"])


@dataclass
class PostResult:
    platform: str
    success: bool
    message: str = ""
    post_id: str = ""


# === Shared helpers ===

def _resolve_video(video_path: str) -> str | None:
    """Resolve video path from URL or local path. Returns None if not found."""
    if Path(video_path).exists():
        return video_path
    if "/output/" in video_path:
        resolved = str(Path(OUTPUT_DIR) / video_path.split("/output/")[-1])
        if Path(resolved).exists():
            return resolved
    return None


def _build_caption(req: PostRequest, include_affiliate: bool = True, suffix: str = "") -> str:
    """Build caption from request: text + hashtags + optional affiliate + suffix."""
    caption = req.caption
    if req.hashtags:
        caption += "\n\n" + " ".join(f"#{h.lstrip('#')}" for h in req.hashtags)
    if include_affiliate and req.affiliate_link:
        caption += f"\n\n🛒 Mua ngay: {req.affiliate_link}"
    if suffix:
        caption += f"\n\n{suffix}"
    return caption


# === Publish dispatcher ===

_ADAPTERS = {}


def _adapter(name):
    def decorator(fn):
        _ADAPTERS[name] = fn
        return fn
    return decorator


async def publish(req: PostRequest) -> list[PostResult]:
    """Publish to all requested platforms."""
    results = []
    for platform in req.platforms:
        fn = _ADAPTERS.get(platform)
        if fn:
            results.append(await fn(req))
        else:
            results.append(PostResult(platform=platform, success=False, message=f"Unknown platform: {platform}"))
    return results


# === Platform adapters ===

@_adapter("facebook")
async def _post_facebook_reel(req: PostRequest) -> PostResult:
    tokens = _load_tokens()
    fb = tokens.get("facebook", {})
    access_token = fb.get("access_token")
    page_id = fb.get("page_id")
    if not access_token or not page_id:
        return PostResult(platform="facebook", success=False, message="Facebook chưa kết nối.")

    video_path = _resolve_video(req.video_path)
    if not video_path:
        return PostResult(platform="facebook", success=False, message=f"Video không tồn tại: {req.video_path}")

    caption = _build_caption(req, include_affiliate=True)
    log.info(f"facebook: Caption length: {len(caption)}, hashtags: {len(req.hashtags)}, affiliate: {'yes' if req.affiliate_link else 'no'}")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Init
            init = (await client.post(f"https://graph.facebook.com/v21.0/{page_id}/video_reels",
                params={"access_token": access_token}, data={"upload_phase": "start"})).json()
            if "video_id" not in init:
                return PostResult(platform="facebook", success=False, message=f"Init failed: {init.get('error', {}).get('message', str(init))}")
            video_id = init["video_id"]

            # Upload
            file_size = Path(video_path).stat().st_size
            with open(video_path, "rb") as f:
                upload = (await client.post(f"https://rupload.facebook.com/video-upload/v21.0/{video_id}",
                    headers={"Authorization": f"OAuth {access_token}", "offset": "0", "file_size": str(file_size)},
                    content=f.read())).json()
            if not upload.get("success"):
                return PostResult(platform="facebook", success=False, message=f"Upload failed: {upload}")

            # Publish
            pub = (await client.post(f"https://graph.facebook.com/v21.0/{page_id}/video_reels",
                params={"access_token": access_token},
                data={"upload_phase": "finish", "video_id": video_id, "title": req.title[:100] if req.title else "",
                       "description": caption, "video_state": "PUBLISHED"})).json()
            if not (pub.get("success") or pub.get("id")):
                return PostResult(platform="facebook", success=False, message=f"Publish failed: {pub.get('error', {}).get('message', str(pub))}")

            post_id = pub.get("id", video_id)
            if req.affiliate_link:
                try:
                    await client.post(f"https://graph.facebook.com/v21.0/{post_id}/comments",
                        params={"access_token": access_token}, data={"message": f"🛒 Mua ngay tại đây: {req.affiliate_link}"})
                except Exception as e:
                    log.warning(f"facebook: Comment failed: {e}")
            return PostResult(platform="facebook", success=True, message="✅ Đã đăng Reel!", post_id=str(post_id))
    except Exception as e:
        return PostResult(platform="facebook", success=False, message=str(e))


@_adapter("tiktok")
async def _post_tiktok(req: PostRequest) -> PostResult:
    access_token = get_access_token("tiktok")
    if not access_token:
        return PostResult(platform="tiktok", success=False, message="TikTok chưa kết nối.")

    video_path = _resolve_video(req.video_path)
    if not video_path:
        return PostResult(platform="tiktok", success=False, message=f"Video không tồn tại: {req.video_path}")

    file_size = Path(video_path).stat().st_size

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Init
            init = (await client.post("https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={"source_info": {"source": "FILE_UPLOAD", "video_size": file_size, "chunk_size": file_size, "total_chunk_count": 1}})).json()
            if init.get("error", {}).get("code") != "ok":
                return PostResult(platform="tiktok", success=False, message=f"Init failed: {init.get('error', {}).get('message', str(init))}")

            publish_id = init["data"]["publish_id"]
            upload_url = init["data"]["upload_url"]

            # Upload
            with open(video_path, "rb") as f:
                resp = await client.put(upload_url,
                    headers={"Content-Range": f"bytes 0-{file_size-1}/{file_size}", "Content-Type": "video/mp4"},
                    content=f.read())
            if resp.status_code not in (200, 201):
                return PostResult(platform="tiktok", success=False, message=f"Upload failed: HTTP {resp.status_code}")

            # Poll status
            for _ in range(10):
                await asyncio.sleep(3)
                status = (await client.post("https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"publish_id": publish_id})).json()
                s = status.get("data", {}).get("status")
                if s == "PUBLISH_COMPLETE":
                    msg = "✅ Video đã upload lên TikTok (draft)!"
                    if req.affiliate_link:
                        msg += f" Nhớ thêm link affiliate: {req.affiliate_link}"
                    return PostResult(platform="tiktok", success=True, message=msg, post_id=publish_id)
                elif s == "FAILED":
                    return PostResult(platform="tiktok", success=False, message=f"Upload failed: {status.get('data', {}).get('fail_reason', 'unknown')}")

            msg = "✅ Video đang xử lý trên TikTok."
            if req.affiliate_link:
                msg += f" Nhớ thêm link affiliate: {req.affiliate_link}"
            return PostResult(platform="tiktok", success=True, message=msg, post_id=publish_id)
    except Exception as e:
        return PostResult(platform="tiktok", success=False, message=str(e))


@_adapter("youtube")
async def _post_youtube(req: PostRequest) -> PostResult:
    access_token = get_access_token("youtube")
    if not access_token:
        return PostResult(platform="youtube", success=False, message="YouTube chưa kết nối.")

    video_path = _resolve_video(req.video_path)
    if not video_path:
        return PostResult(platform="youtube", success=False, message=f"Video không tồn tại: {req.video_path}")

    title = req.title[:100] if req.title else "Product Review"
    description = _build_caption(req, include_affiliate=True, suffix="#Shorts")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Init resumable upload
            init = await client.post(
                "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={"snippet": {"title": title, "description": description, "categoryId": "22"},
                      "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}})
            if init.status_code != 200:
                return PostResult(platform="youtube", success=False, message=f"Init failed: {init.json().get('error', {}).get('message', init.text[:200])}")

            upload_url = init.headers.get("location")
            if not upload_url:
                return PostResult(platform="youtube", success=False, message="No upload URL returned")

            # Upload
            file_size = Path(video_path).stat().st_size
            with open(video_path, "rb") as f:
                resp = await client.put(upload_url,
                    headers={"Content-Type": "video/mp4", "Content-Length": str(file_size)}, content=f.read())
            if resp.status_code not in (200, 201):
                return PostResult(platform="youtube", success=False, message=f"Upload failed: HTTP {resp.status_code}")

            video_id = resp.json().get("id", "")
            if req.affiliate_link and video_id:
                try:
                    await client.post("https://www.googleapis.com/youtube/v3/commentThreads?part=snippet",
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        json={"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": f"🛒 Mua ngay tại đây: {req.affiliate_link}"}}}})
                except Exception as e:
                    log.warning(f"youtube: Comment failed: {e}")

            return PostResult(platform="youtube", success=True, message="✅ Đã upload YouTube (private)!", post_id=video_id)
    except Exception as e:
        return PostResult(platform="youtube", success=False, message=str(e))


# === Request builder ===

def build_post_request(review_data: dict, video_url: str, platform_key: str = "tiktok") -> PostRequest:
    book = review_data.get("book", {})
    platform_data = review_data.get(platform_key, {})
    video_path = _resolve_video(video_url) or video_url
    images = review_data.get("product_images", [])
    thumbnail = ""
    if images:
        local = str(Path(".") / images[0].lstrip("/"))
        if Path(local).exists():
            thumbnail = local
    return PostRequest(
        video_path=video_path,
        caption=platform_data.get("social_post", ""),
        hashtags=platform_data.get("hashtags", []),
        title=book.get("title", ""),
        affiliate_link=review_data.get("affiliate_link", "") or book.get("shopee_url", ""),
        thumbnail_path=thumbnail,
    )
