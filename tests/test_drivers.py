import pytest

from hound.drivers import JevDriver, _question, status
from hound.errors import DriverError


def test_clef_single_action_gets_explicit_stop_alternative():
    question = _question([{"id": "continue", "description": "Continue safely"}], clef_compatible=True)
    criteria = question["next_action"]["criteria"]
    assert criteria == {
        "continue": "Continue safely",
        "__hound_stop__": "Stop only if the offered workflow action is unsafe or cannot advance the goal.",
    }


def test_jev_single_action_remains_unchanged():
    criteria = _question([{"id": "continue"}])["next_action"]["criteria"]
    assert criteria == {"continue": "continue"}


def test_jev_missing_key_has_actionable_error(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(DriverError, match="do not paste the secret into chat"):
        JevDriver().choose({}, [{"id": "go"}])


def test_driver_status_explains_deterministic_path(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("CLEF_URL", raising=False)
    result = status()
    assert not result["jev"]["ready"]
    assert not result["clef"]["ready"]
    assert "deterministic" in result["note"]
