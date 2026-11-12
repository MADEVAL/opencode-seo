# Install OpenCode SEO into the native OpenCode config directory.
# Usage: .\install-opencode.ps1 [--skip-browser] [--no-setup] [--dry-run]

$ErrorActionPreference = "Stop"

$Installer = Join-Path $PSScriptRoot "scripts\install_opencode_package.py"
if (-not (Test-Path $Installer)) {
    Write-Error "OpenCode SEO installer is missing. Run this from the repository root."
    exit 2
}

& python $Installer @args
exit $LASTEXITCODE
