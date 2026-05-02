"""Post content to social platforms."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from auth import get_access_token
from config import OUTPUT_DIR


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


async def publish(req: PostRequest) -> list[PostResult]:
    """Publish to all requested platforms."""
    results = []
    for platform in req.platforms:
        if platform == "facebook":
            results.append(await _post_facebook_reel(req))
        elif platform == "tiktok":
            results.append(await _post_tiktok(req))
        elif platform == "youtube":
            results.append(await _post_youtube(req))
        else:
            results.append(PostResult(platform=platform, success=False, message=f"Unknown platform: {platform}"))
    return results


async def _post_facebook_reel(req: PostRequest) -> PostResult:
    """Post a Reel to Facebook Page via Graph API."""
    from auth import get_access_token, _load_tokens
    tokens = _load_tokens()
    fb = tokens.get("facebook", {})
    access_token = fb.get("access_token")
    page_id = fb.get("page_id")

    if not access_token or not page_id:
        return PostResult(platform="facebook", success=False, message="Facebook chưa kết nối. Vào ⚙️ API Keys → kết nối Facebook.")

    video_path = req.video_path
    if not Path(video_path).exists():
        # Try resolving from output URL
        if "/output/" in video_path:
            video_path = str(Path(OUTPUT_DIR) / video_path.split("/output/")[-1])
    if not Path(video_path).exists():
        return PostResult(platform="facebook", success=False, message=f"Video không tồn tại: {video_path}")

    # Build caption — clean, no links (affiliate goes in comment)
    caption = req.caption
    if req.hashtags:
        caption += "\n\n" + " ".join(f"#{h.lstrip('#')}" for h in req.hashtags)

    print(f"[facebook] Caption length: {len(caption)}, hashtags: {len(req.hashtags)}, affiliate: {'yes' if req.affiliate_link else 'no'}")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Step 1: Initialize upload
            init_resp = await client.post(
                f"https://graph.facebook.com/v21.0/{page_id}/video_reels",
                params={"access_token": access_token},
                data={"upload_phase": "start"},
            )
            init_data = init_resp.json()
            if "video_id" not in init_data:
                return PostResult(platform="facebook", success=False, message=f"Init failed: {init_data.get('error', {}).get('message', str(init_data))}")

            video_id = init_data["video_id"]

            # Step 2: Upload video binary
            file_size = Path(video_path).stat().st_size
            with open(video_path, "rb") as f:
                upload_resp = await client.post(
                    f"https://rupload.facebook.com/video-upload/v21.0/{video_id}",
                    headers={
                        "Authorization": f"OAuth {access_token}",
                        "offset": "0",
                        "file_size": str(file_size),
                    },
                    content=f.read(),
                )
            upload_data = upload_resp.json()
            if not upload_data.get("success"):
                return PostResult(platform="facebook", success=False, message=f"Upload failed: {upload_data}")

            # Step 3: Publish the reel
            publish_resp = await client.post(
                f"https://graph.facebook.com/v21.0/{page_id}/video_reels",
                params={"access_token": access_token},
                data={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "title": req.title[:100] if req.title else "",
                    "description": caption,
                    "video_state": "PUBLISHED",
                },
            )
            pub_data = publish_resp.json()
            if pub_data.get("success") or pub_data.get("id"):
                post_id = pub_data.get("id", video_id)
                # Auto-comment with affiliate link (more clickable than in caption)
                if req.affiliate_link:
                    try:
                        await client.post(
                            f"https://graph.facebook.com/v21.0/{post_id}/comments",
                            params={"access_token": access_token},
                            data={"message": f"🛒 Mua ngay tại đây: {req.affiliate_link}"},
                        )
                    except Exception as e:
                        print(f"[facebook] Comment failed: {e}")
                return PostResult(platform="facebook", success=True, message="✅ Đã đăng Reel!", post_id=str(post_id))
            else:
                return PostResult(platform="facebook", success=False, message=f"Publish failed: {pub_data.get('error', {}).get('message', str(pub_data))}")

    except Exception as e:
        return PostResult(platform="facebook", success=False, message=str(e))


async def _post_tiktok(req: PostRequest) -> PostResult:
    """Post to TikTok (placeholder — requires developer app approval)."""
    return PostResult(platform="tiktok", success=False, message="TikTok posting chưa sẵn sàng — cần đăng ký developer app")


async def _post_youtube(req: PostRequest) -> PostResult:
    """Post to YouTube (placeholder)."""
    return PostResult(platform="youtube", success=False, message="YouTube posting chưa sẵn sàng")


def build_post_request(review_data: dict, video_url: str, platform_key: str = "tiktok") -> PostRequest:
    """Build a PostRequest from pipeline review data + video URL."""
    book = review_data.get("book", {})
    platform_data = review_data.get(platform_key, {})

    video_path = video_url
    if "/output/" in video_url:
        video_path = str(Path(OUTPUT_DIR) / video_url.split("/output/")[-1])

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
        affiliate_link=review_data.get("affiliate_link", ""),
        thumbnail_path=thumbnail,
    )
