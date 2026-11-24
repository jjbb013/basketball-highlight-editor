import json
from pathlib import Path

import pytest

from basketball_highlight.identity_model import LocalIdentityModel
from engine.python.basketball_engine.adapters.analysis import (
    PipelineCancelled,
    build_player_identification_command,
)
from engine.python.basketball_engine.service import EngineService

FEATURES = {"shirt": {"values": [1.0, 0.0], "quality": 1.0}}


class _Store:
    def __init__(self, identities=None):
        self.identities = identities or []

    def list_identities(self):
        return self.identities


def _row():
    return {
        "id": "candidate-1",
        "event_time_ms": 60_500,
        "evidence_json": json.dumps({"rim_check": {"trajectory": [{"time": 60.4, "x": 10, "y": 20}]}}),
    }


def _files(tmp_path: Path):
    paths = {name: tmp_path / f"{name}.pt" for name in ("source", "ball", "pose")}
    paths["source"] = tmp_path / "source.mp4"
    for path in paths.values():
        if not path.exists():
            path.write_bytes(b"test weights")
    return paths


def _identify(service, tmp_path, store=None, pipeline=None, pose_exists=True, person_roi=None):
    paths = _files(tmp_path)
    if not pose_exists:
        paths["pose"].unlink()
    return service._identify_players(
        repo_root=Path(__file__).resolve().parents[1],
        source_video=paths["source"],
        model_path=paths["ball"],
        pose_model_path=paths["pose"],
        run_root=tmp_path / "run",
        rows=[_row()],
        source_roi=[0, 0, 100, 100],
        person_roi=person_roi,
        source_size=[1920, 1080],
        store=store or _Store(),
        on_stage=lambda *_: None,
        cancel_event=None,
        job_id="job-1",
        pipeline=pipeline if pipeline is not None else {"logs": []},
        device="mps",
    )


def _output(model):
    from basketball_highlight.player_analysis import ALGORITHM_VERSION

    return {
        "schema_version": 1,
        "algorithm_version": ALGORITHM_VERSION,
        "model": model.to_dict(),
        "results": {
            "candidate-1": {
                "status": "identified",
                "needs_review": False,
                "touch": {"status": "identified", "touch_time_ms": 59_800, "confidence": .8},
                "identity": {"identity_id": "identity_will", "confidence": .9, "needs_review": False},
                "appearance_samples": 3,
                "algorithm_version": ALGORITHM_VERSION,
            },
        },
    }


def test_review_identity_without_a_saved_prototype_is_rejected_before_persistence():
    output = _output(LocalIdentityModel())
    result = output["results"]["candidate-1"]
    result["status"] = "review"
    result["needs_review"] = True
    result["identity"]["needs_review"] = True

    with pytest.raises(LookupError, match="IDENTITY_NOT_FOUND"):
        EngineService._validate_identity_output(output, {"candidate-1"})


def test_identity_command_forwards_source_models_roi_and_device(tmp_path: Path):
    command = build_player_identification_command(
        tmp_path, Path("source.mp4"), Path("ball.pt"), Path("pose.pt"),
        Path("input.json"), Path("output.json"), [1, 2, 3, 4], device="mps",
    )
    assert command[1].endswith("identify_players.py")
    assert command[command.index("--pose-model") + 1] == str(Path("pose.pt").resolve())
    assert command[command.index("--roi") + 1:command.index("--roi") + 5] == ["1", "2", "3", "4"]
    assert command[command.index("--device") + 1] == "mps"


