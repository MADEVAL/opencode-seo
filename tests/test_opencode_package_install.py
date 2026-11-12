"""Contract tests for the top-level OpenCode package installer."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import install_opencode_package as installer  # noqa: E402


def test_install_package_copies_generated_target(tmp_path) -> None:
    counts = installer.install_package(tmp_path, setup=False)
    assert counts == {"skills": 26, "agents": 19, "commands": 35, "plugins": 1}

    assert (tmp_path / "plugins" / "opencode-seo" / "index.ts").is_file()
    assert (tmp_path / "plugins" / "opencode-seo" / "package.json").is_file()
    assert (tmp_path / "opencode-seo" / ".opencode-seo-root").is_file()
    assert (tmp_path / "opencode-seo" / "scripts" / "runtime.py").is_file()
    assert (tmp_path / "commands" / "seo.md").is_file()
    assert (tmp_path / "commands" / "seo" / "audit.md").is_file()
    assert len(list((tmp_path / "skills").glob("*/SKILL.md"))) == 26
    assert len(list((tmp_path / "agents").glob("*.md"))) == 19


def test_install_package_does_not_remove_user_skills(tmp_path) -> None:
    user_skill = tmp_path / "skills" / "my-skill" / "SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text("---\nname: my-skill\ndescription: Mine\n---\n", encoding="utf-8")

    installer.install_package(tmp_path, setup=False)
    assert user_skill.is_file()

    installer.uninstall_package(tmp_path)
    assert user_skill.is_file()
    assert not (tmp_path / "skills" / "seo" / "SKILL.md").exists()
    assert not (tmp_path / "agents" / "seo-technical.md").exists()
    assert not (tmp_path / "plugins" / "opencode-seo").exists()
    assert not (tmp_path / "opencode-seo").exists()
