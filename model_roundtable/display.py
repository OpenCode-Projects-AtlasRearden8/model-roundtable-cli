"""Terminal rendering: header, side-by-side answer panels, token/latency lines.

Keep this module pure (no I/O) so it stays easy to test.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import textwrap

from .endpoint import Result

SEP = " | "


def format_latency(result: Result) -> str:
    if not result.ok:
        return "failed"
    seconds = result.latency
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    return f"{seconds:.2f} s"


def format_tokens(result: Result) -> str:
    if not result.ok:
        return "-"
    prompt_part = str(result.prompt_tokens) if result.prompt_tokens is not None else "?"
    completion_part = (
        str(result.completion_tokens) if result.completion_tokens is not None else "?"
    )
    suffix = " (est.)" if result.tokens_estimated else ""
    return f"{prompt_part} in / {completion_part} out{suffix}"


def header_line(result: Result) -> str:
    return f"{result.name} ({result.model})"


def status_line(result: Result) -> str:
    return f"{format_latency(result)} · {format_tokens(result)}"


def wrap_text(text: str, width: int) -> list[str]:
    """Wrap answer text to width; keeps long words intact."""
    lines: list[str] = []
    for chunk in text.split("\n"):
        if chunk.strip() == "":
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(
                chunk,
                width=width,
                replace_whitespace=True,
                break_long_words=True,
                break_on_hyphens=False,
            )
        )
    return lines


def column_widths(count: int, width: int) -> tuple[int, ...]:
    """Split terminal width among columns; returns empty tuple if too narrow."""
    if count <= 0 or width <= 0:
        return ()
    sep_total = SEP * (count - 1)
    available = width - len(sep_total)
    if available < 20 * count:
        return ()
    base = available // count
    widths = [base] * count
    extra = available - base * count
    widths[0] += extra
    return tuple(widths)


def column_for(result: Result, width: int) -> list[str]:
    """Build the wrapped lines of one column (header, status, rule, body)."""
    if not result.ok:
        body = wrap_text(f"Error: {result.error}", width)
    else:
        body = wrap_text(result.answer or "", width)
    return [
        header_line(result),
        status_line(result),
        "-" * width,
    ] + body


def render_stack(results: list[Result]) -> str:
    """Narrow-terminal fallback: print results one after another."""
    blocks = []
    for result in results:
        blocks.append("\n".join(column_for(result, 78)))
    return "\n\n".join(blocks)


def render_side_by_side(results: list[Result], width: int) -> str:
    """Two or three panels joined with a vertical divider."""
    widths = column_widths(len(results), width)
    columns = [
        column_for(result, col_width) for result, col_width in zip(results, widths)
    ]
    height = max(len(col) for col in columns)
    rows: list[str] = []
    for row_index in range(height):
        parts = []
        for col_index, col in enumerate(columns):
            line = col[row_index] if row_index < len(col) else ""
            parts.append(line.ljust(widths[col_index])[: widths[col_index]])
        rows.append(SEP.join(parts).rstrip())
    return "\n".join(rows)


def render(results: list[Result], width: int) -> str:
    """Choose side-by-side or stacked layout, return the full answer block."""
    if not results:
        return "(no endpoints configured)"
    if len(column_widths(len(results), width)) == len(results):
        return render_side_by_side(results, width)
    return render_stack(results)


def render_json(results: list[Result]) -> str:
    """Machine-readable output, one object per endpoint."""
    import json

    payload = []
    for result in results:
        entry: dict = {
            "name": result.name,
            "model": result.model,
            "ok": result.ok,
            "latency_s": round(result.latency, 3) if result.ok else None,
            "tokens_estimated": result.tokens_estimated if result.ok else None,
            "prompt_tokens": result.prompt_tokens if result.ok else None,
            "completion_tokens": result.completion_tokens if result.ok else None,
        }
        if result.ok:
            entry["answer"] = result.answer
        else:
            entry["answer"] = None
            entry["error"] = result.error
        payload.append(entry)
    return json.dumps(payload, indent=2)
