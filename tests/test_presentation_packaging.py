from pathlib import Path


def test_macos_runtime_contains_presentation_assets():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts/prepare_macos_runtime.sh").read_text(encoding="utf-8")
    assert 'cp -R "$ROOT/assets" "$OUT/assets/"' in script
    assert (root / "assets/fonts/OFL.txt").is_file()
    assert (root / "assets/fonts/NotoSansSC-Regular.ttf").stat().st_size > 1_000_000
    for name in ("electronic_drive", "hip_hop_bounce", "rock_pulse"):
        assert (root / f"assets/bgm/{name}.wav").stat().st_size > 100_000
