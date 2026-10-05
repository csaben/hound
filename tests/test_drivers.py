from hound.drivers import _question


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
