"""Narrow YOLO Pose adapter; no private model or image data is serialized."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .inference import load_detector

# 出手/封盖等手臂高举姿态下，人物框上段的衣服采样带会混入手臂和球，
# 上衣颜色分布系统性失真；此时降低上衣特征质量，避免衣着冲突守卫误否决同一人。
RAISED_WRIST_CONFIDENCE = 0.4
RAISED_WRIST_TOP_RATIO = 0.25
RAISED_ARM_SHIRT_QUALITY = 0.25


def adjust_appearance_for_pose(person: dict) -> None:
    """Down-weight the shirt region when a confident wrist is raised."""
    appearance = person.get("appearance") or {}
    shirt = appearance.get("shirt")
    if not shirt:
        return
    try:
        bbox = person["bbox"]
        top, height = float(bbox[1]), max(1.0, float(bbox[3]) - float(bbox[1]))
    except (KeyError, IndexError, TypeError, ValueError):
        return
    raised = any(
        len(wrist) >= 3
        and float(wrist[2]) >= RAISED_WRIST_CONFIDENCE
        and float(wrist[1]) <= top + RAISED_WRIST_TOP_RATIO * height
        for wrist in person.get("wrists") or []
    )
    if raised:
        shirt["quality"] = float(shirt.get("quality", 0.0)) * RAISED_ARM_SHIRT_QUALITY


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

    def __init__(
        self, model_path: str | Path, device: str | None = None, loader=None,
        *, include_appearance: bool = False,
    ):
        self.model_path = Path(model_path)
        self._loader = loader or (lambda path: load_detector(path, device=device))
        self._include_appearance = include_appearance
        self._model = None

    def predict(self, image: Any, time_ms: int) -> list[dict]:
        if self._model is None:
            self._model = self._loader(self.model_path)
        results = self._model.predict(image, verbose=False)
        return normalize_pose_result(results[0], time_ms) if results else []

    def predict_batch(
        self,
        images: list[Any],
        time_ms: list[int],
        *,
        device: str | None = None,
        conf: float = 0.25,
        imgsz: int = 960,
        batch: int = 8,
    ) -> list[list[dict]]:
        """Run source-frame pose inference without losing frame timestamps."""
        if len(images) != len(time_ms):
            raise ValueError("POSE_FRAME_TIME_MISMATCH")
        if not images:
            return []
        if self._model is None:
            self._model = self._loader(self.model_path)
        options = {"verbose": False, "conf": conf, "imgsz": imgsz, "batch": batch}
        if device is not None:
            options["device"] = device
        results = self._model.predict(images, **options)
        output = []
        for result, stamp in zip(results, time_ms):
            people = normalize_pose_result(result, stamp)
            original = getattr(result, "orig_img", None)
            if self._include_appearance and original is not None:
                from PIL import Image
                import numpy as np
                from .appearance import image_appearance
                image = original if isinstance(original, Image.Image) else Image.fromarray(
                    np.asarray(original)[..., :3][..., ::-1]
                )
                for person in people:
                    person["appearance"] = image_appearance(
                        image, person["bbox"], quality=person["detection_confidence"],
                    )
                    adjust_appearance_for_pose(person)
            output.append(people)
        return output
