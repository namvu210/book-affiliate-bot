"""Platform OAuth, publish, history, and settings routes."""

import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from config import OUTPUT_DIR, make_ts

router = APIRouter()


@router.post("/publish")
async def publish_content(
    review_json: str = Form(...),
    video_url: str = Form(""),
    platforms: str = Form("facebook"),
    page_id: str = Form(""),
    force: str = Form("0"),
):
    """Publish video + caption to social platforms."""
    from poster import publish, build_post_request
    from history import check_duplicate, record_publish
    try:
        data = json.loads(review_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid review JSON")
    if not isinstance(data, dict):
        raise HTTPException(400, "review_json must be a JSON object")
    valid_platforms = {"facebook", "tiktok", "youtube", "instagram", "threads"}
    platform_list = [p.strip() for p in platforms.split(",") if p.strip() in valid_platforms]
    if not platform_list:
        raise HTTPException(400, f"No valid platform. Choose from: {', '.join(valid_platforms)}")

    book = data.get("book", {})
    product_url = book.get("shopee_url", "")
    if product_url and force != "1":
        warnings = []
        for plat in platform_list:
            prev = check_duplicate(product_url, plat)
            if prev:
                warnings.append(f"{plat}: đã đăng ngày {prev['published_at'][:10]}")
        if warnings:
            return {"duplicate_warning": True, "warnings": warnings, "message": "Sản phẩm đã được đăng trước đó. Đăng lại?"}

    req = build_post_request(data, video_url, platform_list[0])
    req.platforms = platform_list
    req.page_id = page_id
    results = await publish(req)

    product_images = data.get("product_images", [])
    ai_imgs = [p for p in product_images if "ai_images" in p]
    real_imgs = [p for p in product_images if "ai_images" not in p]
    for r in results:
        if r.success:
            plat_data = data.get(r.platform, {})
            post_url = ""
            if r.post_id:
                if r.platform == "facebook":
                    post_url = f"https://www.facebook.com/reel/{r.post_id}"
                elif r.platform == "tiktok":
                    post_url = f"https://www.tiktok.com/@/video/{r.post_id}"
                elif r.platform == "youtube":
                    post_url = f"https://youtube.com/shorts/{r.post_id}"
                elif r.platform == "threads":
                    post_url = f"https://www.threads.net/post/{r.post_id}"
            record_publish(
                product_url, book.get("shopee_url", ""), r.platform, book.get("title", ""),
                persona=data.get("audience_name", ""),
                hook=plat_data.get("hook", ""),
                cta=plat_data.get("cta", ""),
                review_text=plat_data.get("social_post", ""),
                images=real_imgs, ai_images=ai_imgs, video_path=video_url,
                post_url=post_url,
            )

    return {"results": [{"platform": r.platform, "success": r.success, "message": r.message, "post_id": r.post_id} for r in results]}


@router.get("/api/history")
async def get_history(platform: str = "", days: int = 90):
    """Return publish history, optionally filtered by platform and date range."""
    from history import HISTORY_FILE
    if not HISTORY_FILE.exists():
        return {"records": []}
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    records = []
    with open(HISTORY_FILE, 'r', newline='') as f:
        for row in csv.DictReader(f):
            if row.get('published_at', '') < cutoff:
                continue
            if platform and row.get('platform') != platform:
                continue
            records.append(row)
    records.reverse()
    return {"records": records}


@router.get("/api/platforms")
async def platform_status():
    """Check which social platforms are connected."""
    from auth import get_platform_status
    return get_platform_status()


@router.get("/api/facebook-pages")
async def facebook_pages():
    """List connected Facebook pages."""
    from auth import get_facebook_pages
    pages = get_facebook_pages()
    return {"pages": [{"page_id": p["page_id"], "name": p["display_name"]} for p in pages]}


@router.get("/connect/{platform}")
async def connect_platform(platform: str, request: Request):
    """Redirect to OAuth login for a platform."""
    from auth import tiktok_auth_url, youtube_auth_url, facebook_auth_url, threads_auth_url
    from fastapi.responses import RedirectResponse
    if platform == "tiktok":
        origin = f"{request.url.scheme}://{request.url.netloc}"
        url = tiktok_auth_url(server_origin=origin)
    else:
        urls = {"youtube": youtube_auth_url, "facebook": facebook_auth_url, "threads": threads_auth_url}
        fn = urls.get(platform)
        if not fn:
            raise HTTPException(400, f"Unknown platform: {platform}")
        url = fn()
    return RedirectResponse(url)


@router.get("/callback/{platform}")
async def oauth_callback(platform: str, code: str = "", state: str = ""):
    """Handle OAuth callback from platforms."""
    if not code:
        return HTMLResponse("<html><body><h2>❌ Lỗi: không nhận được mã xác thực</h2></body></html>")
    from auth import tiktok_exchange_code, youtube_exchange_code, facebook_exchange_code, threads_exchange_code, save_platform_token
    exchangers = {"tiktok": tiktok_exchange_code, "youtube": youtube_exchange_code, "facebook": facebook_exchange_code, "threads": threads_exchange_code}
    fn = exchangers.get(platform)
    if not fn:
        return HTMLResponse(f"<html><body><h2>❌ Unknown platform: {platform}</h2></body></html>")
    token_data = await fn(code)
    if token_data and token_data.get("access_token"):
        save_platform_token(platform, token_data)
        name = token_data.get("display_name", platform)
        return HTMLResponse(f"<html><body><h2>✅ Đã kết nối {name}!</h2><p>Bạn có thể đóng tab này.</p><script>window.close()</script></body></html>")
    error_detail = token_data.get("error", "") if token_data else ""
    return HTMLResponse(f"<html><body><h2>❌ Kết nối thất bại.</h2><p style='color:#666;font-size:14px'>{error_detail}</p></body></html>")


@router.post("/disconnect/{platform}")
async def disconnect(platform: str):
    """Disconnect a platform."""
    from auth import disconnect_platform
    disconnect_platform(platform)
    return {"status": "ok"}


@router.get("/api/settings")
async def get_settings():
    """Return which credentials are configured (not the values)."""
    keys = ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET",
            "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
            "FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET",
            "THREADS_APP_ID", "THREADS_APP_SECRET",
            "ELEVENLABS_API_KEY", "AFFIPAD_API_KEY", "BITLY_API_KEY", "GEMINI_API_KEY"]
    return {k: bool(os.getenv(k, "")) for k in keys}


@router.post("/api/settings")
async def save_settings(request: Request):
    """Save credentials to .env file."""
    data = await request.json()
    env_path = Path(".env")
    existing = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
    for k, v in data.items():
        if v and v.strip():
            existing[k] = v.strip()
    env_path.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")
    return {"status": "ok", "message": "✅ Đã lưu. Khởi động lại server để áp dụng."}
