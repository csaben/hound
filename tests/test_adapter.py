from pathlib import Path

import pytest

from hound.adapter import load, validate
from hound.errors import AdapterError


ROOT = Path(__file__).resolve().parents[1]


def test_example_loads_and_expands():
    adapter = load(ROOT / "examples" / "notepad").expanded({"text": "hello"})
    action = next(x for x in adapter.workflow["actions"] if x["op"] == "type")
    assert adapter.name == "notepad-example"
    assert action["text"] == "hello"


def test_duplicate_action_ids_rejected():
    with pytest.raises(AdapterError, match="unique id"):
        validate({
            "schema": "hound.adapter/v1", "name": "bad", "target": {"process": "x.exe"},
            "workflow": {"goal": "x", "actions": [
                {"id": "same", "op": "key", "keys": "A"},
                {"id": "same", "op": "key", "keys": "B"},
            ]},
        })

