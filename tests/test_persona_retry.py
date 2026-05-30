"""Test persona suggestion retry behavior on LLM failures."""
import sys
sys.path.insert(0, ".")

from unittest.mock import patch, MagicMock
from reviewer import generate_json


def test_generate_json_retries_on_503():
    """generate_json should retry up to 3 times on 503 errors."""
    call_count = {"n": 0}

    def mock_generate(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise Exception("503 Service Unavailable")
        # Succeed on 3rd attempt
        mock_resp = MagicMock()
        mock_resp.text = '[{"name": "Test Persona", "tone": "friendly", "focus": "quality"}]'
        return mock_resp

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content = mock_generate
        result = generate_json("test prompt", max_tokens=500)
        assert isinstance(result, list)
        assert result[0]["name"] == "Test Persona"
        assert call_count["n"] == 3, f"Expected 3 calls, got {call_count['n']}"


def test_generate_json_fails_after_3_retries():
    """generate_json should raise after 3 failed retries on 503."""
    def mock_generate(*args, **kwargs):
        raise Exception("503 Service Unavailable")

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content = mock_generate
        try:
            generate_json("test prompt", max_tokens=500)
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "3 retries" in str(e)


def test_generate_json_no_retry_on_400():
    """generate_json should NOT retry on non-transient errors (400, 404)."""
    call_count = {"n": 0}

    def mock_generate(*args, **kwargs):
        call_count["n"] += 1
        raise Exception("400 Bad Request: invalid model")

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content = mock_generate
        try:
            generate_json("test prompt", max_tokens=500)
            assert False, "Should have raised"
        except RuntimeError as e:
            assert call_count["n"] == 1, f"Should not retry on 400, got {call_count['n']} calls"


def test_suggest_personas_returns_error_on_failure():
    """The /suggest-personas endpoint should return error field when LLM fails."""
    with patch("reviewer.generate_json", side_effect=RuntimeError("503 after 3 retries")):
        from fastapi.testclient import TestClient
        from app import app
        client = TestClient(app)
        resp = client.post("/suggest-personas", data={"title": "Test Product"})
        data = resp.json()
        assert resp.status_code == 200
        assert data["personas"] == []
        assert data["error"] != "", "Should return error message when LLM fails"


def test_suggest_personas_uses_flash_lite():
    """Persona suggestion should always use gemini-2.5-flash-lite regardless of global model."""
    calls = []

    def mock_generate(*args, **kwargs):
        model = kwargs.get("model") or (args[0] if args else "")
        calls.append(model)
        mock_resp = MagicMock()
        mock_resp.text = '[{"name": "Persona", "tone": "t", "focus": "f"}]'
        return mock_resp

    with patch("reviewer._get_client") as mock_client:
        mock_client.return_value.models.generate_content = mock_generate
        from fastapi.testclient import TestClient
        from app import app
        client = TestClient(app)
        resp = client.post("/suggest-personas", data={"title": "Test"})
        assert resp.status_code == 200
        assert "gemini-2.5-flash-lite" in calls[0], f"Expected flash-lite, got {calls[0]}"


if __name__ == "__main__":
    test_generate_json_retries_on_503()
    print("✅ test_generate_json_retries_on_503")
    test_generate_json_fails_after_3_retries()
    print("✅ test_generate_json_fails_after_3_retries")
    test_generate_json_no_retry_on_400()
    print("✅ test_generate_json_no_retry_on_400")
    test_suggest_personas_returns_error_on_failure()
    print("✅ test_suggest_personas_returns_error_on_failure")
    test_suggest_personas_uses_flash_lite()
    print("✅ test_suggest_personas_uses_flash_lite")
    print("\n✅ All 5 persona retry tests passed")
