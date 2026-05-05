"""Publish history — track posted products to warn on duplicates."""

import csv
import re
import threading
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path("publish_history.csv")
_lock = threading.Lock()


def _extract_product_id(url: str) -> str:
    """Extract stable product ID (shopid.itemid) from Shopee URL."""
    m = re.search(r'-i\.(\d+\.\d+)', url)
    if m:
        return m.group(1)
    # Fallback: use full URL stripped of params
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


def record_publish(url: str, affiliate_url: str, platform: str, title: str = ""):
    """Record a successful publish."""
    product_id = _extract_product_id(url)
    exists = HISTORY_FILE.exists()
    with _lock:
        with open(HISTORY_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['product_id', 'url', 'affiliate_url', 'platform', 'title', 'published_at'])
            if not exists:
                writer.writeheader()
            writer.writerow({
                'product_id': product_id,
                'url': url,
                'affiliate_url': affiliate_url,
                'platform': platform,
                'title': title[:100],
                'published_at': datetime.now().isoformat(),
            })
