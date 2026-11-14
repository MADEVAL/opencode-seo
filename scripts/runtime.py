#!/usr/bin/env python3
"""Cross-platform runtime for OpenCode SEO's bundled Python scripts.

This module deliberately uses only the Python standard library. It is launched
by the sibling ``scripts/claude-seo`` launcher under a base Python, then
dispatches work through the managed virtual environment created by ``setup``.
Skills, agents, and hooks invoke that launcher as
``"${CLAUDE_PLUGIN_ROOT}/scripts/claude-seo"``; the repository keeps no
top-level ``bin/`` directory because hosted marketplaces reject one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# The runtime imports sibling modules before dispatching a script. Keep the
# install root free of __pycache__ even when the caller did not set
# PYTHONDONTWRITEBYTECODE (the OpenCode plugin does set it as well).
sys.dont_write_bytecode = True

RUNTIME_SCHEMA = 1
# Supported interpreter range. scripts/claude-seo and install.ps1 repeat these
# bounds, and tests/test_python_range.py keeps every copy in step. 3.15 waits
# on google-ads, whose wheels declare Python < 3.15.
MIN_PYTHON = (3, 11)
MAX_PYTHON = (3, 14)
LOCK_STALE_SECONDS = 30 * 60
# Kept in sync with pyproject.toml [project.optional-dependencies] render.
PLAYWRIGHT_REQUIREMENT = "playwright>=1.63.0,<2.0.0"
SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*\.py$")
EXTENSION_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MANUAL_EXTENSION_SKILLS = {"banana": "seo-image-gen"}
ALLOWED_CORE_SCRIPTS = frozenset(
    {
        "agent_ux_check.py", "agentic_check.py", "agentic_fix.py", "analyze_visual.py", "backlinks_auth.py",
        "bing_webmaster.py", "capture_screenshot.py", "commoncrawl_graph.py",
        "content_humanize.py", "content_quality.py", "content_verify.py",
        "crux_history.py", "dataforseo_costs.py", "dataforseo_merchant.py",
        "dataforseo_normalize.py", "domain_history.py", "drift_baseline.py",
        "drift_compare.py", "drift_history.py", "drift_report.py", "fetch_page.py",
        "ga4_report.py", "gbp_deprecation_lint.py", "google_auth.py",
        "google_report.py", "gsc_inspect.py", "gsc_query.py", "indexing_notify.py",
        "indexnow_submit.py", "iptc_ai_label.py", "keyword_planner.py",
        "keywordseverywhere_api.py",
        "lcp_subparts.py", "lighthouse_agentic.py", "matomo_auth.py", "matomo_report.py", "metadata_template.py",
        "moz_api.py", "nlp_analyze.py", "page_checks.py", "pagespeed_check.py",
        "parasite_risk.py", "parse_html.py", "preload_check.py", "render_page.py",
        "render_backend.py",
        "portability_check.py", "consistency_check.py",
        "schema_ecommerce_validate.py", "schema_generate.py", "seo_updates.py",
        "sitemap_discovery.py", "sync_flow.py", "transport_check.py", "ucp_check.py",
        "unlighthouse_run.py",
        "url_safety.py", "validate_backlink_report.py", "verify_backlinks.py",
        "youtube_search.py",
    }
)
REDACTIONS = (
    (re.compile(r"(?i)(https?://[^\s:/]+:)[^@\s]+@"), r"\1<redacted>@"),
    (re.compile(r"(?i)(https?://[^\s?]+\?)[^\s]+"), r"\1<redacted>"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<redacted-email>"),
    (re.compile(r"(?i)(token|password|secret|api[_-]?key)([=:\s]+)[^\s]+"), r"\1\2<redacted>"),
)


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _product() -> str:
    if os.environ.get("OPENCODE_SEO_ROOT"):
        return "OpenCode SEO"
    root = Path(__file__).resolve().parent.parent
    if (root / ".opencode-seo-root").is_file():
        return "OpenCode SEO"
    return "Claude SEO"


def _python_env_name() -> str:
    return "OPENCODE_SEO_PYTHON" if _product() == "OpenCode SEO" else "CLAUDE_SEO_PYTHON"


def _plugin_version(root: Path) -> str:
    for manifest in (
        root / "package.json",
        root / ".claude-plugin" / "plugin.json",
        root / "runtime-plugin.json",
    ):
        try:
            value = json.loads(manifest.read_text(encoding="utf-8")).get("version")
            if isinstance(value, str):
                return value
        except (OSError, ValueError):
            pass
    metadata = root / "pyproject.toml"
    try:
        match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', metadata.read_text(encoding="utf-8"))
        if match:
            return match.group(1)
    except OSError:
        pass
    return "unknown"


def _requirements_hash(root: Path) -> str:
    try:
        content = (root / "requirements.txt").read_bytes()
    except OSError:
        return "missing"
    return hashlib.sha256(content).hexdigest()


def _is_plugin(root: Path) -> bool:
    if (
        os.environ.get("OPENCODE_SEO_ROOT")
        or os.environ.get("OPENCODE_SEO_DATA_DIR")
        or os.environ.get("CLAUDE_PLUGIN_DATA")
        or os.environ.get("CLAUDE_PLUGIN_ROOT")
    ):
        return True
    if (root / ".opencode-seo-root").is_file():
        return True
    return (root / ".claude-plugin" / "plugin.json").is_file() and not (root / ".git").exists()


def _configured_data_dir(raw: str) -> Path:
    """Resolve a configured data directory and reject destructive broad roots."""
    candidate = Path(raw).expanduser().resolve()
    filesystem_root = Path(candidate.anchor).resolve()
    try:
        user_home = Path.home().resolve()
    except RuntimeError:
        user_home = None
    if candidate == filesystem_root or candidate == user_home:
        raise ValueError("runtime data directory must be a dedicated subdirectory")
    return candidate


def _data_dir(root: Path) -> tuple[Path, str]:
    override = os.environ.get("OPENCODE_SEO_DATA_DIR") or os.environ.get("CLAUDE_SEO_DATA_DIR")
    if override:
        return _configured_data_dir(override), "override"
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        return _configured_data_dir(plugin_data), "plugin"
    if _is_plugin(root):
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        name = "opencode-seo" if (root / ".opencode-seo-root").is_file() else "claude-seo"
        return (base / name).resolve(), "plugin-fallback"
    return root, "manual"


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _state_path(data_dir: Path) -> Path:
    return data_dir / "runtime-state.json"


def _load_state(data_dir: Path) -> dict[str, Any]:
    try:
        value = json.loads(_state_path(data_dir).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _expected(root: Path) -> dict[str, Any]:
    return {
        "runtime_schema": RUNTIME_SCHEMA,
        "plugin_version": _plugin_version(root),
        "requirements_sha256": _requirements_hash(root),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def _python_supported() -> bool:
    return MIN_PYTHON <= sys.version_info[:2] <= MAX_PYTHON


def _python_range_message() -> str:
    found = f"{sys.version_info.major}.{sys.version_info.minor}"
    return (
        f"{_product()} needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} to "
        f"{MAX_PYTHON[0]}.{MAX_PYTHON[1]}. Found {found} ({sys.executable}). "
        f"Install a supported Python or set {_python_env_name()}."
    )


def _venv_has_package(venv: Path, name: str) -> bool:
    """Cheap check for an installed distribution inside the managed venv."""
    try:
        candidates = list(venv.glob("Lib/site-packages")) + list(
            venv.glob("lib/python*/site-packages")
        )
    except OSError:
        return False
    return any((path / name).is_dir() for path in candidates)


def _render_status(status: dict[str, Any]) -> dict[str, Any]:
    """Resolve the render backend without launching a browser."""
    try:
        import render_backend
    except (ImportError, OSError):
        return {
            "backend": "static",
            "degraded": True,
            "available": {"static": True},
        }
    available = render_backend.availability(
        playwright=_venv_has_package(status["venv"], "playwright"),
        managed=status["data_dir"] / "ms-playwright",
    )
    backend = render_backend.choose_backend("auto", available)
    return {
        "backend": backend,
        "degraded": backend in ("cli", "static"),
        "available": available,
    }


def _probe_render(status: dict[str, Any]) -> dict[str, Any]:
    """Run the probing version under the managed interpreter, falling back cheaply."""
    python = status["python_path"]
    script = Path(__file__).resolve().parent / "render_backend.py"
    if not python.is_file() or not script.is_file():
        return _render_status(status)
    try:
        result = subprocess.run(
            [str(python), str(script), "--probe", "--json"],
            env=_safe_env(status),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError):
        return _render_status(status)
    if result.returncode:
        return _render_status(status)
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return _render_status(status)
    backend = payload.get("backend")
    if backend not in ("managed", "system", "channel", "cli", "static"):
        return _render_status(status)
    return {
        "backend": backend,
        "degraded": bool(payload.get("degraded")),
        "available": payload.get("available") if isinstance(payload.get("available"), dict) else {},
    }


def _status(root: Path) -> dict[str, Any]:
    data_dir, mode = _data_dir(root)
    venv = data_dir / ".venv"
    python = _venv_python(venv)
    state = _load_state(data_dir)
    expected = _expected(root)
    reasons: list[str] = []
    if not _python_supported():
        reasons.append(f"python {expected['python']} is outside the supported range")
    if not python.is_file():
        reasons.append("managed environment is missing")
    for key in ("runtime_schema", "requirements_sha256", "python"):
        if state.get(key) != expected[key]:
            reasons.append(f"{key} changed")
    render = _render_status(
        {"data_dir": data_dir, "venv": venv, "python_path": python}
    )
    return {
        "ready": not reasons,
        "mode": mode,
        "python_version": expected["python"],
        "plugin_version": expected["plugin_version"],
        "browser_ready": render["backend"] != "static",
        "render_backend": render["backend"],
        "degraded": render["degraded"],
        "reasons": reasons,
        "data_dir": data_dir,
        "venv": venv,
        "python_path": python,
        "state": state,
        "expected": expected,
    }


def _safe_env(status: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    managed = status["data_dir"] / "ms-playwright"
    env["OPENCODE_SEO_BROWSERS_PATH"] = str(managed)

    # An empty managed directory must not shadow Playwright's normal cache or a
    # path the caller configured. Keep a working caller value; otherwise unset
    # the variable so Playwright falls back to the system browser cache.
    try:
        import render_backend

        has_managed = render_backend.has_chromium(managed)
        existing = env.get("PLAYWRIGHT_BROWSERS_PATH")
        has_existing = bool(existing) and render_backend.has_chromium(Path(existing))
    except (ImportError, OSError):
        has_managed = False
        has_existing = False
    if has_managed:
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(managed)
    elif not has_existing:
        env.pop("PLAYWRIGHT_BROWSERS_PATH", None)
    return env


def _home_pattern(home: str) -> re.Pattern[str]:
    # Child output quotes paths in repr form (doubled or quadrupled separators
    # once nested) and Windows tools mix drive-letter case, so match the home
    # directory by its segments rather than by the exact string.
    parts = [re.escape(part) for part in re.split(r"[\\/]+", home) if part]
    if not parts:
        # A root home directory would otherwise redact every path separator.
        return re.compile(r"(?!x)x")
    pattern = r"[\\/]+".join(parts)
    if home[:1] in ("\\", "/"):
        pattern = r"[\\/]+" + pattern
    return re.compile(pattern, re.IGNORECASE)


def _redact(text: str) -> str:
    try:
        home = str(Path.home())
        if home:
            text = _home_pattern(home).sub("<home>", text)
    except RuntimeError:
        pass
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _tail(text: str, limit: int = 30, width: int = 400) -> str:
    lines = [line.rstrip()[:width] for line in text.splitlines() if line.strip()]
    return "\n".join(f"  {line}" for line in lines[-limit:])


def _run_checked(
    argv: list[str], *, env: dict[str, str], stage: str
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        # The child's own diagnostics (pip's OSError, a missing ensurepip,
        # a proxy rejection) are the only thing that makes the failure
        # actionable; the exit code alone is not.
        detail = _tail(result.stderr or result.stdout)
        message = f"{stage} failed with exit code {result.returncode}"
        raise RuntimeError(f"{message}\n{detail}" if detail else message)
    return result


class SetupLock:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self) -> "SetupLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                handle.write(f"{os.getpid()}\n{int(time.time())}\n")
        except FileExistsError:
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError:
                age = 0
            if age <= LOCK_STALE_SECONDS:
                raise RuntimeError(f"another {_product()} setup is already running")
            self.path.unlink(missing_ok=True)
            with self.path.open("x", encoding="utf-8") as handle:
                handle.write(f"{os.getpid()}\n{int(time.time())}\n")
        return self

    def __exit__(self, *_: object) -> None:
        self.path.unlink(missing_ok=True)


def _replace_with_retry(source: Path, target: Path, attempts: int = 8) -> None:
    """Swap a directory into place, tolerating Windows handle-release lag.

    Right after pip or Playwright writes a venv, Windows (often Defender) can
    hold handles in it briefly, so the rename fails with WinError 5 and then
    succeeds about a second later.
    """
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.25 * (attempt + 1))


def command_setup(args: argparse.Namespace) -> int:
    if not _python_supported():
        print(_python_range_message(), file=sys.stderr)
        return 2
    root = _root()
    status = _status(root)
    data_dir: Path = status["data_dir"]
    final_venv: Path = status["venv"]
    staged = data_dir / f".venv.next-{os.getpid()}"
    backup = data_dir / ".venv.previous"
    temp_state = data_dir / ".runtime-state.next"
    shutil.rmtree(staged, ignore_errors=True)
    env = _safe_env(status)
    browser_ready = False
    previous_moved = False
    swapped = False
    committed = False
    had_previous = final_venv.exists()
    try:
        with SetupLock(data_dir / ".setup.lock"):
            print(f"Creating isolated {_product()} environment...", flush=True)
            # venv bootstraps pip itself but discards ensurepip's output, so a
            # failing bootstrap would surface only as "ensurepip returned 1".
            # Running it as its own stage keeps pip's diagnostics visible.
            _run_checked(
                [sys.executable, "-m", "venv", "--without-pip", str(staged)],
                env=env,
                stage="virtual environment creation",
            )
            staged_python = _venv_python(staged)
            _run_checked(
                [str(staged_python), "-m", "ensurepip", "--upgrade", "--default-pip"],
                env=env,
                stage="pip bootstrap",
            )
            _run_checked(
                [str(staged_python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(root / "requirements.txt")],
                env=env,
                stage="dependency installation",
            )
            if not args.skip_browser:
                # Playwright is an optional render extra. The package alone
                # enables the system and channel backends with no browser
                # download; Chromium is only fetched for the managed backend.
                browser_env = dict(env)
                browser_env["PLAYWRIGHT_BROWSERS_PATH"] = str(
                    data_dir / "ms-playwright"
                )
                download_chromium = not getattr(args, "playwright", False)
                try:
                    _run_checked(
                        [
                            str(staged_python),
                            "-m",
                            "pip",
                            "install",
                            "--disable-pip-version-check",
                            PLAYWRIGHT_REQUIREMENT,
                        ],
                        env=env,
                        stage="Playwright installation",
                    )
                    if download_chromium:
                        _run_checked(
                            [str(staged_python), "-m", "playwright", "install", "chromium"],
                            env=browser_env,
                            stage="Chromium installation",
                        )
                except RuntimeError as exc:
                    print(f"Browser setup incomplete: {_redact(str(exc))}", file=sys.stderr)
            browser_ready = _venv_has_package(staged, "playwright") and _render_status(
                {
                    "data_dir": data_dir,
                    "venv": staged,
                    "python_path": _venv_python(staged),
                }
            )["backend"] == "managed"
            validation = "import bs4, lxml, lxml_html_clean, requests, trafilatura"
            if not args.skip_browser and _venv_has_package(staged, "playwright"):
                validation += ", playwright"
            _run_checked(
                [str(staged_python), "-c", validation],
                env=env,
                stage="runtime import validation",
            )
            shutil.rmtree(backup, ignore_errors=True)
            if final_venv.exists():
                _replace_with_retry(final_venv, backup)
                previous_moved = True
            _replace_with_retry(staged, final_venv)
            swapped = True
            state = dict(status["expected"])
            state["browser_ready"] = browser_ready
            temp_state.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temp_state.replace(_state_path(data_dir))
            committed = True
            shutil.rmtree(backup, ignore_errors=True)
    except (OSError, RuntimeError) as exc:
        shutil.rmtree(staged, ignore_errors=True)
        temp_state.unlink(missing_ok=True)
        if not committed:
            if swapped:
                shutil.rmtree(final_venv, ignore_errors=True)
            if previous_moved and had_previous and backup.exists():
                _replace_with_retry(backup, final_venv)
        print(f"{_product()} setup failed: {_redact(str(exc))}", file=sys.stderr)
        return 1
    render = _render_status(
        {
            "data_dir": data_dir,
            "venv": final_venv,
            "python_path": _venv_python(final_venv),
        }
    )
    backend = render["backend"]
    if args.skip_browser or backend != "static":
        suffix = "" if backend in ("managed", "system", "channel") else f" Render backend: {backend} (degraded)."
        print(f"{_product()} runtime is ready.{suffix}")
        return 0
    print(
        "Core runtime is ready, but no browser render backend is available. "
        "Install Chrome or Edge, or run setup again with --with-browser to "
        "download managed Chromium.",
        file=sys.stderr,
    )
    return 10


def _resolve_script(root: Path, name: str, extension: str | None) -> Path:
    if not SCRIPT_NAME_RE.fullmatch(name):
        raise ValueError("script must be a bundled Python script basename")
    if extension:
        if not EXTENSION_NAME_RE.fullmatch(extension):
            raise ValueError("invalid extension name")
        scripts_dir = root / "extensions" / extension / "scripts"
        if not scripts_dir.is_dir() and extension in MANUAL_EXTENSION_SKILLS:
            scripts_dir = root.parent / MANUAL_EXTENSION_SKILLS[extension] / "scripts"
    else:
        if name not in ALLOWED_CORE_SCRIPTS:
            raise ValueError("script is not in the bundled runtime allowlist")
        scripts_dir = root / "scripts"
    candidate = (scripts_dir / name).resolve()
    scripts_root = scripts_dir.resolve()
    if candidate.parent != scripts_root or not candidate.is_file() or candidate == Path(__file__).resolve():
        raise ValueError("script is not in the bundled runtime allowlist")
    return candidate


def command_run(args: argparse.Namespace) -> int:
    root = _root()
    try:
        script = _resolve_script(root, args.script, args.extension)
    except ValueError as exc:
        print(f"{_product()} runtime: {exc}", file=sys.stderr)
        return 2
    status = _status(root)
    if not status["ready"]:
        print(f"{_product()} runtime is not ready. Run `/seo setup` and retry.", file=sys.stderr)
        return 3
    result = subprocess.run(
        [str(status["python_path"]), str(script), *args.script_args],
        env=_safe_env(status),
    )
    if result.returncode < 0:
        os.kill(os.getpid(), -result.returncode)
        return 128 + (-result.returncode)
    return result.returncode


def command_doctor(args: argparse.Namespace) -> int:
    status = _status(_root())
    render = _probe_render(status)
    public = {
        "ready": status["ready"],
        "mode": status["mode"],
        "plugin_version": status["plugin_version"],
        "python_version": status["python_version"],
        "browser_ready": render["backend"] != "static",
        "render_backend": render["backend"],
        "degraded": render["degraded"],
        "reasons": status["reasons"],
    }
    if args.json:
        print(json.dumps(public, indent=2, sort_keys=True))
    else:
        print(f"Runtime: {'ready' if public['ready'] else 'setup required'}")
        print(f"Install mode: {public['mode']}")
        print(f"Python: {public['python_version']}")
        print(f"Chromium: {'ready' if public['browser_ready'] else 'not installed'}")
        print(
            f"Render backend: {public['render_backend']}"
            + (" (degraded)" if public["degraded"] else "")
        )
        for reason in public["reasons"]:
            print(f"Reason: {reason}")
    return 0 if status["ready"] else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opencode-seo" if _product() == "OpenCode SEO" else "claude-seo",
        description=f"{_product()} managed Python runtime",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="create or refresh the isolated runtime")
    setup.add_argument("--skip-browser", action="store_true")
    setup.add_argument(
        "--playwright",
        action="store_true",
        help="install Playwright for system/channel rendering without downloading Chromium",
    )
    setup.set_defaults(func=command_setup)
    doctor = sub.add_parser("doctor", help="check runtime readiness without changing it")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=command_doctor)
    run = sub.add_parser("run", help="run one bundled Python script")
    run.add_argument("--extension")
    run.add_argument("script")
    run.add_argument("script_args", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_utf8()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"{_product()} runtime failed: {_redact(str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
