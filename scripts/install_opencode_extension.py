#!/usr/bin/env python3
"""Install an extension into the native OpenCode layout.

This is the OpenCode counterpart to extensions/<name>/install.sh. It copies the
extension skill and agent, rewrites Claude-only frontmatter and runtime calls,
and merges the MCP server into the OpenCode configuration.

Examples:
  python scripts/install_opencode_extension.py dataforseo --username me@example.com --password secret
  python scripts/install_opencode_extension.py firecrawl --key fc-...
  python scripts/install_opencode_extension.py matomo --url https://analytics.example.com --key token --site-id 1
  python scripts/install_opencode_extension.py banana --key google-ai-key
  python scripts/install_opencode_extension.py unlighthouse
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_opencode  # noqa: E402

EXTENSION_ROOT = ROOT / "extensions"

MCP_SERVERS: dict[str, dict[str, Any]] = {
    "dataforseo": {
        "type": "local",
        "command": ["npx", "-y", "dataforseo-mcp-server@2.8.10"],
        "environment": {
            "ENABLED_MODULES": "SERP,KEYWORDS_DATA,ONPAGE,DATAFORSEO_LABS,BACKLINKS,DOMAIN_ANALYTICS,BUSINESS_DATA,CONTENT_ANALYSIS,AI_OPTIMIZATION"
        },
        "codemode": False,
        "timeout": {"execution": 600000},
    },
    "firecrawl": {
        "type": "local",
        "command": ["npx", "-y", "firecrawl-mcp@3.11.0"],
        "environment": {},
        "codemode": False,
        "timeout": {"execution": 300000},
    },
    "ahrefs": {
        "type": "local",
        "command": ["npx", "--yes", "--package=@ahrefs/mcp@0.0.11", "mcp"],
        "environment": {},
        "codemode": False,
        "timeout": {"execution": 300000},
    },
    "banana": {
        "type": "local",
        "command": ["npx", "-y", "@ycse/nanobanana-mcp@1.1.1"],
        "environment": {},
        "codemode": False,
        "timeout": {"execution": 300000},
    },
}

CREDENTIAL_ENV = {
    "dataforseo": {"username": "DATAFORSEO_USERNAME", "password": "DATAFORSEO_PASSWORD"},
    "firecrawl": {"key": "FIRECRAWL_API_KEY"},
    "ahrefs": {"key": "AHREFS_API_TOKEN"},
    "banana": {"key": "GOOGLE_AI_API_KEY"},
}


def opencode_config_dir() -> Path:
    configured = os.environ.get("OPENCODE_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "opencode"


def strip_jsonc(text: str) -> str:
    """Remove comments and trailing commas while respecting strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escape = False
    line_comment = False
    block_comment = False

    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
                output.append(char)
            index += 1
            continue

        if block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue

        if in_string:
            output.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue

        if char == "/" and following == "/":
            line_comment = True
            index += 2
            continue

        if char == "/" and following == "*":
            block_comment = True
            index += 2
            continue

        output.append(char)
        index += 1

    cleaned = "".join(output)
    return re.sub(r",(\s*[}\]])", r"\1", cleaned)


def load_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"$schema": "https://opencode.ai/config.json"}
    raw = path.read_text(encoding="utf-8-sig")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = json.loads(strip_jsonc(raw))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_document(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f"{path.name}.bak")
        shutil.copy2(path, backup)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".opencode.", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
        if os.name == "nt":
            try:
                import subprocess

                identity = subprocess.run(
                    ["whoami"], capture_output=True, text=True, timeout=5
                ).stdout.strip()
                if identity:
                    subprocess.run(
                        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{identity}:F"],
                        capture_output=True,
                        check=False,
                        timeout=10,
                    )
            except Exception:
                pass
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def prompt_value(label: str, provided: str | None, secret: bool = False) -> str:
    if provided:
        return provided
    if not sys.stdin.isatty():
        raise SystemExit(f"{label} is required. Pass it as a command-line argument.")
    return getpass.getpass(f"{label}: ") if secret else input(f"{label}: ")


def transform_markdown(text: str, skill_name: str) -> str:
    text = build_opencode.transform_skill(text, skill_name)
    text = text.replace("${CLAUDE_SKILL_DIR}/references/", "references/")
    text = text.replace("${CLAUDE_SKILL_DIR}", "the skill directory")
    text = text.replace("~/.claude/settings.json", "the OpenCode SEO configuration")
    text = text.replace("~/.config/opencode/settings.json", "the OpenCode SEO configuration")
    text = text.replace("~/.claude.json", "the OpenCode configuration")
    return text


def install_skill(source: Path, target: Path, references: Path | None = None) -> None:
    skill_name = source.name
    for item in sorted(source.rglob("*")):
        if item.is_dir():
            continue
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if item.suffix.lower() == ".md":
            destination.write_text(
                transform_markdown(item.read_text(encoding="utf-8"), skill_name),
                encoding="utf-8",
                newline="\n",
            )
        else:
            shutil.copy2(item, destination)

    if references and references.is_dir():
        target_references = target / "references"
        shutil.copytree(references, target_references, dirs_exist_ok=True)


def install_agent(source: Path, target: Path) -> None:
    target.write_text(
        build_opencode.transform_agent(source.read_text(encoding="utf-8"), source.stem),
        encoding="utf-8",
        newline="\n",
    )


