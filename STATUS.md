# STATUS

**Project:** model-roundtable - ask one prompt once, get two or three OpenAI-compatible endpoints to answer it at the same time, side by side, with latency and token counts.
**Owner:** Asdale Dynamics, LLC (copyright (c) 2026 Asdale Dynamics, LLC)
**Date:** 2026-11-07
**Status:** Working, tested, committed. Nothing was published or pushed - local repo only.

## What was built

A dependency-free Python package (`model_roundtable`, requires Python 3.11+, stdlib only) that:

1. **Reads one local TOML config file** (`config.py`): `~/.model-roundtable.toml` by default,
   or `--config PATH`, or the `MODEL_ROUNDTABLE_CONFIG` environment variable. It supports a
   `[[endpoints]]` table array (each row: `name`, `base_url`, `model`, optional `api_key` or
   `api_key_env`), a one-endpoint shorthand (`base_url` + `model` at top level), plus optional
   `timeout` and `system` (shared system message) settings. Duplicate names, missing
   `base_url`/`model`, and malformed TOML produce friendly errors, not tracebacks.
   `--config-example` prints a starter config.
2. **Races the endpoints in parallel** (`endpoint.py`): one `POST <base_url>/chat/completions`
   per configured endpoint, all launched together on a thread pool, config order preserved in
   the output. Measures wall-clock latency per endpoint. Token counts come from the server's
   `usage` report when available; otherwise they are estimated (~4 characters/token) and
   marked `(est.)`. Parse errors, HTTP 401/403/404/5xx, connection refusals, and timeouts each
   become a readable error inside that endpoint's panel - one dead endpoint never kills the
   table. Each endpoint's key (if any) is sent only to that endpoint's own base_url.
3. **Prints a side-by-side roundtable** (`display.py`, `cli.py`): a column per endpoint with
   name (model), latency, token counts, a rule, and the wrapped answer body. Two or three
   endpoints fit side by side; terminals too narrow fall back to stacked output. Flags:
   `--prompt/-p`, positional prompt or stdin, `--model` (override all), `--config/-c`,
   `--timeout`, `--width`, `--json` (pure-JSON stdout: header notes shift to stderr),
   `--config-example`, `--version`. Missing config falls back to a single default Ollama
   endpoint (with a note and a tip); more than three endpoints is refused with guidance.
   Exit codes: 0 if any endpoint answered, 1 if none did or the config/args are wrong.

Distinguishing purpose (vs. sibling tools): `ai-model-picker` picks which model to *install*
offline; `llm-diff-explainer` compares *two existing drafts*; this one *runs and races your
actual model candidates on real prompts* so you can choose the right default per task.

## How to run it

```bash
# Zero install, from the project folder:
python -m model_roundtable --config-example > ~/.model-roundtable.toml  # then edit it
python -m model_roundtable "Explain quantization in plain English"

# Or install the console entry point:
pip install -e .
model-roundtable "your prompt" --config my-endpoints.toml --width 120
echo "piped prompt" | model-roundtable --model qwen2.5:14b --json
```

## Verification results

- **Tests:** 73/73 passing (`python3 -m pytest`, and again via `pytest` on a fresh
  `pip install .[dev]` in a clean venv - covering the import-from-package edge).
- **Lint/format:** `ruff check` clean, `ruff format --check` clean.
- **Packaging:** clean-venv `pip install .[dev]` works; `model-roundtable --version/--help`
  and the `--config-example` output all correct; `python -m model_roundtable` works.
- **Live smoke tests** (three fake OpenAI-compatible HTTP servers on localhost, varied
  delays and token `usage`):
  - Three-way side-by-side table rendered at 110 columns with correct latency
    (110-310 ms) and *reported* token counts per endpoint; exit 0.
  - `--json` output is pure JSON (headers go to stderr), parses, `latency_s`,
    `prompt_tokens`, `completion_tokens`, `ok` all correct.
  - One dead endpoint among live ones: its panel shows the error, exit still 0
    (partial-success policy); all-dead runs exit 1.
- Confirmed no secrets or personal data are read or stored in the repo; API keys are only
  ever read from env vars or the user's own config file at runtime and sent only to that
  endpoint's base_url.

## Known gaps

- Token estimate fallback is a crude ~4-chars/token heuristic; tokenizers vary by model.
- No streaming: answers appear only when each endpoint finishes; a very chatty endpoint
  delays the whole table (mitigation: `--timeout` per endpoint).
- Parallel requests assume every endpoint is independent; the same Ollama server mirrored
  under two names would run serially inside the server, skewing the latency comparison.
- Only `chat/completions` (OpenAI dialect) is spoken; `/v1/completions`-only servers and
  Ollama's native `/api/generate` are not supported.
- Windows/macOS are supported only insofar as the code is pure stdlib; exercised here on Linux.

## Files

- `model_roundtable/` - `cli.py`, `config.py`, `endpoint.py`, `display.py`, `__main__.py`
- `tests/` - 73 tests: config parsing, display rendering, endpoint client, end-to-end CLI
  against fake local servers (no third-party deps beyond pytest)
- `README.md`, `LICENSE` (MIT, Copyright (c) 2026 Asdale Dynamics, LLC), `pyproject.toml`,
  `.gitignore`, `STATUS.md`
