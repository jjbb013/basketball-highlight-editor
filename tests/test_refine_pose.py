import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import refine_candidates


class Result:
    boxes = []


class BallModel:
    def predict(self, crops, **kwargs):
        return [Result() for _ in crops]


class PoseModel:
    def __init__(self):
        self.calls = []

    def predict_batch(self, frames, time_ms, **kwargs):
        self.calls.append((frames, time_ms, kwargs))
        return [[{
            "time_ms": stamp,
            "bbox": [10, 20, 110, 220],
            "wrists": [],
            "detection_confidence": 0.9,
        }] for stamp in time_ms]


def test_pose_uses_original_frames_and_shares_the_ball_decode(tmp_path):
    video = tmp_path / "game.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for _ in range(10):
        writer.write(np.full((240, 320, 3), 60, dtype=np.uint8))
    writer.release()
    pose = PoseModel()

    records = refine_candidates.scan_window(
        BallModel(), video, (0, 0, 160, 240), 0.5, 0.4, 10, 1, 0.2,
        "cpu", batch=2, pose_detector=pose,
    )

    assert len(records) == sum(len(frames) for frames, _, _ in pose.calls)
    assert records
    assert all(record["people"][0]["time_ms"] == round(record["time"] * 1000) for record in records)
    assert pose.calls
    for frames, _, options in pose.calls:
        assert all(frame.shape == (240, 320, 3) for frame in frames)
        assert options["device"] == "cpu"
        assert options["batch"] == 2
        assert options["imgsz"] == 960


def test_person_ball_crops_share_decode_and_keep_source_coordinates(tmp_path):
    from basketball_highlight.player_analysis import person_ball_roi
    assert person_ball_roi([1400, 570, 1510, 855], 1920, 1080) == [1227, 484, 1683, 940]

    video = tmp_path / "game.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for _ in range(4):
        writer.write(np.full((240, 320, 3), 60, dtype=np.uint8))
    writer.release()

    class CropBallModel(BallModel):
        def __init__(self):
            self.crops = []

        def predict(self, crops, **kwargs):
            self.crops.extend(crops)
            return super().predict(crops, **kwargs)

    ball, pose = CropBallModel(), PoseModel()
    records = refine_candidates.scan_window(
        ball, video, (0, 0, 160, 240), .2, .2, 10, 1, .2,
        "cpu", batch=4, pose_detector=pose, person_ball_crops=True,
    )
    assert len(ball.crops) > len(records)
    assert len(records) == sum(len(frames) for frames, _, _ in pose.calls)
