"""End-to-end CLI tests: fake local endpoints + captured output.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from __future__ import annotations

import json
import textwrap

import pytest

from model_roundtable.cli import main
from tests.conftest import chat_response


def write_config(tmp_path, servers, extra=""):
    lines = [""]
    for name, url, model in servers:
        lines.append(
            textwrap.dedent(
                f"""
                [[endpoints]]
                name = "{name}"
                base_url = "{url}"
                model = "{model}"
                """
            ).lstrip("\n")
        )
    cfg = tmp_path / "roundtable.toml"
    cfg.write_text("\n".join(lines) + extra)
    return str(cfg)


@pytest.fixture()
def no_config_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_ROUNDTABLE_CONFIG", str(tmp_path / "missing.toml"))


class TestHappyPath:
    def test_two_endpoints_side_by_side(self, fake_server, tmp_path, capsys):
        server = fake_server(
            {
                "/one/chat/completions": (200, chat_response("First answer")),
                "/two/chat/completions": (200, chat_response("Second answer")),
            }
        )
        config = write_config(
            tmp_path,
            [("one", f"{server.url}/one", "m1"), ("two", f"{server.url}/two", "m2")],
        )
        code = main(["--config", config, "--width", "100", "Which is better?"])
        out = capsys.readouterr().out
        assert code == 0
        assert "one (m1)" in out and "two (m2)" in out
        assert "First answer" in out and "Second answer" in out
        assert " | " in out

    def test_three_endpoints(self, fake_server, tmp_path, capsys):
        server = fake_server(
            {
                "/one/chat/completions": (200, chat_response("A")),
                "/two/chat/completions": (200, chat_response("B")),
                "/three/chat/completions": (200, chat_response("C")),
            }
        )
        config = write_config(
            tmp_path,
            [
                ("one", f"{server.url}/one", "m1"),
                ("two", f"{server.url}/two", "m2"),
                ("three", f"{server.url}/three", "m3"),
            ],
        )
        code = main(["--config", config, "--width", "120", "prompt"])
        out = capsys.readouterr().out
        assert code == 0
        header = [line for line in out.splitlines() if line.count(" | ") == 2]
        assert header, out

    def test_json_output(self, fake_server, tmp_path, capsys):
        server = fake_server({"/v1/chat/completions": (200, chat_response("Answer A"))})
        config = write_config(tmp_path, [("one", server.url, "m1")])
        code = main(["--config", config, "--json", "hi"])
        data = json.loads(capsys.readouterr().out)
        assert code == 0
        assert data[0]["name"] == "one"
        assert data[0]["answer"] == "Answer A"

    def test_prompt_from_flag(self, fake_server, tmp_path, capsys):
        server = fake_server()
        config = write_config(tmp_path, [("one", server.url, "m1")])
        code = main(["--config", config, "--prompt", "flagged prompt", "--json"])
        assert server.requests[0]["body"]["messages"][-1]["content"] == "flagged prompt"
        assert code == 0

    def test_model_override(self, fake_server, tmp_path, capsys):
        server = fake_server()
        config = write_config(tmp_path, [("one", server.url, "orig")])
        code = main(["--config", config, "--model", "override-model", "--json", "hi"])
        assert server.requests[0]["body"]["model"] == "override-model"
        assert capsys.readouterr().out  # ran fine
        assert code == 0

    def test_prompt_via_stdin(self, fake_server, tmp_path, capsys, monkeypatch):
        import io

        server = fake_server()
        config = write_config(tmp_path, [("one", server.url, "m1")])
        monkeypatch.setattr("sys.stdin", io.StringIO("piped question\n"))
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        code = main(["--config", config, "--json"])
        assert server.requests[0]["body"]["messages"][-1]["content"] == "piped question"
        assert code == 0


class TestErrors:
    def test_no_prompt(self, no_config_env, capsys):
        code = main([])
        err = capsys.readouterr().err
        assert code == 1
        assert "no prompt given" in err

    def test_broken_config(self, tmp_path, capsys):
        cfg = tmp_path / "bad.toml"
        cfg.write_text("not [ valid toml")
        code = main(["--config", str(cfg), "hi"])
        err = capsys.readouterr().err
        assert code == 1
        assert "could not parse" in err

    def test_more_than_three_endpoints(self, fake_server, tmp_path, capsys):
        server = fake_server()
        servers = [(f"ep{i}", f"{server.url}/ep{i}", "m") for i in range(4)]
        config = write_config(tmp_path, servers)
        code = main(["--config", config, "hi"])
        err = capsys.readouterr().err
        assert code == 1
        assert "two or three" in err

    def test_all_endpoints_fail(self, tmp_path, capsys):
        config = write_config(
            tmp_path,
            [
                ("dead1", "http://localhost:1/v1", "m"),
                ("dead2", "http://localhost:2/v1", "m"),
            ],
        )
        code = main(["--config", config, "hi"])
        captured = capsys.readouterr()
        assert "Error:" in captured.out
        assert code == 1

    def test_partial_failure_exit_zero(self, fake_server, tmp_path, capsys):
        server = fake_server({"/good/chat/completions": (200, chat_response("works"))})
        config = write_config(
            tmp_path,
            [
                ("good", f"{server.url}/good", "m"),
                ("dead", "http://localhost:1/v1", "m"),
            ],
        )
        code = main(["--config", config, "hi"])
        assert code == 0


class TestDefaults:
    def test_no_config_uses_ollama_default(self, no_config_env, capsys):
        code = main(["hi"])
        captured = capsys.readouterr()
        assert code == 1
        assert "no config file found" in captured.err
        assert "ollama" in captured.out

    def test_tip_for_single_endpoint(self, fake_server, tmp_path, capsys):
        server = fake_server()
        config = write_config(tmp_path, [("only", server.url, "m1")])
        code = main(["--config", config, "--json", "hi"])
        err = capsys.readouterr().err
        assert code == 0
        assert "tip:" in err

    def test_config_example(self, capsys, no_config_env):
        code = main(["--config-example"])
        out = capsys.readouterr().out
        assert code == 0
        assert "[[endpoints]]" in out
        assert "localhost:11434" in out
