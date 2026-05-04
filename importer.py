"""Import product data from Excel files."""

import io
from urllib.parse import unquote

import openpyxl


def parse_product_excel(data: bytes) -> list[dict]:
    """Parse Excel bytes into a list of {url, affiliate, title} dicts."""
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []

    # Find column indices from header row
    header = [str(c).strip().lower() if c else "" for c in rows[0]]
    url_col = next((i for i, h in enumerate(header) if h in ("url", "link", "product_url", "product url")), 0)
    aff_col = next((i for i, h in enumerate(header) if h in ("affiliate", "aff", "affiliate_link", "affiliate link")), None)

    results = []
    for row in rows[1:]:
        url = str(row[url_col]).strip() if url_col < len(row) and row[url_col] else ""
        affiliate = ""
        if aff_col is not None and aff_col < len(row) and row[aff_col]:
            affiliate = str(row[aff_col]).strip()
        # If no URL but has affiliate link, use affiliate as URL
        if (not url or not url.startswith("http")) and affiliate and affiliate.startswith("http"):
            url = affiliate
        if not url or not url.startswith("http"):
            continue
        title = _title_from_url(url)
        results.append({"url": url, "affiliate": affiliate, "title": title})
    return results


def _title_from_url(url: str) -> str:
    """Extract product title from Shopee URL slug."""
    path = unquote(url.split("shopee.vn/")[-1] if "shopee.vn/" in url else "")
    slug = path.split("-i.")[0] if "-i." in path else path
    return slug.replace("-", " ").strip()
