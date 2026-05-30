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
    page_id: str = ""  # specific FB page to post to (empty = default)
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
    import re
    # Strip audio tags [excited], [sighs] etc — not for social media display
    caption = re.sub(r'\[[a-zA-Z_ ]+\]', '', req.caption).strip()
    caption = re.sub(r'  +', ' ', caption)  # collapse double spaces
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
    from auth import get_facebook_token
    access_token, page_id = get_facebook_token(req.page_id)
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
        return PostResult(platform="tiktok", success=False, message="TikTok chưa kết nối. Vào Settings để kết nối lại.")

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
        return PostResult(platform="tiktok", success=False, message=str(e) or f"TikTok error: {type(e).__name__}")


@_adapter("youtube")
async def _post_youtube(req: PostRequest) -> PostResult:
    access_token = get_access_token("youtube")
    if not access_token:
        return PostResult(platform="youtube", success=False, message="YouTube chưa kết nối.")

    video_path = _resolve_video(req.video_path)
    if not video_path:
        return PostResult(platform="youtube", success=False, message=f"Video không tồn tại: {req.video_path}")

    raw_title = req.title[:90] if req.title else "Product Review"
    title = f"{raw_title} #Shorts"
    description = _build_caption(req, include_affiliate=True)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Init resumable upload
            init = await client.post(
                "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={"snippet": {"title": title, "description": description, "categoryId": "22"},
                      "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}})
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

            return PostResult(platform="youtube", success=True, message="✅ Đã đăng YouTube Shorts!", post_id=video_id)
    except Exception as e:
        return PostResult(platform="youtube", success=False, message=str(e) or f"YouTube error: {type(e).__name__}")


@_adapter("instagram")
async def _post_instagram_reel(req: PostRequest) -> PostResult:
    from auth import get_facebook_token, get_facebook_pages
    pages = get_facebook_pages()
    ig_page = next((p for p in pages if p.get("instagram_business_account_id")), None)
    if not ig_page:
        return PostResult(platform="instagram", success=False, message="Instagram chưa liên kết.")

    access_token = ig_page["access_token"]
    ig_user_id = ig_page["instagram_business_account_id"]

    video_path = _resolve_video(req.video_path)
    if not video_path:
        return PostResult(platform="instagram", success=False, message=f"Video không tồn tại: {req.video_path}")

    caption = _build_caption(req, include_affiliate=True)
    file_size = Path(video_path).stat().st_size

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            # Step 1: Create container with resumable upload
            log.info(f"Instagram: creating container for IG user {ig_user_id}, video={video_path} ({file_size} bytes)")
            init = (await client.post(f"https://graph.facebook.com/v21.0/{ig_user_id}/media", params={
                "access_token": access_token,
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": caption,
            })).json()
            if "id" not in init:
                log.warning(f"Instagram: init failed: {init}")
                return PostResult(platform="instagram", success=False, message=f"Init failed: {init.get('error', {}).get('message', str(init))}")

            container_id = init["id"]
            upload_uri = init.get("uri")
            log.info(f"Instagram: container created: {container_id}")

            if not upload_uri:
                return PostResult(platform="instagram", success=False, message="No upload URI returned")

            # Step 2: Upload video
            with open(video_path, "rb") as f:
                upload_resp = await client.post(upload_uri,
                    headers={
                        "Authorization": f"OAuth {access_token}",
                        "offset": "0",
                        "file_size": str(file_size),
                    },
                    content=f.read())
            if upload_resp.status_code not in (200, 201):
                log.warning(f"Instagram: upload failed: HTTP {upload_resp.status_code} — {upload_resp.text[:200]}")
                return PostResult(platform="instagram", success=False, message=f"Upload failed: HTTP {upload_resp.status_code}")
            log.info(f"Instagram: video uploaded OK")

            # Step 3: Poll container status
            for poll_i in range(20):
                await asyncio.sleep(5)
                resp = await client.get(f"https://graph.facebook.com/v21.0/{container_id}", params={
                    "access_token": access_token,
                    "fields": "status_code,status",
                })
                if resp.status_code != 200:
                    log.warning(f"Instagram: poll {poll_i} failed: HTTP {resp.status_code} — {resp.text[:300]}")
                    return PostResult(platform="instagram", success=False, message=f"Poll failed: HTTP {resp.status_code} — {resp.text[:200]}")
                status = resp.json()
                code = status.get("status_code")
                log.info(f"Instagram: poll {poll_i} status={code}")
                if code == "FINISHED":
                    break
                elif code == "ERROR":
                    log.warning(f"Instagram: processing error: {status}")
                    return PostResult(platform="instagram", success=False, message=f"Processing failed: {status.get('status', '')}")
            else:
                log.warning(f"Instagram: timeout after 20 polls")
                return PostResult(platform="instagram", success=False, message="Video processing timeout")

            # Step 4: Publish
            log.info(f"Instagram: publishing container {container_id}")
            pub = (await client.post(f"https://graph.facebook.com/v21.0/{ig_user_id}/media_publish", params={
                "access_token": access_token,
                "creation_id": container_id,
            })).json()
            if "id" not in pub:
                log.warning(f"Instagram: publish failed: {pub}")
                return PostResult(platform="instagram", success=False, message=f"Publish failed: {pub.get('error', {}).get('message', str(pub))}")

            log.info(f"Instagram: published! post_id={pub['id']}")
            return PostResult(platform="instagram", success=True, message="✅ Đã đăng Instagram Reel!", post_id=pub["id"])
    except Exception as e:
        return PostResult(platform="instagram", success=False, message=str(e) or f"Instagram error: {type(e).__name__}")


@_adapter("threads")
async def _post_threads(req: PostRequest) -> PostResult:
    tokens = _load_tokens()
    t = tokens.get("threads", {})
    access_token = get_access_token("threads")
    if not access_token:
        return PostResult(platform="threads", success=False, message="Threads chưa kết nối.")
    user_id = t.get("user_id", "me")

    caption = _build_caption(req, include_affiliate=True)
    # Truncate to Threads 500-char limit
    if len(caption) > 500:
        caption = caption[:497] + "..."

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # Determine media type: video, image, or text-only
            video_path = _resolve_video(req.video_path) if req.video_path else None
            container_params: dict = {"text": caption}

            if video_path:
                # Video post — needs a publicly accessible URL
                # For now, use image fallback if no public URL available
                container_params["media_type"] = "VIDEO"
                container_params["video_url"] = req.video_path if req.video_path.startswith("http") else ""
                if not container_params["video_url"]:
                    # Fall back to text-only if no public video URL
                    container_params.pop("video_url")
                    container_params["media_type"] = "TEXT"
            else:
                container_params["media_type"] = "TEXT"

            # Check if we have a product image URL for image post
            if container_params["media_type"] == "TEXT" and req.thumbnail_path and req.thumbnail_path.startswith("http"):
                container_params["media_type"] = "IMAGE"
                container_params["image_url"] = req.thumbnail_path

            # Step 1: Create container
            create_resp = (await client.post(
                f"https://graph.threads.net/v1.0/{user_id}/threads",
                params={"access_token": access_token},
                data=container_params,
            )).json()
            container_id = create_resp.get("id")
            if not container_id:
                return PostResult(platform="threads", success=False,
                    message=f"Create failed: {create_resp.get('error', {}).get('message', str(create_resp))}")

            # Step 2: Wait for processing (needed for video)
            if container_params.get("media_type") == "VIDEO":
                for _ in range(15):
                    await asyncio.sleep(3)
                    status_resp = (await client.get(
                        f"https://graph.threads.net/v1.0/{container_id}",
                        params={"access_token": access_token, "fields": "status"},
                    )).json()
                    status = status_resp.get("status")
                    if status == "FINISHED":
                        break
                    elif status == "ERROR":
                        return PostResult(platform="threads", success=False, message="Video processing failed")
            else:
                await asyncio.sleep(2)

            # Step 3: Publish
            pub_resp = (await client.post(
                f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
                params={"access_token": access_token},
                data={"creation_id": container_id},
            )).json()
            post_id = pub_resp.get("id")
            if not post_id:
                return PostResult(platform="threads", success=False,
                    message=f"Publish failed: {pub_resp.get('error', {}).get('message', str(pub_resp))}")

            return PostResult(platform="threads", success=True, message="✅ Đã đăng Threads!", post_id=post_id)
    except Exception as e:
        return PostResult(platform="threads", success=False, message=str(e) or f"Threads error: {type(e).__name__}")


# === Request builder ===

def build_post_request(review_data: dict, video_url: str, platform_key: str = "tiktok") -> PostRequest:
    book = review_data.get("book", {})
    platform_data = review_data.get(platform_key) or review_data.get("facebook") or review_data.get("tiktok") or {}
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
