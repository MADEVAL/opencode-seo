#!/usr/bin/env python3
"""Install the generated OpenCode SEO package into the OpenCode config directory.

This is the OpenCode counterpart to the Claude installers. It copies the
generated `.opencode` target, the Python runtime, and the local plugin, then
optionally prepares the managed Python environment.

Examples:
  python scripts/install_opencode_package.py
  python scripts/install_opencode_package.py --skip-browser
  python scripts/install_opencode_package.py --no-setup
  python scripts/install_opencode_package.py --uninstall
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_opencode  # noqa: E402

SOURCE = ROOT / ".opencode"
MARKER = ".opencode-seo-root"


def config_dir() -> Path:
    configured = os.environ.get("OPENCODE_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "opencode"


def install_root(target: Path) -> Path:
    return target / "opencode-seo"


def check_source() -> None:
    if not (SOURCE / "skills").is_dir() or not (SOURCE / "agents").is_dir():
        raise SystemExit(
            "OpenCode target is missing. Run: python scripts/build_opencode.py"
        )


def install_package(
    target: Path,
    *,
    setup: bool = True,
    with_browser: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    check_source()
    skills = sorted(path for path in (SOURCE / "skills").glob("*") if (path / "SKILL.md").is_file())
    agents = sorted((SOURCE / "agents").glob("*.md"))
    commands = SOURCE / "commands"
    plugin = SOURCE / "plugins" / "opencode-seo"
    root = install_root(target)

    counts = {
        "skills": len(skills),
        "agents": len(agents),
        "commands": len(list(commands.rglob("*.md"))) if commands.is_dir() else 0,
        "plugins": 1 if plugin.is_dir() else 0,
    }
    if dry_run:
        return counts

    target.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        build_opencode.sync_tree(skill, target / "skills" / skill.name)

    for agent in agents:
        destination = target / "agents" / agent.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(agent, destination)

    if commands.is_dir():
        build_opencode.sync_tree(commands / "seo", target / "commands" / "seo")
        shutil.copy2(commands / "seo.md", target / "commands" / "seo.md")

    if plugin.is_dir():
        build_opencode.sync_tree(plugin, target / "plugins" / "opencode-seo")

    root.mkdir(parents=True, exist_ok=True)
    for name in ("scripts", "data", "schema", "hooks"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, root / name, dirs_exist_ok=True)
    for name in ("requirements.txt", "pyproject.toml", "package.json", "AGENTS.md"):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, root / name)
    (root / MARKER).write_text("OpenCode SEO install root.\n", encoding="utf-8", newline="\n")

    if setup:
        runtime = root / "scripts" / "runtime.py"
        command = [sys.executable, str(runtime), "setup"]
        if not with_browser:
            command.append("--skip-browser")
        result = subprocess.run(command, cwd=root, check=False)
        if result.returncode not in (0, 10):
            print("Runtime setup failed. Run the command above to see the error.", file=sys.stderr)
            return counts

    return counts


def uninstall_package(target: Path, *, dry_run: bool = False) -> None:
    check_source()
    paths: list[Path] = []
    for skill in (SOURCE / "skills").glob("*"):
        if (skill / "SKILL.md").is_file():
            paths.append(target / "skills" / skill.name)
    for agent in (SOURCE / "agents").glob("*.md"):
        paths.append(target / "agents" / agent.name)
    paths.extend(
        [
            target / "commands" / "seo",
            target / "commands" / "seo.md",
            target / "plugins" / "opencode-seo",
            install_root(target),
        ]
    )

    for path in paths:
        if dry_run:
            print(path)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", help="Override the OpenCode config directory")
    parser.add_argument("--no-setup", action="store_true", help="Skip Python runtime setup")
    parser.add_argument("--with-browser", action="store_true", help="Install Chromium during setup")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    target = Path(args.config_dir).expanduser() if args.config_dir else config_dir()
    if args.uninstall:
        uninstall_package(target, dry_run=args.dry_run)
        print(f"Removed OpenCode SEO from {target}")
        return 0

    counts = install_package(
        target,
        setup=not args.no_setup,
        with_browser=args.with_browser,
        dry_run=args.dry_run,
    )
    print(f"{'Would install' if args.dry_run else 'Installed'} OpenCode SEO into {target}")
    print(f"  skills: {counts['skills']}")
    print(f"  agents: {counts['agents']}")
    print(f"  commands: {counts['commands']}")
    print("Verify with: opencode plugin list; opencode debug agents; opencode mcp list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
