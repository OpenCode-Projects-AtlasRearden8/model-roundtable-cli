"""Tests for display rendering (the other part the project goal calls out).

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import json

from model_roundtable.display import (
    column_widths,
    format_latency,
    format_tokens,
    header_line,
    render,
    render_json,
    render_side_by_side,
    render_stack,
    status_line,
    wrap_text,
)
from tests.conftest import make_result


class TestFormatters:
    def test_latency_fast_milliseconds(self):
        assert format_latency(make_result(latency=0.05)) == "50 ms"

    def test_latency_seconds(self):
        assert format_latency(make_result(latency=1.234)) == "1.23 s"

    def test_latency_failed(self):
        assert format_latency(make_result(ok=False)) == "failed"

    def test_tokens_reported(self):
        assert format_tokens(make_result()) == "4 in / 10 out"

    def test_tokens_estimated_suffix(self):
        result = make_result(prompt_tokens=None, tokens_estimated=True)
        assert format_tokens(result) == "? in / 10 out (est.)"

    def test_tokens_failed(self):
        assert format_tokens(make_result(ok=False)) == "-"

    def test_header_line(self):
        assert header_line(make_result(name="ollama", model="llama3.2:3b")) == (
            "ollama (llama3.2:3b)"
        )

    def test_status_line(self):
        assert status_line(make_result(latency=2.0)) == "2.00 s · 4 in / 10 out"


class TestWrap:
    def test_short_text(self):
        assert wrap_text("hello", 40) == ["hello"]

    def test_wraps_to_width(self):
        lines = wrap_text("one two three four five", 8)
        assert all(len(line) <= 8 for line in lines)
        assert lines == ["one two", "three", "four", "five"]

    def test_preserves_blank_lines(self):
        assert wrap_text("a\n\nb", 10) == ["a", "", "b"]

    def test_breaks_long_words(self):
        lines = wrap_text("x" * 30, 10)
        assert all(len(line) <= 10 for line in lines)
        assert "".join(lines) == "x" * 30


class TestColumnWidths:
    def test_two_columns(self):
        widths = column_widths(2, 100)
        assert len(widths) == 2
        assert sum(widths) == 100 - 3  # " | " separator

    def test_three_columns(self):
        widths = column_widths(3, 120)
        assert len(widths) == 3
        assert sum(widths) == 120 - 6

    def test_too_narrow_returns_empty(self):
        assert column_widths(3, 40) == ()

    def test_zero(self):
        assert column_widths(0, 100) == ()


class TestRender:
    def test_side_by_side_joins_columns(self):
        results = [
            make_result(name="ollama", model="m1", answer="Answer one here."),
            make_result(name="lmstudio", model="m2", answer="Answer two here."),
        ]
        out = render_side_by_side(results, 80)
        assert "ollama (m1)" in out
        assert "lmstudio (m2)" in out
        assert " | " in out
        for line in out.splitlines():
            assert len(line.rstrip()) <= 80 or line.startswith(" ")

    def test_every_answer_visible(self):
        results = [
            make_result(name="a", model="m", answer="LEFT-SIDE-ANSWER"),
            make_result(name="b", model="m", answer="RIGHT-SIDE-ANSWER"),
        ]
        out = render_side_by_side(results, 60)
        assert "LEFT-SIDE-ANSWER" in out
        assert "RIGHT-SIDE-ANSWER" in out

    def test_three_columns_fit(self):
        results = [make_result(name=f"ep{i}", model="m") for i in range(3)]
        out = render_side_by_side(results, 120)
        header = out.splitlines()[0]
        assert header.count(" | ") == 2

    def test_narrow_terminal_stacks(self):
        results = [
            make_result(name="a", model="m", answer="STACK-A"),
            make_result(name="b", model="m", answer="STACK-B"),
        ]
        out = render(results, 30)
        assert out.index("STACK-A") < out.index("STACK-B")
        assert " | " not in out
        assert "STACK-A" in render_stack(results)

    def test_failed_endpoint_shows_error(self):
        results = [
            make_result(ok=True, answer="good"),
            make_result(ok=False, error="could not connect (..."),
        ]
        out = render_side_by_side(results, 80)
        assert "Error: could not connect (..." in out

    def test_long_answers_wrap_within_column(self):
        results = [
            make_result(answer="word " * 100),
            make_result(answer="word " * 100),
        ]
        out = render_side_by_side(results, 80)
        for line in out.splitlines():
            assert len(line) <= 80

    def test_empty(self):
        assert render([], 80) == "(no endpoints configured)"

    def test_json_roundtrip(self):
        results = [
            make_result(name="a", answer="ans", latency=0.25),
            make_result(name="b", ok=False, error="timed out"),
        ]
        data = json.loads(render_json(results))
        assert data[0]["ok"] is True
        assert data[0]["answer"] == "ans"
        assert data[0]["latency_s"] == 0.25
        assert data[0]["prompt_tokens"] == 4
        assert data[1]["ok"] is False
        assert data[1]["error"] == "timed out"
        assert data[1]["answer"] is None
