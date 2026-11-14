"""Render backend selection: no browser download is required for the fallbacks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import render_backend  # noqa: E402


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValueError):
        render_backend.normalize_backend("hologram")


def test_environment_selects_a_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(render_backend.ENV_VAR, "channel")
    assert render_backend.normalize_backend() == "channel"
    assert render_backend.normalize_backend("cli") == "cli"


def test_auto_order_is_managed_system_channel_cli_static() -> None:
    available = {
        "managed": True,
        "system": True,
        "channel": True,
        "cli": True,
        "static": True,
    }
    assert render_backend.plan_backends("auto", available) == [
        "managed",
        "system",
        "channel",
        "cli",
        "static",
    ]


def test_auto_skips_unavailable_layers() -> None:
    available = {
        "managed": False,
        "system": False,
        "channel": True,
        "cli": True,
        "static": True,
    }
    assert render_backend.plan_backends("auto", available) == [
        "channel",
        "cli",
        "static",
    ]
    assert render_backend.choose_backend("auto", available) == "channel"


def test_forced_backend_does_not_fall_through() -> None:
    available = {"managed": False, "system": True, "static": True}
    assert render_backend.plan_backends("managed", available) == ["managed"]


def test_find_chromium_prefers_the_newest_full_build(tmp_path: Path) -> None:
    older = tmp_path / "chromium-1000" / "chrome-win"
    newer = tmp_path / "chromium-1255" / "chrome-win"
    shell = tmp_path / "chromium_headless_shell-1300" / "chrome-win"
    for directory in (older, newer, shell):
        directory.mkdir(parents=True)
    (older / "chrome.exe").write_text("", encoding="utf-8")
    (newer / "chrome.exe").write_text("", encoding="utf-8")
    (shell / "headless_shell.exe").write_text("", encoding="utf-8")

    found = render_backend.find_chromium(tmp_path)
    assert found == newer / "chrome.exe"


def test_find_chromium_falls_back_to_the_headless_shell(tmp_path: Path) -> None:
    shell = tmp_path / "chromium_headless_shell-1300" / "chrome-win"
    shell.mkdir(parents=True)
    (shell / "headless_shell.exe").write_text("", encoding="utf-8")
    assert render_backend.find_chromium(tmp_path) == shell / "headless_shell.exe"


def test_availability_requires_playwright_for_managed_and_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed = tmp_path / "managed"
    (managed / "chromium-1" / "chrome-win").mkdir(parents=True)
    (managed / "chromium-1" / "chrome-win" / "chrome.exe").write_text("", encoding="utf-8")
    system = tmp_path / "system"
    (system / "chromium-1" / "chrome-win").mkdir(parents=True)
    (system / "chromium-1" / "chrome-win" / "chrome.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(render_backend, "system_browsers_dir", lambda: system)
    monkeypatch.setattr(render_backend, "channel_candidates", lambda: ("chrome",))
    monkeypatch.setattr(render_backend, "cli_executable", lambda: "/usr/bin/chrome")

    without_playwright = render_backend.availability(playwright=False, managed=managed)
    assert without_playwright == {
        "managed": False,
        "system": False,
        "channel": False,
        "cli": True,
        "static": True,
    }

    with_playwright = render_backend.availability(playwright=True, managed=managed)
    assert with_playwright["managed"] is True
    assert with_playwright["system"] is True
    assert with_playwright["channel"] is True
