"""Shared test helpers and fixtures for model-roundtable tests.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from model_roundtable.endpoint import Result


def make_result(name="a", model="m", ok=True, **kwargs):
    """Convenience Result factory for display tests."""
    defaults = {
        "name": name,
        "model": model,
        "ok": ok,
        "latency": 0.5,
        "prompt_tokens": 4,
        "completion_tokens": 10,
        "tokens_estimated": False,
        "answer": "Hello there." if ok else None,
        "error": None if ok else "not authorized (bad or missing key)",
    }
    defaults.update(kwargs)
    return Result(**defaults)


class FakeLLMServer:
    """A tiny OpenAI-compatible /chat/completions double for smoke tests."""

    def __init__(self, responses):
        self.responses = responses  # path -> (status, payload-dict or raw-str)
        self.requests: list[dict] = []
        lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                with lock:
                    self.server.requests.append(
                        {
                            "path": self.path,
                            "auth": self.headers.get("Authorization"),
                            "body": json.loads(body) if body else {},
                        }
                    )
                status, response = self.server.lookup(self.path)
                text = (
                    json.dumps(response).encode()
                    if isinstance(response, dict)
                    else response.encode()
                )
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(text)))
                self.end_headers()
                self.wfile.write(text)

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def log_message(self, *args):  # silence request logging
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.requests = self.requests
        self.httpd.responses = self.responses
        self.httpd.lookup = self._lookup
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def _lookup(self, path):
        """Match a registered route by exact path or path suffix.

        Routes are stored under keys like "/v1/chat/completions"; incoming
        paths may carry additional prefix segments (multi-endpoint servers).
        """
        for route, response in self.responses.items():
            if path == route or path.endswith(route):
                return response
        return (404, {"error": {"message": "not found"}})

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def chat_response(text, prompt_tokens=7, completion_tokens=12, include_usage=True):
    payload = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
    }
    if include_usage:
        payload["usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
    return payload


@pytest.fixture()
def fake_server():
    """Server answering any /v1/chat/completions path; tests set responses."""
    started = []

    def factory(responses=None):
        server = FakeLLMServer(
            responses or {"/v1/chat/completions": (200, chat_response("Hi!"))}
        )
        started.append(server)
        return server

    yield factory
    for server in started:
        server.close()
