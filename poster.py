"""Post content to social platforms via n8n webhook."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from config import N8N_WEBHOOK_URL, OUTPUT_DIR


@dataclass
class PostRequest:
    video_path: str
    caption: str
    hashtags: list[str] = field(default_factory=list)
    title: str = ""
    affiliate_link: str = ""
    thumbnail_path: str = ""
    platforms: list[str] = field(default_factory=lambda: ["tiktok", "youtube"])


@dataclass
class PostResult:
    platform: str
    success: bool
    message: str = ""
    post_url: str = ""


async def publish(req: PostRequest) -> list[PostResult]:
    """Send content to n8n webhook for posting to social platforms."""
    if not N8N_WEBHOOK_URL:
        return [PostResult(platform="all", success=False, message="N8N_WEBHOOK_URL not configured in .env")]

    # Build caption with hashtags and affiliate link
    full_caption = req.caption
    if req.hashtags:
        full_caption += "\n\n" + " ".join(f"#{h.lstrip('#')}" for h in req.hashtags)
    if req.affiliate_link:
        full_caption += f"\n\n🛒 Mua ngay: {req.affiliate_link}"

    # Send video file + metadata to n8n
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            files = {}
            if req.video_path and Path(req.video_path).exists():
                files["video"] = (Path(req.video_path).name, Path(req.video_path).read_bytes(), "video/mp4")
            if req.thumbnail_path and Path(req.thumbnail_path).exists():
                files["thumbnail"] = (Path(req.thumbnail_path).name, Path(req.thumbnail_path).read_bytes(), "image/jpeg")

            data = {
                "caption": full_caption,
                "title": req.title or req.caption[:100],
                "hashtags": json.dumps(req.hashtags),
                "affiliate_link": req.affiliate_link,
                "platforms": json.dumps(req.platforms),
            }

            resp = await client.post(N8N_WEBHOOK_URL, data=data, files=files)

            if resp.status_code == 200:
                result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                return [PostResult(
                    platform=p,
                    success=True,
                    message=result.get("message", "Sent to n8n"),
                    post_url=result.get(f"{p}_url", ""),
                ) for p in req.platforms]
            else:
                return [PostResult(platform="all", success=False, message=f"n8n returned {resp.status_code}: {resp.text[:200]}")]
    except Exception as e:
        return [PostResult(platform="all", success=False, message=str(e))]


def build_post_request(review_data: dict, video_url: str, platform_key: str = "tiktok") -> PostRequest:
    """Build a PostRequest from pipeline review data + video URL."""
    book = review_data.get("book", {})
    platform_data = review_data.get(platform_key, {})

    # Resolve video path from URL
    video_path = str(Path(OUTPUT_DIR) / video_url.split("/output/")[-1]) if "/output/" in video_url else video_url

    # Use first product image as thumbnail
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
