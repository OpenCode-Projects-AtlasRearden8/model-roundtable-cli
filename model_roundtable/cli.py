"""Command-line entry point for model-roundtable.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import argparse
import shutil
import sys

from . import __version__
from .config import EXAMPLE_CONFIG, ConfigError, load_config
from .display import render, render_json
from .endpoint import Endpoint, ask_all

DEFAULT_OLLAMA = Endpoint("ollama", "http://localhost:11434/v1", "llama3.2:3b")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model-roundtable",
        description=(
            "Ask one prompt, get answers from two or three OpenAI-compatible "
            "endpoints at once - side by side, with latency and token counts."
        ),
        epilog=(
            "Endpoints live in your config file (~/.model-roundtable.toml by "
            "default, or --config PATH). Keys never leave your machine except "
            "to the single endpoint they belong to."
        ),
    )
    parser.add_argument(
        "prompt", nargs="?", help="the prompt to send to every endpoint"
    )
    parser.add_argument(
        "-p", "--prompt", dest="prompt_flag", help="same as positional prompt"
    )
    parser.add_argument(
        "--config", "-c", help="config file path (default: ~/.model-roundtable.toml)"
    )
    parser.add_argument(
        "--model", help="override every endpoint's model name in one go"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--timeout", type=float, help="seconds per endpoint (default: config or 120)"
    )
    parser.add_argument(
        "--width", type=int, help="output width in columns (default: your terminal's)"
    )
    parser.add_argument(
        "--config-example", action="store_true", help="print a starter config and exit"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def terminal_width(override: int | None = None) -> int:
    if override and override >= 20:
        return override
    try:
        return shutil.get_terminal_size(fallback=(100, 24)).columns
    except Exception:  # noqa: BLE001 - terminal width is best-effort
        return 100


def read_prompt(args: argparse.Namespace) -> str | None:
    if args.prompt_flag:
        return args.prompt_flag
    if args.prompt:
        return args.prompt
    try:
        if not sys.stdin.isatty():
            piped = sys.stdin.read().strip()
            if piped:
                return piped
    except (OSError, ValueError):
        pass
    return None


def cli_error(message: str, hint: str | None = None) -> int:
    print(f"model-roundtable: {message}", file=sys.stderr)
    if hint:
        print(hint, file=sys.stderr)
    return 1


def run(args: argparse.Namespace) -> int:
    try:
        endpoints, settings = load_config(args.config)
    except ConfigError as exc:
        return cli_error(
            str(exc),
            hint="See a working example:  model-roundtable --config-example",
        )

    if args.config_example:
        print(EXAMPLE_CONFIG, end="")
        return 0

    if not endpoints:
        endpoints = [DEFAULT_OLLAMA]
        print(
            "note: no config file found; using default Ollama endpoint "
            "(run 'model-roundtable --config-example' to set up two or three).",
            file=sys.stderr,
        )
    if len(endpoints) < 2:
        print(
            "tip: a roundtable works best with two or three endpoints; add more "
            "to your config file to compare side by side.",
            file=sys.stderr,
        )
    if len(endpoints) > 3:
        return cli_error(
            f"config declares {len(endpoints)} endpoints; roundtable fits two or "
            "three side by side - trim the list or use --config to pick a smaller set."
        )

    if args.model:
        endpoints = [
            Endpoint(ep.name, ep.base_url, args.model, ep.api_key, ep.api_key_env)
            for ep in endpoints
        ]

    prompt = read_prompt(args)
    if not prompt:
        return cli_error(
            "no prompt given",
            hint="try: model-roundtable 'Explain quantization in plain English'",
        )

    timeout = (
        args.timeout if args.timeout is not None else settings.get("timeout", 120.0)
    )
    system = settings.get("system")

    header_names = ", ".join(f"{ep.name} ({ep.model})" for ep in endpoints)
    stream = sys.stderr if args.json else sys.stdout
    print(f"Asked {len(endpoints)} endpoints: {header_names}", file=stream)
    print(f"Prompt: {prompt[:160]}{'...' if len(prompt) > 160 else ''}", file=stream)

    results = ask_all(endpoints, prompt, timeout=timeout, system=system)
    width = terminal_width(args.width)
    if args.json:
        print(render_json(results))
    else:
        print(render(results, width))
        ok_count = sum(1 for r in results if r.ok)
        if ok_count < len(results):
            failed = ", ".join(r.name for r in results if not r.ok)
            print(flush=True)
            print(f"note: {failed} did not answer (see error above).", file=sys.stderr)

    return 0 if any(r.ok for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
