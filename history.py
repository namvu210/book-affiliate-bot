"""Publish history — track posted products to warn on duplicates."""

import csv
import re
import threading
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path("publish_history.csv")
FIELDS = ['product_id', 'url', 'affiliate_url', 'platform', 'title',
           'persona', 'hook', 'cta', 'review_text',
           'images', 'ai_images', 'video_path', 'post_url', 'published_at']
_lock = threading.Lock()


def _extract_product_id(url: str) -> str:
    """Extract stable product ID (shopid.itemid) from Shopee URL."""
    m = re.search(r'-i\.(\d+\.\d+)', url)
    if m:
        return m.group(1)
    return url.split('?')[0].rstrip('/')


def check_duplicate(url: str, platform: str) -> dict | None:
    """Check if product was previously published. Returns record dict or None."""
    product_id = _extract_product_id(url)
    if not HISTORY_FILE.exists():
        return None
    with _lock:
        with open(HISTORY_FILE, 'r', newline='') as f:
            for row in csv.DictReader(f):
                if row.get('product_id') == product_id and row.get('platform') == platform:
                    return row
    return None


def record_publish(url: str, affiliate_url: str, platform: str, title: str = "",
                   persona: str = "", hook: str = "", cta: str = "",
                   review_text: str = "", images: list[str] = None,
                   ai_images: list[str] = None, video_path: str = "", post_url: str = ""):
    """Record a successful publish with all asset locations."""
    product_id = _extract_product_id(url)
    exists = HISTORY_FILE.exists()
    with _lock:
        with open(HISTORY_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow({
                'product_id': product_id,
                'url': url,
                'affiliate_url': affiliate_url,
                'platform': platform,
                'title': title[:100],
                'persona': persona[:100],
                'hook': hook[:200],
                'cta': cta[:200],
                'review_text': (review_text or '')[:500],
                'images': '|'.join(images or []),
                'ai_images': '|'.join(ai_images or []),
                'video_path': video_path,
                'post_url': post_url,
                'published_at': datetime.now().isoformat(),
            })
