"""Narrow YOLO Pose adapter; no private model or image data is serialized."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .inference import load_detector


def _values(value):
    if value is None:
        return []
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return value.tolist() if hasattr(value, "tolist") else value


def normalize_pose_result(result: Any, time_ms: int) -> list[dict]:
    """Return person boxes and COCO wrists (indices 9, 10) in source pixels."""
    keypoints = getattr(result, "keypoints", None)
    coordinates = _values(getattr(keypoints, "xy", None))
    confidences = _values(getattr(keypoints, "conf", None))
    boxes = getattr(result, "boxes", None)
    people = []
    for index, box in enumerate([] if boxes is None else boxes):
        try:
            bbox = [float(value) for value in _values(box.xyxy[0])]
            confidence = float(_values(box.conf[0]))
        except (AttributeError, IndexError, TypeError, ValueError):
            continue
        if (
            len(bbox) != 4
            or not all(math.isfinite(value) for value in (*bbox, confidence))
            or bbox[2] <= bbox[0]
            or bbox[3] <= bbox[1]
        ):
            continue
        points = coordinates[index] if index < len(coordinates) else []
        scores = confidences[index] if index < len(confidences) else []
        wrists = []
        for keypoint_index in (9, 10):
            if keypoint_index >= len(points):
                continue
            point = points[keypoint_index]
            score = scores[keypoint_index] if keypoint_index < len(scores) else 0.0
            wrists.append([float(point[0]), float(point[1]), float(score)])
        people.append({
            "time_ms": int(time_ms),
            "bbox": bbox,
            "wrists": wrists,
            "detection_confidence": confidence,
        })
    return people


class PoseDetector:
    """Lazy wrapper so feature normalization does not load native ML runtimes."""

    def __init__(self, model_path: str | Path, device: str | None = None, loader=None):
        self.model_path = Path(model_path)
        self._loader = loader or (lambda path: load_detector(path, device=device))
        self._model = None

    def predict(self, image: Any, time_ms: int) -> list[dict]:
        if self._model is None:
            self._model = self._loader(self.model_path)
        results = self._model.predict(image, verbose=False)
        return normalize_pose_result(results[0], time_ms) if results else []
