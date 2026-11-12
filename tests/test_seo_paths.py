"""Config and cache path resolution for OpenCode and Claude installs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import seo_paths  # noqa: E402


def test_opencode_config_dir_uses_new_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(seo_paths, "_home", lambda: tmp_path)
    monkeypatch.setenv("OPENCODE_SEO_CONFIG_DIR", str(tmp_path / "explicit"))
    monkeypatch.delenv("CLAUDE_SEO_CONFIG_DIR", raising=False)
    assert seo_paths.config_dir() == tmp_path / "explicit"


def test_legacy_config_dir_still_works(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(seo_paths, "_home", lambda: tmp_path)
    monkeypatch.delenv("OPENCODE_SEO_CONFIG_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_SEO_CONFIG_DIR", str(tmp_path / "legacy"))
    assert seo_paths.config_dir() == tmp_path / "legacy"


def test_opencode_cache_dir_uses_new_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(seo_paths, "_home", lambda: tmp_path)
    monkeypatch.setenv("OPENCODE_SEO_CACHE_DIR", str(tmp_path / "explicit-cache"))
    monkeypatch.delenv("CLAUDE_SEO_CACHE_DIR", raising=False)
    assert seo_paths.cache_dir() == tmp_path / "explicit-cache"


def test_legacy_cache_dir_still_works(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(seo_paths, "_home", lambda: tmp_path)
    monkeypatch.delenv("OPENCODE_SEO_CACHE_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_SEO_CACHE_DIR", str(tmp_path / "legacy-cache"))
    assert seo_paths.cache_dir() == tmp_path / "legacy-cache"


def test_opencode_config_file_falls_back_to_legacy_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(seo_paths, "_home", lambda: tmp_path)
    modern = tmp_path / ".config" / "opencode-seo"
    legacy = tmp_path / ".config" / "claude-seo"
    modern.mkdir(parents=True)
    legacy.mkdir(parents=True)
    (legacy / "google-api.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCODE_SEO_CONFIG_DIR", str(modern))
    monkeypatch.delenv("CLAUDE_SEO_CONFIG_DIR", raising=False)

    assert seo_paths.config_file("google-api.json") == legacy / "google-api.json"
    assert seo_paths.config_file("missing.json") == modern / "missing.json"


def test_opencode_cache_file_falls_back_to_legacy(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(seo_paths, "_home", lambda: tmp_path)
    modern = tmp_path / ".cache" / "opencode-seo"
    legacy = tmp_path / ".cache" / "claude-seo"
    modern.mkdir(parents=True)
    legacy.mkdir(parents=True)
    (legacy / "drift").mkdir()
    (legacy / "drift" / "baselines.db").write_text("", encoding="utf-8")
    monkeypatch.setenv("OPENCODE_SEO_CACHE_DIR", str(modern))
    monkeypatch.delenv("CLAUDE_SEO_CACHE_DIR", raising=False)

    assert seo_paths.cache_file("drift/baselines.db") == legacy / "drift" / "baselines.db"
    assert seo_paths.cache_file("missing.lock") == modern / "missing.lock"


def test_new_config_file_is_preferred_when_present(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(seo_paths, "_home", lambda: tmp_path)
    modern = tmp_path / ".config" / "opencode-seo"
    legacy = tmp_path / ".config" / "claude-seo"
    modern.mkdir(parents=True)
    legacy.mkdir(parents=True)
    (modern / "matomo.json").write_text("{}", encoding="utf-8")
    (legacy / "matomo.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCODE_SEO_CONFIG_DIR", str(modern))
    monkeypatch.delenv("CLAUDE_SEO_CONFIG_DIR", raising=False)

    assert seo_paths.config_file("matomo.json") == modern / "matomo.json"
