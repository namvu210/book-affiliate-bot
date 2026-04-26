"""Extract book/product info from PDF files or Shopee product links."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import httpx

SHOPEE_BROWSER_DIR = "/tmp/shopee-session"


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
    """Extract product info from Shopee URL (title from URL slug, no browser needed)."""
    title = _title_from_url(url)
    return BookInfo(
        title=title or "Sản phẩm từ Shopee",
        author=_guess_author(title, ""),
        description="",
        shopee_url=url,
        source="shopee",
    )


def _filter_bot_reviews(reviews: list[dict]) -> list[dict]:
    real = []
    for r in reviews:
        text = r.get("text", "")
        if len(text) < 10:
            continue
        if len(set(text.replace(" ", ""))) < 5:
            continue
        bot_patterns = [
            r'^(good|ok|nice|tốt|hay|đẹp|ổn|👍|⭐|\.+|!+)\s*$',
            r'^.{1,5}$',
            r'^(.)\1{4,}',
            r'^(shop giao hàng nhanh|giao hàng nhanh|đóng gói cẩn thận|hàng đẹp|chất lượng tốt)\s*\.?\s*$',
        ]
        if not any(re.match(p, text.strip(), re.IGNORECASE) for p in bot_patterns):
            real.append(r)
    return real


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


async def download_images(image_urls: list[str], output_dir: str) -> list[str]:
    paths = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for i, url in enumerate(image_urls[:15]):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    is_video = ".mp4" in url or "video" in url
                    ext = "mp4" if is_video else "jpg"
                    path = str(Path(output_dir) / f"product_{i}.{ext}")
                    Path(path).write_bytes(resp.content)
                    paths.append(path)
            except Exception:
                continue
    return paths
