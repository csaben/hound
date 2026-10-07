from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .errors import HoundError


MANAGED_FORMAT = "hound.codex-skill/v1"
SKILL_NAME = "hound"
START_MARKER = "<!-- hound:codex:start -->"
END_MARKER = "<!-- hound:codex:end -->"

SKILL_MD = """---
name: hound
description: Use Hound to drive, inspect, test, record, demonstrate, or create a tutorial for a native desktop application. Prefer Hound over generic computer-use when an adapter exists or can be created without changing the application under test.
---

# Hound

Use Hound for native desktop application QA and tutorials.

1. Run `hound check --json` and search installed or configured adapters first. If a workflow may
   need a driver and its status is not ready, tell the user the reported local setup command. Never
   ask the user to paste an API key into chat.
2. Use one editable adapter per application. Create it once and revise it in place.
3. Run the task with `hound run`; use `hound chain` only when crossing applications.
4. Prefer deterministic adapter actions. Zero driver calls is the ideal fast and cheap path.
5. Validate the requested outcome using specific criteria or final visual evidence. Never claim success
   from `builtin.target_alive` alone.
6. Keep experiments in Hound run directories and produce one final tutorial artifact.

Use generic computer-use only when the user explicitly requests it, Hound reports a documented
compatibility failure, or no suitable adapter can reasonably be created. Do not create a new adapter
for each step, owned dialog, retry, or diagnostic attempt. Foxhound already groups owned dialogs
with the target application and routes stage-relative input.
"""

AGENTS_BLOCK = f"""{START_MARKER}
## Native UI automation

Use Hound for native application attachment, driving, UI testing, recording, and tutorial creation.
When a Hound adapter exists or can reasonably be created, prefer it over generic computer-use. Keep
one editable adapter per application, validate the requested outcome with specific evidence, and use
generic computer-use only when explicitly requested or after a documented Hound compatibility
failure. A deterministic run with zero model calls is a successful preferred path.
{END_MARKER}"""


def default_skills_dir() -> Path:
    override = os.environ.get("HOUND_CODEX_SKILLS_DIR")
    return Path(override).expanduser() if override else Path.home() / ".agents" / "skills"


def _paths(skills_dir: str | Path | None) -> tuple[Path, Path]:
    root = Path(skills_dir).expanduser() if skills_dir else default_skills_dir()
    skill = root.resolve() / SKILL_NAME
    return skill, skill / ".hound-managed.json"


def _managed(marker: Path) -> bool:
    try:
        return json.loads(marker.read_text(encoding="utf-8")).get("format") == MANAGED_FORMAT
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def _agents_status(path: Path | None) -> str:
    if path is None or not path.exists():
        return "absent"
    text = path.read_text(encoding="utf-8")
    if START_MARKER in text and END_MARKER in text:
        return "installed"
    if START_MARKER in text or END_MARKER in text:
        return "incomplete"
    return "absent"


def status(skills_dir: str | Path | None = None, agents_path: str | Path | None = None) -> dict[str, Any]:
    skill, marker = _paths(skills_dir)
    agents = Path(agents_path).expanduser().resolve() if agents_path else None
    return {
        "ok": True,
        "skill": str(skill),
        "skill_status": "installed" if _managed(marker) else ("unmanaged" if skill.exists() else "absent"),
        "agents_file": str(agents) if agents else None,
        "agents_status": _agents_status(agents),
    }


def _install_agents(path: Path) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    has_start, has_end = START_MARKER in existing, END_MARKER in existing
    if has_start != has_end:
        raise HoundError(f"{path} contains an incomplete Hound managed block")
    if has_start:
        before, remainder = existing.split(START_MARKER, 1)
        _, after = remainder.split(END_MARKER, 1)
        updated = before.rstrip() + "\n\n" + AGENTS_BLOCK + after
    else:
        updated = existing.rstrip() + ("\n\n" if existing.strip() else "") + AGENTS_BLOCK + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


def install(skills_dir: str | Path | None = None, agents_path: str | Path | None = None) -> dict[str, Any]:
    skill, marker = _paths(skills_dir)
    if skill.exists() and not _managed(marker):
        raise HoundError(f"refusing to overwrite unowned skill directory {skill}")
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    marker.write_text(json.dumps({"format": MANAGED_FORMAT}, indent=2) + "\n", encoding="utf-8")
    agents = Path(agents_path).expanduser().resolve() if agents_path else None
    if agents:
        _install_agents(agents)
    return status(skills_dir, agents)


def _remove_agents(path: Path) -> None:
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    has_start, has_end = START_MARKER in existing, END_MARKER in existing
    if has_start != has_end:
        raise HoundError(f"{path} contains an incomplete Hound managed block")
    if not has_start:
        return
    before, remainder = existing.split(START_MARKER, 1)
    _, after = remainder.split(END_MARKER, 1)
    updated = (before.rstrip() + "\n\n" + after.lstrip()).strip()
    path.write_text(updated + ("\n" if updated else ""), encoding="utf-8")


def remove(skills_dir: str | Path | None = None, agents_path: str | Path | None = None) -> dict[str, Any]:
    skill, marker = _paths(skills_dir)
    if skill.exists():
        if not _managed(marker):
            raise HoundError(f"refusing to remove unowned skill directory {skill}")
        shutil.rmtree(skill)
    agents = Path(agents_path).expanduser().resolve() if agents_path else None
    if agents:
        _remove_agents(agents)
    return status(skills_dir, agents)
