"""OpenCode environment aliases keep the new names first and the old names usable."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import google_auth  # noqa: E402
import runtime  # noqa: E402
import url_safety  # noqa: E402


def test_opencode_google_auth_wins(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_SEO_GOOGLE_AUTH", "adc")
    monkeypatch.setenv("CLAUDE_SEO_GOOGLE_AUTH", "service-account")
    assert google_auth._prefers_gcloud() is True


def test_legacy_google_auth_still_works(monkeypatch) -> None:
    monkeypatch.delenv("OPENCODE_SEO_GOOGLE_AUTH", raising=False)
    monkeypatch.setenv("CLAUDE_SEO_GOOGLE_AUTH", "adc")
    assert google_auth._prefers_gcloud() is True


def test_opencode_local_targets_wins(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_SEO_LOCAL_TARGETS", "example.com:8080")
    monkeypatch.setenv("CLAUDE_SEO_LOCAL_TARGETS", "legacy.example:9090")
    assert ("example.com", 8080) in url_safety._local_targets()


def test_legacy_local_targets_still_works(monkeypatch) -> None:
    monkeypatch.delenv("OPENCODE_SEO_LOCAL_TARGETS", raising=False)
    monkeypatch.setenv("CLAUDE_SEO_LOCAL_TARGETS", "legacy.example:9090")
    assert ("legacy.example", 9090) in url_safety._local_targets()


def test_opencode_data_dir_wins(monkeypatch, tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("OPENCODE_SEO_DATA_DIR", str(tmp_path / "new-data"))
    monkeypatch.setenv("CLAUDE_SEO_DATA_DIR", str(tmp_path / "old-data"))
    data_dir, mode = runtime._data_dir(root)
    assert mode == "override"
    assert data_dir == (tmp_path / "new-data").resolve()


def test_legacy_data_dir_still_works(monkeypatch, tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.delenv("OPENCODE_SEO_DATA_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_SEO_DATA_DIR", str(tmp_path / "old-data"))
    data_dir, mode = runtime._data_dir(root)
    assert mode == "override"
    assert data_dir == (tmp_path / "old-data").resolve()


def test_opencode_root_marker_selects_plugin_mode(monkeypatch, tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / ".opencode-seo-root").write_text("marker\n", encoding="utf-8")
    monkeypatch.delenv("OPENCODE_SEO_DATA_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_SEO_DATA_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.delenv("OPENCODE_SEO_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    _, mode = runtime._data_dir(root)
    assert mode == "plugin-fallback"
