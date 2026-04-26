import os

# AWS Bedrock config (Claude)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

# Upload
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"

# Target audience templates
AUDIENCES = {
    "phu-huynh-lop-5": {
        "name": "Phụ huynh có con lớp 5",
        "tone": "thân thiện, dễ hiểu, như một người bạn đồng hành cùng con",
        "focus": "giá trị giáo dục, phù hợp lứa tuổi, giúp con học tốt hơn",
    },
    "phu-huynh-mam-non": {
        "name": "Phụ huynh có con mầm non",
        "tone": "nhẹ nhàng, ấm áp, khuyến khích đọc sách cùng con",
        "focus": "hình ảnh đẹp, kích thích trí tưởng tượng, phát triển ngôn ngữ",
    },
    "hoc-sinh-thpt": {
        "name": "Học sinh THPT",
        "tone": "năng động, truyền cảm hứng, gần gũi gen Z",
        "focus": "kỹ năng sống, định hướng nghề nghiệp, phát triển bản thân",
    },
}
