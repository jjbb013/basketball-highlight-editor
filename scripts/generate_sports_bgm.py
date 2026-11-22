"""Generate three original, deterministic sports loops without sampled material."""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22050
TRACKS = {
    "electronic_drive": {"bpm": 128, "root": 45, "style": "electronic"},
    "hip_hop_bounce": {"bpm": 92, "root": 41, "style": "hip_hop"},
    "rock_pulse": {"bpm": 140, "root": 40, "style": "rock"},
}


def _frequency(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def _tone(signal, start, duration, frequency, amplitude, style, sample_rate=SAMPLE_RATE):
    first = int(start * sample_rate)
    count = min(int(duration * sample_rate), len(signal) - first)
    if first < 0 or count <= 0:
        return
    t = np.arange(count, dtype=np.float64) / sample_rate
    phase = 2 * np.pi * frequency * t
    if style == "bass":
        wave_data = np.sin(phase) + 0.24 * np.sin(2 * phase) + 0.08 * np.sin(3 * phase)
    elif style == "rock":
        wave_data = np.tanh(2.4 * (np.sin(phase) + 0.45 * np.sin(2 * phase)))
    else:
        wave_data = np.sin(phase) + 0.15 * np.sin(2 * phase)
    attack = np.minimum(1.0, t / 0.012)
    envelope = attack * np.exp(-t / max(0.04, duration * 0.55))
    signal[first:first + count] += amplitude * wave_data * envelope


def _drums(signal, rng, start, kind, amplitude, sample_rate=SAMPLE_RATE):
    duration = {"kick": 0.28, "snare": 0.18, "hat": 0.055}[kind]
    first = int(start * sample_rate)
    count = min(int(duration * sample_rate), len(signal) - first)
    if first < 0 or count <= 0:
        return
    t = np.arange(count, dtype=np.float64) / sample_rate
    noise = rng.standard_normal(count)
    if kind == "kick":
        phase = 2 * np.pi * (48 * t + 38 * 0.025 * (1 - np.exp(-t / 0.025)))
        sound = np.sin(phase) * np.exp(-t / 0.075)
    elif kind == "snare":
        bright = np.concatenate(([0.0], np.diff(noise)))
        sound = (0.65 * bright + 0.35 * np.sin(2 * np.pi * 175 * t)) * np.exp(-t / 0.045)
    else:
        sound = np.concatenate(([0.0], np.diff(noise))) * np.exp(-t / 0.013)
    signal[first:first + count] += amplitude * sound


def _render(name, spec):
    sample_rate = SAMPLE_RATE
    beat = 60.0 / spec["bpm"]
    duration = beat * 16
    count = round(duration * sample_rate)
    signal = np.zeros(count, dtype=np.float64)
    rng = np.random.default_rng(20261123 + list(TRACKS).index(name))
    roots = [0, 0, 5, 7]
    style = spec["style"]
    for index in range(16):
        start = index * beat
        root = spec["root"] + roots[index // 4]
        if style == "electronic":
            _tone(signal, start, beat * 0.88, _frequency(root), 0.32, "bass")
            _tone(signal, start + beat * 0.5, beat * 0.25, _frequency(root + 12), 0.11, "lead")
            _drums(signal, rng, start, "kick", 0.42)
            if index % 2:
                _drums(signal, rng, start, "snare", 0.18)
            _drums(signal, rng, start + beat * 0.5, "hat", 0.045)
        elif style == "hip_hop":
            _tone(signal, start, beat * 0.65, _frequency(root), 0.36, "bass")
            if index % 2 == 0:
                _tone(signal, start, beat * 0.7, _frequency(root + 12), 0.12, "lead")
                _tone(signal, start, beat * 0.7, _frequency(root + 15), 0.09, "lead")
            if index % 4 in (0, 2):
                _drums(signal, rng, start, "kick", 0.40)
            if index % 2:
                _drums(signal, rng, start, "snare", 0.17)
            _drums(signal, rng, start + beat * 0.54, "hat", 0.035)
        else:
            _tone(signal, start, beat * 0.83, _frequency(root), 0.28, "rock")
            _tone(signal, start, beat * 0.83, _frequency(root + 7), 0.15, "rock")
            _drums(signal, rng, start, "kick", 0.38)
            if index % 2:
                _drums(signal, rng, start, "snare", 0.20)
            _drums(signal, rng, start + beat * 0.5, "hat", 0.04)
    signal -= np.mean(signal)
    fade = min(256, count // 2)
    signal[:fade] *= np.linspace(0, 1, fade)
    signal[-fade:] *= np.linspace(1, 0, fade)
    peak = float(np.max(np.abs(signal)))
    if peak:
        signal *= 0.84 / peak
    return (signal * 32767).astype("<i2")


def generate_tracks(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, spec in TRACKS.items():
        path = output_dir / f"{name}.wav"
        samples = _render(name, spec)
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(SAMPLE_RATE)
            audio.writeframes(samples.tobytes())
        paths[name] = path
    return paths


def main(output_dir=None):
    root = Path(__file__).resolve().parents[1]
    paths = generate_tracks(output_dir or root / "assets" / "bgm")
    for path in paths.values():
        print(path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
