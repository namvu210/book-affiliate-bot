import logging; _log = logging.getLogger("auth")
"""OAuth token management for social platforms."""

import json
import os
import time
from pathlib import Path

import httpx

TOKENS_FILE = Path(__file__).parent / "tokens.json"


def _load_tokens() -> dict:
    if TOKENS_FILE.exists():
        return json.loads(TOKENS_FILE.read_text())
    return {}


def _save_tokens(data: dict):
    TOKENS_FILE.write_text(json.dumps(data, indent=2))


def get_platform_status() -> dict:
    """Return connection status for all platforms."""
    tokens = _load_tokens()
    result = {}
    for platform in ["tiktok", "youtube", "facebook"]:
        t = tokens.get(platform, {})
        result[platform] = {
            "connected": bool(t.get("access_token")),
            "name": t.get("display_name", ""),
            "expires_at": t.get("expires_at", 0),
        }
    # Add FB page count
    pages = get_facebook_pages()
    if pages:
        result["facebook"]["connected"] = True
        result["facebook"]["name"] = ", ".join(p["display_name"] for p in pages)
        result["facebook"]["page_count"] = len(pages)
    return result


def get_access_token(platform: str) -> str | None:
    """Get a valid access token, refreshing if needed."""
    tokens = _load_tokens()
    t = tokens.get(platform, {})
    if not t.get("access_token"):
        return None

    # Check if expired and refresh
    if t.get("expires_at", 0) < time.time() and t.get("refresh_token"):
        refreshed = _refresh_token(platform, t)
        if refreshed:
            tokens[platform].update(refreshed)
            _save_tokens(tokens)
            return refreshed["access_token"]

    return t.get("access_token")


def save_platform_token(platform: str, token_data: dict):
    """Save OAuth token data for a platform."""
    tokens = _load_tokens()
    tokens[platform] = token_data
    _save_tokens(tokens)


def disconnect_platform(platform: str):
    """Remove stored tokens for a platform."""
    tokens = _load_tokens()
    tokens.pop(platform, None)
    if platform == "facebook":
        tokens.pop("facebook_pages", None)
    _save_tokens(tokens)


def get_facebook_pages() -> list[dict]:
    """Return all connected Facebook pages."""
    tokens = _load_tokens()
    pages = tokens.get("facebook_pages", [])
    if not pages:
        # Backward compat: single page in old format
        fb = tokens.get("facebook", {})
        if fb.get("access_token"):
            pages = [{"access_token": fb["access_token"], "page_id": fb["page_id"], "display_name": fb.get("display_name", "")}]
    return pages


def get_facebook_token(page_id: str = "") -> tuple[str, str]:
    """Get access token for a specific FB page. Returns (token, page_id)."""
    pages = get_facebook_pages()
    if not pages:
        return "", ""
    if page_id:
        for p in pages:
            if p["page_id"] == page_id:
                return p["access_token"], p["page_id"]
    # Default: first page
    return pages[0]["access_token"], pages[0]["page_id"]


# === TikTok OAuth ===

def tiktok_auth_url(server_origin: str = "") -> str:
    import hashlib, base64, secrets
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    redirect = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8000/callback/tiktok")
    # PKCE
    code_verifier = secrets.token_urlsafe(43)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    # Store verifier for token exchange
    tokens = _load_tokens()
    tokens["_tiktok_pkce"] = code_verifier
    _save_tokens(tokens)
    # Encode server origin in state so callback page can redirect back
    import urllib.parse
    state = urllib.parse.quote(server_origin) if server_origin else ""
    return (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={client_key}"
        f"&scope=video.upload,user.info.basic"
        f"&response_type=code"
        f"&redirect_uri={redirect}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&state={state}"
    )


async def tiktok_exchange_code(code: str) -> dict:
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")
    redirect = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8000/callback/tiktok")
    # Retrieve PKCE verifier
    tokens = _load_tokens()
    code_verifier = tokens.pop("_tiktok_pkce", "")
    _save_tokens(tokens)
    _log.info(f"Exchange: key={client_key}, redirect={redirect}, verifier={'yes' if code_verifier else 'MISSING'}, code={code[:20]}...")
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://open.tiktokapis.com/v2/oauth/token/", data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
            "code_verifier": code_verifier,
        })
        data = resp.json()
        _log.info(f"Token response: {data}")
        if "access_token" in data:
            # Fetch user info
            display_name = "TikTok User"
            try:
                user_resp = await client.get(
                    "https://open.tiktokapis.com/v2/user/info/?fields=display_name",
                    headers={"Authorization": f"Bearer {data['access_token']}"},
                )
                udata = user_resp.json()
                display_name = udata.get("data", {}).get("user", {}).get("display_name", display_name)
            except Exception:
                pass
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", ""),
                "expires_at": time.time() + data.get("expires_in", 86400),
                "open_id": data.get("open_id", ""),
                "display_name": display_name,
            }
    return {}