def merge_mcp(document: dict[str, Any], name: str, server: dict[str, Any]) -> None:
    mcp = document.setdefault("mcp", {})
    servers = mcp.setdefault("servers", {})
    servers[name] = server


def build_extension(name: str, args: argparse.Namespace) -> tuple[Path, dict[str, Any] | None, dict[str, str]]:
    source = EXTENSION_ROOT / name
    if not source.is_dir():
        raise SystemExit(f"Unknown extension: {name}")

    config_dir = opencode_config_dir()
    install_root = config_dir / "opencode-seo"
    skills_dir = config_dir / "skills"
    agents_dir = config_dir / "agents"
    installed_skills = sorted(path.parent for path in (source / "skills").glob("*/SKILL.md"))
    if not installed_skills:
        raise SystemExit(f"{name} has no skills to install")

    credentials: dict[str, str] = {}
    mapping = CREDENTIAL_ENV.get(name, {})
    if "username" in mapping:
        credentials[mapping["username"]] = prompt_value(
            "DataForSEO username (email)", args.username
        )
    if "password" in mapping:
        credentials[mapping["password"]] = prompt_value(
            "DataForSEO password", args.password, secret=True
        )
    if "key" in mapping:
        credentials[mapping["key"]] = prompt_value(f"{name} API key", args.key, secret=True)

    if name == "matomo":
        credentials["MATOMO_URL"] = prompt_value("Matomo URL", args.url)
        credentials["MATOMO_TOKEN"] = prompt_value("Matomo token_auth", args.key, secret=True)
        if args.site_id:
            credentials["MATOMO_SITE_ID"] = str(args.site_id)

    for pair in args.env or []:
        if "=" not in pair:
            raise SystemExit(f"--env must be KEY=VALUE, got {pair}")
        key, value = pair.split("=", 1)
        credentials[key] = value

    server: dict[str, Any] | None = None
    field_target: Path | None = None
    if name in MCP_SERVERS:
        server = json.loads(json.dumps(MCP_SERVERS[name]))
        server["environment"] = {**server.get("environment", {}), **credentials}
        if name == "dataforseo":
            field_source = source / "field-config.json"
            if field_source.is_file():
                field_target = install_root / "dataforseo-field-config.json"
                server["environment"]["FIELD_CONFIG_PATH"] = str(field_target)
    elif args.url and name != "matomo":
        # Matomo is a REST API consumed by matomo_report.py, not an MCP
        # server. Its --url is the analytics instance, not an MCP endpoint.
        server = {
            "type": "remote",
            "url": args.url,
            "headers": {key: f"{{env:{key}}}" for key in credentials},
        }

    if args.dry_run:
        return source, server, credentials

    if field_target and (source / "field-config.json").is_file():
        field_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "field-config.json", field_target)

    for skill in installed_skills:
        install_skill(skill, skills_dir / skill.name, source / "references")

    for agent in sorted((source / "agents").glob("*.md")):
        agents_dir.mkdir(parents=True, exist_ok=True)
        install_agent(agent, agents_dir / agent.name)

    scripts = source / "scripts"
    if scripts.is_dir():
        shutil.copytree(scripts, install_root / "extensions" / name / "scripts", dirs_exist_ok=True)

    if name == "matomo":
        # The extension installer runs outside the plugin. Point matomo_auth at
        # the OpenCode credential location explicitly instead of mutating the
        # process environment, which would leak into later work.
        import matomo_auth  # noqa: PLC0415

        matomo_auth.CONFIG_PATH = str(
            opencode_config_dir().with_name("opencode-seo") / "matomo.json"
        )
        matomo_auth.save_config(
            {
                "matomo_url": credentials.get("MATOMO_URL", ""),
                "matomo_token": credentials.get("MATOMO_TOKEN", ""),
                "matomo_site_id": credentials.get("MATOMO_SITE_ID", ""),
            }
        )

    if server:
        config_path = config_dir / "opencode.json"
        if not config_path.exists() and (config_dir / "opencode.jsonc").exists():
            config_path = config_dir / "opencode.jsonc"
        document = load_document(config_path)
        merge_mcp(document, name if name != "banana" else "nanobanana-mcp", server)
        write_document(config_path, document)

    return source, server, credentials


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extension", choices=sorted(path.name for path in EXTENSION_ROOT.iterdir() if path.is_dir()))
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--key")
    parser.add_argument("--url")
    parser.add_argument("--site-id")
    parser.add_argument("--env", action="append", metavar="KEY=VALUE")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    source, server, credentials = build_extension(args.extension, args)
    if args.dry_run:
        print(f"Would install {args.extension} from {source}")
        if server:
            preview = json.loads(json.dumps(server))
            environment = preview.get("environment", {})
            for key in environment:
                if key != "ENABLED_MODULES":
                    environment[key] = "***"
            print(f"Would configure MCP server: {json.dumps(preview, indent=2)}")
        return 0

    print(f"Installed {args.extension} into {opencode_config_dir()}")
    if server:
        print(f"Configured MCP server for {args.extension}. Verify with: opencode mcp list")
    else:
        print("No MCP server is defined for this extension. Skills and agents were installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
