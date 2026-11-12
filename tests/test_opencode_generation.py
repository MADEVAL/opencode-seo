"""Contract tests for the generated OpenCode target.

The canonical skills, agents, and hooks stay Claude-compatible. The OpenCode
target is generated into `.opencode/` so OpenCode sees native frontmatter,
native tool calls, slash commands, and the local plugin. These tests fail when
the generated layer drifts from the canonical source or regresses to Claude-only
syntax.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENCODE = ROOT / ".opencode"
SKILLS = ROOT / "skills"
AGENTS = ROOT / "agents"


def frontmatter(text: str) -> str:
    match = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    assert match, "missing frontmatter"
    return match.group(1)


def test_generated_target_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_opencode.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_skill_and_agent_counts_match_canonical_sources() -> None:
    expected_skills = {path.parent.name for path in SKILLS.glob("*/SKILL.md")}
    expected_agents = {path.stem for path in AGENTS.glob("*.md")}
    actual_skills = {path.parent.name for path in (OPENCODE / "skills").glob("*/SKILL.md")}
    actual_agents = {path.stem for path in (OPENCODE / "agents").glob("*.md")}
    assert actual_skills == expected_skills
    assert actual_agents == expected_agents


def test_generated_markdown_has_no_claude_tokens() -> None:
    forbidden = ("${CLAUDE_PLUGIN_ROOT}", "mcp__", "maxTurns")
    hits: list[str] = []
    for path in sorted((OPENCODE / "skills").rglob("*.md")) + sorted((OPENCODE / "agents").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append(f"{path.relative_to(ROOT).as_posix()}: {token}")
    assert not hits, "\n".join(hits)


def test_generated_skills_do_not_declare_claude_only_frontmatter() -> None:
    hits: list[str] = []
    for path in sorted((OPENCODE / "skills").glob("*/SKILL.md")):
        value = frontmatter(path.read_text(encoding="utf-8"))
        for key in ("user-invocable", "argument-hint"):
            if re.search(rf"(?m)^{key}:", value):
                hits.append(f"{path.relative_to(ROOT).as_posix()}: {key}")
    assert not hits, "\n".join(hits)


def test_generated_agents_use_opencode_fields() -> None:
    for path in sorted((OPENCODE / "agents").glob("*.md")):
        value = frontmatter(path.read_text(encoding="utf-8"))
        assert re.search(r"(?m)^mode:\s*subagent$", value), path
        assert re.search(r"(?m)^steps:\s*\d+$", value), path
        assert re.search(r"(?m)^permissions:$", value), path
        assert not re.search(r"(?m)^tools:", value), path
        assert not re.search(r"(?m)^maxTurns:", value), path
        assert not re.search(r"(?m)^model:\s*(sonnet|opus)$", value), path
        assert 'action: "seo"' in value, path


def test_agent_permissions_keep_seo_tool_and_env_safety() -> None:
    for path in sorted((OPENCODE / "agents").glob("*.md")):
        value = frontmatter(path.read_text(encoding="utf-8"))
        assert 'action: "*"' in value
        assert "effect: deny" in value
        assert 'action: "read"' in value
        assert 'resource: "*.env"' in value
        assert "effect: ask" in value


def test_commands_exist() -> None:
    assert (OPENCODE / "commands" / "seo.md").is_file()
    for name in ("audit", "page", "technical", "schema", "sitemap", "geo"):
        assert (OPENCODE / "commands" / "seo" / f"{name}.md").is_file(), name


def test_plugin_and_root_config_exist() -> None:
    assert (OPENCODE / "plugins" / "opencode-seo" / "index.ts").is_file()
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    assert "skills" not in config, "explicit skills source would override .opencode/skills"
    assert config["experimental"]["subagent_depth"] == 1


def test_plugin_exposes_runtime_bridge_and_schema_hook() -> None:
    plugin = (OPENCODE / "plugins" / "opencode-seo" / "index.ts").read_text(encoding="utf-8")
    assert "ctx.tool.transform" in plugin
    assert "ctx.tool.hook(\"execute.after\"" in plugin
    assert "ctx.permission.assert" in plugin
    assert "runtime.py" in plugin
    for action in ("run", "setup", "doctor", "path", "read"):
        assert f'"{action}"' in plugin
    assert "shell: true" not in plugin

