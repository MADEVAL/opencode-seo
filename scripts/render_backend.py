#!/usr/bin/env python3
"""Resolve the browser backend used for rendered-page work.

This module is deliberately standard-library only until a backend actually
starts. Managed and system browsers go through Playwright; the channel backend
lets Playwright find an installed Chrome or Edge; the CLI backend drives a
browser binary with ``--dump-dom``; and ``static`` means no renderer at all.

Selection order for ``auto`` (the default) is:

    managed -> system -> channel -> cli -> static

``managed`` is the Chromium copy installed under the OpenCode SEO data
directory (the old 150 MB download). ``system`` is any Chromium already in
Playwright's normal cache. ``channel`` launches the Chrome or Edge the user
already has, with no download. ``cli`` is the last resort when Playwright is
not installed at all: it returns the DOM but loses the accessibility tree and
console errors. ``static`` keeps the raw HTML fetch.

The request can come from ``--backend`` or the ``OPENCODE_SEO_RENDER``
environment variable. ``python render_backend.py --probe --json`` reports the
backend that really launches, which is what ``runtime.py doctor`` publishes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

BACKENDS = ("auto", "managed", "system", "channel", "cli", "static")
PLAYWRIGHT_BACKENDS = frozenset({"managed", "system", "channel"})
ENV_VAR = "OPENCODE_SEO_RENDER"
CHANNELS = ("chrome", "msedge")

# Full Chromium is preferred over the headless shell because the full build
# exposes the accessibility tree on every platform.
_CHROMIUM_PATTERNS = (
    "chromium-*/chrome-win/chrome.exe",
    "chromium-*/chrome-win64/chrome.exe",
    "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
    "chromium-*/chrome-linux*/chrome",
    "chromium_headless_shell-*/chrome-win/headless_shell.exe",
    "chromium_headless_shell-*/chrome-mac*/headless_shell",
    "chromium_headless_shell-*/chrome-linux*/headless_shell",
)


def normalize_backend(value: Optional[str] = None) -> str:
    """Return a valid backend name from an argument, the environment, or auto."""
    raw = (value or os.environ.get(ENV_VAR) or "auto").strip().lower()
    if raw not in BACKENDS:
        raise ValueError(
            f"invalid render backend {raw!r}; choose from {', '.join(BACKENDS)}"
        )
    return raw


def playwright_available() -> bool:
    try:
        return importlib.util.find_spec("playwright") is not None
    except (ImportError, ValueError):
        return False


def managed_browsers_dir() -> Optional[Path]:
    raw = os.environ.get("OPENCODE_SEO_BROWSERS_PATH")
    if raw:
        return Path(raw).expanduser()
    data_dir = (
        os.environ.get("OPENCODE_SEO_DATA_DIR")
        or os.environ.get("CLAUDE_SEO_DATA_DIR")
        or os.environ.get("CLAUDE_PLUGIN_DATA")
    )
    if data_dir:
        return Path(data_dir).expanduser() / "ms-playwright"
    return None


def system_browsers_dir() -> Path:
    """Playwright's default browser cache, which the managed copy shadows."""
    if sys.platform == "win32":
        base = Path(
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        )
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "ms-playwright"


def _revision(path: Path) -> tuple[int, str]:
    """Sort browser executables by the revision in their browser directory."""
    name = next(
        (
            part
            for part in path.parts
            if part.startswith(("chromium-", "chromium_headless_shell-"))
        ),
        path.name,
    )
    digits = "".join(ch for ch in name.split("-")[-1] if ch.isdigit())
    return (int(digits) if digits else 0, str(path))


def find_chromium(root: Optional[Path]) -> Optional[Path]:
    """Return the newest Chromium executable under ``root``, or None."""
    if root is None:
        return None
    try:
        for pattern in _CHROMIUM_PATTERNS:
            for candidate in sorted(root.glob(pattern), key=_revision, reverse=True):
                if candidate.is_file():
                    return candidate
    except OSError:
        return None
    return None


def has_chromium(root: Optional[Path]) -> bool:
    return find_chromium(root) is not None


def _browser_executables() -> dict[str, str]:
    """Locate installed Chrome and Edge binaries for the channel and CLI layers."""
    found: dict[str, str] = {}
    if sys.platform == "win32":
        roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        relative = {
            "chrome": ("Google\\Chrome\\Application\\chrome.exe",),
            "msedge": ("Microsoft\\Edge\\Application\\msedge.exe",),
        }
        for channel, names in relative.items():
            for root in roots:
                if not root:
                    continue
                for name in names:
                    candidate = Path(root) / name
                    if candidate.is_file():
                        found.setdefault(channel, str(candidate))
                        break
                if channel in found:
                    break
        return found

    if sys.platform == "darwin":
        relative = {
            "chrome": (
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ),
            "msedge": (
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ),
        }
        for channel, names in relative.items():
            for name in names:
                if Path(name).is_file():
                    found[channel] = name
                    break
        return found

    names = {
        "chrome": (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        ),
        "msedge": ("microsoft-edge", "microsoft-edge-stable"),
    }
    for channel, commands in names.items():
        for command in commands:
            executable = shutil.which(command)
            if executable:
                found[channel] = executable
                break
    return found


def channel_candidates() -> tuple[str, ...]:
    installed = _browser_executables()
    return tuple(channel for channel in CHANNELS if channel in installed)


def cli_executable() -> Optional[str]:
    installed = _browser_executables()
    return installed.get("chrome") or installed.get("msedge")


