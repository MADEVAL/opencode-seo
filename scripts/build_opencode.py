#!/usr/bin/env python3
"""Generate the OpenCode target from the canonical Claude-compatible sources.

The repository keeps one canonical skill and agent set so every harness reads the
same analysis logic. OpenCode needs different frontmatter, tool names, command
paths, and runtime calls, so this script writes a dedicated `.opencode/` tree and
the install payloads under `dist/`.

Run `python scripts/build_opencode.py` to refresh the generated tree.
Run `python scripts/build_opencode.py --check` in CI to detect drift.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
OPENCODE = ROOT / ".opencode"
COMMAND_SOURCE = ROOT / "opencode" / "commands"
PLUGIN_SOURCE = ROOT / "opencode" / "plugin" / "opencode-seo"
AGENT_SOURCE = ROOT / "agents"
SKILL_SOURCE = ROOT / "skills"
MARKER = ".opencode-seo-generated"

LAUNCHER = r"\$\{CLAUDE_PLUGIN_ROOT\}/scripts/claude-seo"
QUOTED_LAUNCHER = r'"\$\{CLAUDE_PLUGIN_ROOT\}/scripts/claude-seo"'

TOOL_MAP = {
    "read": "read",
    "write": "edit",
    "edit": "edit",
    "bash": "shell",
    "glob": "glob",
    "grep": "grep",
    "webfetch": "webfetch",
    "websearch": "websearch",
    "task": "subagent",
    "agent": "subagent",
    "skill": "skill",
}

ENV_RULES = (
    ("*.env", "ask"),
    ("*.env.*", "ask"),
    ("*.env.example", "allow"),
)

RUNTIME_PARAGRAPH = (
    "**Runtime:** Call the `seo` tool with action `run`, a script name, and "
    "arguments, for example "
    '`seo({"action": "run", "script": "page_checks.py", "args": ["--url", "<url>"]})`. '
    "The plugin resolves the install root automatically, so no `PATH` entry is "
    "needed. Do not invoke bundled scripts with a bare Python interpreter."
)

SUBAGENT_PROTOCOL = (
    "## OpenCode Subagent Protocol\n\n"
    "Use the `subagent` tool for specialist work. Children always run in the background.\n\n"
    "- Launch independent specialists in the same step so they run in parallel.\n"
    "- Every call needs `agent`, `description`, and `prompt`. Put the URL, output directory,\n"
    "  and exact scope in the prompt.\n"
    "- Do not launch the same specialist twice.\n"
    "- Children cannot launch children because `subagent_depth` is 1.\n"
    "- Keep collecting while children run. Do not present the final report until every\n"
    "  launched child has reported or failed.\n"
    "- Merge reports as they arrive. If a child fails, record the failure and continue with\n"
    "  the rest.\n"
    "- Follow up with the returned `sessionID` only when a report is incomplete.\n"
    "- If no child can launch, run that specialist inline and label the section as fallback.\n\n"
    "Example:\n"
    '`subagent({"agent": "seo-technical", "description": "Technical SEO", '
    '"prompt": "Audit <url> and write findings to <domain>-audit/findings/technical.md."})`'
)


def split_frontmatter(text: str) -> tuple[str | None, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.DOTALL)
    if not match:
        return None, text
    return match.group(1), text[match.end() :]


def parse_frontmatter(frontmatter: str) -> dict[str, str]:
    values: dict[str, str] = {}
    key: str | None = None
    block: list[str] = []

    def flush() -> None:
        nonlocal block, key
        if key is not None:
            values[key] = " ".join(part.strip() for part in block if part.strip()).strip()
        block = []

    for raw in frontmatter.splitlines():
        if not raw.strip():
            continue
        if raw[:1].isspace() and key is not None:
            block.append(raw)
            continue
        flush()
        if ":" not in raw:
            key = None
            continue
        name, value = raw.split(":", 1)
        key = name.strip()
        value = value.strip()
        if value in {">", "|", ">-", "|-"}:
            block = []
        else:
            values[key] = value
            key = None

    flush()
    return values


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def yaml_quote(value: str) -> str:
    return json.dumps(" ".join(value.split()), ensure_ascii=False)


def replace_references(text: str, current_skill: str | None, is_agent: bool) -> str:
    pattern = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/([a-z0-9-]+)/([^\s`)\]]+)")

    def replacement(match: re.Match[str]) -> str:
        target, rest = match.group(1), match.group(2)
        if is_agent:
            return f"../skills/{target}/{rest}"
        if current_skill == target:
            return rest
        return f"../{target}/{rest}"

    return pattern.sub(replacement, text)


def replace_runtime_calls(text: str) -> str:
    def run_replacement(match: re.Match[str]) -> str:
        script = match.group(1)
        rest = match.group(2).strip().rstrip("`").strip()
        if not rest:
            return f'seo({{"action": "run", "script": "{script}"}})'

        try:
            arguments = shlex.split(rest)
        except ValueError:
            arguments = rest.split()

        args_json = json.dumps(arguments, ensure_ascii=False)
        return f'seo({{"action": "run", "script": "{script}", "args": {args_json}}})'

    text = re.sub(
        QUOTED_LAUNCHER + r"\s+run\s+([A-Za-z0-9_.-]+\.py)([^\n`]*)",
        run_replacement,
        text,
    )
    text = re.sub(
        LAUNCHER + r"\s+run\s+([A-Za-z0-9_.-]+\.py)([^\n`]*)",
        run_replacement,
        text,
    )
    text = re.sub(QUOTED_LAUNCHER + r"\s+setup(?:\s+--json)?\b", 'seo({"action": "setup"})', text)
    text = re.sub(LAUNCHER + r"\s+setup(?:\s+--json)?\b", 'seo({"action": "setup"})', text)
    text = re.sub(QUOTED_LAUNCHER + r"\s+doctor(?:\s+--json)?\b", 'seo({"action": "doctor"})', text)
    text = re.sub(LAUNCHER + r"\s+doctor(?:\s+--json)?\b", 'seo({"action": "doctor"})', text)
    text = re.sub(QUOTED_LAUNCHER, "seo run", text)
    text = re.sub(LAUNCHER, "seo run", text)
    return text


def transform_body(text: str, current_skill: str | None, is_agent: bool = False) -> str:
    text = replace_runtime_calls(text)
    text = replace_references(text, current_skill, is_agent)
    text = text.replace("~/.claude/skills", "~/.config/opencode/skills")
    text = text.replace("~/.claude/agents", "~/.config/opencode/agents")
    text = text.replace("~/.claude.json", "~/.config/opencode/opencode.json")
    text = text.replace("~/.claude", "~/.config/opencode")
    text = text.replace("$HOME/.claude", "$HOME/.config/opencode")
    text = text.replace('"$HOME/.config/opencode/skills/seo/scripts/claude-seo"', "the seo tool")
    text = text.replace("./scripts/claude-seo", "./scripts/opencode-seo")
    text = text.replace("Claude Code expands", "OpenCode resolves")
    text = text.replace("Claude Code", "OpenCode")
    text = text.replace("Claude SEO", "OpenCode SEO")
    text = text.replace("claude-seo uses", "OpenCode SEO uses")
    text = text.replace("CLAUDE.md", "AGENTS.md")
    text = text.replace(
        "schema/templates.json",
        'seo({"action": "read", "path": "schema/templates.json"})',
    )
    text = text.replace("CLAUDE_PLUGIN_DATA", "OPENCODE_SEO_DATA_DIR")
    text = text.replace("CLAUDE_SEO_", "OPENCODE_SEO_")
    text = re.sub(r"\bmaxTurns\b", "steps", text)
    text = re.sub(r"mcp__([a-z0-9]+)__([a-z0-9_]+)", r"\1_\2", text)
    text = re.sub(r"\bWebFetch\b", "webfetch", text)
    text = re.sub(r"\bWebSearch\b", "websearch", text)
    text = re.sub(r"\bTask tool\b", "subagent tool", text)
    text = re.sub(r"\bAgent tool\b", "subagent tool", text)
    text = re.sub(r"\bBash tool\b", "shell tool", text)
    text = re.sub(r"\bRead tool\b", "read tool", text)
    text = re.sub(r"\bWrite tool\b", "edit tool", text)
    text = re.sub(r"\bEdit tool\b", "edit tool", text)
    text = re.sub(r"\bSkill tool\b", "skill tool", text)
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", "<seo-root>")
    return text


def transform_skill(text: str, skill_name: str) -> str:
    frontmatter, body = split_frontmatter(text)
    if frontmatter is not None:
        lines = [
            line
            for line in frontmatter.splitlines()
            if not re.match(r"^(user-invocable|argument-hint):", line.strip())
        ]
        frontmatter = "\n".join(lines).strip()
        body = transform_body(body, skill_name, is_agent=False)
        if skill_name == "seo":
            body = re.sub(
                r"\*\*Runtime:\*\*.*?Never invoke bundled scripts\nwith a bare Python interpreter\.",
                RUNTIME_PARAGRAPH,
                body,
                flags=re.DOTALL,
            )
            body = body.replace(
                "When the user invokes `/seo audit`, delegate to subagents in parallel:",
                "When the user invokes `/seo audit`, launch `subagent` calls in one step so "
                "they run in parallel. Each child runs in the background and reports back; "
                "merge its findings when it arrives. Use `subagent({\"agent\": \"seo-technical\", "
                "\"description\": \"Technical SEO\", \"prompt\": \"...\"})` for each specialist:",
            )
        if skill_name == "seo-audit":
            body = body.replace(
                "**Delegate to subagents** (if available, otherwise run inline sequentially):",
                "**Delegate with the OpenCode `subagent` tool.** Launch independent specialists "
                "in one step so they run in parallel. Children run in the background and report "
                "back; merge each report when it arrives. If a child cannot launch, run that "
                "specialist inline. Example: `subagent({\"agent\": \"seo-technical\", "
                "\"description\": \"Technical SEO\", \"prompt\": \"Audit <url> and write findings.\"})`.",
            )
            body = body.replace("## Process", f"{SUBAGENT_PROTOCOL}\n\n## Process", 1)
        if skill_name == "seo":
            body = body.replace(
                "## Synthesis Methodology",
                f"{SUBAGENT_PROTOCOL}\n\n## Synthesis Methodology",
                1,
            )
        return f"---\n{frontmatter}\n---\n{body}" if frontmatter else body
    return transform_body(text, skill_name, is_agent=False)


def tools_from_agent(values: dict[str, str]) -> list[str]:
    raw = values.get("tools", "")
    raw = raw.split("#", 1)[0]
    return [part.strip() for part in raw.split(",") if part.strip()]


def permissions_for(tools: Iterable[str]) -> list[tuple[str, str, str]]:
    actions: list[str] = []
    for tool in tools:
        lowered = tool.lower()
        if lowered.startswith("mcp__"):
            parts = tool.split("__")
            if len(parts) >= 3:
                actions.append(f"{parts[1]}_*")
            continue
        mapped = TOOL_MAP.get(lowered)
        if mapped and mapped not in actions:
            actions.append(mapped)

    rules: list[tuple[str, str, str]] = [("*", "*", "deny")]
    for action in actions:
        rules.append((action, "*", "allow"))
    rules.append(("seo", "*", "allow"))
    rules.append(("skill", "seo*", "allow"))
    rules.append(("question", "*", "allow"))
    if "read" in actions:
        for resource, effect in ENV_RULES:
            rules.append(("read", resource, effect))
    return rules


def transform_agent(text: str, agent_name: str) -> str:
    frontmatter, body = split_frontmatter(text)
    values = parse_frontmatter(frontmatter or "")
    description = unquote(values.get("description", agent_name.replace("-", " ")))
    steps = values.get("maxTurns", "30").strip()
    if not steps.isdigit() or int(steps) <= 0:
        steps = "30"

    rules = permissions_for(tools_from_agent(values))
    lines = [
        "---",
        f"description: {yaml_quote(description)}",
        "mode: subagent",
        f"steps: {steps}",
        "permissions:",
    ]
    for action, resource, effect in rules:
        lines.extend(
            [
                f'  - action: "{action}"',
                f'    resource: "{resource}"',
                f"    effect: {effect}",
            ]
        )
    lines.append("---")
    body = transform_body(body, None, is_agent=True)
    return "\n".join(lines) + "\n" + body


def copy_transformed(source: Path, target: Path, current_skill: str | None = None, is_agent: bool = False) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.rglob("*")):
        if item.is_dir():
            continue
        if "__pycache__" in item.parts or item.name in {".DS_Store"}:
            continue
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if item.suffix.lower() == ".md":
            text = item.read_text(encoding="utf-8")
            transformed = (
                transform_agent(text, item.stem)
                if is_agent
                else transform_skill(text, current_skill or item.parent.name)
            )
            destination.write_text(transformed, encoding="utf-8", newline="\n")
        else:
            shutil.copy2(item, destination)


def generate_tree(base: Path) -> None:
    for name in ("skills", "agents", "commands", "plugins"):
        shutil.rmtree(base / name, ignore_errors=True)

    for skill in sorted(path for path in SKILL_SOURCE.iterdir() if path.is_dir()):
        copy_transformed(skill, base / "skills" / skill.name, current_skill=skill.name)

    (base / "agents").mkdir(parents=True, exist_ok=True)
    for agent in sorted(AGENT_SOURCE.glob("*.md")):
        target = base / "agents" / agent.name
        target.write_text(
            transform_agent(agent.read_text(encoding="utf-8"), agent.stem),
            encoding="utf-8",
            newline="\n",
        )

    if COMMAND_SOURCE.is_dir():
        shutil.copytree(COMMAND_SOURCE, base / "commands")

    if PLUGIN_SOURCE.is_dir():
        shutil.copytree(PLUGIN_SOURCE, base / "plugins" / "opencode-seo")

    (base / MARKER).write_text(
        "Generated by scripts/build_opencode.py. Do not edit by hand.\n",
        encoding="utf-8",
        newline="\n",
    )


def file_map(base: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for item in sorted(base.rglob("*")):
        if item.is_file():
            result[item.relative_to(base).as_posix()] = item.read_bytes()
    return result


def sync_tree(source: Path, target: Path) -> tuple[int, int]:
    """Copy changed files and remove stale files without deleting the whole tree.

    Deleting a watched skill directory makes OpenCode rescan every skill and can
    briefly hide all of them. Writing only changed files keeps the watcher quiet
    and preserves unchanged timestamps.
    """
    expected = file_map(source)
    actual = file_map(target) if target.is_dir() else {}
    written = 0
    removed = 0

    for relative, content in expected.items():
        destination = target / relative
        if actual.get(relative) == content:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.opencode-tmp")
        temporary.write_bytes(content)
        os.replace(temporary, destination)
        written += 1

    for relative in sorted(set(actual) - set(expected)):
        (target / relative).unlink(missing_ok=True)
        removed += 1

    for directory in sorted(
        (path for path in target.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass

    return written, removed


def check_tree() -> int:
    if not OPENCODE.is_dir():
        print("OpenCode target is missing. Run python scripts/build_opencode.py")
        return 1

    with tempfile.TemporaryDirectory(prefix="opencode-seo-") as temporary:
        generated = Path(temporary) / ".opencode"
        generate_tree(generated)
        expected = file_map(generated)
        actual = file_map(OPENCODE)

        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])

        if not missing and not extra and not changed:
            print("OpenCode target is up to date.")
            return 0

        for name in missing:
            print(f"missing: {name}")
        for name in extra:
            print(f"extra: {name}")
        for name in changed:
            print(f"changed: {name}")
        print("Run python scripts/build_opencode.py to refresh the OpenCode target.")
        return 1


def copy_install_root(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("scripts", "data", "schema"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, destination / name, dirs_exist_ok=True)
    for name in ("requirements.txt", "pyproject.toml"):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, destination / name)
    hooks = ROOT / "hooks"
    if hooks.is_dir():
        shutil.copytree(hooks, destination / "hooks", dirs_exist_ok=True)
    (destination / ".opencode-seo-root").write_text(
        "OpenCode SEO install root.\n", encoding="utf-8", newline="\n"
    )


def build_dist() -> None:
    dist = ROOT / "dist"
    opencode_dist = dist / "opencode"
    claude_dist = dist / "claude"
    generic_dist = dist / "generic"

    for target in (opencode_dist, claude_dist, generic_dist):
        shutil.rmtree(target, ignore_errors=True)

    opencode_dist.mkdir(parents=True, exist_ok=True)
    for name in ("skills", "agents", "commands", "plugins"):
        source = OPENCODE / name
        if source.is_dir():
            shutil.copytree(source, opencode_dist / name)
    for name in ("opencode.json", "AGENTS.md"):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, opencode_dist / name)
    copy_install_root(opencode_dist / "opencode-seo")

    claude_dist.mkdir(parents=True, exist_ok=True)
    for name in ("skills", "agents", "hooks", "scripts", "data", "schema"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, claude_dist / name)
    for name in ("requirements.txt", "pyproject.toml", "CLAUDE.md", "AGENTS.md"):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, claude_dist / name)

    generic_dist.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SKILL_SOURCE, generic_dist / "skills")
    shutil.copytree(AGENT_SOURCE, generic_dist / "agents")
    for name in ("AGENTS.md", "README.md"):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, generic_dist / name)

    print(f"Built install payloads in {dist}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the generated tree without writing")
    parser.add_argument("--dist", action="store_true", help="also build dist/ install payloads")
    args = parser.parse_args(argv)

    if args.check:
        status = check_tree()
        if status == 0 and args.dist:
            build_dist()
        return status

    with tempfile.TemporaryDirectory(prefix="opencode-seo-") as temporary:
        generated = Path(temporary) / ".opencode"
        generate_tree(generated)
        written, removed = sync_tree(generated, OPENCODE)

    print(f"Generated {OPENCODE} ({written} written, {removed} removed)")
    if args.dist:
        build_dist()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
