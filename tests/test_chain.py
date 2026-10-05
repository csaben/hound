from pathlib import Path
from types import SimpleNamespace

from hound.chain import ChainRunner, load_chain
from hound.runner import RunOptions


def test_load_chain_requires_unique_stage_ids(tmp_path: Path):
    manifest = tmp_path / "chain.yaml"
    manifest.write_text(
        "schema: hound.chain/v1\nname: demo\nstages:\n"
        "  - {id: one, adapter: alpha}\n  - {id: two, adapter: beta}\n",
        encoding="utf-8",
    )
    chain = load_chain(manifest)
    assert chain.name == "demo"


def test_chain_runs_stages_and_aggregates_metrics(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "chain.yaml"
    manifest.write_text(
        "schema: hound.chain/v1\nname: demo\nstages:\n"
        "  - {id: one, adapter: alpha}\n  - {id: two, adapter: beta}\n",
        encoding="utf-8",
    )
    calls = []

    class FakeHound:
        def __init__(self, adapter, driver):
            calls.append((str(adapter), driver))

        def run(self, goal, options):
            options.output.mkdir(parents=True)
            return SimpleNamespace(
                success=True, reason="done", steps=1, captioned=None, recording=None,
                metrics={"driver_calls": 1, "driver_ms": 2, "driver_input_tokens": 3,
                         "driver_output_tokens": 4, "estimated_model_cost_usd": 0.0001},
                as_dict=lambda: {"success": True, "run_dir": str(options.output), "steps": 1},
            )

    monkeypatch.setattr("hound.chain.Hound", FakeHound)
    result = ChainRunner(manifest, "clef").run(RunOptions(record=False, output=tmp_path / "run"))

    assert result.success
    assert result.metrics["stages"] == 2
    assert result.metrics["driver_calls"] == 2
    assert calls == [("alpha", "clef"), ("beta", "clef")]
