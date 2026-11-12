"""Contract tests for OpenCode subagent orchestration.

OpenCode subagents always run in the background. The generated audit skills must
therefore launch independent specialists in one step, collect their reports, and
avoid finalizing before the reports arrive. Specialist agents must not spawn
children, which the default `subagent_depth: 1` also prevents.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENCODE = ROOT / ".opencode"
AGENTS = ROOT / "agents"


def frontmatter(text: str) -> str:
    match = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    assert match, "missing frontmatter"
    return match.group(1)


def test_audit_skills_document_background_protocol() -> None:
    for name in ("seo", "seo-audit"):
        text = (OPENCODE / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "OpenCode Subagent Protocol" in text, name
        assert "subagent` tool" in text, name
        assert "background" in text, name
        assert "parallel" in text, name
        assert "sessionID" in text, name
        assert "inline" in text, name


def test_audit_command_names_parallel_specialists() -> None:
    text = (OPENCODE / "commands" / "seo" / "audit.md").read_text(encoding="utf-8")
    assert "`subagent` tool" in text
    for agent in ("seo-technical", "seo-content", "seo-schema"):
        assert agent in text


def test_all_specialist_agents_are_available() -> None:
    expected = {path.stem for path in AGENTS.glob("*.md")}
    actual = {path.stem for path in (OPENCODE / "agents").glob("*.md")}
    assert actual == expected
    assert len(actual) == 19


def test_specialists_cannot_spawn_children() -> None:
    for path in sorted((OPENCODE / "agents").glob("*.md")):
        value = frontmatter(path.read_text(encoding="utf-8"))
        assert 'action: "subagent"' not in value, path.name
        assert 'action: "*"' in value
        assert "effect: deny" in value


def test_subagent_depth_is_one() -> None:
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    assert config["experimental"]["subagent_depth"] == 1
    assert {
        "action": "subagent",
        "resource": "seo-*",
        "effect": "allow",
    } in config["permissions"]
