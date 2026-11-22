"""Same-game player tracking, final-touch inference and local identity clustering.

Local track IDs describe only a short observation window. Identity prototypes
contain appearance descriptors, never photographs, and are not cross-day biometrics.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .appearance import appearance_distance, appearance_vector
from .identity_model import LocalIdentityModel
from .last_touch import select_last_touch

ALGORITHM_VERSION = "yolo-pose-last-touch-local-appearance-v1"
MAX_TRACK_GAP_MS = 350


def identity_model_from_rows(rows: Sequence[Mapping[str, Any]]) -> LocalIdentityModel:
    """Restore only local-game prototypes; names remain in the private database."""
    model = LocalIdentityModel()
    for row in rows:
        prototype = row.get("prototype_json", {})
        if isinstance(prototype, str):
            import json
            prototype = json.loads(prototype or "{}")
        if not prototype or int(row.get("sample_count", 0)) < 1:
            continue
        model.prototypes[str(row["id"])] = {
            "features": prototype,
            "samples": int(row["sample_count"]),
        }
    return LocalIdentityModel.from_dict(model.to_dict())


def expanded_roi(
    roi: Sequence[float], source_width: int, source_height: int, *, factor: float = 2.5,
) -> list[int]:
    """Expand the ball search around the rim without enlarging the pose crop."""
    if len(roi) != 4 or factor < 1 or source_width <= 0 or source_height <= 0:
        raise ValueError("PLAYER_ROI_INVALID")
    x1, y1, x2, y2 = (float(value) for value in roi)
    if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
        raise ValueError("PLAYER_ROI_INVALID")
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half_width, half_height = (x2 - x1) * factor / 2, (y2 - y1) * factor / 2
    left, right = max(0, round(cx - half_width)), min(source_width, round(cx + half_width))
    top, bottom = max(0, round(cy - half_height)), min(source_height, round(cy + half_height))
    if right <= left or bottom <= top:
        raise ValueError("PLAYER_ROI_INVALID")
    return [left, top, right, bottom]


def person_ball_roi(
    bbox: Sequence[float], source_width: int, source_height: int,
) -> list[int] | None:
    """Upscale a person and their hands without cropping away a held ball."""
    values = _bbox_values(bbox)
    if values is None or source_width <= 0 or source_height <= 0:
        return None
    x1, y1, x2, y2 = values
    side = min(640.0, max(128.0, (y2 - y1) * 1.6))
    side = min(side, float(source_width), float(source_height))
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    left = round(min(max(0.0, cx - side / 2), source_width - side))
    top = round(min(max(0.0, cy - side / 2), source_height - side))
    return [left, top, round(left + side), round(top + side)]


def _bbox_values(bbox: Sequence[float]) -> tuple[float, float, float, float] | None:
    try:
        values = tuple(float(value) for value in bbox)
    except (TypeError, ValueError):
        return None
    if len(values) != 4 or not all(math.isfinite(value) for value in values):
        return None
    if values[2] <= values[0] or values[3] <= values[1]:
        return None
    return values


def _track_cost(last: Mapping[str, Any], current: Mapping[str, Any]) -> float | None:
    first, second = _bbox_values(last["bbox"]), _bbox_values(current["bbox"])
    if first is None or second is None:
        return None
    height = max(1.0, (first[3] - first[1] + second[3] - second[1]) / 2)
    distance = math.hypot(
        (first[0] + first[2] - second[0] - second[2]) / 2,
        (first[1] + first[3] - second[1] - second[3]) / 2,
    ) / height
    scale = abs(math.log(max(1.0, second[3] - second[1]) / max(1.0, first[3] - first[1])))
    appearance, _ = appearance_distance(
        last.get("appearance") or {}, current.get("appearance") or {},
    )
    return distance + scale * 0.4 + (appearance or 0.0) * 0.25


def link_people(frames: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Greedily associate short person tracks by motion, scale and appearance.

    One-to-one matching prevents two detections in a frame sharing a track.
    A gap or implausible movement starts a new local track instead of forcing
    a cross-window identity match.
    """
    tracks: dict[str, dict[str, Any]] = {}
    linked: list[dict[str, Any]] = []
    for frame in sorted(frames, key=lambda item: int(item["time_ms"])):
        time_ms = int(frame["time_ms"])
        people = sorted(
            (person for person in frame.get("people", []) if _bbox_values(person.get("bbox", []))),
            key=lambda person: (float(person["bbox"][0]), float(person["bbox"][1])),
        )
        costs = []
        for person_index, person in enumerate(people):
            for track_id, track in tracks.items():
                gap = time_ms - int(track["time_ms"])
                if gap <= 0 or gap > MAX_TRACK_GAP_MS:
                    continue
                cost = _track_cost(track, person)
                if cost is not None and cost <= 0.95:
                    costs.append((cost, track_id, person_index))
        used_tracks, used_people = set(), set()
        assignments = {}
        for _, track_id, person_index in sorted(costs):
            if track_id in used_tracks or person_index in used_people:
                continue
            assignments[person_index] = track_id
            used_tracks.add(track_id)
            used_people.add(person_index)
        for index, person in enumerate(people):
            track_id = assignments.get(index) or f"track_{len(tracks) + 1:04d}"
            observation = {**person, "time_ms": time_ms, "track_id": track_id}
            tracks[track_id] = observation
            linked.append(observation)
    return linked


