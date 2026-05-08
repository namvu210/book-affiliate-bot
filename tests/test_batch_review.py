"""Test batch review generation retry behavior."""
import sys
sys.path.insert(0, ".")

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_batch_review_success():
    """Successful review returns facebook data with all required fields."""
    mock_resp = MagicMock()
    mock_resp.text = '{"social_post":"Great product!","review":"Nice","hashtags":["test"],"hook":"Hook!","key_points":["point1"],"cta":"Buy now"}'

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = mock_resp
        resp = client.post("/batch-review", data={
            "url": "https://shopee.vn/Test-Product-i.123.456",
            "audience": "custom",
            "custom_audience": '{"name":"Test","tone":"friendly","focus":"quality"}',
            "platforms": "facebook",
        })
        data = resp.json()
        assert resp.status_code == 200
        assert "facebook" in data
        assert data["facebook"]["social_post"] == "Great product!"
        assert data["facebook"]["hook"] == "Hook!"
        assert data["facebook"]["cta"] == "Buy now"


def test_batch_review_shared_across_platforms():
    """One review is shared to all requested platforms."""
    mock_resp = MagicMock()
    mock_resp.text = '{"social_post":"Shared review","review":"r","hashtags":[],"hook":"H","key_points":[],"cta":"C"}'

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = mock_resp
        resp = client.post("/batch-review", data={
            "url": "https://shopee.vn/Test-i.123.456",
            "audience": "custom",
            "custom_audience": '{"name":"Test","tone":"t","focus":"f"}',
            "platforms": "facebook,tiktok",
        })
        data = resp.json()
        assert data["facebook"]["social_post"] == "Shared review"
        assert data["tiktok"]["social_post"] == "Shared review"


def test_batch_review_retries_on_503():
    """Review generation retries on 503 and succeeds."""
    call_count = {"n": 0}

    def mock_generate(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise Exception("503 Service Unavailable")
        mock_resp = MagicMock()
        mock_resp.text = '{"social_post":"Recovered","review":"r","hashtags":[],"hook":"H","key_points":[],"cta":"C"}'
        return mock_resp

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content = mock_generate
        resp = client.post("/batch-review", data={
            "url": "https://shopee.vn/Test-i.123.456",
            "audience": "custom",
            "custom_audience": '{"name":"Test","tone":"t","focus":"f"}',
            "platforms": "facebook",
        })
        data = resp.json()
        assert resp.status_code == 200
        assert data["facebook"]["social_post"] == "Recovered"
        assert call_count["n"] == 3


def test_batch_review_fails_after_retries():
    """Review generation returns error data after exhausting retries."""
    def mock_generate(*args, **kwargs):
        raise Exception("503 Service Unavailable")

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content = mock_generate
        resp = client.post("/batch-review", data={
            "url": "https://shopee.vn/Test-i.123.456",
            "audience": "custom",
            "custom_audience": '{"name":"Test","tone":"t","focus":"f"}',
            "platforms": "facebook",
        })
        data = resp.json()
        assert resp.status_code == 200
        fb = data["facebook"]
        # On failure, review contains error OR social_post is empty
        has_error = "Error" in fb.get("review", "") or not fb.get("social_post")
        assert has_error, f"Expected error indication, got: {fb}"


def test_batch_review_strips_audio_tags_from_hook_cta():
    """Hook and CTA should have audio tags stripped."""
    mock_resp = MagicMock()
    mock_resp.text = '{"social_post":"[excited] Text","review":"r","hashtags":[],"hook":"[whispers] Clean hook","key_points":[],"cta":"[laughs] Buy now!"}'

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = mock_resp
        resp = client.post("/batch-review", data={
            "url": "https://shopee.vn/Test-i.123.456",
            "audience": "custom",
            "custom_audience": '{"name":"Test","tone":"t","focus":"f"}',
            "platforms": "facebook",
        })
        data = resp.json()
        assert "[whispers]" not in data["facebook"]["hook"]
        assert "Clean hook" in data["facebook"]["hook"]
        assert "[laughs]" not in data["facebook"]["cta"]
        assert "Buy now!" in data["facebook"]["cta"]
        # social_post keeps audio tags (for TTS)
        assert "[excited]" in data["facebook"]["social_post"]


if __name__ == "__main__":
    test_batch_review_success()
    print("✅ test_batch_review_success")
    test_batch_review_shared_across_platforms()
    print("✅ test_batch_review_shared_across_platforms")
    test_batch_review_retries_on_503()
    print("✅ test_batch_review_retries_on_503")
    test_batch_review_fails_after_retries()
    print("✅ test_batch_review_fails_after_retries")
    test_batch_review_strips_audio_tags_from_hook_cta()
    print("✅ test_batch_review_strips_audio_tags_from_hook_cta")
    print("\n✅ All 5 batch review tests passed")
