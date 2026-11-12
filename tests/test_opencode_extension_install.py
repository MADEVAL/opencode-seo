"""Contract tests for the native OpenCode extension installer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import install_opencode_extension as installer  # noqa: E402


def args_for(extension: str, **overrides) -> argparse.Namespace:
    values = {
        "extension": extension,
        "username": "user@example.com",
        "password": "secret",
        "key": "test-key",
        "url": None,
        "site_id": None,
        "env": None,
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_strip_jsonc_keeps_strings_and_removes_comments() -> None:
    text = """{
      // comment
      "url": "https://example.com/a//b",
      "items": [1, 2,],
      /* block */
    }"""
    parsed = json.loads(installer.strip_jsonc(text))
    assert parsed["url"] == "https://example.com/a//b"
    assert parsed["items"] == [1, 2]


def test_dataforseo_installs_skill_agent_and_mcp(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    installer.build_extension("dataforseo", args_for("dataforseo"))

    skill = tmp_path / "skills" / "seo-dataforseo" / "SKILL.md"
    agent = tmp_path / "agents" / "seo-dataforseo.md"
    assert skill.is_file()
    assert agent.is_file()

    skill_text = skill.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}" not in skill_text
    assert 'seo({"action": "run"' in skill_text
    assert "user-invocable" not in skill_text

    agent_text = agent.read_text(encoding="utf-8")
    assert "mode: subagent" in agent_text
    assert 'action: "seo"' in agent_text
    assert "maxTurns" not in agent_text

    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    server = config["mcp"]["servers"]["dataforseo"]
    assert server["type"] == "local"
    assert server["codemode"] is False
    assert server["environment"]["DATAFORSEO_USERNAME"] == "user@example.com"
    assert Path(server["environment"]["FIELD_CONFIG_PATH"]).is_file()


def test_banana_transforms_extension_runner_and_references(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    installer.build_extension("banana", args_for("banana"))

    skill = tmp_path / "skills" / "seo-image-gen" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert '"extension": "banana"' in text
    assert "CLAUDE_SKILL_DIR" not in text
    assert (tmp_path / "skills" / "seo-image-gen" / "references" / "prompt-engineering.md").is_file()
    assert (tmp_path / "opencode-seo" / "extensions" / "banana" / "scripts" / "generate.py").is_file()

    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "nanobanana-mcp" in config["mcp"]["servers"]


def test_jsonc_config_is_merged_without_losing_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    config_path = tmp_path / "opencode.jsonc"
    config_path.write_text(
        '{\n  // keep this value\n  "model": "deepseek/deepseek-flash",\n  "permissions": [],\n}\n',
        encoding="utf-8",
    )

    installer.build_extension("firecrawl", args_for("firecrawl"))

    document = json.loads((tmp_path / "opencode.jsonc").read_text(encoding="utf-8"))
    assert document["model"] == "deepseek/deepseek-flash"
    assert "firecrawl" in document["mcp"]["servers"]
    assert (tmp_path / "opencode.jsonc.bak").is_file()
