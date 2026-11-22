import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_rim_crossing
from basketball_highlight.rim_check import RIM_CHECK_VERSION

RIM = {"center_x": 500.0, "rim_y": 300.0, "width": 50.0, "height": 20.0}


def test_script_preserves_the_timed_trajectory_used_by_player_attribution():
    frames = []
    for step in range(16):
        if step in {6, 7}:
            frames.append([])
            continue
        x = 500 + (0.3 - 0.5 * step / 15) * 50
        y = 225 + step * 12.5
        frames.append([{
            "name": "ball", "confidence": 0.85,
            "xyxy": [x - 12.5, y - 12.5, x + 12.5, y + 12.5],
        }])
    result = verify_rim_crossing.judge_job({
        "frames": frames, "rim": RIM, "net_motion_series": None, "first": 300,
    }, 30.0)

    assert result["frame_times"] == [10.0 + index / 30 for index in range(16)]
    assert result["trajectory"]
    assert result["trajectory"][0] == {"time": 10.0, "x": 515.0, "y": 225.0}


def test_trajectory_schema_has_a_new_cache_version():
    assert RIM_CHECK_VERSION == "rim-dense-v3"