# === YouTube OAuth ===

def youtube_auth_url() -> str:
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
    redirect = os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8000/callback/youtube")
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect}"
        f"&response_type=code"
        f"&scope=https://www.googleapis.com/auth/youtube.upload"
        f"&access_type=offline"
        f"&prompt=consent"
    )


async def youtube_exchange_code(code: str) -> dict:
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    redirect = os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8000/callback/youtube")
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
        })
        data = resp.json()
        if "access_token" in data:
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", ""),
                "expires_at": time.time() + data.get("expires_in", 3600),
                "display_name": "YouTube Channel",
            }
    return {}


# === Facebook OAuth ===

def facebook_auth_url() -> str:
    app_id = os.getenv("FACEBOOK_APP_ID", "")
    redirect = os.getenv("FACEBOOK_REDIRECT_URI", "http://localhost:8000/callback/facebook")
    state = "https://localhost:8000"
    return (
        f"https://www.facebook.com/v21.0/dialog/oauth"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect}"
        f"&scope=pages_manage_posts,pages_read_engagement,pages_show_list,pages_manage_engagement"
        f"&response_type=code"
        f"&state={state}"
    )


async def facebook_exchange_code(code: str) -> dict:
    app_id = os.getenv("FACEBOOK_APP_ID", "")
    app_secret = os.getenv("FACEBOOK_APP_SECRET", "")
    redirect = os.getenv("FACEBOOK_REDIRECT_URI", "http://localhost:8000/callback/facebook")
    async with httpx.AsyncClient() as client:
        # Exchange code for user token
        resp = await client.get("https://graph.facebook.com/v21.0/oauth/access_token", params={
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
            "redirect_uri": redirect,
        })
        data = resp.json()
        user_token = data.get("access_token", "")
        if not user_token:
            return {}

        # Get all page tokens (long-lived)
        pages_resp = await client.get(f"https://graph.facebook.com/v21.0/me/accounts", params={
            "access_token": user_token,
        })
        pages = pages_resp.json().get("data", [])
        if not pages:
            return {}

        # Save all pages as array
        fb_pages = []
        for page in pages:
            fb_pages.append({
                "access_token": page["access_token"],
                "page_id": page["id"],
                "display_name": page.get("name", "Facebook Page"),
                "expires_at": time.time() + 5184000,
            })

        # Store as array; return first for backward compat
        tokens = _load_tokens()
        tokens["facebook_pages"] = fb_pages
        # Keep single "facebook" entry for backward compat (first page)
        tokens["facebook"] = {**fb_pages[0], "refresh_token": ""}
        _save_tokens(tokens)
        return tokens["facebook"]


def _refresh_token(platform: str, token_data: dict) -> dict | None:
    """Refresh an expired access token."""
    try:
        if platform == "tiktok":
            r = httpx.post("https://open.tiktokapis.com/v2/oauth/token/", data={
                "client_key": os.getenv("TIKTOK_CLIENT_KEY", ""),
                "client_secret": os.getenv("TIKTOK_CLIENT_SECRET", ""),
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
            })
            d = r.json()
            if "access_token" in d:
                return {"access_token": d["access_token"], "expires_at": time.time() + d.get("expires_in", 86400),
                        "refresh_token": d.get("refresh_token", token_data["refresh_token"])}

        elif platform == "youtube":
            r = httpx.post("https://oauth2.googleapis.com/token", data={
                "client_id": os.getenv("YOUTUBE_CLIENT_ID", ""),
                "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", ""),
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
            })
            d = r.json()
            if "access_token" in d:
                return {"access_token": d["access_token"], "expires_at": time.time() + d.get("expires_in", 3600)}
    except Exception as e:
        _log.warning(f"Refresh failed for {platform}: {e}")
    return None
