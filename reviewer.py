"""Generate product reviews using Google Gemini."""

import json

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL, AUDIENCES
from extractor import BookInfo

_client = None
_model_name = GEMINI_MODEL


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def set_model(name: str):
    """Switch the Gemini model at runtime."""
    global _model_name
    _model_name = name


def generate_json(prompt: str, max_tokens: int = 2000, model: str = "") -> dict | list:
    """Send a prompt to Gemini and parse the JSON response."""
    try:
        resp = _get_client().models.generate_content(
            model=model or _model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}") from e

    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    # Try progressively more aggressive JSON repair
    import re
    for attempt, t in enumerate([
        text,
        re.sub(r',\s*([}\]])', r'\1', text).replace('\n', '\\n'),
        re.sub(r',\s*([}\]])', r'\1', re.sub(r"(?<=[{,\[])\s*'([^']+)'\s*:", r' "\1":', re.sub(r":\s*'([^']*)'", r': "\1"', text))),
    ]):
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            continue
    # Last resort: extract the raw text as a single review
    raise json.JSONDecodeError("All repair attempts failed", text[:100], 0)


def build_review_prompt(
    book: BookInfo,
    audience: dict,
    platform: str,
    word_count: int,
) -> str:
    """Build the LLM prompt for a review. Pure function — no I/O."""
    platform_guide = {
        "facebook": f"Bài viết Facebook ĐÚNG {word_count} từ (KHÔNG được vượt quá), có emoji, chia đoạn rõ ràng, kết thúc bằng CTA mua sản phẩm. Viết theo góc nhìn KOL/người dùng thực sự đã trải nghiệm sản phẩm, KHÔNG viết như shop bán hàng. Dùng ngôi thứ nhất (mình/tôi), chia sẻ cảm nhận cá nhân, kể trải nghiệm thực tế.",
        "tiktok": f"""Script TikTok ĐÚNG {word_count} từ (KHÔNG được vượt quá, KHÔNG tính audio tag trong []). Viết dạng văn nói tự nhiên, KHÔNG dùng timestamp như [0-3s]. Mở đầu bằng hook gây tò mò, ngắn gọn, có nhịp điệu. Viết như KOL đang nói chuyện với người xem, chia sẻ trải nghiệm cá nhân. KHÔNG viết như quảng cáo hay shop bán hàng.

Chèn 3-4 audio tag [excited], [laughs], [gasps], [curious] vào script tại điểm chuyển cảm xúc. KHÔNG tính vào số từ. Dùng dấu … để tạo khoảng dừng, CHỮ IN HOA để nhấn mạnh.
Ví dụ: '[curious] Mà khoan… các bạn có biết không? [gasps] Sản phẩm này ĐỈNH thật sự! [laughs]'""",
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

    return f"""Bạn là một KOL (Key Opinion Leader) chuyên review sản phẩm trên mạng xã hội tại Việt Nam. Bạn là người có chuyên môn và kiến thức sâu trong lĩnh vực sản phẩm, có kỹ năng chọn lọc và đánh giá sản phẩm chất lượng. Bạn viết review từ góc nhìn chuyên gia đã thực sự mua và trải nghiệm sản phẩm — chia sẻ nhận định dựa trên kiến thức chuyên môn, KHÔNG phải từ góc nhìn shop bán hàng. Giọng văn tự nhiên, chân thực, thể hiện sự am hiểu về sản phẩm.

THÔNG TIN SẢN PHẨM:
- Tên: {book.title}
- Tác giả/Thương hiệu: {book.author}
- Mô tả/Nội dung: {book.description[:3000]}
{f"- Giá: {book.price}" if book.price else ""}
{f"- Link mua: {book.shopee_url}" if book.shopee_url and platform != "tiktok" else ""}
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
  "review": "Bài review chi tiết về sản phẩm ({word_count} từ)",
  "social_post": "Bài đăng {platform} hoàn chỉnh (khoảng {word_count} từ) — KHÔNG chứa hashtag, KHÔNG chứa link",
  "hashtags": ["danh sách hashtag phù hợp — CHỈ đặt ở đây, KHÔNG trong social_post"],
  "hook": "Câu mở đầu gây chú ý (dùng cho video/reel)",
  "key_points": ["3-5 điểm nổi bật của sản phẩm"],
  "cta": "Lời kêu gọi hành động — PHẢI hướng dẫn người xem tìm link mua (VD: 'Link mua ở mô tả nhé!', 'Bấm link ở bio để mua nha!')"
}}

CHỈ trả về JSON, không giải thích thêm."""


_REVIEW_FALLBACK = {
    "review": "", "social_post": "", "hashtags": [],
    "hook": "", "key_points": [], "cta": "",
}


def generate_review(
    book: BookInfo,
    audience_key: str = "phu-huynh-lop-5",
    platform: str = "facebook",
    custom_audience: dict | None = None,
    word_count: int = 150,
) -> dict:
    """Generate a review + social post for a book targeting a specific audience."""
    audience = custom_audience or AUDIENCES.get(audience_key, AUDIENCES["phu-huynh-lop-5"])
    prompt = build_review_prompt(book, audience, platform, word_count)
    try:
        return generate_json(prompt)
    except (json.JSONDecodeError, RuntimeError) as e:
        err = str(e)
        return {**_REVIEW_FALLBACK, "review": err}


def generate_review_all_platforms(
    book: BookInfo,
    audience_key: str = "phu-huynh-lop-5",
    custom_audience: dict | None = None,
    word_count_fb: int = 200,
    word_count_tk: int = 150,
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
        "facebook": generate_review(book, audience_key, "facebook", custom_audience, word_count_fb),
        "tiktok": generate_review(book, audience_key, "tiktok", custom_audience, word_count_tk),
    }
