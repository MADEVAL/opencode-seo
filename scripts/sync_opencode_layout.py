#!/usr/bin/env python3
"""Developer wrapper around scripts/build_opencode.py.

Use `python scripts/sync_opencode_layout.py` to refresh `.opencode/`.
Use `python scripts/sync_opencode_layout.py --check` to verify it is current.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_opencode import main as build_main

    args = ["--check"] if "--check" in sys.argv[1:] else []
    if "--dist" in sys.argv[1:]:
        args.append("--dist")
    return build_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
