from basketball_highlight.identity_model import LocalIdentityModel
from basketball_highlight.player_analysis import analyze_player_event, expanded_roi
from identify_players import frames_from_records


def test_identity_ball_roi_expands_beyond_the_rim_but_stays_inside_source():
    assert expanded_roi([100, 100, 300, 400], 640, 480, factor=2) == [0, 0, 400, 480]


def test_ball_selection_prefers_the_candidate_trajectory_over_a_distractor():
    records = [{
        "time": 10.0,
        "people": [{"bbox": [0, 0, 100, 200], "wrists": []}],
        "detections": [
            {"name": "ball", "center": [900, 100], "confidence": 0.99},
            {"name": "ball", "center": [200, 150], "confidence": 0.4},
            {"name": "hoop", "center": [200, 100], "confidence": 0.95},
        ],
    }]
    trajectory = [{"time": 9.9, "x": 190, "y": 150}, {"time": 10.1, "x": 210, "y": 150}]
    frames = frames_from_records(records, trajectory)
    assert frames == [{
        "time_ms": 10000,
        "ball": [200, 150],
        "people": [{"bbox": [0, 0, 100, 200], "wrists": []}],
    }]


def test_ball_track_is_extended_backwards_from_the_verified_basket():
    records = [{
        "time": time,
        "people": [],
        "detections": [
            {"name": "ball", "center": [50, 180], "confidence": .99},
            {"name": "ball", "center": [x, 180], "confidence": .5},
        ],
    } for time, x in ((9.0, 300), (9.1, 400), (9.2, 500))]
    trajectory = [{"time": 9.3, "x": 600, "y": 220}, {"time": 9.4, "x": 650, "y": 300}]
    frames = frames_from_records(records, trajectory, rim_width=100)
    assert [frame["ball"] for frame in frames] == [[300, 180], [400, 180], [500, 180]]


def test_unanchored_ball_detections_never_create_an_identity():
    # Reproduces the 56–61 s source-video false positive: a stationary mark on
    # a bystander's clothing looked like a hand-ball release near the rim ROI.
    records = []
    for index, ball in enumerate(([510, 619], [510, 619], [510, 619], [900, 600])):
        records.append({
            "time": 56.733 + index * 0.133,
            "people": [{
                "bbox": [490, 560, 580, 805],
                "wrists": [[570, 666, .9], [512, 680, .95]],
                "appearance": {"shirt": {"values": [0, 0], "quality": 1}},
            }],
            "detections": [{"name": "ball", "center": ball, "confidence": .38}],
        })
    frames = frames_from_records(records, [])
    assert all(frame["ball"] is None for frame in frames)
    result = analyze_player_event(frames, 60_500, LocalIdentityModel())
    assert result["touch"]["status"] == "review"
    assert result["identity"]["identity_id"] is None
    assert result["model"]["prototypes"] == {}
