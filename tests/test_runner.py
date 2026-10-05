from pathlib import Path

from hound.runner import Hound, RunOptions


class FakeBackend:
    def __init__(self, target, timeout=10):
        self.target = target
        self.acted = []

    def start(self):
        pass

    def close(self):
        pass

    def screenshot(self):
        return b"not-a-real-png"

    def windows(self):
        return [{"title": "Test"}]

    def health(self):
        return {"target": {"title": "Test"}}

    def act(self, action):
        self.acted.append(action["id"])
        return {"ok": True}


class FakeDriver:
    def choose(self, state, actions, image=None):
        class Choice:
            action_id = "finish"
            confidence = 1.0
            elapsed_ms = 0.1
            raw = {"usage": {"input_tokens": 10, "output_tokens": 1}}
        return Choice()


def test_complete_run_writes_contract(tmp_path: Path, monkeypatch):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter.yaml").write_text("""
schema: hound.adapter/v1
name: test
target: {backend: foxhound, process: test.exe}
workflow:
  goal: Finish the test.
  actions:
    - {id: finish, op: key, keys: Enter, terminal: true}
  done: {after_action: finish}
  criteria:
    - {id: alive, expect: target lives, check: builtin.target_alive}
""")
    monkeypatch.setattr("hound.runner.FoxhoundBackend", FakeBackend)
    monkeypatch.setattr("hound.runner.create", lambda *args, **kwargs: FakeDriver())
    output = tmp_path / "run"
    result = Hound(adapter).run(options=RunOptions(record=False, captions=True, output=output))
    assert result.success
    assert result.steps == 1
    assert (output / "run.json").exists()
    assert (output / "trace.jsonl").exists()
    assert (output / "captions.vtt").exists()
