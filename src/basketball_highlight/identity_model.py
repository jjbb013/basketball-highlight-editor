"""Incremental, versioned appearance prototypes scoped to a single game."""
from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from .appearance import appearance_distance, appearance_vector


def _validated_features(features: Mapping) -> dict:
    if not isinstance(features, Mapping):
        raise ValueError("INVALID_APPEARANCE")
    return appearance_vector(
        {name: value["values"] for name, value in features.items()},
        {name: value["quality"] for name, value in features.items()},
    )


def _result(identity_id, confidence, needs_review, second_distance, alternatives, new_identity=False):
    return {
        "identity_id": identity_id,
        "confidence": round(float(confidence), 6),
        "needs_review": bool(needs_review),
        "second_distance": second_distance,
        "alternative_identity_ids": alternatives,
        "new_identity": new_identity,
    }


class LocalIdentityModel:
    """A collection of local prototypes, not a pretrained biometric classifier."""

    VERSION = 1

    def __init__(self, threshold=0.22, margin=0.06):
        self.threshold = float(threshold)
        self.margin = float(margin)
        if not 0 < self.threshold <= 1 or not 0 <= self.margin <= 1:
            raise ValueError("INVALID_IDENTITY_THRESHOLD")
        self.prototypes: dict[str, dict] = {}

    @staticmethod
    def new_identity_id() -> str:
        return f"identity_{uuid4().hex}"

    def assign(self, features: Mapping) -> dict:
        features = _validated_features(features)
        if not features:
            return _result(None, 0.0, True, None, [])
        if not self.prototypes:
            return _result(self.new_identity_id(), 0.0, True, None, [], True)
        scored = []
        for identity_id, prototype in self.prototypes.items():
            distance, weight = appearance_distance(features, prototype["features"])
            if distance is not None and weight > 0:
                scored.append((distance, weight, identity_id))
        scored.sort(key=lambda item: (item[0], item[2]))
        if not scored:
            return _result(None, 0.0, True, None, [])
        distance, weight, identity_id = scored[0]
        second_distance = scored[1][0] if len(scored) > 1 else None
        alternatives = [item[2] for item in scored[:3]]
        prototype_features = self.prototypes[identity_id]["features"]
        clothing_conflict = False
        for name in ("shirt", "pants", "shoes"):
            if name not in features or name not in prototype_features:
                continue
            current_region = features[name]
            prototype_region = prototype_features[name]
            if min(current_region["quality"], prototype_region["quality"]) < 0.25:
                continue
            region_distance, _ = appearance_distance(
                {name: current_region}, {name: prototype_region},
            )
            if region_distance is not None and region_distance > self.threshold / 2:
                clothing_conflict = True
                break
        if second_distance is not None and second_distance - distance < self.margin:
            return _result(None, 0.0, True, second_distance, alternatives)
        if distance <= self.threshold:
            if clothing_conflict:
                # A weighted average must not hide reliable clothing disagreement.
                return _result(None, 0.0, True, second_distance, alternatives)
            confidence = (1.0 - distance / self.threshold) * min(1.0, weight)
            return _result(identity_id, confidence, False, second_distance, alternatives)
        if distance > self.threshold + self.margin:
            return _result(
                self.new_identity_id(), 0.0, True, second_distance, alternatives, True,
            )
        return _result(None, 0.0, True, second_distance, alternatives)

    def observe(self, identity_id: str, features: Mapping) -> None:
        features = _validated_features(features)
        if not identity_id or not features:
            raise ValueError("INVALID_IDENTITY_OBSERVATION")
        old = self.prototypes.get(identity_id, {"features": {}, "samples": 0})
        count = int(old["samples"])
        merged = dict(old["features"])
        for name, value in features.items():
            previous = merged.get(name)
            if previous is None:
                merged[name] = value
                continue
            if len(previous["values"]) != len(value["values"]):
                raise ValueError("IDENTITY_FEATURE_VERSION_MISMATCH")
            averaged = appearance_vector(
                {
                    name: [
                        (first * count + second) / (count + 1)
                        for first, second in zip(previous["values"], value["values"])
                    ]
                },
                {
                    name: (
                        float(previous["quality"]) * count + float(value["quality"])
                    ) / (count + 1)
                },
            )
            # Opposing normalized colors may cancel; retain the newest evidence
            # instead of silently turning the whole region into missing data.
            merged[name] = averaged.get(name, value)
        self.prototypes[identity_id] = {"features": merged, "samples": count + 1}

    def to_dict(self) -> dict:
        return {
            "version": self.VERSION,
            "threshold": self.threshold,
            "margin": self.margin,
            "prototypes": self.prototypes,
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "LocalIdentityModel":
        if not isinstance(data, Mapping) or data.get("version") != cls.VERSION:
            raise ValueError("IDENTITY_MODEL_VERSION_UNSUPPORTED")
        model = cls(data.get("threshold", 0.22), data.get("margin", 0.06))
        prototypes = data.get("prototypes")
        if not isinstance(prototypes, Mapping):
            raise ValueError("INVALID_IDENTITY_MODEL")
        for identity_id, prototype in prototypes.items():
            if (
                not identity_id
                or not isinstance(prototype, Mapping)
                or int(prototype.get("samples", 0)) < 1
            ):
                raise ValueError("INVALID_IDENTITY_MODEL")
            features = _validated_features(prototype.get("features", {}))
            if not features:
                raise ValueError("INVALID_IDENTITY_MODEL")
            model.prototypes[str(identity_id)] = {
                "features": features,
                "samples": int(prototype["samples"]),
            }
        return model
