"""Generate book reviews using Google Gemini."""

import json

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL, AUDIENCES
from extractor import BookInfo

_model = None


def _get_model():
    global _model
    if _model is None:
        genai.configure(api_key=GEMINI_API_KEY)
        _model = genai.GenerativeModel(GEMINI_MODEL)
    return _model


def generate_review(
    book: BookInfo,
    audience_key: str = "phu-huynh-lop-5",
    platform: str = "facebook",
    custom_audience: dict | None = None,
    word_count: int = 150,
) -> dict:
    """Generate a review + social post for a book targeting a specific audience."""
    audience = custom_audience or AUDIENCES.get(audience_key, AUDIENCES["phu-huynh-lop-5"])

    platform_guide = {
        "facebook": "Bài viết Facebook 300-500 từ, có emoji, chia đoạn rõ ràng, kết thúc bằng CTA mua sách.",
        "tiktok": "Script TikTok 60-90 giây. Viết dạng văn nói tự nhiên, KHÔNG dùng timestamp như [0-3s]. Mở đầu bằng hook gây tò mò, ngắn gọn, có nhịp điệu. Viết như đang nói chuyện với người xem.",
    }

    ratings_context = ""
    if book.rating:
        ratings_context += f"\n- Đánh giá: {book.rating}/5 ({book.rating_count} lượt đánh giá)"
    if book.reviews:
        top_reviews = sorted(book.reviews, key=lambda r: r.get("likes", 0), reverse=True)[:10]
        review_texts = []
        for r in top_reviews:
            stars = "⭐" * r.get("rating", 0)
            review_texts.append(f"  {stars} {r['text'][:200]}")
        ratings_context += "\n- Nhận xét thực từ người mua:\n" + "\n".join(review_texts)

    prompt = f"""Bạn là chuyên gia review sách và content creator cho mạng xã hội tại Việt Nam.

THÔNG TIN SÁCH:
- Tên: {book.title}
- Tác giả: {book.author}
- Mô tả/Nội dung: {book.description[:3000]}
{f"- Giá: {book.price}" if book.price else ""}
{f"- Link mua: {book.shopee_url}" if book.shopee_url else ""}
{ratings_context}

ĐỐI TƯỢNG: {audience['name']}
GIỌNG VĂN: {audience['tone']}
TRỌNG TÂM: {audience['focus']}

YÊU CẦU: Tạo nội dung cho {platform}.
{platform_guide.get(platform, platform_guide['facebook'])}

LƯU Ý QUAN TRỌNG:
- Dựa vào MÔ TẢ SẢN PHẨM để hiểu rõ nội dung/tính năng sản phẩm
- Tham khảo nhận xét thực từ người mua để tăng tính thuyết phục (trích dẫn ý kiến nổi bật nếu có)
- Nếu có đánh giá cao, nhấn mạnh điều đó trong bài viết
- Nếu có nhận xét tiêu cực hợp lý, đề cập khéo léo hoặc đưa ra góc nhìn cân bằng

Trả về JSON với format:
{{
  "review": "Bài review chi tiết về sách ({word_count} từ)",
  "social_post": "Bài đăng {platform} hoàn chỉnh (khoảng {word_count} từ)",
  "hashtags": ["danh sách hashtag phù hợp"],
  "hook": "Câu mở đầu gây chú ý (dùng cho video/reel)",
  "key_points": ["3-5 điểm nổi bật của sách"],
  "cta": "Lời kêu gọi hành động"
}}

CHỈ trả về JSON, không giải thích thêm."""

    try:
        resp = _get_model().generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=2000,
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}") from e

    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "review": text,
            "social_post": text,
            "hashtags": [],
            "hook": "",
            "key_points": [],
            "cta": "",
        }


def generate_review_all_platforms(
    book: BookInfo,
    audience_key: str = "phu-huynh-lop-5",
    custom_audience: dict | None = None,
    word_count: int = 150,
) -> dict:
    """Generate reviews for both Facebook and TikTok."""
    return {
        "book": {
            "title": book.title,
            "author": book.author,
            "price": book.price,
            "shopee_url": book.shopee_url,
            "image_url": book.image_url,
            "source": book.source,
            "rating": book.rating,
            "rating_count": book.rating_count,
            "review_count_used": len(book.reviews),
        },
        "audience": audience_key,
        "facebook": generate_review(book, audience_key, "facebook", custom_audience, word_count),
        "tiktok": generate_review(book, audience_key, "tiktok", custom_audience, word_count),
    }