def test_person_roi_forwards_to_identify_command_and_splits_cache(tmp_path: Path, monkeypatch):
    model = LocalIdentityModel()
    model.observe("identity_will", FEATURES)
    store = _Store([{
        "id": "identity_will", "prototype_json": json.dumps(FEATURES),
        "sample_count": 1, "player_name": "Will",
    }])
    captured = {}

    def fake_run(commands, output_path, *_args, **kwargs):
        command = commands[0]
        captured["command"] = command
        input_path = Path(command[command.index("--candidates") + 1])
        captured["input"] = json.loads(input_path.read_text(encoding="utf-8"))
        Path(output_path).write_text(json.dumps(_output(model)), encoding="utf-8")
        return {"refined": _output(model), "logs": ["identified=1"], "cache_hits": 0}

    monkeypatch.setattr("engine.python.basketball_engine.service.run_pipeline", fake_run)
    pipeline = {"logs": []}
    _identify(EngineService(), tmp_path, store=store, pipeline=pipeline,
              person_roi=[10, 20, 300, 400])

    command = captured["command"]
    assert command[command.index("--person-roi") + 1:command.index("--person-roi") + 5] == [
        "10", "20", "300", "400",
    ]
    assert not any("fallback" in line for line in pipeline["logs"])  # 合法人物区：不回退

    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("a different person zone must not reuse the cached identity output")

    monkeypatch.setattr("engine.python.basketball_engine.service.run_pipeline", unexpected_run)
    # 同一份输入 + 不同人物区：缓存 key 必须不同 → 命中不到旧缓存，会重新调用
    # run_pipeline（被 unexpected_run 拦下，服务层吞掉异常记为 failed）。
    second_pipeline = {"logs": []}
    assert _identify(EngineService(), tmp_path, store=store,
                     pipeline=second_pipeline, person_roi=[50, 60, 700, 800]) is None
    assert second_pipeline["identity_counts"]["status"] == "failed"

    # 相同人物区：命中缓存，completed 且不触碰 run_pipeline。
    third_pipeline = {"logs": []}
    cached = _identify(EngineService(), tmp_path, store=store,
                       pipeline=third_pipeline, person_roi=[10, 20, 300, 400])
    assert cached is not None
    assert third_pipeline["identity_counts"]["status"] == "completed"


def test_missing_person_roi_falls_back_to_shot_roi_and_logs(tmp_path: Path, monkeypatch):
    model = LocalIdentityModel()
    store = _Store([{
        "id": "identity_will", "prototype_json": json.dumps(FEATURES),
        "sample_count": 1, "player_name": "Will",
    }])
    captured = {}

    def fake_run(commands, output_path, *_args, **kwargs):
        command = commands[0]
        captured["command"] = command
        input_path = Path(command[command.index("--candidates") + 1])
        captured["input"] = json.loads(input_path.read_text(encoding="utf-8"))
        Path(output_path).write_text(json.dumps(_output(model)), encoding="utf-8")
        return {"refined": _output(model), "logs": ["identified=1"], "cache_hits": 0}

    monkeypatch.setattr("engine.python.basketball_engine.service.run_pipeline", fake_run)
    pipeline = {"logs": []}
    _identify(EngineService(), tmp_path, store=store, pipeline=pipeline, person_roi=None)

    assert "--person-roi" not in captured["command"]
    assert any("person" in line and "fallback" in line for line in pipeline["logs"])


def test_identity_analysis_restores_named_prototypes_without_exporting_names(tmp_path: Path, monkeypatch):
    model = LocalIdentityModel()
    model.observe("identity_will", FEATURES)
    store = _Store([{
        "id": "identity_will", "prototype_json": json.dumps(FEATURES),
        "sample_count": 1, "player_name": "Will",
    }])
    captured = {}

    def fake_run(commands, output_path, *_args, **kwargs):
        input_path = Path(commands[0][commands[0].index("--candidates") + 1])
        captured["input"] = json.loads(input_path.read_text(encoding="utf-8"))
        Path(output_path).write_text(json.dumps(_output(model)), encoding="utf-8")
        return {"refined": _output(model), "logs": ["identified=1"], "cache_hits": 0}

    monkeypatch.setattr("engine.python.basketball_engine.service.run_pipeline", fake_run)
    pipeline = {"logs": []}
    result = _identify(EngineService(), tmp_path, store=store, pipeline=pipeline)

    assert captured["input"]["model"]["prototypes"] == model.prototypes
    assert "Will" not in json.dumps(captured["input"])
    assert result["results"]["candidate-1"]["identity"]["identity_id"] == "identity_will"
    assert pipeline["identity_counts"] == {"status": "completed", "auto_assigned": 1, "review": 0}

    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("an identical analysis must reuse its cached output")

    monkeypatch.setattr("engine.python.basketball_engine.service.run_pipeline", unexpected_run)
    cached = _identify(EngineService(), tmp_path, store=store, pipeline=pipeline)
    assert cached == result


