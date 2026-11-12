#!/usr/bin/env bash
set -euo pipefail

# Install an extension into the native OpenCode layout.
# Usage: ./extensions/install-opencode.sh <extension> [options]
# Example: ./extensions/install-opencode.sh dataforseo --username me@example.com --password secret

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
helper="${script_dir}/../scripts/install_opencode_extension.py"

if [[ ! -f "${helper}" ]]; then
    echo "OpenCode extension installer is missing. Reinstall OpenCode SEO." >&2
    exit 2
fi

exec python3 "${helper}" "$@"
