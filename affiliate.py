"""Affiliate link conversion and URL shortening."""

import httpx

from config import log, AFFIPAD_API_KEY, AFFIPAD_TOOL_ID, BITLY_API_KEY, SHORTIO_API_KEY, SHORTIO_DOMAIN


async def get_affiliate_link(product_url: str) -> str:
    """Convert a Shopee product URL to a shortened affiliate link. Returns '' on failure."""
    log.info(f"affipad: API_KEY: {'set' if AFFIPAD_API_KEY else 'MISSING'}, TOOL_ID: {'set' if AFFIPAD_TOOL_ID else 'MISSING'}")
    if not AFFIPAD_API_KEY or not AFFIPAD_TOOL_ID:
        return ""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.affipad.com/v1/fb-convert",
                headers={"Authorization": f"Bearer {AFFIPAD_API_KEY}", "Content-Type": "application/json"},
                json={"url": product_url, "toolId": AFFIPAD_TOOL_ID},
            )
            data = resp.json()
            if not data.get("success"):
                return ""
            results = data.get("data", {}).get("results", [])
            if not results:
                return ""
            long_link = results[0].get("link", "")
            if not long_link:
                return ""
            short = await _shorten_url(client, long_link)
            return short or long_link
    except Exception as e:
        log.warning(f"affipad: {e}")
    return ""


async def _shorten_url(client: httpx.AsyncClient, long_url: str) -> str:
    """Shorten a URL using Short.io or Bitly."""
    if SHORTIO_API_KEY and SHORTIO_DOMAIN:
        try:
            r = await client.post("https://api.short.io/links", headers={
                "Authorization": SHORTIO_API_KEY, "Content-Type": "application/json",
            }, json={"domain": SHORTIO_DOMAIN, "originalURL": long_url}, timeout=10)
            if r.status_code in (200, 201):
                return r.json().get("shortURL", "")
        except Exception as e:
            log.warning(f"shortio: {e}")
    if BITLY_API_KEY:
        try:
            r = await client.post("https://api-ssl.bitly.com/v4/shorten", headers={
                "Authorization": f"Bearer {BITLY_API_KEY}", "Content-Type": "application/json",
            }, json={"long_url": long_url}, timeout=10)
            if r.status_code in (200, 201):
                return r.json().get("link", "")
        except Exception as e:
            log.warning(f"bitly: {e}")
    return ""
