import logging; _log = logging.getLogger("extractor")
"""Extract product info from PDF files or Shopee product links."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import httpx

import tempfile
SHOPEE_BROWSER_DIR = str(Path(tempfile.gettempdir()) / "shopee-session")


@dataclass
class BookInfo:
    title: str
    author: str
    description: str
    price: str | None = None
    image_url: str | None = None
    image_urls: list[str] = field(default_factory=list)
    shopee_url: str | None = None
    source: str = ""  # "pdf" or "shopee"
    rating: float | None = None
    rating_count: int = 0
    sold_count: int = 0
    reviews: list[dict] = field(default_factory=list)


def extract_from_pdf(file_path: str) -> BookInfo:
    """Extract book metadata and sample text from a PDF."""
    doc = fitz.open(file_path)
    meta = doc.metadata or {}
    title = meta.get("title", "")
    author = meta.get("author", "")

    text_parts = []
    char_count = 0
    for page in doc:
        page_text = page.get_text()
        text_parts.append(page_text)
        char_count += len(page_text)
        if char_count > 3000:
            break

    full_text = "\n".join(text_parts)[:3000]
    if not title:
        for line in full_text.split("\n"):
            line = line.strip()
            if len(line) > 3 and not line.isdigit():
                title = line
                break

    doc.close()
    return BookInfo(
        title=title or Path(file_path).stem,
        author=author or "Không rõ tác giả",
        description=full_text,
        source="pdf",
    )


async def extract_from_shopee(url: str) -> BookInfo:
    """Extract product info from Shopee URL."""
    # Resolve short URLs (s.shopee.vn/xxx) to full product URLs
    if 's.shopee.vn/' in url and '-i.' not in url:
        try:
            r = httpx.head(url, follow_redirects=True, timeout=10)
            resolved = str(r.url).split('?')[0]  # strip tracking params
            if 'shopee.vn/' in resolved:
                url = resolved
        except Exception:
            pass

    title = _title_from_url(url)

    # If URL has no readable slug, try AffiPad
    import re as _re
    is_unreadable = not title or title.startswith("product/") or len(title) < 5 or bool(_re.search(r'/\d{5,}', title))
    if is_unreadable:
        try:
            import os
            api_key = os.getenv("AFFIPAD_API_KEY", "")
            if api_key:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post("https://api.affipad.com/v1/product-info",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"url": url})
                    data = resp.json()
                    if data.get("success"):
                        info = data["data"]["productInfo"]
                        title = info.get("name", title)
                        price = info.get("price")
                        return BookInfo(
                            title=title or "Sản phẩm từ Shopee",
                            author=_guess_author(title, ""),
                            description="",
                            price=f"₫{price:,.0f}" if price else None,
                            shopee_url=url,
                            source="shopee",
                        )
        except Exception as e:
            _log.warning(f" AffiPad product-info failed: {e}")

    return BookInfo(
        title=title or "Sản phẩm từ Shopee",
        author=_guess_author(title, ""),
        description="",
        shopee_url=url,
        source="shopee",
    )


def _title_from_url(url: str) -> str:
    from urllib.parse import unquote
    path = unquote(url.split("shopee.vn/")[-1] if "shopee.vn/" in url else "")
    slug = path.split("-i.")[0] if "-i." in path else path
    return slug.replace("-", " ").strip()


def _guess_author(title: str, desc: str) -> str:
    patterns = [
        r"(?:tác giả|author)[:\s]+([^\-\|,]+)",
        r"(?:của|by)\s+([^\-\|,]+)",
    ]
    for text in [title, desc]:
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return "Không rõ tác giả"


async def download_images(image_urls: list[str], output_dir: str, include_video: bool = False) -> list[str]:
    paths = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for i, url in enumerate(image_urls[:15]):
            try:
                is_video = ".mp4" in url or "video" in url
                if is_video and not include_video:
                    continue
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    ext = "mp4" if is_video else "jpg"
                    path = str(Path(output_dir) / f"product_{i}.{ext}")
                    Path(path).write_bytes(resp.content)
                    # Validate image is not blank
                    if not is_video:
                        try:
                            from PIL import Image
                            img = Image.open(path)
                            # Skip if too small or mostly single color
                            if img.size[0] < 50 or img.size[1] < 50:
                                Path(path).unlink(missing_ok=True)
                                continue
                            colors = img.convert("RGB").getcolors(maxcolors=100)
                            if colors and len(colors) == 1:
                                Path(path).unlink(missing_ok=True)
                                continue
                        except Exception:
                            Path(path).unlink(missing_ok=True)
                            continue
                    paths.append(path)
            except Exception:
                continue
    return paths
