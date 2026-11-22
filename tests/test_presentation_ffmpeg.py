import hashlib
import json
import re
import subprocess
import wave
from pathlib import Path

import pytest

from engine.python.basketball_engine.adapters import presentation


def make_video(path, duration=1, audio=True):
    command = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=64x64:rate=25:duration={duration}",
    ]
    if audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=1000:sample_rate=48000:duration={duration}", "-c:a", "aac"]
    command += ["-c:v", "mpeg4", "-q:v", "2", str(path)]
    subprocess.run(command, check=True, capture_output=True)


def probe(path):
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,duration,sample_rate,channels:format=duration", "-of", "json", str(path),
    ]))
    return data


def mean_volume(path, start=0):
    result = subprocess.run([
        "ffmpeg", "-v", "info", "-ss", str(start), "-i", str(path),
        "-af", "volumedetect", "-f", "null", "-",
    ], check=True, capture_output=True, text=True)
    match = re.search(r"mean_volume: (-?[0-9.]+) dB", result.stderr)
    return float(match.group(1))


@pytest.fixture(autouse=True)
def fast_encoder(monkeypatch):
    monkeypatch.setattr(presentation, "video_codecs", lambda: ["mpeg4"])


def test_default_adds_three_second_cover_and_bgm(tmp_path):
    target = tmp_path / "highlight.mp4"
    make_video(target)
    result = presentation.enhance_video(target, {}, "Will")
    streams = {item["codec_type"]: item for item in probe(target)["streams"]}
    assert result["duration_ms"] == 4000
    assert result["cover_duration_ms"] == 3000
    assert float(probe(target)["format"]["duration"]) == pytest.approx(4, abs=0.15)
    assert streams["audio"]["sample_rate"] == "48000"
    assert streams["audio"]["channels"] == 2


def test_cover_can_be_disabled_independently(tmp_path):
    target = tmp_path / "highlight.mp4"
    make_video(target)
    result = presentation.enhance_video(target, {"cover": {"enabled": False}}, "Will")
    assert result["cover_duration_ms"] == 0
    assert float(probe(target)["format"]["duration"]) == pytest.approx(1, abs=0.1)
    assert any(item["codec_type"] == "audio" for item in probe(target)["streams"])


def test_disabled_presentation_is_a_byte_for_byte_noop(tmp_path):
    target = tmp_path / "highlight.mp4"
    make_video(target)
    before = hashlib.sha256(target.read_bytes()).digest()
    result = presentation.enhance_video(target, {"cover": {"enabled": False}, "audio": {"enabled": False}}, "Will")
    assert result["changed"] is False
    assert hashlib.sha256(target.read_bytes()).digest() == before


def test_custom_bgm_is_mixed_at_twenty_percent_volume(tmp_path):
    target = tmp_path / "highlight.mp4"
    music = tmp_path / "tone.wav"
    make_video(target, audio=False)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=48000:duration=6", str(music),
    ], check=True, capture_output=True)
    presentation.enhance_video(target, {"audio": {"custom_path": str(music)}}, "Will")
    measured = mean_volume(target)
    # A 0.125-amplitude sine has -21.07 dB RMS; 20% is another -13.98 dB.
    assert measured == pytest.approx(-35.0, abs=1.5)


def test_original_sound_is_not_attenuated_when_bgm_is_disabled(tmp_path):
    target = tmp_path / "highlight.mp4"
    make_video(target)
    before = mean_volume(target)
    presentation.enhance_video(target, {"audio": {"enabled": False}}, "Will")
    after = mean_volume(target, start=3)
    assert after == pytest.approx(before, abs=1.0)


def test_failed_enhancement_preserves_original_file(tmp_path, monkeypatch):
    target = tmp_path / "highlight.mp4"
    make_video(target)
    before = target.read_bytes()
    def fail(*args, **kwargs):
        raise OSError("synthetic encoder failure")
    monkeypatch.setattr(presentation, "run_encoded_ffmpeg", fail)
    with pytest.raises(OSError, match="synthetic encoder failure"):
        presentation.enhance_video(target, {}, "Will")
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("*.part*"))
