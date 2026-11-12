#!/usr/bin/env bash
set -euo pipefail

# Install OpenCode SEO into the native OpenCode config directory.
# Usage: ./install-opencode.sh [--skip-browser] [--no-setup] [--dry-run]

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
installer="${script_dir}/scripts/install_opencode_package.py"

if [[ ! -f "${installer}" ]]; then
    echo "OpenCode SEO installer is missing. Run this from the repository root." >&2
    exit 2
fi

exec python3 "${installer}" "$@"
