"""Tests for api_client module."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

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


class TestRetryRequest:
    def test_retries_with_exponential_backoff(self):
        client = APIClient("https://api.example.com")
        attempts = []

        def fail_get(path):
            attempts.append(path)
            raise RuntimeError("temporary failure")

        sleep = Mock()
        with patch.object(client, "get", side_effect=fail_get), patch(
            "examples.api_client.time", SimpleNamespace(sleep=sleep), create=True
        ):
            result = client.retry_request("/unstable", max_retries=3)

        assert attempts == ["/unstable", "/unstable", "/unstable"]
        assert sleep.call_count == 2
        assert [call.args[0] for call in sleep.call_args_list] == [1, 2]
        assert "Failed after 3 retries" in result["error"]
