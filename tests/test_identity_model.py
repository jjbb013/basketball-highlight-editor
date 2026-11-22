import json

import pytest

from basketball_highlight.appearance import appearance_vector
from basketball_highlight.identity_model import LocalIdentityModel


def features(red, region="shirt"):
    return appearance_vector({region: (red, 1 - red, 0.1)}, {region: 1.0})


def add_identity(model, value):
    identity_id = model.assign(features(value))["identity_id"]
    assert identity_id is not None
    model.observe(identity_id, features(value))
    return identity_id


def test_new_identity_can_be_reidentified_after_serialization():
    model = LocalIdentityModel()
    first = add_identity(model, 0.9)
    restored = LocalIdentityModel.from_dict(json.loads(json.dumps(model.to_dict())))
    result = restored.assign(features(0.88))
    assert result["identity_id"] == first
    assert not result["needs_review"]
    assert result["confidence"] > 0.9
    assert restored.prototypes[first]["samples"] == 1


def test_no_common_features_requires_review_without_creating_identity():
    model = LocalIdentityModel()
    add_identity(model, 0.9)
    result = model.assign(features(0.9, "pants"))
    assert result["needs_review"]
    assert result["identity_id"] is None
    assert len(model.prototypes) == 1


def test_empty_features_cannot_create_identity():
    result = LocalIdentityModel().assign({})
    assert result["needs_review"]
    assert result["identity_id"] is None


def test_distinct_clothing_creates_another_identity():
    model = LocalIdentityModel()
    first = add_identity(model, 0.9)
    result = model.assign(features(0.1))
    assert result["identity_id"] is not None
    assert result["identity_id"] != first
    assert result["new_identity"]


def test_conflicting_shirt_cannot_be_hidden_by_other_matching_regions():
    model = LocalIdentityModel()
    regions = {name: (1.0, 0.0, 0.0) for name in
               ('hair', 'face', 'skin', 'shirt', 'pants', 'shoes')}
    first = model.assign(appearance_vector(regions, {name: 1.0 for name in regions}))
    assert first['identity_id'] is not None
    model.observe(first['identity_id'], appearance_vector(
        regions, {name: 1.0 for name in regions},
    ))
    conflicting = dict(regions, shirt=(0.8, 0.6, 0.0))

    result = model.assign(appearance_vector(conflicting, {name: 1.0 for name in regions}))

    assert result['needs_review']
    assert result['identity_id'] is None
    assert result['alternative_identity_ids'] == [first['identity_id']]


def test_two_close_identities_require_review():
    model = LocalIdentityModel()
    first = add_identity(model, 0.9)
    second = add_identity(model, 0.1)
    result = model.assign(features(0.5))
    assert result["needs_review"]
    assert result["identity_id"] is None
    assert set(result["alternative_identity_ids"]) == {first, second}


def test_observe_rejects_empty_identity_or_features():
    model = LocalIdentityModel()
    with pytest.raises(ValueError, match="INVALID_IDENTITY_OBSERVATION"):
        model.observe("", features(0.9))
    with pytest.raises(ValueError, match="INVALID_IDENTITY_OBSERVATION"):
        model.observe("identity_1", {})


def test_unsupported_serialized_model_is_rejected():
    with pytest.raises(ValueError, match="IDENTITY_MODEL_VERSION_UNSUPPORTED"):
        LocalIdentityModel.from_dict({"version": 999, "prototypes": {}})
