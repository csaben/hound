import json
from pathlib import Path

import pytest

from hound.errors import AdapterError
from hound.registry import registry_url, search


def test_registry_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("HOUND_REGISTRY_URL", raising=False)
    with pytest.raises(AdapterError, match="no adapter registry is configured"):
        registry_url()


def test_local_registry_filters_platform(tmp_path: Path, monkeypatch):
    registry = tmp_path / "index.json"
    registry.write_text(json.dumps({
        "schema": "hound.registry/v1",
        "adapters": [
            {"name": "here", "platforms": {"windows": {}}, "repository": "x"},
            {"name": "elsewhere", "platforms": {"linux": {}}, "repository": "x"},
        ],
    }))
    monkeypatch.setattr("hound.registry.platform_name", lambda: "windows")
    assert [x["name"] for x in search(url=str(registry))] == ["here"]
    assert len(search(include_incompatible=True, url=str(registry))) == 2
