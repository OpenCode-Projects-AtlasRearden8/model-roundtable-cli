"""Tests for config parsing (the part the project goal calls out).

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import os
import textwrap

import pytest

from model_roundtable.config import (
    ConfigError,
    default_config_path,
    load_config,
    parse_config,
)


def parse_toml(text):
    import tomllib

    return tomllib.loads(textwrap.dedent(text))


class TestParseConfig:
    def test_two_endpoints(self):
        endpoints, _ = parse_config(
            parse_toml(
                """
                [[endpoints]]
                name = "ollama"
                base_url = "http://localhost:11434/v1"
                model = "llama3.2:3b"

                [[endpoints]]
                name = "lmstudio"
                base_url = "http://localhost:1234/v1"
                model = "qwen2.5-7b-instruct"
                """
            )
        )
        assert [ep.name for ep in endpoints] == ["ollama", "lmstudio"]
        assert endpoints[0].base_url == "http://localhost:11434/v1"
        assert endpoints[0].model == "llama3.2:3b"
        assert endpoints[1].resolve_api_key() is None

    def test_three_endpoints(self):
        endpoints, _ = parse_config(
            parse_toml(
                """
                [[endpoints]]
                name = "one"
                base_url = "http://a/v1"
                model = "m1"

                [[endpoints]]
                name = "two"
                base_url = "http://b/v1"
                model = "m2"
                api_key = "sk-test"

                [[endpoints]]
                name = "three"
                base_url = "http://c/v1"
                model = "m3"
                api_key_env = "MY_KEY"
                """
            )
        )
        assert len(endpoints) == 3
        assert endpoints[1].resolve_api_key() == "sk-test"
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MY_KEY", "env-secret")
            assert endpoints[2].resolve_api_key() == "env-secret"

    def test_missing_base_url_raises(self):
        with pytest.raises(ConfigError, match="missing base_url"):
            parse_config(parse_toml('[[endpoints]]\nmodel = "m"'))

    def test_missing_model_raises(self):
        with pytest.raises(ConfigError, match="missing model"):
            parse_config(
                parse_toml('[[endpoints]]\nname = "a"\nbase_url = "http://a/v1"')
            )

    def test_default_name_when_unnamed(self):
        endpoints, _ = parse_config(
            parse_toml('[[endpoints]]\nbase_url = "http://a/v1"\nmodel = "m"')
        )
        assert endpoints[0].name == "endpoint-1"

    def test_duplicate_names_raise(self):
        with pytest.raises(ConfigError, match="duplicate endpoint name"):
            parse_config(
                parse_toml(
                    """
                    [[endpoints]]
                    name = "same"
                    base_url = "http://a/v1"
                    model = "m1"

                    [[endpoints]]
                    name = "same"
                    base_url = "http://b/v1"
                    model = "m2"
                    """
                )
            )

    def test_settings_timeout_and_system(self):
        endpoints, settings = parse_config(
            parse_toml(
                """
                timeout = 45.5
                system = "Be concise."

                [[endpoints]]
                name = "a"
                base_url = "http://a/v1"
                model = "m"
                """
            )
        )
        assert settings == {"timeout": 45.5, "system": "Be concise."}
        assert endpoints[0].model == "m"

    def test_shorthand_single_endpoint(self):
        endpoints, _ = parse_config(
            parse_toml(
                """
                base_url = "http://localhost:11434/v1"
                model = "llama3.2:3b"
                """
            )
        )
        assert len(endpoints) == 1
        assert endpoints[0].name == "endpoint-1"

    def test_invalid_timeout_ignored(self):
        _, settings = parse_config(parse_toml("timeout = 0"))
        assert settings == {}

    def test_api_key_env_beats_inline_key(self):
        endpoints, _ = parse_config(
            parse_toml(
                """
                [[endpoints]]
                name = "a"
                base_url = "http://a/v1"
                model = "m"
                api_key = "file-key"
                api_key_env = "TEST_ROUNDTRIPLE_KEY"
                """
            )
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TEST_ROUNDTRIPLE_KEY", "env-key")
            assert endpoints[0].resolve_api_key() == "env-key"
        os.environ.pop("TEST_ROUNDTRIPLE_KEY", None)
        assert endpoints[0].resolve_api_key() == "file-key"


class TestLoadConfig:
    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MODEL_ROUNDTABLE_CONFIG", str(tmp_path / "nope.toml"))
        endpoints, settings = load_config()
        assert endpoints == [] and settings == {}

    def test_loads_from_explicit_path(self, tmp_path):
        cfg = tmp_path / "roundtable.toml"
        cfg.write_text(
            textwrap.dedent(
                """
                [[endpoints]]
                name = "ollama"
                base_url = "http://localhost:11434/v1"
                model = "llama3.2:3b"

                [[endpoints]]
                name = "second"
                base_url = "http://localhost:1234/v1"
                model = "qwen2.5-7b-instruct"
                """
            )
        )
        endpoints, _ = load_config(str(cfg))
        assert [ep.name for ep in endpoints] == ["ollama", "second"]

    def test_env_var_path(self, tmp_path, monkeypatch):
        cfg = tmp_path / "auto.toml"
        cfg.write_text('base_url = "http://x/v1"\nmodel = "m"\n')
        monkeypatch.setenv("MODEL_ROUNDTABLE_CONFIG", str(cfg))
        endpoints, _ = load_config()
        assert endpoints[0].base_url == "http://x/v1"

    def test_broken_toml_raises(self, tmp_path):
        cfg = tmp_path / "bad.toml"
        cfg.write_text("this is not = = toml [[")
        with pytest.raises(ConfigError, match="could not parse"):
            load_config(str(cfg))

    def test_unreadable_file_raises(self, tmp_path):
        cfg = tmp_path / "d.toml"
        cfg.write_text("[[endpoints]]")
        cfg.chmod(0o000)
        try:
            with pytest.raises(ConfigError, match="could not read"):
                load_config(str(cfg))
        finally:
            cfg.chmod(0o644)


class TestDefaultPath:
    def test_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_ROUNDTABLE_CONFIG", str(tmp_path / "c.toml"))
        assert default_config_path() == str(tmp_path / "c.toml")

    def test_home_default(self, monkeypatch):
        monkeypatch.delenv("MODEL_ROUNDTABLE_CONFIG", raising=False)
        path = default_config_path()
        assert path.endswith(".model-roundtable.toml")
