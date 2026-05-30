"""Review generation routes — single, batch-review, regen, preview."""

import json
import asyncio

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from config import make_ts, output_path, output_url
from extractor import BookInfo

router = APIRouter()


@router.post("/from-url")
async def from_url(
    url: str = Form(...),
    audience: str = Form("phu-huynh-lop-5"),
    custom_audience: str = Form(""),
    affiliate_url: str = Form(""),
    word_count_fb: int = Form(120),
    word_count_tk: int = Form(120),
    platforms: str = Form("facebook,tiktok"),
    voice_type: str = Form("edge"),
    voice_speed: int = Form(140),
    voice_id: str = Form(""),
    review_style: str = Form("auto"),
    bookmarklet_images: str = Form("[]"),
    scraped_reviews: str = Form("[]"),
    scraped_rating: float = Form(0),
    scraped_rating_count: int = Form(0),
    scraped_sold_count: int = Form(0),
    scraped_description: str = Form(""),
    scraped_price: str = Form(""),
    media: list[UploadFile] = File(default=[]),
):
    from pathlib import Path
    if "shopee" not in url:
        raise HTTPException(400, "Hiện chỉ hỗ trợ link Shopee")

    ca = json.loads(custom_audience) if custom_audience else None
    bm_imgs = json.loads(bookmarklet_images)

    uploaded_paths = []
    if media and media[0].filename:
        ts_upload = make_ts()
        img_dir = output_path(ts_upload, "images")
        img_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(media):
            ext = Path(f.filename).suffix or ".jpg"
            save_to = img_dir / f"product_{i}{ext}"
            save_to.write_bytes(await f.read())
            uploaded_paths.append(f"{output_url(ts_upload, 'images')}/product_{i}{ext}")

    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
    from pipeline import PipelineInput, process_product
    inp = PipelineInput(
        url=url, audience=audience, custom_audience=ca,
        affiliate_url=affiliate_url,
        word_count_fb=word_count_fb, word_count_tk=word_count_tk,
        image_urls=uploaded_paths or bm_imgs,
        voice_type=voice_type, elevenlabs_voice_id=voice_id, voice_speed=voice_speed,
        platforms=platform_list,
        scraped_reviews=json.loads(scraped_reviews),
        scraped_rating=scraped_rating or None,
        scraped_rating_count=scraped_rating_count,
        scraped_sold_count=scraped_sold_count,
        scraped_description=scraped_description,
        scraped_price=scraped_price,
        style_id=review_style,
    )
    result = await process_product(inp)
    if result.error:
        raise HTTPException(500, result.error)
    return result.review_data


@router.post("/batch-review")
async def batch_review(
    url: str = Form(...),
    audience: str = Form("custom"),
    custom_audience: str = Form(""),
    affiliate_url: str = Form(""),
    word_count_fb: int = Form(120),
    word_count_tk: int = Form(120),
    platforms: str = Form("facebook,tiktok"),
    review_style: str = Form("auto"),
    scraped_reviews: str = Form("[]"),
    scraped_rating: float = Form(0),
    scraped_rating_count: int = Form(0),
    scraped_sold_count: int = Form(0),
    scraped_description: str = Form(""),
    scraped_price: str = Form(""),
):
    """Step 2a: Generate review text only (no audio, no images)."""
    from extractor import extract_from_shopee
    from reviewer import generate_review
    from affiliate import get_affiliate_link

    ca = json.loads(custom_audience) if custom_audience else None
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    book = await extract_from_shopee(url)
    if scraped_description and not book.description:
        book.description = scraped_description
    if scraped_price and not book.price:
        book.price = scraped_price
    if scraped_rating and not book.rating:
        book.rating = scraped_rating
    if scraped_rating_count and not book.rating_count:
        book.rating_count = scraped_rating_count
    if scraped_sold_count and not book.sold_count:
        book.sold_count = scraped_sold_count
    reviews_list = json.loads(scraped_reviews)
    if reviews_list and not book.reviews:
        book.reviews = reviews_list
    if affiliate_url:
        book.shopee_url = affiliate_url
    else:
        aff = await get_affiliate_link(url)
        if aff:
            book.shopee_url = aff

    _fallback = {"social_post": "", "review": "", "hashtags": [], "hook": "", "key_points": [], "cta": ""}
    try:
        review = await asyncio.to_thread(generate_review, book, audience, "facebook", ca, min(word_count_fb, 300), review_style)
    except Exception as e:
        review = {**_fallback, "review": f"Error: {e}"}

    result = {"book": {"title": book.title, "author": book.author, "price": book.price, "shopee_url": book.shopee_url, "source": book.source}}
    for platform in platform_list:
        result[platform] = dict(review)

    result["affiliate_link"] = book.shopee_url or ""
    result["audience_name"] = ca.get("name", "") if ca else ""
    return result


