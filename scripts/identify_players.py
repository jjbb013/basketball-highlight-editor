"""Local YOLO Pose + last-touch + same-game appearance attribution.

Input and output contain descriptors only. No source frames or player names are
written by this script; the calling engine owns the private project database.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from basketball_highlight.identity_model import LocalIdentityModel
from basketball_highlight.inference import current_device, load_detector, select_device
from basketball_highlight.player_analysis import ALGORITHM_VERSION, analyze_player_event, expanded_roi
from basketball_highlight.pose import PoseDetector
from basketball_highlight.tracking import link_ball_detections
from refine_candidates import scan_window


def parse_args():
    parser = argparse.ArgumentParser(description="Identify final ball contact within candidate windows.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--pose-model", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--roi", nargs=4, type=int, required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--sample-fps", type=float, default=15)
    parser.add_argument("--before", type=float, default=4.5)
    parser.add_argument("--after", type=float, default=0.5)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--pose-conf", type=float, default=0.25)
    parser.add_argument("--pose-imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=4)
    return parser.parse_args()


def _interpolate(trajectory, time_seconds):
    points = sorted(trajectory, key=lambda point: float(point["time"]))
    for first, second in zip(points, points[1:]):
        start, end = float(first["time"]), float(second["time"])
        if start <= time_seconds <= end and end > start:
            ratio = (time_seconds - start) / (end - start)
            return [
                float(first[axis]) + (float(second[axis]) - float(first[axis])) * ratio
                for axis in ("x", "y")
            ]
    return None


def frames_from_records(records, trajectory, rim_width=80):
    """Extend a verified rim path backwards; never choose a free-standing ball."""
    path = sorted(trajectory or [], key=lambda point: float(point["time"]))
    if path:
        anchor = path[0]
        earlier = [record for record in records if float(record["time"]) <= float(anchor["time"])]
        path = [
            *link_ball_detections(earlier, anchor=anchor, rim_width=rim_width)[:-1],
            *path,
        ]
    frames = []
    for record in records:
        expected = _interpolate(path, float(record["time"]))
        balls = []
        if expected is not None:
            balls = [item for item in record.get("detections", []) if item.get("name") == "ball"]
            balls = [item for item in balls if math.hypot(
                float(item["center"][0]) - expected[0], float(item["center"][1]) - expected[1],
            ) <= max(24.0, float(rim_width) * .75)]
            balls.sort(key=lambda item: (
                math.hypot(float(item["center"][0]) - expected[0], float(item["center"][1]) - expected[1]),
                -float(item.get("confidence", 0)),
            ))
        frames.append({
            "time_ms": round(float(record["time"]) * 1000),
            "ball": balls[0]["center"] if balls else None,
            "people": record.get("people", []),
        })
    return frames


def validate_args(args):
    if not all(path.is_file() for path in (args.video, args.model, args.pose_model, args.candidates)):
        raise ValueError("PLAYER_MODEL_OR_INPUT_NOT_FOUND")
    if args.sample_fps <= 0 or args.batch <= 0 or args.before <= 0 or args.after < 0:
        raise ValueError("PLAYER_PARAMETERS_INVALID")
    if not 0 < args.conf < 1 or not 0 < args.pose_conf < 1:
        raise ValueError("PLAYER_PARAMETERS_INVALID")


def main(args):
    validate_args(args)
    data = json.loads(args.candidates.read_text(encoding="utf-8"))
    candidates = data.get("candidates", [])
    initial_model = data.get("model") or LocalIdentityModel().to_dict()
    identity_model = LocalIdentityModel.from_dict(initial_model)
    results = {}
    started = time.perf_counter()
    if not candidates:
        raise ValueError("PLAYER_CANDIDATES_EMPTY")
    device = select_device(args.device, args.model)
    ball_model = load_detector(args.model)
    ball_device = current_device()
    pose_device = select_device(device, args.pose_model)
    pose = PoseDetector(args.pose_model, include_appearance=True)
    for index, candidate in enumerate(candidates, 1):
        event_time = float(candidate["time"])
        evidence = candidate.get("evidence") or {}
        overlay = evidence.get("overlay") or {}
        trajectory = (evidence.get("rim_check") or {}).get("trajectory") or overlay.get("trajectory") or []
        rim_width = (overlay.get("rim") or {}).get("width") or (evidence.get("rim_check") or {}).get("rim_width_px") or 80
        records = scan_window(
            ball_model, args.video, expanded_roi(args.roi, *candidate["source_size"]),
            event_time, 0, args.sample_fps, args.scale, args.conf, ball_device,
            batch=args.batch,
            start_time_override=max(0, event_time - args.before),
            end_time_override=event_time + args.after,
            pose_detector=pose, pose_conf=args.pose_conf, pose_imgsz=args.pose_imgsz,
            person_ball_crops=True,
        )
        result = analyze_player_event(
            frames_from_records(records, trajectory, rim_width=rim_width), round(event_time * 1000), identity_model,
        )
        results[str(candidate["id"])] = result
        print(f"progress={index / len(candidates):.4f}", flush=True)
        print(
            f"{index:03d} event={event_time:.3f}s touch={result['touch']['status']} "
            f"identity={'review' if result['needs_review'] else 'matched'} "
            f"samples={result['appearance_samples']}",
            flush=True,
        )
    output = {
        "schema_version": 1,
        "algorithm_version": ALGORITHM_VERSION,
        "model": identity_model.to_dict(),
        "results": results,
        "devices": {"ball": ball_device, "pose": pose_device},
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    temporary.replace(args.output)
    print(f"identified={sum(not item['needs_review'] for item in results.values())}", flush=True)
    print(f"review={sum(item['needs_review'] for item in results.values())}", flush=True)
    print(f"output={args.output}", flush=True)


if __name__ == "__main__":
    main(parse_args())
