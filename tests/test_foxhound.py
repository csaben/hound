from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hound.errors import BackendError
from hound.foxhound import ensure_helper


class Response:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


def test_downloads_verified_helper(tmp_path: Path, monkeypatch):
    payload = b"test helper"
    monkeypatch.setenv("HOUND_HOME", str(tmp_path))
    monkeypatch.setenv("HOUND_FOXHOUND_URL", "https://example.invalid/helper.exe")
    monkeypatch.setenv("HOUND_FOXHOUND_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr("hound.foxhound.os.name", "nt")
    monkeypatch.setattr("hound.foxhound.platform.machine", lambda: "AMD64")
    monkeypatch.setattr("hound.foxhound.find_helper", lambda _explicit=None: None)
    monkeypatch.setattr("hound.foxhound.requests.get", lambda *_args, **_kwargs: Response(payload))

    helper = Path(ensure_helper())

    assert helper.read_bytes() == payload


def test_rejects_unverified_helper(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOUND_HOME", str(tmp_path))
    monkeypatch.setenv("HOUND_FOXHOUND_SHA256", "0" * 64)
    monkeypatch.setattr("hound.foxhound.os.name", "nt")
    monkeypatch.setattr("hound.foxhound.platform.machine", lambda: "AMD64")
    monkeypatch.setattr("hound.foxhound.find_helper", lambda _explicit=None: None)
    monkeypatch.setattr(
        "hound.foxhound.requests.get", lambda *_args, **_kwargs: Response(b"unexpected")
    )

    with pytest.raises(BackendError, match="checksum mismatch"):
        ensure_helper()
