"""Privacy-local, quality-weighted appearance features for one game.

The descriptors distinguish people in similar recording conditions. They are not
face recognition and must not be treated as cross-day biometric identification.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from PIL import Image


def appearance_vector(
    regions: Mapping[str, Sequence[float]],
    qualities: Mapping[str, float],
) -> dict:
    """Normalize each valid region independently and retain its evidence quality."""
    result = {}
    for name, values in regions.items():
        quality = float(qualities.get(name, 0.0))
        vector = [float(value) for value in values]
        if (
            not vector
            or not math.isfinite(quality)
            or not all(math.isfinite(value) for value in vector)
        ):
            raise ValueError("INVALID_APPEARANCE")
        quality = max(0.0, min(1.0, quality))
        norm = math.sqrt(sum(value * value for value in vector))
        if quality > 0 and norm > 0:
            result[name] = {
                "values": [value / norm for value in vector],
                "quality": quality,
            }
    return result


def appearance_distance(left: Mapping, right: Mapping) -> tuple[float | None, float]:
    """Return weighted cosine distance using only regions visible in both samples."""
    numerator = denominator = 0.0
    for name in left.keys() & right.keys():
        first, second = left[name], right[name]
        if len(first["values"]) != len(second["values"]):
            continue
        weight = float(first["quality"]) * float(second["quality"])
        cosine = sum(
            x * y for x, y in zip(first["values"], second["values"])
        )
        numerator += weight * (1.0 - max(-1.0, min(1.0, cosine)))
        denominator += weight
    if denominator == 0:
        return None, 0.0
    return numerator / denominator, denominator


def _color_descriptor(region: Image.Image) -> tuple[list[float], float]:
    hsv = np.asarray(region.convert("HSV"), dtype=np.uint8)
    if hsv.size == 0:
        return [], 0.0
    values = []
    for channel, bins in ((0, 12), (1, 4), (2, 4)):
        histogram = np.histogram(hsv[..., channel], bins=bins, range=(0, 256))[0]
        values.extend((histogram / max(1, histogram.sum())).tolist())
    rgb = np.asarray(region.convert("RGB"), dtype=np.float32)
    chroma = rgb / np.maximum(rgb.sum(axis=-1, keepdims=True), 1.0)
    # Hue histograms lose their discrimination when many bins are almost empty.
    # Relative RGB retains color evidence while reducing brightness differences.
    values.extend((np.mean(chroma, axis=(0, 1)) * 3.0).tolist())
    coverage = min(1.0, float(hsv.shape[0] * hsv.shape[1]) / 400.0)
    return values, coverage


def _skin_descriptor(region: Image.Image) -> tuple[list[float], float]:
    hsv = np.asarray(region.convert("HSV"), dtype=np.uint8)
    if hsv.size == 0:
        return [], 0.0
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = (
        ((hue <= 25) | (hue >= 170))
        & (saturation >= 25)
        & (saturation <= 210)
        & (value >= 45)
    )
    count = int(mask.sum())
    if count < 12:
        return [], 0.0
    # Relative skin hue is illumination-sensitive; quality reflects visible support.
    selected = hsv[mask]
    histogram = np.histogram(selected[:, 0], bins=8, range=(0, 256))[0]
    descriptor = (histogram / count).tolist()
    descriptor.extend(
        (np.mean(selected, axis=0) / 255.0).tolist()
    )
    return descriptor, min(1.0, count / 200.0)


def _shape_descriptor(region: Image.Image) -> tuple[list[float], float]:
    gray = np.asarray(region.convert("L").resize((12, 16)), dtype=np.float32)
    horizontal = np.abs(np.diff(gray, axis=1)).ravel()
    vertical = np.abs(np.diff(gray, axis=0)).ravel()
    gradients = np.concatenate((horizontal, vertical))
    histogram = np.histogram(gradients, bins=8, range=(0, 128))[0]
    aspect = region.width / max(1, region.height)
    return [aspect, *(histogram / max(1, histogram.sum())).tolist()], 0.5


def _crop(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    left = max(0, min(image.width, math.floor(box[0])))
    top = max(0, min(image.height, math.floor(box[1])))
    right = max(left, min(image.width, math.ceil(box[2])))
    bottom = max(top, min(image.height, math.ceil(box[3])))
    return image.crop((left, top, right, bottom))


def image_appearance(
    image: Image.Image,
    bbox: Sequence[float],
    *,
    quality: float = 1.0,
    head_bbox: Sequence[float] | None = None,
) -> dict:
    """Extract hair, weak face shape, visible skin and clothing from a person crop."""
    if len(bbox) != 4:
        raise ValueError("INVALID_PERSON_BBOX")
    x1, y1, x2, y2 = (float(value) for value in bbox)
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2, quality)):
        raise ValueError("INVALID_PERSON_BBOX")
    if x2 - x1 < 16 or y2 - y1 < 32 or quality <= 0:
        return {}
    width, height = x2 - x1, y2 - y1
    head = tuple(head_bbox) if head_bbox is not None else (
        x1 + width * 0.2,
        y1,
        x2 - width * 0.2,
        y1 + height * 0.30,
    )
    hx1, hy1, hx2, hy2 = head
    head_height = max(1.0, hy2 - hy1)
    boxes = {
        "hair": (hx1, hy1, hx2, hy1 + head_height * 0.50),
        "face": (hx1, hy1 + head_height * 0.50, hx2, hy2),
        "skin": (hx1, hy1 + head_height * 0.50, hx2, hy2),
        "shirt": (x1 + width * 0.1, y1 + height * 0.30, x2 - width * 0.1, y1 + height * 0.60),
        "pants": (x1 + width * 0.12, y1 + height * 0.60, x2 - width * 0.12, y1 + height * 0.875),
        "shoes": (x1 + width * 0.05, y1 + height * 0.875, x2 - width * 0.05, y2),
    }
    regions = {}
    qualities = {}
    for name, region_box in boxes.items():
        crop = _crop(image, region_box)
        if crop.width < 4 or crop.height < 4:
            continue
        if name == "skin":
            values, support = _skin_descriptor(crop)
        elif name == "face":
            values, support = _shape_descriptor(crop)
        else:
            values, support = _color_descriptor(crop)
        if values and support > 0:
            regions[name] = values
            qualities[name] = support * max(0.0, min(1.0, quality))
    return appearance_vector(regions, qualities)
