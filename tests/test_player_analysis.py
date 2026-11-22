from basketball_highlight.identity_model import LocalIdentityModel
from basketball_highlight.player_analysis import analyze_player_event, link_people


def appearance(red=1.0, green=0.0):
    return {"shirt": {"values": [red, green], "quality": 1.0}}


def person(x=100, *, color=None, wrist_offset=0):
    return {
        "bbox": [x, 100, x + 100, 400],
        "wrists": [[x + 50 + wrist_offset, 180, 0.95]],
        "detection_confidence": 0.9,
        "appearance": color or appearance(),
    }


def shot_frames(*, color=None, later_touch=False, with_appearance=True):
    frames = []
    for index, time_ms in enumerate(range(0, 601, 100)):
        # The ball leaves the shooter's hand after 200 ms and approaches the rim.
        ball = [150, 180] if time_ms <= 200 else [150 + (time_ms - 200) * 2, 180 - (time_ms - 200)]
        people = [person(color=color)]
        if not with_appearance:
            people[0].pop("appearance")
        frames.append({"time_ms": time_ms, "ball": ball, "people": people})
    if later_touch:
        frames.append({
            "time_ms": 700,
            "ball": [150, 180],
            "people": [person(color=color)],
        })
    return frames


def test_local_tracks_survive_detection_order_changes_without_using_track_ids_as_identity():
    frames = [
        {"time_ms": 0, "people": [person(100), person(500, color=appearance(0, 1))]},
        {"time_ms": 100, "people": [person(510, color=appearance(0, 1)), person(105)]},
    ]
    linked = link_people(frames)
    first = {row["bbox"][0] // 400: row["track_id"] for row in linked if row["time_ms"] == 0}
    second = {row["bbox"][0] // 400: row["track_id"] for row in linked if row["time_ms"] == 100}
    assert first == second
    assert len(set(first.values())) == 2


def test_touch_is_limited_to_the_last_release_before_this_basket():
    result = analyze_player_event(shot_frames(later_touch=True), 600, LocalIdentityModel())
    assert result["touch"]["status"] == "identified"
    assert result["touch"]["touch_time_ms"] == 200
    assert result["touch"]["release_time_ms"] == 300


def test_same_game_appearance_is_reused_after_model_serialization_and_new_identity_can_be_named_later():
    model = LocalIdentityModel()
    first = analyze_player_event(shot_frames(), 600, model)
    assert first["identity"]["identity_id"] is not None
    assert first["identity"]["new_identity"] is True
    assert first["needs_review"] is True

    restored = LocalIdentityModel.from_dict(first["model"])
    second = analyze_player_event(shot_frames(), 600, restored)
    assert second["identity"]["identity_id"] == first["identity"]["identity_id"]
    assert second["identity"]["new_identity"] is False
    assert second["needs_review"] is False
    assert second["identity"]["confidence"] > 0.9
    assert second["model"]["prototypes"][first["identity"]["identity_id"]]["samples"] >= 2


def test_different_clothing_creates_a_second_reviewable_identity_not_a_name_guess():
    model = LocalIdentityModel()
    first = analyze_player_event(shot_frames(), 600, model)
    second = analyze_player_event(shot_frames(color=appearance(0, 1)), 600, model)
    assert second["identity"]["identity_id"] != first["identity"]["identity_id"]
    assert second["identity"]["new_identity"] is True
    assert len(second["model"]["prototypes"]) == 2


def test_no_release_evidence_or_no_appearance_never_becomes_an_automatic_identity():
    no_touch = analyze_player_event([], 600, LocalIdentityModel())
    assert no_touch["touch"]["status"] == "review"
    assert no_touch["identity"]["identity_id"] is None
    assert no_touch["needs_review"] is True

    no_appearance = analyze_player_event(shot_frames(with_appearance=False), 600, LocalIdentityModel())
    assert no_appearance["touch"]["status"] == "identified"
    assert no_appearance["identity"]["identity_id"] is None
    assert no_appearance["needs_review"] is True
    assert no_appearance["model"]["prototypes"] == {}
