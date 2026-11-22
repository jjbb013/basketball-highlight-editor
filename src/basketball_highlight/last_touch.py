"""Conservative final-ball-contact inference from short YOLO Pose windows."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

CONTACT_DISTANCE = 0.25
RELEASE_DISTANCE = 0.35
MIN_WRIST_CONFIDENCE = 0.5
MAX_FRAME_GAP_MS = 450


def _wrist_distance(person: Mapping[str, Any], ball: Sequence[float]) -> float | None:
    try:
        bbox = person["bbox"]
        height = max(1.0, float(bbox[3]) - float(bbox[1]))
        distances = [
            math.hypot(float(ball[0]) - float(wrist[0]), float(ball[1]) - float(wrist[1])) / height
            for wrist in person.get("wrists") or []
            if len(wrist) >= 3 and float(wrist[2]) >= MIN_WRIST_CONFIDENCE
        ]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return min(distances) if distances else None


def _track_candidates(frames: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    observations = []
    for frame in frames:
        try:
            time_ms = int(frame["time_ms"])
            ball = frame.get("ball")
            distance = _wrist_distance(frame, ball) if ball is not None else None
        except (KeyError, TypeError, ValueError):
            continue
        observations.append({"time_ms": time_ms, "distance": distance, "ball": ball})
    observations.sort(key=lambda item: item["time_ms"])
    candidates = []
    for end in range(len(observations) - 1):
        contact = observations[end]
        distance = contact["distance"]
        if distance is None or distance > CONTACT_DISTANCE:
            continue
        start = end
        while (
            start > 0
            and observations[start - 1]["distance"] is not None
            and observations[start - 1]["distance"] <= CONTACT_DISTANCE
            and contact["time_ms"] - observations[start - 1]["time_ms"] <= MAX_FRAME_GAP_MS
        ):
            start -= 1
        duration_ms = contact["time_ms"] - observations[start]["time_ms"]
        if duration_ms < 50:
            continue
        # Only the final contact of a continuous hand-ball segment can be release.
        next_observation = observations[end + 1]
        if next_observation["distance"] is not None and next_observation["distance"] <= CONTACT_DISTANCE:
            continue
        release = next(
            (
                item for item in observations[end + 1:]
                if item["time_ms"] - contact["time_ms"] <= MAX_FRAME_GAP_MS
                and item["distance"] is not None
                and item["distance"] >= RELEASE_DISTANCE
            ),
            None,
        )
        if release is None:
            continue
        proximity = max(0.0, 1.0 - distance / CONTACT_DISTANCE)
        release_strength = min(1.0, release["distance"] / 0.6)
        duration_support = min(1.0, duration_ms / 150.0)
        candidates.append({
            "touch_time_ms": contact["time_ms"],
            "confidence": round(0.5 * proximity + 0.3 * release_strength + 0.2 * duration_support, 6),
            "contact_start_ms": observations[start]["time_ms"],
            "release_time_ms": release["time_ms"],
        })
    return candidates


def _review(alternatives: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "review",
        "local_track_id": None,
        "touch_time_ms": None,
        "confidence": 0.0,
        "alternatives": alternatives,
    }


def select_last_touch(
    frames: Sequence[Mapping[str, Any]],
    rim: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select the last released contact, or explicitly require human review.

    ``rim`` is reserved for calibrated trajectory direction; its absence never
    turns a missing contact into an automatic assignment.
    """
    tracks: dict[str, list[Mapping[str, Any]]] = {}
    for frame in frames:
        if not isinstance(frame, Mapping) or frame.get("track_id") is None:
            continue
        tracks.setdefault(str(frame["track_id"]), []).append(frame)
    candidates = []
    for track_id, observations in tracks.items():
        for contact in _track_candidates(observations):
            candidates.append({"local_track_id": track_id, **contact})
    candidates.sort(
        key=lambda item: (item["touch_time_ms"], item["confidence"], item["local_track_id"]),
        reverse=True,
    )
    if not candidates:
        return _review([])
    winner = candidates[0]
    if len(candidates) > 1:
        runner_up = candidates[1]
        simultaneous = abs(winner["touch_time_ms"] - runner_up["touch_time_ms"]) < 100
        ambiguous = abs(winner["confidence"] - runner_up["confidence"]) < 0.15
        if simultaneous and ambiguous:
            return _review(candidates)
    return {
        "status": "identified",
        "local_track_id": winner["local_track_id"],
        "touch_time_ms": winner["touch_time_ms"],
        "confidence": winner["confidence"],
        "contact_start_ms": winner["contact_start_ms"],
        "release_time_ms": winner["release_time_ms"],
        "alternatives": candidates[1:],
    }
