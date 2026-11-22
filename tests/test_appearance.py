import numpy as np
import pytest
from PIL import Image

from basketball_highlight.appearance import (
    appearance_distance,
    appearance_vector,
    image_appearance,
)


def sample(shirt, skin=(0.7, 0.5, 0.4), quality=1.0):
    return appearance_vector(
        {"shirt": shirt, "skin": skin, "hair": (0.1, 0.1, 0.1)},
        {"shirt": quality, "skin": 0.8, "hair": 0.6},
    )


def test_same_appearance_has_zero_distance_and_full_weight():
    distance, weight = appearance_distance(sample((10, 20, 30)), sample((10, 20, 30)))
    assert distance == pytest.approx(0.0)
    assert weight == pytest.approx(2.0)


def test_missing_region_does_not_become_black_evidence():
    left = sample((0.8, 0.2, 0.1))
    right = appearance_vector({"shirt": (0.8, 0.2, 0.1)}, {"shirt": 1.0})
    distance, weight = appearance_distance(left, right)
    assert distance == pytest.approx(0.0)
    assert weight == pytest.approx(1.0)


def test_no_common_region_requires_review():
    left = appearance_vector({"shirt": (1, 0, 0)}, {"shirt": 1})
    right = appearance_vector({"pants": (1, 0, 0)}, {"pants": 1})
    assert appearance_distance(left, right) == (None, 0.0)


def test_non_finite_vectors_are_rejected():
    with pytest.raises(ValueError, match="INVALID_APPEARANCE"):
        appearance_vector({"shirt": (float("nan"),)}, {"shirt": 1})


def test_zero_quality_region_is_not_used_as_evidence():
    assert appearance_vector({"shirt": (1, 0, 0)}, {"shirt": 0}) == {}


def person_image(shirt):
    pixels = np.zeros((200, 100, 3), dtype=np.uint8)
    pixels[:30, 25:75] = (35, 25, 20)
    pixels[30:60, 25:75] = (170, 125, 95)
    pixels[60:120, :] = shirt
    pixels[120:175, :] = (35, 45, 90)
    pixels[175:, 10:90] = (220, 220, 220)
    return Image.fromarray(pixels, "RGB")


def test_image_features_separate_hair_skin_clothing_and_shape():
    features = image_appearance(person_image((210, 40, 30)), (0, 0, 100, 200))
    assert {"hair", "face", "skin", "shirt", "pants", "shoes"} <= features.keys()
    assert len(features["shirt"]["values"]) > 3
    assert features["shirt"]["quality"] > 0.5
    assert features["face"]["quality"] > 0


def test_image_features_distinguish_different_shirts():
    red = image_appearance(person_image((210, 40, 30)), (0, 0, 100, 200))
    blue = image_appearance(person_image((30, 60, 210)), (0, 0, 100, 200))
    same, _ = appearance_distance(red, red)
    different, _ = appearance_distance(red, blue)
    assert same == pytest.approx(0.0)
    assert different > 0.1


def test_tiny_person_crop_has_no_appearance_evidence():
    image = Image.new("RGB", (8, 8), (200, 30, 30))
    assert image_appearance(image, (0, 0, 8, 8)) == {}
