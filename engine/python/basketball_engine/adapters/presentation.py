"""Optional cover art and background music for finished highlight exports."""
from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

from .export import run_encoded_ffmpeg, video_codec_options, video_codecs
from .hdr import SDR_TAGS
from ..media_tools import resolve_media_tool

COVER_STYLES = ("court", "poster", "photo")
BGM_TRACKS = ("electronic_drive", "hip_hop_bounce", "rock_pulse")
DEFAULT_COVER = {
    "enabled": True,
    "duration_ms": 3000,
    "style": "court",
    "title": None,
    "subtitle": None,
    "background_path": None,
    "accent_color": "#F97316",
}
DEFAULT_AUDIO = {
    "enabled": True,
    "track": "electronic_drive",
    "custom_path": None,
    "volume": 0.2,
}


def _mapping(value: Any, code: str) -> Mapping:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(code)
    return value


def _optional_text(value: Any, code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(code)
    return value.strip() or None


def normalize_presentation(config: Mapping | None) -> dict:
    """Return a JSON-safe, fully materialized presentation configuration."""
    config = _mapping(config, "INVALID_PRESENTATION")
    raw_cover = _mapping(config.get("cover"), "INVALID_COVER_CONFIG")
    raw_audio = _mapping(config.get("audio"), "INVALID_AUDIO_CONFIG")
    cover = {**DEFAULT_COVER, **raw_cover}
    audio = {**DEFAULT_AUDIO, **raw_audio}
    if type(cover["enabled"]) is not bool:
        raise ValueError("INVALID_COVER_ENABLED")
    if type(cover["duration_ms"]) is not int or not 0 <= cover["duration_ms"] <= 10_000:
        raise ValueError("INVALID_COVER_DURATION")
    if cover["style"] not in COVER_STYLES:
        raise ValueError("INVALID_COVER_STYLE")
    cover["title"] = _optional_text(cover["title"], "INVALID_COVER_TITLE")
    cover["subtitle"] = _optional_text(cover["subtitle"], "INVALID_COVER_SUBTITLE")
    cover["background_path"] = _optional_text(cover["background_path"], "INVALID_COVER_BACKGROUND")
    if cover["style"] == "photo" and not cover["background_path"]:
        raise ValueError("COVER_BACKGROUND_REQUIRED")
    try:
        color = ImageColor.getrgb(cover["accent_color"])
    except (ValueError, TypeError) as exc:
        raise ValueError("INVALID_ACCENT_COLOR") from exc
    if not isinstance(cover["accent_color"], str) or len(cover["accent_color"]) != 7:
        raise ValueError("INVALID_ACCENT_COLOR")
    cover["accent_color"] = "#%02X%02X%02X" % color
    if type(audio["enabled"]) is not bool:
        raise ValueError("INVALID_AUDIO_ENABLED")
    if audio["track"] not in BGM_TRACKS:
        raise ValueError("INVALID_BGM_TRACK")
    audio["custom_path"] = _optional_text(audio["custom_path"], "INVALID_BGM_PATH")
    if isinstance(audio["volume"], bool):
        raise ValueError("INVALID_BGM_VOLUME")
    try:
        audio["volume"] = float(audio["volume"])
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_BGM_VOLUME") from exc
    if not math.isfinite(audio["volume"]) or not 0 <= audio["volume"] <= 1:
        raise ValueError("INVALID_BGM_VOLUME")
    return {"cover": cover, "audio": audio}


def _runtime_root() -> Path:
    configured = os.environ.get("BHE_RUNTIME_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def resolve_bgm(config: Mapping) -> Path | None:
    """Resolve only allow-listed built-ins or an explicit existing local file."""
    audio = normalize_presentation(config)["audio"]
    if not audio["enabled"]:
        return None
    if audio["custom_path"]:
        path = Path(audio["custom_path"]).expanduser().resolve()
    else:
        path = _runtime_root() / "assets" / "bgm" / f"{audio['track']}.wav"
    if not path.is_file():
        raise OSError(f"BGM_NOT_FOUND: {path}")
    return path


def _font(size: int) -> ImageFont.FreeTypeFont:
    path = _runtime_root() / "assets" / "fonts" / "NotoSansSC-Regular.ttf"
    if not path.is_file():
        raise OSError(f"COVER_FONT_NOT_FOUND: {path}")
    return ImageFont.truetype(str(path), max(12, int(size)))


def _fitted_font(draw: ImageDraw.ImageDraw, text: str, width: int, height: int) -> ImageFont.FreeTypeFont:
    low, high = 12, max(12, height)
    while low < high:
        size = (low + high + 1) // 2
        font = _font(size)
        bounds = draw.textbbox((0, 0), text, font=font)
        if bounds[2] - bounds[0] <= width:
            low = size
        else:
            high = size - 1
    return _font(low)


def _background(size: tuple[int, int], style: str, accent: tuple[int, int, int], background_path: str | None) -> Image.Image:
    width, height = size
    if background_path:
        try:
            with Image.open(background_path) as source:
                background = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), size)
        except (OSError, ValueError) as exc:
            raise OSError(f"COVER_BACKGROUND_NOT_FOUND: {background_path}") from exc
        overlay = Image.new("RGBA", size, (7, 12, 25, 125))
        return Image.alpha_composite(background.convert("RGBA"), overlay).convert("RGB")
    top = (10, 18, 34) if style == "poster" else tuple(max(0, channel // 3) for channel in accent)
    bottom = (22, 31, 51) if style == "poster" else (12, 20, 32)
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        fraction = y / max(1, height - 1)
        color = tuple(round(a + (b - a) * fraction) for a, b in zip(top, bottom))
        draw.line((0, y, width, y), fill=color)
    return image


def render_cover(
    path: Path,
    size: tuple[int, int],
    config: Mapping | None,
    title: str,
    subtitle: str | None = None,
) -> Path:
    """Render one RGB PNG; all text and backgrounds remain local user content."""
    width, height = (int(value) for value in size)
    if width < 64 or height < 64 or width % 2 or height % 2:
        raise ValueError("INVALID_COVER_SIZE")
    cover = normalize_presentation({"cover": dict(config or {})})["cover"]
    accent = ImageColor.getrgb(cover["accent_color"])
    image = _background(size, cover["style"], accent, cover["background_path"]).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    margin = int(width * 0.07)
    if cover["style"] == "court":
        line = (*accent, 135)
        draw.rectangle((int(width * 0.55), int(height * 0.13), int(width * 0.94), int(height * 0.87)), outline=line, width=max(2, width // 320))
        radius = int(height * 0.19)
        center = (int(width * 0.75), int(height * 0.5))
        draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=line, width=max(2, width // 320))
        draw.line((int(width * 0.55), int(height * 0.5), int(width * 0.94), int(height * 0.5)), fill=line, width=max(2, width // 320))
    else:
        draw.rectangle((0, 0, max(8, width // 32), height), fill=(*accent, 255))
        draw.rectangle((margin, int(height * 0.18), margin + int(width * 0.18), int(height * 0.20)), fill=(*accent, 255))
    label_font = _font(max(13, int(height * 0.052)))
    draw.text((margin, int(height * 0.10)), "PLAYER HIGHLIGHTS", font=label_font, fill=(*accent, 255))
    title = str(title or cover["title"] or "进球集锦")
    title_font = _fitted_font(draw, title, int(width * 0.86), int(height * 0.32))
    title_y = int(height * 0.36)
    draw.text((margin + 2, title_y + 3), title, font=title_font, fill=(0, 0, 0, 170))
    draw.text((margin, title_y), title, font=title_font, fill=(255, 255, 255, 255))
    subtitle = subtitle or cover["subtitle"] or "进球集锦 · BASKETBALL"
    subtitle_font = _fitted_font(draw, subtitle, int(width * 0.80), int(height * 0.075))
    draw.text((margin, int(height * 0.76)), subtitle, font=subtitle_font, fill=(235, 239, 246, 245))
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output, format="PNG")
    return output


def _probe_media(path: Path) -> dict:
    result = subprocess.run(
        [
            resolve_media_tool("ffprobe"), "-v", "error",
            "-show_entries", "stream=codec_type,width,height,channels,avg_frame_rate,duration:format=duration",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    data = json.loads(result.stdout)
    video = next((stream for stream in data["streams"] if stream["codec_type"] == "video"), None)
    if not video:
        raise OSError("EXPORT_VIDEO_STREAM_MISSING")
    audio = next((stream for stream in data["streams"] if stream["codec_type"] == "audio"), None)
    rate = Fraction(video.get("avg_frame_rate") or "25")
    if rate <= 0:
        rate = Fraction(25)
    duration = float(video.get("duration") or data["format"]["duration"])
    return {
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": rate,
        "has_audio": audio is not None,
        "audio_channels": int(audio.get("channels") or 2) if audio else 0,
        "duration_s": duration,
    }


def _audio_channels(path: Path) -> int:
    result = subprocess.run(
        [
            resolve_media_tool("ffprobe"), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=channels", "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True, timeout=30,
    )
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        raise OSError(f"BGM_AUDIO_STREAM_MISSING: {path}")
    return int(streams[0]["channels"])


def _audio_filter(channels: int) -> str:
    if channels == 1:
        return "aresample=48000,aformat=sample_fmts=fltp,pan=stereo|c0=c0|c1=c0"
    return "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"


def _presentation_command(
    source: Path,
    output: Path,
    codec: str,
    media: Mapping,
    config: Mapping,
    cover_path: Path | None,
    bgm_path: Path | None,
) -> list[str]:
    cover_s = config["cover"]["duration_ms"] / 1000 if cover_path else 0.0
    total_s = media["duration_s"] + cover_s
    width, height = media["width"] // 2 * 2, media["height"] // 2 * 2
    fps = str(media["fps"])
    fit = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    graph = [f"[0:v:0]setpts=PTS-STARTPTS,fps={fps},{fit},format=yuv420p[base]"]
    inputs = [resolve_media_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    if cover_path:
        inputs += ["-loop", "1", "-framerate", fps, "-i", str(cover_path)]
        graph.append(f"[1:v:0]setpts=PTS-STARTPTS,fps={fps},{fit},trim=duration={cover_s:.3f},setpts=PTS-STARTPTS[cover]")
        graph.append("[cover][base]concat=n=2:v=1:a=0[vout]")
    else:
        graph.append("[base]null[vout]")
    if bgm_path:
        bgm_index = 2 if cover_path else 1
        inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
    original_label = None
    if media["has_audio"]:
        graph.append(f"[0:a:0]{_audio_filter(media['audio_channels'])},asetpts=PTS-STARTPTS[original]")
        if cover_path:
            graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={cover_s:.3f}[silence]")
            graph.append("[silence][original]concat=n=2:v=0:a=1[original_delayed]")
            original_label = "original_delayed"
        else:
            original_label = "original"
    if bgm_path:
        graph.append(
            f"[{bgm_index}:a:0]{_audio_filter(_audio_channels(bgm_path))},"
            f"volume={config['audio']['volume']:.4f},atrim=duration={total_s:.3f}[bed]"
        )
        if original_label:
            graph.append(f"[{original_label}][bed]amix=inputs=2:duration=first:normalize=0[aout]")
        else:
            graph.append("[bed]anull[aout]")
    elif original_label:
        graph.append(f"[{original_label}]anull[aout]")
    has_audio = bool(bgm_path or original_label)
    return [
        *inputs,
        "-filter_complex", ";".join(graph),
        "-map", "[vout]", *(["-map", "[aout]"] if has_audio else ["-an"]),
        *video_codec_options(codec), *SDR_TAGS,
        *(["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"] if has_audio else []),
        "-t", f"{total_s:.3f}", "-movflags", "+faststart", str(output),
    ]


def enhance_video(
    path: Path,
    config: Mapping | None,
    title: str,
    subtitle: str | None = None,
    cancel_check=None,
    process_callback=None,
) -> dict:
    """Enhance a finished export in place with a restorable atomic handoff."""
    path = Path(path)
    normalized = normalize_presentation(config)
    started = time.perf_counter()
    media = _probe_media(path)
    cover_ms = normalized["cover"]["duration_ms"] if normalized["cover"]["enabled"] else 0
    bgm_path = resolve_bgm(normalized)
    if cover_ms == 0 and bgm_path is None:
        return {
            "changed": False,
            "duration_ms": round(media["duration_s"] * 1000),
            "cover_duration_ms": 0,
            "processing_ms": round((time.perf_counter() - started) * 1000),
        }
    expected_ms = round(media["duration_s"] * 1000) + cover_ms
    with tempfile.TemporaryDirectory(prefix=".bhe-presentation-", dir=path.parent) as temporary:
        work = Path(temporary)
        cover_path = None
        if cover_ms:
            cover_path = render_cover(
                work / "cover.png",
                (media["width"] // 2 * 2, media["height"] // 2 * 2),
                normalized["cover"],
                title,
                subtitle,
            )
        backup = work / "original.mp4"
        path.replace(backup)
        try:
            run_encoded_ffmpeg(
                lambda codec: _presentation_command(
                    backup, path, codec, media, normalized, cover_path, bgm_path,
                ),
                path,
                video_codecs(),
                cancel_check=cancel_check,
                process_callback=process_callback,
            )
            result = _probe_media(path)
            tolerance = max(0.15, expected_ms / 1000 * 0.02)
            if abs(result["duration_s"] - expected_ms / 1000) > tolerance:
                raise OSError("PRESENTATION_DURATION_MISMATCH")
            if bgm_path and not result["has_audio"]:
                raise OSError("PRESENTATION_AUDIO_MISSING")
        except Exception:
            path.unlink(missing_ok=True)
            backup.replace(path)
            raise
    return {
        "changed": True,
        "duration_ms": expected_ms,
        "cover_duration_ms": cover_ms,
        "processing_ms": round((time.perf_counter() - started) * 1000),
    }
