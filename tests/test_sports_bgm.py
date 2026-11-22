import hashlib
import wave
from pathlib import Path

import numpy as np
import pytest

from engine.python.basketball_engine.adapters.presentation import (
    normalize_presentation,
    resolve_bgm,
)
from scripts.generate_sports_bgm import TRACKS, generate_tracks


def test_three_original_tracks_are_deterministic_non_silent_and_unclipped(tmp_path):
    first = generate_tracks(tmp_path / "first")
    second = generate_tracks(tmp_path / "second")
    assert set(first) == {"electronic_drive", "hip_hop_bounce", "rock_pulse"}
    for name in first:
        assert hashlib.sha256(first[name].read_bytes()).digest() == hashlib.sha256(second[name].read_bytes()).digest()
        with wave.open(str(first[name]), "rb") as audio:
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2
            assert audio.getframerate() == 22050
            assert audio.getnframes() > audio.getframerate() * 3
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
        assert np.sqrt(np.mean(samples.astype(np.float64) ** 2)) > 300
        assert np.max(np.abs(samples.astype(np.int32))) < 32767 * 0.95


def test_builtin_tracks_resolve_from_packaged_assets():
    for name in TRACKS:
        config = normalize_presentation({"audio": {"track": name}})
        path = resolve_bgm(config)
        assert path.is_file()
        assert path.name == f"{name}.wav"


def test_custom_music_is_supported(tmp_path):
    music = tmp_path / "my song.wav"
    music.write_bytes(b"test music")
    config = normalize_presentation({"audio": {"custom_path": str(music)}})
    assert resolve_bgm(config) == music.resolve()


def test_disabled_or_missing_music_is_explicit(tmp_path):
    disabled = normalize_presentation({"audio": {"enabled": False}})
    assert resolve_bgm(disabled) is None
    missing = normalize_presentation({"audio": {"custom_path": str(tmp_path / "missing.wav")}})
    with pytest.raises(OSError, match="BGM_NOT_FOUND"):
        resolve_bgm(missing)
