# Install an extension into the native OpenCode layout.
# Usage: .\extensions\install-opencode.ps1 <extension> [options]
# Example: .\extensions\install-opencode.ps1 dataforseo --username me@example.com --password secret

$ErrorActionPreference = "Stop"

$Helper = Join-Path $PSScriptRoot "..\scripts\install_opencode_extension.py"
if (-not (Test-Path $Helper)) {
    Write-Error "OpenCode extension installer is missing. Reinstall OpenCode SEO."
    exit 2
}

& python $Helper @args
exit $LASTEXITCODE