@router.post("/batch-personas")
async def batch_personas(
    urls: str = Form(...),
    affiliate_urls: str = Form("{}"),
    voice_type: str = Form("edge"),
    voice_id: str = Form(""),
    word_count: int = Form(150),
    word_count_fb: int = Form(120),
):
    """Batch: suggest personas per product, generate reviews for each persona."""
    from pipeline import batch_with_personas
    url_list = [u.strip() for u in urls.split("\n") if u.strip().startswith("http")]
    if not url_list:
        raise HTTPException(400, "Nhập ít nhất 1 link Shopee")
    aff_map = json.loads(affiliate_urls) if affiliate_urls else {}
    results = await batch_with_personas(url_list[:10], voice_type, voice_id, word_count, aff_map, word_count_fb)
    return {"results": [
        {
            "url": r.url,
            "title": r.title,
            "error": r.error,
            "personas": r.personas,
            "reviews": [
                {"persona": r.personas[i] if i < len(r.personas) else {},
                 "data": rv.review_data, "error": rv.error}
                for i, rv in enumerate(r.reviews)
            ],
        } for r in results
    ]}


@router.post("/preview")
async def preview_review(
    title: str = Form(...),
    author: str = Form(""),
    description: str = Form(""),
    audience: str = Form("phu-huynh-lop-5"),
    platform: str = Form("facebook"),
    review_style: str = Form("auto"),
):
    """Quick preview: manually enter book info, get a review for one platform."""
    from reviewer import generate_review
    from tts import generate_audio
    book = BookInfo(
        title=title,
        author=author or "Không rõ tác giả",
        description=description,
    )
    result = generate_review(book, audience, platform, style_id=review_style)

    ts = make_ts()
    text = result.get("social_post", result.get("review", ""))
    if text:
        suffix = f"{platform}.mp3"
        await generate_audio(text, str(output_path(ts, suffix)))
        result["audio_url"] = output_url(ts, suffix)

    return result


@router.post("/regen-review")
async def regen_review(
    platform: str = Form(...),
    title: str = Form(""),
    author: str = Form(""),
    description: str = Form(""),
    shopee_url: str = Form(""),
    audience: str = Form("phu-huynh-lop-5"),
    custom_audience: str = Form(""),
    word_count: int = Form(150),
    review_style: str = Form("auto"),
    scraped_reviews: str = Form("[]"),
    scraped_rating: float = Form(0),
    scraped_rating_count: int = Form(0),
    scraped_sold_count: int = Form(0),
):
    """Regenerate review for a single platform."""
    from reviewer import generate_review
    ca = json.loads(custom_audience) if custom_audience else None
    book = BookInfo(title=title, author=author or "Không rõ tác giả", description=description, shopee_url=shopee_url)
    if scraped_rating:
        book.rating = scraped_rating
    if scraped_rating_count:
        book.rating_count = scraped_rating_count
    if scraped_sold_count:
        book.sold_count = scraped_sold_count
    reviews = json.loads(scraped_reviews)
    if reviews:
        book.reviews = reviews
    result = generate_review(book, audience, platform, ca, word_count, review_style)
    return result
