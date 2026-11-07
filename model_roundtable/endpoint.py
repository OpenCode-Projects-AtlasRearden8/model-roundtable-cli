"""Endpoint model and OpenAI-compatible chat-completions client.

One endpoint = one configured row in your config file. The only network call
this module makes is a POST to "<base_url>/chat/completions" of the URL you
configured, carrying your chosen key (if any) for that endpoint alone.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass
class Endpoint:
    name: str
    base_url: str
    model: str
    api_key: str | None = None
    api_key_env: str | None = None

    def resolve_api_key(self) -> str | None:
        """Prefer an env-var key when both are set; never cache it."""
        if self.api_key_env:
            value = os.environ.get(self.api_key_env)
            if value:
                return value
        return self.api_key

    def headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "model-roundtable",
        }
        key = self.resolve_api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers


@dataclass
class Result:
    """Outcome of one endpoint round in the roundtable."""

    name: str
    model: str
    ok: bool
    latency: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_estimated: bool = False
    answer: str | None = None
    error: str | None = None
    timed_out: bool = False


def normalize_base_url(base_url: str) -> str:
    """Trim trailing slashes and stray '/chat/completions' paths."""
    url = base_url.strip().rstrip("/")
    url = re.sub(r"/chat/completions$", "", url)
    return url


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters of reply text per token)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def chat_prompt(endpoint: Endpoint, prompt: str, system: str | None = None) -> str:
    """Serialize the request body (exposed for tests)."""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return json.dumps({"model": endpoint.model, "messages": messages})


def _extract_answer(payload: object) -> str:
    """Pull the assistant reply out of common response shapes."""
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(
                    message.get("content"), str
                ):
                    return message["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]
    raise ValueError("response had no answer text (unexpected shape)")


def _parse_usage(payload: object, answer: str) -> tuple[int | None, int | None, bool]:
    """Prompt/completion token counts, preferring the server's usage report."""
    if isinstance(payload, dict):
        usage = payload.get("usage")
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
                return prompt_tokens, completion_tokens, False
    return None, estimate_tokens(answer), True


def ask_endpoint(
    endpoint: Endpoint,
    prompt: str,
    timeout: float = 120.0,
    system: str | None = None,
) -> Result:
    """Send the prompt to one endpoint and return a Result (never raises)."""
    start = time.monotonic()
    url = normalize_base_url(endpoint.base_url) + "/chat/completions"
    body = chat_prompt(endpoint, prompt, system)
    try:
        request = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers=endpoint.headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
        payload = json.loads(data.decode("utf-8"))
        answer = _extract_answer(payload)
        prompt_tokens, completion_tokens, estimated = _parse_usage(payload, answer)
        return Result(
            name=endpoint.name,
            model=endpoint.model,
            ok=True,
            latency=time.monotonic() - start,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tokens_estimated=estimated,
            answer=answer,
        )
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001 - best effort detail read
            detail = ""
        kind = {401: "not authorized (bad or missing key)", 403: "not authorized"}.get(
            exc.code, f"HTTP {exc.code}"
        )
        snippet = f": {detail[:200]}" if detail else ""
        return Result(
            endpoint.name,
            endpoint.model,
            False,
            time.monotonic() - start,
            error=f"{kind}{snippet}",
            timed_out=False,
        )
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            return Result(
                endpoint.name,
                endpoint.model,
                False,
                time.monotonic() - start,
                error="timed out",
                timed_out=True,
            )
        return Result(
            endpoint.name,
            endpoint.model,
            False,
            time.monotonic() - start,
            error=f"could not connect ({reason})",
            timed_out=False,
        )
    except TimeoutError:
        return Result(
            endpoint.name,
            endpoint.model,
            False,
            time.monotonic() - start,
            error="timed out",
            timed_out=True,
        )
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        return Result(
            endpoint.name,
            endpoint.model,
            False,
            time.monotonic() - start,
            error=f"bad response ({exc})",
            timed_out=False,
        )


def ask_all(
    endpoints: list[Endpoint],
    prompt: str,
    timeout: float = 120.0,
    system: str | None = None,
    max_workers: int = 4,
) -> list[Result]:
    """Ask every endpoint at once (parallel), preserving config order."""
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(ask_endpoint, endpoint, prompt, timeout, system)
            for endpoint in endpoints
        ]
        return [future.result() for future in futures]
