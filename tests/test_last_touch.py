import pytest

from basketball_highlight.last_touch import select_last_touch


def frame(ms, track, hand_x, ball_x, wrist_confidence=0.95):
    return {
        "time_ms": ms,
        "track_id": track,
        "bbox": [0, 0, 100, 200],
        "wrists": [[hand_x, 100, wrist_confidence]],
        "ball": [ball_x, 100],
    }


def shot(track="shooter", offset_ms=0):
    return [
        frame(1000 + offset_ms, track, 100, 100),
        frame(1100 + offset_ms, track, 100, 100),
        frame(1200 + offset_ms, track, 100, 180),
        frame(1300 + offset_ms, track, 100, 240),
    ]


def test_contact_immediately_before_release_is_selected():
    result = select_last_touch(shot())
    assert result["status"] == "identified"
    assert result["local_track_id"] == "shooter"
    assert result["touch_time_ms"] == 1100
    assert result["confidence"] > 0.8


def test_stationary_player_near_ball_has_no_release():
    frames = [frame(ms, "bystander", 100, 100) for ms in (1000, 1100, 1200, 1300)]
    result = select_last_touch(frames)
    assert result["status"] == "review"
    assert result["local_track_id"] is None


def test_later_valid_contact_supersedes_earlier_contact():
    early = shot("early")
    late = [
        frame(1200, "late", 180, 180),
        frame(1250, "late", 180, 180),
        frame(1300, "late", 180, 240),
        frame(1350, "late", 180, 300),
    ]
    result = select_last_touch(early + late)
    assert result["local_track_id"] == "late"
    assert result["touch_time_ms"] == 1250


def test_close_second_candidate_is_not_overconfident():
    result = select_last_touch(shot() + shot("other"))
    assert result["status"] == "review"
    assert result["local_track_id"] is None
    assert len(result["alternatives"]) == 2


def test_low_confidence_wrist_is_not_positive_contact():
    frames = [dict(item, wrists=[[100, 100, 0.1]]) for item in shot()]
    assert select_last_touch(frames)["status"] == "review"


def test_single_contact_frame_does_not_make_a_track():
    frames = [shot()[0], *shot()[1:]]
    del frames[1]
    assert select_last_touch(frames)["status"] == "review"


def test_occluded_ball_does_not_create_contact():
    frames = [dict(item, ball=None) for item in shot()]
    result = select_last_touch(frames)
    assert result["status"] == "review"
    assert result["alternatives"] == []


def test_no_person_is_an_explicit_review_not_an_exception():
    result = select_last_touch([])
    assert result == {
        "status": "review",
        "local_track_id": None,
        "touch_time_ms": None,
        "confidence": 0.0,
        "alternatives": [],
    }
