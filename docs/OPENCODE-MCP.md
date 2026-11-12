# OpenCode MCP and extension installation

OpenCode reads MCP servers from `mcp.servers` in `opencode.json(c)`. The generic
installer copies an extension skill and agent into the native OpenCode layout and
merges its MCP server into that file.

## Install

Unix:

```bash
./extensions/install-opencode.sh dataforseo --username me@example.com --password secret
./extensions/install-opencode.sh firecrawl --key fc-...
./extensions/install-opencode.sh ahrefs --key ahrefs-token
./extensions/install-opencode.sh banana --key google-ai-key
./extensions/install-opencode.sh matomo --url https://analytics.example.com --key token --site-id 1
./extensions/install-opencode.sh unlighthouse
```

Windows:

```powershell
.\extensions\install-opencode.ps1 dataforseo --username me@example.com --password secret
.\extensions\install-opencode.ps1 firecrawl --key fc-...
```

Other extensions install their skills and agents the same way:

```bash
./extensions/install-opencode.sh profound
./extensions/install-opencode.sh seranking
./extensions/install-opencode.sh bing-webmaster
```

Use `--dry-run` to preview the files and MCP block without writing anything:

```bash
./extensions/install-opencode.sh dataforseo --username me@example.com --password secret --dry-run
```

## What is written

```text
~/.config/opencode/
  opencode.json                     # mcp.servers.<name>
  skills/<skill>/SKILL.md           # transformed for OpenCode
  skills/<skill>/references/
  agents/<agent>.md                 # mode: subagent, permissions, steps
  opencode-seo/
    dataforseo-field-config.json    # DataForSEO only
    extensions/<name>/scripts/      # extension scripts, when present
```

Set `OPENCODE_CONFIG_DIR` to install into a different directory, for example in
tests or a portable setup.

## MCP servers

| Extension | Server name | Type | Notes |
|---|---|---|---|
| dataforseo | `dataforseo` | local | `npx dataforseo-mcp-server@2.8.10`, `codemode: false` |
| firecrawl | `firecrawl` | local | `firecrawl-mcp@3.11.0`, `codemode: false` |
| ahrefs | `ahrefs` | local | `@ahrefs/mcp@0.0.11`, `codemode: false` |
| banana | `nanobanana-mcp` | local | `@ycse/nanobanana-mcp@1.1.1`, `codemode: false` |
| matomo | none | - | credentials saved by `matomo_auth.py` |
| bing-webmaster | none | - | API key setup remains in the extension flow |
| profound | none | - | configure the vendor MCP server or REST access |
| seranking | none | - | configure the vendor MCP server or REST access |
| unlighthouse | none | - | local runner, no MCP |

For known servers the installer sets `codemode: false` so tools keep direct
names such as `dataforseo_serp_organic_live_advanced`. Permissions can then use
`{ "action": "dataforseo_*", "resource": "*", "effect": "allow" }`.

## Configuration safety

- Existing `opencode.json` or `opencode.jsonc` is read, and a `.bak` copy is made
  before writing.
- JSONC comments and trailing commas are accepted when reading. The rewritten
  file is plain JSON, so comments are removed.
- The file is written atomically with mode 0600 on POSIX and a current-user ACL on
  Windows.
- Credentials are written to the server environment, never to argv or logs.
- `--dry-run` masks environment values.

## Verify

```bash
opencode mcp list
opencode debug config
```

Then ask OpenCode to load the extension skill or run the matching `/seo` command.

## Claude Code

The original `extensions/<name>/install.sh` and `install.ps1` stay unchanged for
Claude Code. Use the OpenCode wrapper when you want the native OpenCode layout.
