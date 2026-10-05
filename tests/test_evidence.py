from pathlib import Path

from hound.evidence import write_captions


def test_caption_file(tmp_path: Path):
    output = tmp_path / "captions.vtt"
    write_captions(output, [
        {"t_video": 0.4, "caption": "Select the editor"},
        {"t_video": 1.8, "caption": "Type the text"},
    ], 3.0)
    text = output.read_text()
    assert text.startswith("WEBVTT")
    assert "00:00:00.400 --> 00:00:01.800" in text
    assert "Type the text" in text