def _aggregate_appearance(observations: Sequence[Mapping[str, Any]]) -> dict:
    samples = [item.get("appearance") or {} for item in observations]
    names = set().union(*(sample.keys() for sample in samples)) if samples else set()
    regions, qualities = {}, {}
    for name in names:
        values = [sample[name] for sample in samples if name in sample]
        support = sum(max(0.0, float(value.get("quality", 0.0))) for value in values)
        if support <= 0:
            continue
        size = len(values[0].get("values", []))
        if not size or any(len(value.get("values", [])) != size for value in values):
            continue
        regions[name] = [
            sum(float(value["values"][index]) * float(value.get("quality", 0.0)) for value in values) / support
            for index in range(size)
        ]
        qualities[name] = support / len(values) * min(1.0, len(values) / 3)
    return appearance_vector(regions, qualities) if regions else {}


def analyze_player_event(
    frames: Sequence[Mapping[str, Any]],
    event_time_ms: int,
    identity_model: LocalIdentityModel,
) -> dict[str, Any]:
    """Attribute only a supported last release before the specified basket."""
    event_time_ms = int(event_time_ms)
    # Associate the complete window together; per-frame IDs are not identities.
    balls = {int(frame["time_ms"]): frame.get("ball") for frame in frames}
    linked = [
        {**person, "ball": balls.get(int(person["time_ms"]))}
        for person in link_people(frames)
        if 0 <= event_time_ms - int(person["time_ms"]) <= 6000
    ]
    touch = select_last_touch(linked)
    identity = {
        "identity_id": None,
        "confidence": 0.0,
        "needs_review": True,
        "new_identity": False,
        "second_distance": None,
        "alternative_identity_ids": [],
    }
    appearance_samples = []
    if touch["status"] == "identified":
        appearance_samples = [
            person for person in linked
            if person["track_id"] == touch["local_track_id"]
            and abs(int(person["time_ms"]) - int(touch["touch_time_ms"])) <= 250
        ]
    features = _aggregate_appearance(appearance_samples)
    if features:
        identity = identity_model.assign(features)
        if identity["identity_id"] is not None:
            identity_model.observe(identity["identity_id"], features)
    needs_review = touch["status"] != "identified" or identity["needs_review"]
    return {
        "event_time_ms": event_time_ms,
        "status": "review" if needs_review else "identified",
        "needs_review": needs_review,
        "touch": touch,
        "identity": identity,
        "appearance_samples": len(appearance_samples),
        "model": identity_model.to_dict(),
        "algorithm_version": ALGORITHM_VERSION,
    }
