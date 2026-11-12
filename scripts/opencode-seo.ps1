# OpenCode SEO launcher for Windows PowerShell.
# The canonical Python runtime lives beside this file as runtime.py.

$ErrorActionPreference = "Stop"

$Runtime = Join-Path $PSScriptRoot "runtime.py"
if (-not (Test-Path $Runtime)) {
    Write-Error "OpenCode SEO runtime is missing. Reinstall OpenCode SEO."
    exit 2
}

$Python = $env:OPENCODE_SEO_PYTHON
if ([string]::IsNullOrEmpty($Python)) { $Python = $env:CLAUDE_SEO_PYTHON }

if (-not [string]::IsNullOrEmpty($Python)) {
    & $Python $Runtime @args
    exit $LASTEXITCODE
}

$PyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($null -ne $PyLauncher) {
    & py -3 $Runtime @args
    exit $LASTEXITCODE
}

$Python3 = Get-Command python3 -ErrorAction SilentlyContinue
if ($null -ne $Python3) {
    & python3 $Runtime @args
    exit $LASTEXITCODE
}

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $PythonCmd) {
    & python $Runtime @args
    exit $LASTEXITCODE
}

Write-Error "OpenCode SEO needs Python 3.11-3.14. Install Python or set OPENCODE_SEO_PYTHON."
exit 2
