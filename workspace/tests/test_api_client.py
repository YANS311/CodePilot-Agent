"""Tests for api_client module."""

from examples.api_client import APIClient


class TestBuildUrl:
    def test_simple(self):
        client = APIClient("https://api.example.com")
        url = client.build_url("/users")
        assert url == "https://api.example.com/users"

    def test_with_params(self):
        client = APIClient("https://api.example.com")
        url = client.build_url("/search", {"q": "hello world", "page": "1"})
        assert url == "https://api.example.com/search?q=hello+world&page=1"


class TestParseResponse:
    def test_valid_json(self):
        client = APIClient("https://api.example.com")
        result = client.parse_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json(self):
        client = APIClient("https://api.example.com")
        result = client.parse_response("not json")
        assert result["error"] == "Invalid JSON"
        assert result["status"] == 400


class TestGet:
    def test_error_status(self):
        client = APIClient("https://httpbin.org")
        result = client.get("/status/404")
        assert "error" in result
        assert result["status"] == 404
