import pytest

from basketball_highlight.pose import PoseDetector, normalize_pose_result


class Values(list):
    def tolist(self):
        return list(self)


class FakeBox:
    def __init__(self, bounds, confidence):
        self.xyxy = [Values(bounds)]
        self.conf = Values([confidence])


class FakeKeypoints:
    def __init__(self, points, confidence):
        self.xy = Values(points)
        self.conf = Values(confidence) if confidence is not None else None


class FakeResult:
    def __init__(self, boxes, keypoints):
        self.boxes = boxes
        self.keypoints = keypoints


def test_pose_adapter_keeps_person_and_both_wrists_in_source_coordinates():
    points = [[0, 0] for _ in range(11)]
    points[9] = [160, 100]
    points[10] = [170, 110]
    result = FakeResult(
        boxes=[FakeBox([10, 20, 110, 220], 0.85)],
        keypoints=FakeKeypoints([points], [[0.9] * 11]),
    )
    people = normalize_pose_result(result, time_ms=1234)
    assert people == [{
        "time_ms": 1234,
        "bbox": [10.0, 20.0, 110.0, 220.0],
        "wrists": [[160.0, 100.0, 0.9], [170.0, 110.0, 0.9]],
        "detection_confidence": 0.85,
    }]


def test_missing_keypoint_confidence_is_not_positive_evidence():
    points = [[0, 0] for _ in range(11)]
    result = FakeResult(
        boxes=[FakeBox([10, 20, 110, 220], 0.85)],
        keypoints=FakeKeypoints([points], None),
    )
    people = normalize_pose_result(result, time_ms=0)
    assert all(wrist[2] == 0.0 for wrist in people[0]["wrists"])


def test_missing_wrists_are_not_zero_coordinate_evidence():
    result = FakeResult(boxes=[FakeBox([0, 0, 10, 20], 0.8)], keypoints=None)
    people = normalize_pose_result(result, time_ms=0)
    assert people[0]["wrists"] == []


def test_pose_detector_loads_model_only_when_prediction_is_requested():
    detector = PoseDetector("private-pose.pt", loader=lambda path: (_ for _ in ()).throw(AssertionError(path)))
    with pytest.raises(AssertionError, match="private-pose.pt"):
        detector.predict(object(), time_ms=0)
