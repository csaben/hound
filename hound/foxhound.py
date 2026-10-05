from __future__ import annotations

import hashlib
import os
import platform
import shutil
import tempfile
from pathlib import Path

import requests

from .errors import BackendError
from .util import user_root


FOXHOUND_VERSION = "0.1.0"
DEFAULT_HELPER_URL = (
    "https://github.com/csaben/foxhound/releases/download/v0.1.0/"
    "foxhound-helper-windows-x86_64.exe"
)
DEFAULT_HELPER_SHA256 = "be75574aaab4f90dbfcf4558a8c15811393a635e6d7c5d8d53523db9f2df9032"


def helper_candidates(explicit: str | None = None) -> list[str | None]:
    return [
        explicit,
        os.environ.get("FOXHOUND_HELPER"),
        shutil.which("foxhound-helper"),
        str(Path(__file__).resolve().parents[1] / ".foxhound-target" / "release" / "foxhound-helper.exe"),
        str(Path(__file__).resolve().parents[2] / "foxhound" / "target" / "release" / "foxhound-helper.exe"),
        str(user_root() / "bin" / f"foxhound-helper-{FOXHOUND_VERSION}.exe"),
    ]


def find_helper(explicit: str | None = None) -> str | None:
    for value in helper_candidates(explicit):
        if value and Path(value).is_file():
            return str(Path(value))
    return None


def ensure_helper(explicit: str | None = None) -> str:
    existing = find_helper(explicit)
    if existing:
        return existing
    if os.name != "nt" or platform.machine().casefold() not in {"amd64", "x86_64"}:
        raise BackendError("the downloadable Foxhound helper currently supports Windows x86_64 only")

    custom_url = os.environ.get("HOUND_FOXHOUND_URL")
    custom_hash = os.environ.get("HOUND_FOXHOUND_SHA256")
    if custom_url and not custom_hash:
        raise BackendError("HOUND_FOXHOUND_SHA256 is required for a custom helper download")
    url = custom_url or DEFAULT_HELPER_URL
    expected = (custom_hash or DEFAULT_HELPER_SHA256).casefold()

    destination = user_root() / "bin" / f"foxhound-helper-{FOXHOUND_VERSION}.exe"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        digest = hashlib.sha256(response.content).hexdigest()
        if digest.casefold() != expected:
            raise BackendError(
                f"Foxhound helper checksum mismatch: expected {expected}, received {digest}"
            )
        with tempfile.NamedTemporaryFile(
            prefix="foxhound-helper-", suffix=".exe", dir=destination.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(response.content)
        os.replace(temporary, destination)
        return str(destination)
    except requests.RequestException as exc:
        raise BackendError(f"could not download Foxhound helper from {url}: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
