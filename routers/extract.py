"""Product extraction routes — Shopee, PDF, bookmarklet."""

import json
import os
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from config import UPLOAD_DIR, make_ts, output_path, output_url
from extractor import BookInfo, extract_from_pdf, extract_from_shopee, download_images

router = APIRouter()

_QUEUE_FILE = Path(__file__).parent.parent / "shopee_queue.json"


def _load_queue() -> list:
    if _QUEUE_FILE.exists():
        try:
            return json.loads(_QUEUE_FILE.read_text())
        except Exception:
            pass
    return []


def _save_queue(queue: list):
    _QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False))


@router.post("/fetch-product-title")
async def fetch_product_title(request: Request):
    """Get product title from AffiPad when URL has no readable slug."""
    data = await request.json()
    url = data.get("url", "")
    api_key = os.getenv("AFFIPAD_API_KEY", "")
    if not api_key or not url:
        return {"title": ""}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("https://api.affipad.com/v1/product-info",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"url": url})
            d = resp.json()
            if d.get("success"):
                return {"title": d["data"]["productInfo"].get("name", "")}
    except Exception:
        pass
    return {"title": ""}


@router.post("/suggest-personas")
async def suggest_personas_endpoint(title: str = Form(...)):
    """Use LLM to suggest 3 customer personas for a product."""
    from reviewer import suggest_personas
    from config import log
    try:
        personas = suggest_personas(title)
        log.info(f"Personas for '{title[:30]}': {[p.get('name','?') for p in personas]}")
    except Exception as e:
        log.warning(f"Persona suggestion failed for '{title[:30]}': {e}")
        personas = []
    return {"personas": personas, "error": "" if personas else "LLM failed"}


@router.post("/receive-shopee-data")
async def receive_shopee_data(request: Request):
    """Receive product data sent from bookmarklet running on Shopee page."""
    data = await request.json()
    return await _process_shopee_data(request, data)


@router.get("/receive-shopee-data")
async def receive_shopee_data_get(request: Request, data: str = ""):
    """GET fallback for bookmarklet (data as query param)."""
    from fastapi.responses import HTMLResponse
    if data:
        await _process_shopee_data(request, json.loads(data))
        return HTMLResponse("<html><body><script>window.close()</script>OK — bạn có thể đóng tab này.</body></html>")
    return {"error": "No data"}


async def _process_shopee_data(request: Request, data: dict):
    result = {
        "title": data.get("title", ""),
        "price": data.get("price", ""),
        "description": data.get("description", ""),
        "rating": data.get("rating"),
        "rating_count": data.get("rating_count", 0),
        "sold_count": data.get("sold_count", 0),
        "reviews": data.get("reviews", []),
        "url": data.get("url", ""),
    }

    request.app.state.last_shopee_data = result
    # Also append to batch queue (persisted to disk)
    if not hasattr(request.app.state, "shopee_queue"):
        request.app.state.shopee_queue = _load_queue()
    # Deduplicate by URL
    request.app.state.shopee_queue = [q for q in request.app.state.shopee_queue if q.get("url") != result.get("url")]
    request.app.state.shopee_queue.append(result)
    _save_queue(request.app.state.shopee_queue)
    return result


@router.get("/poll-shopee-data")
async def poll_shopee_data(request: Request):
    """Poll for bookmarklet data (single product — consumed on read)."""
    data = getattr(request.app.state, "last_shopee_data", None)
    if data:
        request.app.state.last_shopee_data = None
        return {"ready": True, "data": data}
    return {"ready": False}


@router.get("/poll-shopee-queue")
async def poll_shopee_queue(request: Request):
    """Get all queued products from extension/bookmarklet (not consumed)."""
    if not hasattr(request.app.state, "shopee_queue"):
        request.app.state.shopee_queue = _load_queue()
    queue = request.app.state.shopee_queue
    return {"products": queue, "count": len(queue)}


@router.post("/clear-shopee-queue")
async def clear_shopee_queue(request: Request):
    """Clear the batch queue."""
    request.app.state.shopee_queue = []
    _save_queue([])
    return {"ok": True}


@router.post("/fetch-images")
async def fetch_images(url: str = Form(...)):
    """Fetch product images/videos from Shopee URL without generating review."""
    if "shopee" not in url:
        raise HTTPException(400, "Chỉ hỗ trợ link Shopee")

    book = await extract_from_shopee(url)
    ts = make_ts()

    result = {
        "title": book.title,
        "price": book.price,
        "rating": book.rating,
        "rating_count": book.rating_count,
    }

    if book.image_urls:
        img_dir = str(output_path(ts, "images"))
        local = await download_images(book.image_urls, img_dir)
        result["product_images"] = [f"{output_url(ts, 'images')}/{Path(p).name}" for p in local]

    return result


@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    audience: str = Form("phu-huynh-lop-5"),
    custom_audience: str = Form(""),
    word_count: int = Form(150),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Chỉ hỗ trợ file PDF")

    ts = make_ts()
    save_path = Path(UPLOAD_DIR) / f"{ts}_{file.filename}"
    content = await file.read()
    save_path.write_bytes(content)

    book = extract_from_pdf(str(save_path))
    from reviewer import generate_review
    ca = json.loads(custom_audience) if custom_audience else None
    review = generate_review(book, audience, "facebook", ca, min(word_count, 200))
    result = {
        "book": {"title": book.title, "author": book.author, "price": book.price, "shopee_url": book.shopee_url, "source": book.source},
        "audience": audience,
        "facebook": dict(review),
        "tiktok": dict(review),
    }

    from pipeline import _add_audio
    result = await _add_audio(result, ts)

    out_path = output_path(ts, "review.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    result["_pdf_path"] = str(save_path)
    return result


@router.post("/import-excel")
async def import_excel(file: UploadFile):
    """Parse Excel file with product URLs and affiliate links."""
    from importer import parse_product_excel
    import httpx
    data = await file.read()
    products = parse_product_excel(data)
    if not products:
        raise HTTPException(400, "Không tìm thấy sản phẩm trong file Excel")
    api_key = os.getenv("AFFIPAD_API_KEY", "")
    if api_key:
        async with httpx.AsyncClient(timeout=10) as client:
            for p in products:
                if p["title"].startswith("product/") or len(p["title"]) < 5:
                    try:
                        resp = await client.post("https://api.affipad.com/v1/product-info",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={"url": p["url"]})
                        info = resp.json()
                        if info.get("success"):
                            p["title"] = info["data"]["productInfo"].get("name", p["title"])
                    except Exception:
                        pass
    return {"products": products}
