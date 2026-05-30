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
    """Send a prompt to Gemini and parse the JSON response. Retries on transient errors."""
    import time
    last_err = None
    for attempt in range(3):
        try:
            resp = _get_client().models.generate_content(
                model=model or _model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                ),
            )
            break
        except Exception as e:
            last_err = e
            if "503" in str(e) or "429" in str(e) or "overloaded" in str(e).lower():
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Gemini API error: {e}") from e
    else:
        raise RuntimeError(f"Gemini API error after 3 retries: {last_err}") from last_err

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
    style_id: str | None = None,
) -> str:
    """Build the LLM prompt for a review. Pure function — no I/O."""
    import random

    # Style rotation — pick a random writing angle each time
    styles = [
        "Viết như đang kể chuyện cho bạn thân nghe",
        "Viết như đang trả lời câu hỏi 'có nên mua không?'",
        "Viết như đang so sánh trải nghiệm trước và sau khi dùng",
        "Viết như đang chia sẻ một phát hiện bất ngờ",
        "Viết như đang tâm sự về thói quen mới",
        "Viết như đang review nhanh sau 1 tuần sử dụng",
        "Viết như đang trả lời inbox hỏi về sản phẩm",
        "Viết như đang quay unboxing và react luôn",
    ]
    style = random.choice(styles)

    # Opening variety — ban overused openers and suggest alternatives
    banned_openers = ["Dạo này", "Trời ơi", "Công nhận", "Nói thật", "Phải nói luôn"]
    opening_styles = [
        "Mở đầu bằng câu hỏi tu từ gây tò mò",
        "Mở đầu bằng tình huống cụ thể (ví dụ: đang ở đâu, đang làm gì thì phát hiện ra sản phẩm)",
        "Mở đầu bằng so sánh trước/sau ngắn gọn",
        "Mở đầu bằng lời khuyên trực tiếp cho người đọc",
        "Mở đầu bằng con số hoặc thời gian cụ thể (ví dụ: '3 ngày dùng thử...', '2 tuần rồi...')",
        "Mở đầu bằng mini-story 1 câu (chuyện nhỏ dẫn vào sản phẩm)",
    ]
    opening_hint = random.choice(opening_styles)

    # Rotate banned clichés — ban a random subset each time so they appear occasionally, not every time
    all_cliches = ['chân ái', 'must-have', 'đỉnh của chóp', 'xịn sò', 'không thể bỏ qua', 'cực kỳ ưng', 'quá là', 'siêu phẩm', 'đỉnh nóc']
    banned_subset = random.sample(all_cliches, k=min(5, len(all_cliches)))

    # CTA variety — pick 3 random examples per call
    cta_pool = [
        "Link mua ở mô tả nhé!",
        "Bấm link ở bio để mua nha!",
        "Mình để link ở comment đầu tiên nè!",
        "Lướt xuống mô tả là thấy link liền!",
        "Save lại rồi bấm link mua khi cần nhé!",
        "Ghim video + bấm link mô tả để không quên!",
        "Link ở dưới, mua ngay kẻo hết hàng!",
        "Ai cần thì link mình để ở bio nha!",
        "Mình để link mua bên dưới rồi đó!",
        "Xem mô tả để lấy link nha mọi người!",
    ]
    cta_examples = random.sample(cta_pool, k=3)
    banned = f"KHÔNG dùng các cụm từ sau lần này: {', '.join(repr(w) for w in banned_subset)}. Dùng từ ngữ tự nhiên, đa dạng."
    platform_guide = {
        "facebook": f"""Bài viết ĐÚNG {word_count} từ (KHÔNG được vượt quá), BẮT BUỘC có 3-5 emoji rải đều trong bài (💖😍✨🔥👉...), chia đoạn rõ ràng, kết thúc bằng CTA mua sản phẩm. Viết theo góc nhìn KOL/người dùng thực sự đã trải nghiệm sản phẩm, KHÔNG viết như shop bán hàng. Dùng ngôi thứ nhất (mình/tôi), chia sẻ cảm nhận cá nhân, kể trải nghiệm thực tế. Viết dạng văn nói tự nhiên, có nhịp điệu.

GIỌNG NÓI (KHÔNG tính vào số từ):
Chèn 4-6 audio tag vào bài viết. Kết hợp tag + dấu câu cho hiệu ứng mạnh.
- Cảm xúc: [excited], [surprised], [curious], [happy], [thoughtful], [whispers], [sarcastic], [mischievously]
- Phi ngôn ngữ: [laughs], [sighs], [gasps], [chuckles], [exhales], [snorts]
- Dấu … tạo khoảng dừng: "Và kết quả là…"
- CHỮ IN HOA nhấn mạnh: "THỰC SỰ hay"
- Kết hợp tag + dấu câu: "[curious] Mà khoan… các bạn có BIẾT không? [gasps] Sản phẩm này ĐỈNH! [laughs]"
- KHUYẾN KHÍCH kết hợp tag + dấu câu liên tục để tạo nhịp điệu tự nhiên, biểu cảm mạnh.
""",
        "tiktok": f"""Script TikTok ĐÚNG {word_count} từ (KHÔNG được vượt quá, KHÔNG tính audio tag trong []). Viết dạng văn nói tự nhiên, KHÔNG dùng timestamp như [0-3s]. Mở đầu bằng hook gây tò mò, ngắn gọn, có nhịp điệu. Viết như KOL đang nói chuyện với người xem, chia sẻ trải nghiệm cá nhân. KHÔNG viết như quảng cáo hay shop bán hàng.

GIỌNG NÓI (KHÔNG tính vào số từ):
Chèn 4-6 audio tag vào script. Kết hợp tag + dấu câu cho hiệu ứng mạnh.
- Cảm xúc: [excited], [surprised], [curious], [happy], [thoughtful], [whispers], [sarcastic], [mischievously]
- Phi ngôn ngữ: [laughs], [sighs], [gasps], [chuckles], [exhales], [snorts]
- Dấu … tạo khoảng dừng: "Và kết quả là…"
- CHỮ IN HOA nhấn mạnh: "THỰC SỰ hay"
- Kết hợp tag + dấu câu: "[curious] Mà khoan… các bạn có BIẾT không? [gasps] Sản phẩm này ĐỈNH! [laughs]"
- KHUYẾN KHÍCH kết hợp tag + dấu câu liên tục để tạo nhịp điệu tự nhiên, biểu cảm mạnh.
""",
    }

    ratings_context = ""
    social_proof_guide = ""
    has_strong_proof = False
    if book.rating and book.rating_count >= 10:
        ratings_context += f"\n- Đánh giá: {book.rating}/5 ({book.rating_count} lượt đánh giá)"
        has_strong_proof = True
    elif book.rating:
        ratings_context += f"\n- Đánh giá: {book.rating}/5 ({book.rating_count} lượt đánh giá) — còn ít đánh giá"
    if book.sold_count:
        ratings_context += f"\n- Đã bán: {book.sold_count:,}+"
        if book.sold_count >= 100:
            has_strong_proof = True
    if book.reviews and len(book.reviews) >= 3:
        top_reviews = sorted(book.reviews, key=lambda r: r.get("likes", 0), reverse=True)[:10]
        review_texts = []
        for r in top_reviews:
            stars = "⭐" * r.get("rating", 0)
            review_texts.append(f"  {stars} {r['text'][:200]}")
        ratings_context += "\n- Nhận xét thực từ người mua:\n" + "\n".join(review_texts)
        has_strong_proof = True
    elif book.reviews:
        review_texts = [f"  {r['text'][:200]}" for r in book.reviews]
        ratings_context += "\n- Một vài nhận xét (ít mẫu):\n" + "\n".join(review_texts)

    # Build exact numbers string for the strong-proof instruction
    exact_numbers = []
    if book.rating and book.rating_count:
        exact_numbers.append(f"{book.rating}/5 ({book.rating_count} đánh giá)")
    if book.sold_count:
        exact_numbers.append(f"đã bán {book.sold_count:,}+")
    exact_str = ", ".join(exact_numbers)

    if has_strong_proof:
        social_proof_guide = f"- BẮT BUỘC dùng ĐÚNG con số này trong bài: {exact_str}. CẤM thay đổi, làm tròn, hoặc bịa số khác.\n- Trích dẫn hoặc paraphrase 1-2 ý kiến nổi bật từ nhận xét thực của người mua\n- Nếu có nhận xét tiêu cực hợp lý, đề cập khéo léo hoặc đưa ra góc nhìn cân bằng"
    else:
        social_proof_guide = "- Sản phẩm này còn mới/ít đánh giá. TUYỆT ĐỐI KHÔNG bịa số liệu (ví dụ: 'hàng ngàn khách hàng tin dùng', 'best seller', '99% hài lòng'). KHÔNG đề cập số đánh giá hay lượt bán thấp.\n- Viết theo góc nhìn người phát hiện sớm: 'mình vừa tìm được gem này', 'sản phẩm mới mà chất lượng không đùa'. Tạo cảm giác early discovery, người đọc muốn thử trước khi viral.\n- Tập trung vào: chất liệu, công dụng, trải nghiệm cá nhân dựa trên thông tin sản phẩm"

    json_schema = f"""Trả về JSON với format:
{{
  "review": "Bài review chi tiết về sản phẩm ({word_count} từ)",
  "social_post": "Bài đăng {platform} hoàn chỉnh (khoảng {word_count} từ) — KHÔNG chứa hashtag, KHÔNG chứa link",
  "hashtags": ["danh sách hashtag phù hợp — CHỈ đặt ở đây, KHÔNG trong social_post"],
  "hook": "Câu mở đầu gây chú ý (dùng cho video/reel)",
  "key_points": ["3-5 điểm nổi bật của sản phẩm"],
  "cta": "Lời kêu gọi hành động — PHẢI hướng dẫn người xem tìm link mua (VD: '{cta_examples[0]}', '{cta_examples[1]}', '{cta_examples[2]}'). Viết CTA ngắn gọn, tự nhiên, KHÁC với các ví dụ."
}}

CHỈ trả về JSON, không giải thích thêm."""

    # Try template-based rendering
    from prompt_manager import resolve_style, load_preset, render_template
    resolved_id = resolve_style(style_id)
    preset = load_preset(resolved_id)

    if preset and preset.get("template"):
        variables = {
            "product_name": book.title,
            "author": book.author,
            "description": book.description[:3000],
            "price_line": f"- Giá: {book.price}" if book.price else "",
            "shopee_url_line": f"- Link mua: {book.shopee_url}" if book.shopee_url and platform != "tiktok" else "",
            "social_proof_section": ratings_context,
            "audience_name": audience["name"],
            "audience_tone": audience["tone"],
            "audience_focus": audience["focus"],
            "platform": platform,
            "word_count": str(word_count),
            "platform_guide": platform_guide.get(platform, platform_guide["facebook"]),
            "style_hint": style,
            "opening_hint": opening_hint,
            "banned_openers": ", ".join(f'"{w}"' for w in banned_openers),
            "banned_cliches": banned,
            "social_proof_guide": social_proof_guide,
            "cta_examples": "', '".join(cta_examples),
            "json_schema": json_schema,
        }
        return render_template(preset["template"], variables)

    # Fallback: hardcoded prompt
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
- PHONG CÁCH LẦN NÀY: {style}
- CÁCH MỞ ĐẦU: {opening_hint}. TUYỆT ĐỐI KHÔNG mở đầu bằng: {', '.join(f'"{w}"' for w in banned_openers)}. Câu đầu tiên phải khác biệt, bất ngờ.
- {banned}
- Dựa vào MÔ TẢ SẢN PHẨM để hiểu rõ nội dung/tính năng sản phẩm
{social_proof_guide}

