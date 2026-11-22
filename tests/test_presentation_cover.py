from pathlib import Path

import pytest
from PIL import Image

from engine.python.basketball_engine.adapters.presentation import (
    normalize_presentation,
    render_cover,
)


def test_defaults_match_requested_cover_and_music_behavior():
    config = normalize_presentation({})
    assert config["cover"] == {
        "enabled": True,
        "duration_ms": 3000,
        "style": "court",
        "title": None,
        "subtitle": None,
        "background_path": None,
        "accent_color": "#F97316",
    }
    assert config["audio"] == {
        "enabled": True,
        "track": "electronic_drive",
        "custom_path": None,
        "volume": 0.2,
    }


def test_custom_values_do_not_discard_unspecified_defaults():
    config = normalize_presentation({
        "cover": {"enabled": False, "style": "poster", "accent_color": "#112233"},
        "audio": {"volume": 0.35, "track": "rock_pulse"},
    })
    assert config["cover"]["duration_ms"] == 3000
    assert not config["cover"]["enabled"]
    assert config["cover"]["accent_color"] == "#112233"
    assert config["audio"]["volume"] == 0.35
    assert config["audio"]["track"] == "rock_pulse"


@pytest.mark.parametrize("cover, message", [
    ({"style": "unknown"}, "INVALID_COVER_STYLE"),
    ({"duration_ms": -1}, "INVALID_COVER_DURATION"),
    ({"duration_ms": 10001}, "INVALID_COVER_DURATION"),
    ({"accent_color": "orange"}, "INVALID_ACCENT_COLOR"),
    ({"style": "photo"}, "COVER_BACKGROUND_REQUIRED"),
])
def test_invalid_cover_configuration_is_rejected(cover, message):
    with pytest.raises(ValueError, match=message):
        normalize_presentation({"cover": cover})


@pytest.mark.parametrize("volume", [-0.01, 1.01, float("nan"), True])
def test_invalid_music_volume_is_rejected(volume):
    with pytest.raises(ValueError, match="INVALID_BGM_VOLUME"):
        normalize_presentation({"audio": {"volume": volume}})


def test_unknown_builtin_track_is_rejected():
    with pytest.raises(ValueError, match="INVALID_BGM_TRACK"):
        normalize_presentation({"audio": {"track": "unknown"}})


@pytest.mark.parametrize("style", ["court", "poster"])
def test_cover_styles_render_chinese_and_long_names(tmp_path, style):
    target = tmp_path / f"{style}.png"
    render_cover(
        target,
        (320, 180),
        {"style": style},
        "Will 与一个非常长的中文球员名字",
        "进球集锦",
    )
    with Image.open(target) as image:
        assert image.mode == "RGB"
        assert image.size == (320, 180)
        assert len(image.getcolors(maxcolors=100000)) > 10


def test_photo_cover_uses_custom_background_and_accent(tmp_path):
    background = tmp_path / "background.png"
    Image.new("RGB", (640, 360), (20, 120, 80)).save(background)
    target = tmp_path / "photo.png"
    render_cover(
        target,
        (320, 180),
        {"style": "photo", "background_path": str(background), "accent_color": "#AA2244"},
        "Will",
        "10 GOALS",
    )
    with Image.open(target) as image:
        assert image.mode == "RGB"
        assert image.size == (320, 180)
        assert image.getpixel((0, 0)) != (20, 120, 80)


def test_missing_custom_background_is_an_explicit_error(tmp_path):
    with pytest.raises(OSError, match="COVER_BACKGROUND_NOT_FOUND"):
        render_cover(
            tmp_path / "cover.png",
            (320, 180),
            {"style": "photo", "background_path": str(tmp_path / "missing.png")},
            "Will",
        )


def test_odd_output_dimensions_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="INVALID_COVER_SIZE"):
        render_cover(tmp_path / "cover.png", (321, 180), {}, "Will")
