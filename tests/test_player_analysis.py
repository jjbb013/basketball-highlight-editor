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


def test_short_ball_detection_gap_creates_reviewable_identity_not_auto_match():
    model = LocalIdentityModel()
    first = analyze_player_event(shot_frames(), 600, model)
    gapped = [
        shot_frames()[0],
        dict(shot_frames()[1], time_ms=67, ball=None),
        dict(shot_frames()[1], time_ms=133, ball=None),
        *shot_frames()[2:],
    ]
    second = analyze_player_event(gapped, 600, model)
    assert second["touch"]["status"] == "identified"
    assert second["touch"]["needs_review"] is True
    assert second["identity"]["identity_id"] == first["identity"]["identity_id"]
    assert second["identity"]["needs_review"] is False
    assert second["needs_review"] is True
    assert second["appearance_samples"] > 0


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


def occluded_shot_frames(*, second_person_ratio=None):
    """Ball invisible in the hands, first tracked right at the release."""
    frames = []
    for time_ms in range(0, 601, 100):
        if time_ms < 400:
            ball = None  # 持球/运球阶段被身体遮挡
        elif time_ms == 400:
            ball = [160, 190]  # 出手瞬间：球刚离手，仍在手腕旁
        elif time_ms == 500:
            ball = [300, 150]
        else:
            ball = [450, 120]
        people = [person(100)]
        if second_person_ratio is not None:
            # 第二人的手腕按指定比例贴近球（仅出手帧有意义）。
            wrist_x = 160 + second_person_ratio * 300
            other = person(700, color=appearance(0, 1))
            other["wrists"] = [[wrist_x, 190, 0.95]]
            people.append(other)
        frames.append({"time_ms": time_ms, "ball": ball, "people": people})
    return frames


def test_release_point_nearest_wrist_becomes_reviewable_identity_when_tracking_lost():
    result = analyze_player_event(occluded_shot_frames(), 600, LocalIdentityModel())
    # 单帧接触不满足连续触球判定的时长要求，走兜底归因。
    assert result["touch"]["status"] == "inferred"
    assert result["touch"]["touch_time_ms"] == 400
    assert result["touch"]["needs_review"] is True
    assert result["identity"]["identity_id"] is not None
    assert result["identity"]["new_identity"] is True
    assert result["needs_review"] is True
    assert result["appearance_samples"] > 0


def test_release_point_inference_rejects_when_nearest_wrist_is_far_from_ball():
    frames = [
        dict(frame, ball=[700, 180] if frame["time_ms"] >= 400 else None)
        for frame in occluded_shot_frames()
    ]
    result = analyze_player_event(frames, 600, LocalIdentityModel())
    assert result["touch"]["status"] == "review"
    assert result["identity"]["identity_id"] is None


def test_release_point_inference_rejects_ambiguous_nearest_holders():
    frames = occluded_shot_frames(second_person_ratio=0.1)
    result = analyze_player_event(frames, 600, LocalIdentityModel())
    assert result["touch"]["status"] == "review"
    assert result["identity"]["identity_id"] is None


def test_inferred_touch_relaxes_clothing_veto_into_reviewable_match():
    model = LocalIdentityModel()
    first = analyze_player_event(shot_frames(), 600, model)
    assert first["identity"]["identity_id"] is not None
    # 同一人的出手帧：上衣采样带被姿态污染（区域距离 0.2），走推断路径。
    frames = occluded_shot_frames()
    for frame in frames:
        for one in frame["people"]:
            one["appearance"] = appearance(0.8, 0.6)
    second = analyze_player_event(frames, 600, model)
    assert second["touch"]["status"] == "inferred"
    assert second["identity"]["identity_id"] == first["identity"]["identity_id"]
    assert second["identity"]["needs_review"] is True
    assert second["needs_review"] is True


def test_identified_touch_keeps_strict_clothing_veto():
    model = LocalIdentityModel()
    first = analyze_player_event(shot_frames(), 600, model)
    assert first["identity"]["identity_id"] is not None
    # 完整触球证据但上衣冲突：自动路径维持不误并他人的保护。
    second = analyze_player_event(shot_frames(color=appearance(0.8, 0.6)), 600, model)
    assert second["touch"]["status"] == "identified"
    assert second["identity"]["identity_id"] is None