def availability(
    *, playwright: Optional[bool] = None, managed: Optional[Path] = None
) -> dict[str, bool]:
    """Cheap, non-launching availability check for every backend."""
    playwright_ok = playwright_available() if playwright is None else bool(playwright)
    managed_root = managed_browsers_dir() if managed is None else managed
    return {
        "managed": bool(playwright_ok and has_chromium(managed_root)),
        "system": bool(playwright_ok and has_chromium(system_browsers_dir())),
        "channel": bool(playwright_ok and channel_candidates()),
        "cli": cli_executable() is not None,
        "static": True,
    }


def plan_backends(
    requested: Optional[str] = None,
    available: Optional[dict[str, bool]] = None,
) -> list[str]:
    """Return the backend order to try for ``requested``."""
    requested = normalize_backend(requested)
    if available is None:
        available = availability()
    if requested != "auto":
        return [requested]

    plan: list[str] = []
    for backend in ("managed", "system", "channel", "cli"):
        if available.get(backend):
            plan.append(backend)
    plan.append("static")
    return plan


def choose_backend(
    requested: Optional[str] = None,
    available: Optional[dict[str, bool]] = None,
) -> str:
    return plan_backends(requested, available)[0]


def launch_playwright(playwright: Any, backend: str, *, headless: bool = True) -> Any:
    """Launch Chromium through Playwright for one backend.

    Executable paths are passed explicitly for managed and system browsers so
    an older or newer Playwright revision does not have to match the browser
    revision exactly. The channel backend lets Playwright resolve Chrome or
    Edge itself.
    """
    if backend == "managed":
        executable = find_chromium(managed_browsers_dir())
        if executable is None:
            raise RuntimeError(
                "managed Chromium is not installed; run setup with --with-browser"
            )
        return playwright.chromium.launch(
            headless=headless, executable_path=str(executable)
        )

    if backend == "system":
        executable = find_chromium(system_browsers_dir())
        if executable is not None:
            return playwright.chromium.launch(
                headless=headless, executable_path=str(executable)
            )
        # No cache directory we recognise: let Playwright use its own default.
        return playwright.chromium.launch(headless=headless)

    if backend == "channel":
        errors: list[str] = []
        for channel in channel_candidates():
            try:
                return playwright.chromium.launch(headless=headless, channel=channel)
            except Exception as exc:  # noqa: BLE001 - try the next installed channel
                errors.append(f"{channel}: {type(exc).__name__}: {exc}")
        detail = "; ".join(errors) if errors else "no Chrome or Edge installation found"
        raise RuntimeError(f"channel backend unavailable: {detail}")

    raise ValueError(f"{backend!r} is not a Playwright backend")


def run_cli_render(
    url: str, *, timeout_ms: int = 15000, executable: Optional[str] = None
) -> str:
    """Render ``url`` with ``chrome --headless=new --dump-dom``."""
    browser = executable or cli_executable()
    if not browser:
        raise RuntimeError("Chrome or Edge is not installed")

    budget = max(1000, min(int(timeout_ms), 30000))
    profile = tempfile.mkdtemp(prefix="opencode-seo-chrome-")
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        f"--user-data-dir={profile}",
        f"--virtual-time-budget={budget}",
        "--dump-dom",
        url,
    ]
    if os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0:
        command.insert(1, "--no-sandbox")

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(30.0, budget / 1000.0 + 15.0),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Chrome CLI timed out after {budget}ms") from exc
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if completed.returncode:
        detail = " ".join(
            line.strip()
            for line in (completed.stderr or completed.stdout).splitlines()
            if line.strip()
        )[:300]
        raise RuntimeError(
            f"Chrome CLI exited with {completed.returncode}"
            + (f": {detail}" if detail else "")
        )
    dom = completed.stdout
    if not dom.strip():
        raise RuntimeError("Chrome CLI returned an empty DOM")
    return dom


def probe(requested: Optional[str] = None) -> dict[str, Any]:
    """Launch each candidate in order and report the first backend that works."""
    requested = normalize_backend(requested)
    available = availability()
    plan = plan_backends(requested, available)

    for backend in plan:
        if backend in PLAYWRIGHT_BACKENDS:
            if not playwright_available():
                continue
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = launch_playwright(playwright, backend)
                    browser.close()
                return _probe_result(backend, requested, available)
            except Exception:
                continue
        elif backend == "cli":
            executable = cli_executable()
            if not executable:
                continue
            try:
                completed = subprocess.run(
                    [executable, "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if completed.returncode == 0:
                return _probe_result(backend, requested, available)

    return _probe_result("static", requested, available)


def _probe_result(
    backend: str, requested: str, available: dict[str, bool]
) -> dict[str, Any]:
    return {
        "backend": backend,
        "requested": requested,
        "degraded": backend in ("cli", "static"),
        "available": {
            key: bool(available.get(key))
            for key in ("managed", "system", "channel", "cli", "static")
        },
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve the OpenCode SEO render backend (managed, system, channel, cli, static)."
    )
    parser.add_argument("--backend", choices=BACKENDS, help="force one backend")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="launch each candidate and report the first backend that works",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    try:
        requested = normalize_backend(args.backend)
    except ValueError as exc:
        parser.error(str(exc))
    if args.probe:
        payload = probe(requested)
    else:
        available = availability()
        backend = choose_backend(requested, available)
        payload = _probe_result(backend, requested, available)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Render backend: {payload['backend']}")
        print(f"Requested: {payload['requested']}")
        print(f"Degraded: {'yes' if payload['degraded'] else 'no'}")
        for name, ready in payload["available"].items():
            print(f"  {name}: {'available' if ready else 'unavailable'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