{json_schema}"""


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
    style_id: str | None = None,
) -> dict:
    """Generate a review + social post for a book targeting a specific audience."""
    audience = custom_audience or AUDIENCES.get(audience_key, AUDIENCES["phu-huynh-lop-5"])
    prompt = build_review_prompt(book, audience, platform, word_count, style_id=style_id)
    try:
        result = generate_json(prompt)
        # Strip audio tags from fields displayed as text (not spoken)
        import re
        for field in ("hook", "cta"):
            if result.get(field):
                result[field] = re.sub(r'\[[a-zA-Z_ ]+\]', '', result[field]).strip()
        return result
    except (json.JSONDecodeError, RuntimeError) as e:
        err = str(e)
        return {**_REVIEW_FALLBACK, "review": err}


def suggest_personas(title: str) -> list[dict]:
    """Suggest 3 customer personas for a product title via Gemini."""
    prompt = f"""Dựa vào sản phẩm "{title}", gợi ý 3 nhóm khách hàng mục tiêu phù hợp nhất.

Trả về JSON array, mỗi phần tử có:
- "name": tên nhóm khách hàng (ngắn gọn, tiếng Việt)
- "tone": giọng văn phù hợp
- "focus": trọng tâm nội dung khi viết review

CHỈ trả về JSON array, không giải thích."""
    parsed = generate_json(prompt, max_tokens=500, model="gemini-2.5-flash-lite")
    return parsed if isinstance(parsed, list) else parsed.get("personas", [])


