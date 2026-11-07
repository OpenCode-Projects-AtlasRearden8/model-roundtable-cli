# model-roundtable

Ask one prompt once - hear from two or three models at the same time, side by
side, in your terminal.

`model-roundtable` sends the same prompt to every endpoint in your config
file, then prints their answers next to each other with latency and token
counts, so you can pick the right default model for each kind of task: who is
fastest for quick things, who explains clearly, who writes the best first
draft. Works with Ollama and anything else that speaks the OpenAI
`/chat/completions` dialect (LM Studio, llama.cpp server, vLLM, plus hosted
APIs you already pay for).

Made by **Asdale Dynamics, LLC**, part of a beginner-first family of tools.
MIT licensed - Copyright (c) 2026 Asdale Dynamics, LLC.

## How it fits with the other tools

- **Different from `ai-model-picker`** - that one recommends which model to
  *install and run*, offline, from your hardware. This one *runs them and
  races them* on your actual prompts.
- **Different from `llm-diff-explainer`** - that one compares *two drafts that
  already exist*. This one generates the drafts from the same prompt at the
  same time.

## Quick start

```bash
# 1. Print a starter config (zero endpoints, no secrets) and save it:
model-roundtable --config-example > ~/.model-roundtable.toml
#    or: python -m model_roundtable --config-example > ~/.model-roundtable.toml

# 2. Edit the file: give it two or three endpoints you actually run.
# 3. Ask one prompt to all of them at once:
model-roundtable "Explain quantization in plain English"
```

Example output (three endpoints, one row per line of each):

```
Asked 3 endpoints: ollama (llama3.2:3b), lmstudio (qwen2.5-7b), hosted (gpt-4o-mini)
Prompt: Explain quantization in plain English

ollama (llama3.2:3b)      |  lmstudio (qwen2.5-7b)     |  hosted (gpt-4o-mini)
1.42 s · 14 in / 96 out   |  0.98 s · 14 in / 120 out  |  0.41 s · 12 in / 88 out
------------------------- |  ------------------------- |  ------------------------
Quantization means...     |  Think of it like...       |  In one sentence...
```

## Config file

Endpoints and keys live in one local file, `~/.model-roundtable.toml` by
default (or `--config path/to/file.toml`, or the `MODEL_ROUNDTABLE_CONFIG`
environment variable):

```toml
# Optional global settings:
timeout = 120.0          # seconds per endpoint
system = "Be concise."   # optional system message sent to every endpoint

[[endpoints]]
name = "ollama"
base_url = "http://localhost:11434/v1"
model = "llama3.2:3b"

[[endpoints]]
name = "lmstudio"
base_url = "http://localhost:1234/v1"
model = "qwen2.5-7b-instruct"
api_key_env = "LMSTUDIO_API_KEY"

[[endpoints]]
name = "hosted"
base_url = "https://openrouter.ai/api/v1"
model = "meta-llama/llama-3.2-3b-instruct"
api_key_env = "OPENROUTER_API_KEY"
```

A one-endpoint shorthand also works (`base_url` + `model` at the top level,
no `[[endpoints]]` section). Two or three endpoints makes a real roundtable;
the tool politely asks you to trim beyond three because the side-by-side
layout fits that many comfortably.

## Options

```bash
model-roundtable "your prompt"          # positional prompt (or use --prompt)
echo "prompt" | model-roundtable        # or pipe the prompt on stdin
model-roundtable --config ./try.toml    # alternate endpoints for this run
model-roundtable --model qwen2.5:14b    # override every endpoint's model
model-roundtable --timeout 30           # per-endpoint seconds
model-roundtable --json                 # machine-readable output
model-roundtable --width 120            # force panel width (default: terminal)
model-roundtable --config-example       # print a starter config and exit
```

## Privacy & secrets

- Nothing leaves your machine except one HTTPS/HTTP call per endpoint you
  named, carrying only the prompt you chose.
- Keys are optional. If an endpoint needs one, prefer `api_key_env` so the
  key lives in your environment, not in a file. An inline `api_key = "..."`
  is also supported, and either way a key is sent *only* to that endpoint's
  own `base_url` - never to any other endpoint on the list.
- The tool never writes keys, prompts, or answers to disk, and refuses to
  expand your endpoint list silently behind your back.

## Known limits

- Token counts come from the server's `usage` report when it gives one;
  otherwise they are estimates (~4 characters per token), marked `(est.)`.
- Answers are word-wrapped to panels; very narrow terminals (< 60 columns per
  endpoint) fall back to stacked output instead of side-by-side.
- Responses are not streamed: each answer appears when the endpoint finishes,
  and the first answer can't be shown until the last one completes.

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check model_roundtable tests
```

73 tests cover the parts that matter most: config parsing (endpoint tables,
key resolution, error cases) and display rendering (side-by-side layout,
wrapping, latency/token formatting, JSON output), plus an end-to-end suite
against fake local OpenAI-compatible servers.

## License

MIT - see [LICENSE](LICENSE). **Copyright (c) 2026 Asdale Dynamics, LLC.**
