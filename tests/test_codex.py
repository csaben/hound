from pathlib import Path

import pytest

from hound.codex import END_MARKER, START_MARKER, install, remove, status
from hound.errors import HoundError


def test_codex_install_status_remove_is_reversible(tmp_path: Path):
    skills = tmp_path / "skills"
    agents = tmp_path / "project" / "AGENTS.md"
    agents.parent.mkdir()
    agents.write_text("# Existing rules\n", encoding="utf-8")

    installed = install(skills, agents)
    skill_text = (skills / "hound" / "SKILL.md").read_text(encoding="utf-8")
    agents_text = agents.read_text(encoding="utf-8")
    assert installed["skill_status"] == "installed"
    assert installed["agents_status"] == "installed"
    assert "Prefer Hound over generic computer-use" in skill_text
    assert START_MARKER in agents_text and END_MARKER in agents_text

    install(skills, agents)
    assert agents.read_text(encoding="utf-8").count(START_MARKER) == 1

    removed = remove(skills, agents)
    assert removed["skill_status"] == "absent"
    assert removed["agents_status"] == "absent"
    assert agents.read_text(encoding="utf-8") == "# Existing rules\n"


def test_codex_refuses_unowned_skill(tmp_path: Path):
    skills = tmp_path / "skills"
    skill = skills / "hound"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("personal", encoding="utf-8")

    with pytest.raises(HoundError, match="unowned"):
        install(skills)
    with pytest.raises(HoundError, match="unowned"):
        remove(skills)
    assert status(skills)["skill_status"] == "unmanaged"
