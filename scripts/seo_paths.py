#!/usr/bin/env python3
"""Resolve OpenCode SEO config and cache locations.

OpenCode installs use ``~/.config/opencode-seo`` and ``~/.cache/opencode-seo``.
Claude installs keep ``~/.config/claude-seo`` and ``~/.cache/claude-seo`` so
existing credentials and drift baselines continue to work. Set
``OPENCODE_SEO_CONFIG_DIR`` or ``OPENCODE_SEO_CACHE_DIR`` (or the legacy
``CLAUDE_SEO_*`` names) to override either location explicitly.
"""

from __future__ import annotations

import os
from pathlib import Path


def _home() -> Path:
    return Path.home()


def _from_env(name: str) -> Path | None:
    raw = os.environ.get(name)
    if raw:
        return Path(raw).expanduser()
    return None


def _is_opencode() -> bool:
    if any(
        os.environ.get(name)
        for name in (
            "OPENCODE_SEO_ROOT",
            "OPENCODE_SEO_CONFIG_DIR",
            "OPENCODE_SEO_CACHE_DIR",
        )
    ):
        return True
    root = Path(__file__).resolve().parent.parent
    return (root / ".opencode-seo-root").is_file()


def config_dir() -> Path:
    """Return the active config directory."""
    override = _from_env("OPENCODE_SEO_CONFIG_DIR") or _from_env("CLAUDE_SEO_CONFIG_DIR")
    if override is not None:
        return override
    if _is_opencode():
        return _home() / ".config" / "opencode-seo"
    return _home() / ".config" / "claude-seo"


def cache_dir() -> Path:
    """Return the active cache directory."""
    override = _from_env("OPENCODE_SEO_CACHE_DIR") or _from_env("CLAUDE_SEO_CACHE_DIR")
    if override is not None:
        return override
    if _is_opencode():
        return _home() / ".cache" / "opencode-seo"
    return _home() / ".cache" / "claude-seo"


def config_file(name: str) -> Path:
    """Return a config file, falling back to the Claude install on first run.

    OpenCode reads the new path first. If the new file is absent but the
    legacy Claude file exists, the legacy file is used so credentials do not
    disappear after an upgrade. Writes then stay in the location returned here.
    """
    active = config_dir() / name
    if active.exists() or not _is_opencode():
        return active
    legacy = _home() / ".config" / "claude-seo" / name
    if legacy.exists():
        return legacy
    return active


def cache_file(name: str) -> Path:
    """Return a cache path, falling back to the Claude install on first run."""
    active = cache_dir() / name
    if active.exists() or not _is_opencode():
        return active
    legacy = _home() / ".cache" / "claude-seo" / name
    if legacy.exists():
        return legacy
    return active
