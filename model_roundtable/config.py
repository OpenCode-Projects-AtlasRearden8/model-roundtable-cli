"""Config file support: endpoints and optional keys, in one local TOML file.

Default location: ~/.model-roundtable.toml. Example:

    timeout = 120.0

    [[endpoints]]
    name = "ollama"
    base_url = "http://localhost:11434/v1"
    model = "llama3.2:3b"

    [[endpoints]]
    name = "lmstudio"
    base_url = "http://localhost:1234/v1"
    model = "qwen2.5-7b-instruct"
    api_key_env = "LMSTUDIO_API_KEY"

Keys are optional. If one is needed, prefer ``api_key_env`` (read from the
environment at runtime) over pasting ``api_key`` into the file. Either way, a
key is sent only to that endpoint's own base_url, nowhere else.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import os
import tomllib

from .endpoint import Endpoint

CONFIG_ENV_VAR = "MODEL_ROUNDTABLE_CONFIG"
DEFAULT_CONFIG_NAME = ".model-roundtable.toml"


class ConfigError(Exception):
    """Raised when a config file exists but cannot be understood."""


def default_config_path() -> str | None:
    """Where to look for the config file (env override, then home dir)."""
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return override
    home = os.path.expanduser("~")
    home = os.environ.get("MODEL_ROUNDTABLE_HOME", home)
    return os.path.join(home, DEFAULT_CONFIG_NAME)


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _as_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _endpoint_from_table(table: object, index: int) -> Endpoint:
    if not isinstance(table, dict):
        raise ConfigError(
            f"endpoints[{index}] must be a table, got {type(table).__name__}"
        )
    name = _as_str(table.get("name")) or f"endpoint-{index + 1}"
    base_url = _as_str(table.get("base_url"))
    if not base_url:
        raise ConfigError(f"endpoint '{name}' is missing base_url")
    model = _as_str(table.get("model"))
    if not model:
        raise ConfigError(f"endpoint '{name}' is missing model")
    return Endpoint(
        name=name,
        base_url=base_url,
        model=model,
        api_key=_as_str(table.get("api_key")),
        api_key_env=_as_str(table.get("api_key_env")),
    )


def parse_config(data: dict) -> tuple[list[Endpoint], dict]:
    """Turn a parsed TOML dict into (endpoints, settings)."""
    if not isinstance(data, dict):
        raise ConfigError("config file must contain a TOML table")
    settings: dict = {}
    timeout = _as_float(data.get("timeout"))
    if timeout is not None:
        settings["timeout"] = timeout
    system = _as_str(data.get("system"))
    if system is not None:
        settings["system"] = system

    raw_endpoints = data.get("endpoints")
    if raw_endpoints is None:
        # A single-endpoint shorthand: top-level base_url + model.
        base_url = _as_str(data.get("base_url"))
        model = _as_str(data.get("model"))
        if base_url and model:
            raw_endpoints = [
                {
                    "name": _as_str(data.get("name")) or "endpoint-1",
                    "base_url": base_url,
                    "model": model,
                    "api_key": data.get("api_key"),
                    "api_key_env": data.get("api_key_env"),
                }
            ]
        else:
            raw_endpoints = []
    if not isinstance(raw_endpoints, list):
        raise ConfigError("'endpoints' must be a list of tables")

    endpoints: list[Endpoint] = []
    seen: set[str] = set()
    for index, table in enumerate(raw_endpoints):
        endpoint = _endpoint_from_table(table, index)
        if endpoint.name in seen:
            raise ConfigError(f"duplicate endpoint name: '{endpoint.name}'")
        seen.add(endpoint.name)
        endpoints.append(endpoint)
    return endpoints, settings


def load_config(path: str | None = None) -> tuple[list[Endpoint], dict]:
    """Load and parse the config file.

    Returns ([], {}) when the file simply does not exist (the CLI then falls
    back to a default single Ollama endpoint). Raises ConfigError when the
    file exists but cannot be read or parsed.
    """
    if path is None:
        path = default_config_path()
    if not path or not os.path.exists(path):
        return [], {}
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"could not parse {path}: {exc}") from exc
    return parse_config(data if isinstance(data, dict) else {})


EXAMPLE_CONFIG = """\
# model-roundtable config
# Copy to ~/.model-roundtable.toml (or pass --config path/to/file.toml).
# Keys are optional; prefer api_key_env so nothing secret sits in a file.

timeout = 120.0

# Show all named endpoints side by side (two or three works best).
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
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
api_key_env = "OPENAI_API_KEY"
"""