def test_missing_pose_model_keeps_candidates_reviewable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "engine.python.basketball_engine.service.run_pipeline",
        lambda *_args, **_kwargs: pytest.fail("missing models must not launch inference"),
    )
    pipeline = {"logs": []}
    assert _identify(EngineService(), tmp_path, pipeline=pipeline, pose_exists=False) is None
    assert pipeline["identity_counts"] == {"status": "model_unavailable", "auto_assigned": 0, "review": 1}
    assert pipeline["stage_timings_ms"]["identify_players"] >= 0


def test_identity_failure_does_not_discard_basketball_candidates(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "engine.python.basketball_engine.service.run_pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("detector failed")),
    )
    pipeline = {"logs": []}
    assert _identify(EngineService(), tmp_path, pipeline=pipeline) is None
    assert pipeline["identity_counts"]["status"] == "failed"
    assert pipeline["identity_counts"]["review"] == 1


def test_identity_cancellation_is_not_downgraded_to_a_review_result(tmp_path: Path, monkeypatch):
    def cancel(*_args, **_kwargs):
        raise PipelineCancelled("JOB_CANCELLED")

    monkeypatch.setattr("engine.python.basketball_engine.service.run_pipeline", cancel)
    with pytest.raises(PipelineCancelled):
        _identify(EngineService(), tmp_path)


def test_analysis_option_survives_retry_and_atomically_names_all_automatic_rows(tmp_path: Path, monkeypatch):
    from tests.test_engine import _analysis_fixture

    service, store, video, ball_model = _analysis_fixture(tmp_path)
    payload = {
        "project_root": str(store.root), "video_id": video["id"],
        "model_path": str(ball_model), "mode": "fast", "player_identity": True,
    }
    job = service._create_analysis_job(payload)["job"]
    assert json.loads(store.get_job(job["id"])["checkpoint_json"])["player_identity"] is True

    def fake_build(**kwargs):
        Path(kwargs["coarse_detections"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["coarse_detections"]).write_text(
            json.dumps({"records": [{"detections": [{"name": "ball"}]}]}), encoding="utf-8",
        )
        return [["fake", "proxy"], ["fake", "scan"], ["fake", "candidates"]]

    monkeypatch.setattr("engine.python.basketball_engine.service.build_pipeline_commands", fake_build)
    monkeypatch.setattr(
        "engine.python.basketball_engine.service.run_pipeline",
        lambda _commands, output, *_args, **_kwargs: {
            "refined": {"candidates": [{"time": 1.5, "score": .8}, {"time": 4.5, "score": .7}]},
            "logs": [], "stage_timings_ms": {},
        },
    )
    monkeypatch.setattr(
        service, "_prepare_candidate_previews",
        lambda **_: {"generated": 0, "reused": 0, "failed": 0},
    )
    model = LocalIdentityModel()
    model.observe("identity_will", FEATURES)
    called = {}

    def fake_identity(**kwargs):
        called.update(kwargs)
        template = _output(model)["results"]["candidate-1"]
        kwargs["pipeline"]["identity_counts"] = {"status": "completed", "auto_assigned": 2, "review": 0}
        return {
            "model": model.to_dict(),
            "results": {str(row["id"]): dict(template) for row in kwargs["rows"]},
        }

    monkeypatch.setattr(service, "_identify_players", fake_identity)
    service._run_analysis(payload, job["id"])

    assert called["pose_model_path"].name == "yolo11n-pose.pt"
    assert called["source_size"] == [960, 720]
    assert len(called["rows"]) == 2
    assert store.get_job(job["id"])["state"] == "completed"
    named = service.handle("name_identity", {
        "project_root": str(store.root), "identity_id": "identity_will", "player_name": "Will",
    })
    assert named["updated_candidates"] == 2
    assert [candidate["player_name"] for candidate in store.list_candidates(video["id"])] == ["Will", "Will"]
    checkpoint = json.loads(store.get_job(job["id"])["checkpoint_json"])
    assert checkpoint["identity_counts"] == {"status": "completed", "auto_assigned": 2, "review": 0}
    assert "Will" not in checkpoint["logs"]
    assert "prototype" not in checkpoint

    store.update_job(job["id"], state="failed", allow_terminal_transition=True)
    monkeypatch.setattr(service, "start_analysis", lambda value: value)
    retried = service.retry_analysis({"project_root": str(store.root), "job_id": job["id"]})
    assert retried["player_identity"] is True
