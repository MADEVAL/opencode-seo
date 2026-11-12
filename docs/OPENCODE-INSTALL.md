# Install OpenCode SEO

OpenCode SEO installs into the native OpenCode config directory and leaves Claude
Code and other harnesses untouched.

## Requirements

- OpenCode V2.
- Python 3.11 to 3.14.
- Node.js 20+ only when you install an MCP extension.
- Git only when you clone the repository.

## Install from the repository

Unix:

```bash
./install-opencode.sh
```

Windows PowerShell:

```powershell
.\install-opencode.ps1
```

The installer copies:

```text
~/.config/opencode/
  skills/                  # 26 OpenCode skills
  agents/                  # 19 OpenCode agents
  commands/                # /seo and /seo/<sub>
  plugins/opencode-seo/    # local plugin with the seo tool and schema hook
  opencode-seo/            # Python runtime, scripts, data, schema, hooks
```

It also runs the managed Python setup with `--skip-browser` by default. Use
`--with-browser` to install Chromium, or `--no-setup` to skip Python setup.

Set `OPENCODE_CONFIG_DIR` to install somewhere else:

```bash
OPENCODE_CONFIG_DIR=/opt/opencode ./install-opencode.sh --no-setup
```

## Use

```text
/seo
/seo/audit https://example.com
/seo/page https://example.com
@seo
```

OpenCode credentials live in `~/.config/opencode-seo/` and caches in
`~/.cache/opencode-seo/`. The first run reads a matching file from
`~/.config/claude-seo/` if the OpenCode copy is missing, so upgrading does not
lose Google, Matomo, Moz, Bing, or Common Crawl credentials.

The `seo` tool is available to agents as:

```json
{ "action": "run", "script": "page_checks.py", "args": ["--url", "https://example.com"] }
```

## Verify

```bash
opencode plugin list
opencode debug agents
opencode mcp list
```

Expected:

- `opencode-seo` in `opencode plugin list`;
- 19 `seo-*` agents in `opencode debug agents`;
- 26 skills under `~/.config/opencode/skills`;
- `/seo` and `/seo/audit` in the command list.

If `seo` reports that setup is required:

```text
/seo setup
```

or run:

```bash
python ~/.config/opencode/opencode-seo/scripts/runtime.py setup
```

## Optional configuration

The plugin, skills, agents, and commands are discovered automatically. Add
project or global settings only when you need to override defaults:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "experimental": { "subagent_depth": 1 },
  "permissions": [
    { "action": "skill", "resource": "seo*", "effect": "allow" },
    { "action": "subagent", "resource": "seo-*", "effect": "allow" },
    { "action": "seo", "resource": "*", "effect": "allow" }
  ]
}
```

Do not add `skills: ["./skills"]` to a repository that also keeps the canonical
Claude skills. An explicit source outranks `.opencode/skills` and would load the
Claude variants into OpenCode.

## Extensions

See [OPENCODE-MCP.md](OPENCODE-MCP.md):

```bash
./extensions/install-opencode.sh dataforseo --username me@example.com --password secret
./extensions/install-opencode.sh firecrawl --key fc-...
```

## Uninstall

```bash
python scripts/install_opencode_package.py --uninstall
```

This removes only the skills, agents, commands, plugin, and runtime installed by
OpenCode SEO. It does not delete unrelated user skills or the OpenCode config.

## Other harnesses

Claude Code, Cursor, Codex, Cline, Aider, and Antigravity keep using the original
`CLAUDE.md`, `AGENTS.md`, `skills/`, `agents/`, and `hooks/` layout.
