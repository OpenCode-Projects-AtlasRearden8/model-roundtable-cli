"""Tests for the endpoint client: request shape, parsing, errors, parallel ask.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import json

from model_roundtable.endpoint import (
    Endpoint,
    ask_all,
    ask_endpoint,
    chat_prompt,
    estimate_tokens,
    normalize_base_url,
)
from tests.conftest import chat_response


class TestUnit:
    def test_normalize_base_url(self):
        assert normalize_base_url("http://x/v1/") == "http://x/v1"
        assert normalize_base_url("http://x/v1/chat/completions") == "http://x/v1"
        assert normalize_base_url("http://x") == "http://x"

    def test_estimate_tokens(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("x" * 40) == 10
        assert estimate_tokens("hi") == 1

    def test_chat_prompt_has_model_and_messages(self):
        endpoint = Endpoint("a", "http://x/v1", "m1")
        body = json.loads(chat_prompt(endpoint, "Hello", "sys"))
        assert body["model"] == "m1"
        assert body["messages"][0] == {"role": "system", "content": "sys"}
        assert body["messages"][1] == {"role": "user", "content": "Hello"}

    def test_key_never_in_request_body(self):
        endpoint = Endpoint("a", "http://x/v1", "m1", api_key="sk-secret")
        assert "sk-secret" not in chat_prompt(endpoint, "Hello")


class TestHeadersAndKeys:
    def test_inline_key_header(self):
        endpoint = Endpoint("a", "http://x/v1", "m", api_key="sk-inline")
        assert endpoint.headers()["Authorization"] == "Bearer sk-inline"

    def test_env_key_header(self, monkeypatch):
        monkeypatch.setenv("ROUNDTRIPLE_TEST_KEY", "sk-env")
        endpoint = Endpoint("a", "http://x/v1", "m", api_key_env="ROUNDTRIPLE_TEST_KEY")
        assert endpoint.headers()["Authorization"] == "Bearer sk-env"

    def test_missing_env_key_falls_back_to_inline(self, monkeypatch):
        monkeypatch.delenv("ROUNDTRIPLE_GONE", raising=False)
        endpoint = Endpoint(
            "a", "http://x/v1", "m", api_key="sk-file", api_key_env="ROUNDTRIPLE_GONE"
        )
        assert endpoint.headers()["Authorization"] == "Bearer sk-file"

    def test_no_key_no_header(self):
        endpoint = Endpoint("a", "http://x/v1", "m")
        assert "Authorization" not in endpoint.headers()


class TestAskEndpoint:
    def test_success(self, fake_server):
        server = fake_server()
        endpoint = Endpoint("fake", server.url, "test-model")
        result = ask_endpoint(endpoint, "Hi there", timeout=5)
        assert result.ok
        assert result.answer == "Hi!"
        assert result.prompt_tokens == 7
        assert result.completion_tokens == 12
        assert result.tokens_estimated is False
        assert result.latency > 0

        request = server.requests[0]
        assert request["path"] == "/v1/chat/completions"
        assert request["body"]["model"] == "test-model"
        assert request["auth"] is None

    def test_estimated_tokens_when_no_usage(self, fake_server):
        server = fake_server(
            {
                "/v1/chat/completions": (
                    200,
                    chat_response("Hello world!", include_usage=False),
                )
            }
        )
        result = ask_endpoint(Endpoint("fake", server.url, "m"), "Hi", timeout=5)
        assert result.ok
        assert result.prompt_tokens is None
        assert result.completion_tokens > 0
        assert result.tokens_estimated is True

    def test_api_key_sent_only_to_this_endpoint(self, fake_server):
        server = fake_server()
        endpoint = Endpoint("fake", server.url, "m", api_key="sk-roundtable-test")
        result = ask_endpoint(endpoint, "Hi", timeout=5)
        assert result.ok
        assert server.requests[0]["auth"] == "Bearer sk-roundtable-test"

    def test_connection_refused(self):
        endpoint = Endpoint("dead", "http://localhost:1/v1", "m")
        result = ask_endpoint(endpoint, "Hi", timeout=5)
        assert not result.ok
        assert "could not connect" in result.error

    def test_http_401(self, fake_server):
        server = fake_server(
            {"/v1/chat/completions": (401, {"error": {"message": "bad key"}})}
        )
        result = ask_endpoint(Endpoint("fake", server.url, "m"), "Hi", timeout=5)
        assert not result.ok
        assert "not authorized" in result.error

    def test_http_500(self, fake_server):
        server = fake_server({"/v1/chat/completions": (500, {"oops": True})})
        result = ask_endpoint(Endpoint("fake", server.url, "m"), "Hi", timeout=5)
        assert not result.ok
        assert "HTTP 500" in result.error

    def test_non_json_body(self, fake_server):
        server = fake_server({"/v1/chat/completions": (200, "<html>not json</html>")})
        result = ask_endpoint(Endpoint("fake", server.url, "m"), "Hi", timeout=5)
        assert not result.ok
        assert "bad response" in result.error

    def test_timeout(self):
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Slow(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                time.sleep(2)
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/v1"
            result = ask_endpoint(Endpoint("slow", url, "m"), "Hi", timeout=0.2)
            assert not result.ok
            assert result.error == "timed out"
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_missing_answer_text(self, fake_server):
        server = fake_server({"/v1/chat/completions": (200, {"choices": []})})
        result = ask_endpoint(Endpoint("fake", server.url, "m"), "Hi", timeout=5)
        assert not result.ok
        assert "no answer text" in result.error


class TestAskAll:
    def test_three_endpoints_in_parallel_order_preserved(self, fake_server):
        server = fake_server(
            {
                "/alpha/chat/completions": (200, chat_response("alpha says hi")),
                "/beta/chat/completions": (200, chat_response("beta says hi")),
            }
        )
        endpoints = [
            Endpoint("a", f"{server.url}/alpha", "m1"),
            Endpoint("b", f"{server.url}/beta", "m2"),
            Endpoint("c", "http://localhost:1/v1", "m3"),  # unreachable
        ]
        results = ask_all(endpoints, "ping", timeout=5)
        assert [r.name for r in results] == ["a", "b", "c"]
        assert results[0].answer == "alpha says hi"
        assert results[1].answer == "beta says hi"
        assert not results[2].ok
