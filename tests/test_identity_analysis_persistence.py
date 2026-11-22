import json
from pathlib import Path

import pytest

from basketball_highlight.identity_model import LocalIdentityModel
from basketball_highlight.player_analysis import identity_model_from_rows
from engine.python.basketball_engine.storage import ProjectStore

FEATURES = {"shirt": {"values": [1.0, 0.0], "quality": 1.0}}


def candidate(video_id, event_ms=1000):
    return {
        "id": f"c{event_ms}", "video_id": video_id, "event_time_ms": event_ms,
        "default_start_ms": event_ms - 400, "default_end_ms": event_ms + 400,
        "detector_version": "test", "confidence": "review", "evidence_json": "{}",
    }


def analysis(identity_id="identity_will", confidence=0.0):
    return {
        "status": "review", "needs_review": True,
        "touch": {"status": "identified", "touch_time_ms": 650, "confidence": 0.8},
        "identity": {"identity_id": identity_id, "confidence": confidence, "needs_review": True},
        "appearance_samples": 3, "algorithm_version": "test-player-v1",
    }


@pytest.fixture()
def project(tmp_path: Path):
    source = tmp_path / "game.mp4"
    source.write_bytes(b"synthetic test source")
    store = ProjectStore(tmp_path / "project")
    store.initialize()
    store.create_project("project_test", "Test")
    video = store.link_video({
        "source_path": str(source), "source_size_bytes": source.stat().st_size,
        "source_mtime_ns": source.stat().st_mtime_ns, "duration_ms": 8000,
    })
    return store, video


def test_identity_prototypes_assignments_and_candidates_commit_together(project):
    store, video = project
    model = LocalIdentityModel()
    model.observe("identity_will", FEATURES)
    store.replace_candidates(
        video["id"], [candidate(video["id"])],
        identity_analysis={
            "results": {f"c1000": analysis()},
            "model": model.to_dict(),
        },
    )

    row = store.candidate("c1000")
    assert row["identity_id"] == "identity_will"
    assert row["assignment_source"] == "automatic"
    assert row["touch_time_ms"] == 650
    assert row["player_name"] is None
    assert json.loads(row["identity_evidence_json"])["appearance_samples"] == 3
    identities = store.list_identities()
    assert identities[0]["sample_count"] == 1
    assert identity_model_from_rows(identities).prototypes == model.prototypes
    assert store.name_identity("identity_will", player_name="Will")["updated_candidates"] == 1
    assert store.candidate("c1000")["player_name"] == "Will"


def test_reanalysis_reuses_saved_identity_and_preserves_manual_assignment(project):
    store, video = project
    first = LocalIdentityModel()
    first.observe("identity_will", FEATURES)
    store.replace_candidates(
        video["id"], [candidate(video["id"])],
        identity_analysis={"results": {"c1000": analysis()}, "model": first.to_dict()},
    )
    store.name_identity("identity_will", player_name="Will")
    second = LocalIdentityModel()
    second.observe("identity_other", {"shirt": {"values": [0.0, 1.0], "quality": 1.0}})
    store.set_candidate_player("c1000", None)

    store.replace_candidates(
        video["id"], [candidate(video["id"])],
        identity_analysis={"results": {"c1000": analysis("identity_other")}, "model": second.to_dict()},
    )

    row = store.candidate("c1000")
    assert row["identity_id"] == "identity_will"
    assert row["assignment_source"] == "manual"
    assert row["player_id"] is None
    assert store.candidate("c1000")["identity_confidence"] == 0.0


def test_failed_commit_rolls_back_new_prototypes_and_candidates(project):
    store, video = project
    model = LocalIdentityModel()
    model.observe("identity_will", FEATURES)

    def abort():
        raise RuntimeError("cancel before commit")

    with pytest.raises(RuntimeError, match="cancel before commit"):
        store.replace_candidates(
            video["id"], [candidate(video["id"])],
            identity_analysis={"results": {"c1000": analysis()}, "model": model.to_dict()},
            before_commit=abort,
        )
    assert store.list_candidates() == []
    assert store.list_identities() == []


def test_new_identity_from_real_analysis_can_be_saved_named_and_matched(project):
    from basketball_highlight.player_analysis import analyze_player_event

    store, video = project
    frames = []
    for time_ms in range(0, 601, 100):
        ball = [150, 180] if time_ms <= 200 else [150 + (time_ms - 200) * 2, 180 - (time_ms - 200)]
        frames.append({
            "time_ms": time_ms,
            "ball": ball,
            "people": [{
                "bbox": [100, 100, 200, 400],
                "wrists": [[150, 180, 0.95]],
                "detection_confidence": 0.9,
                "appearance": FEATURES,
            }],
        })

    first = analyze_player_event(frames, 600, LocalIdentityModel())
    identity_id = first["identity"]["identity_id"]
    assert first["identity"]["new_identity"] is True
    assert first["model"]["prototypes"][identity_id]["samples"] == 1
    store.replace_candidates(
        video["id"], [candidate(video["id"])],
        identity_analysis={"results": {"c1000": first}, "model": first["model"]},
    )

    assert store.list_identities()[0]["sample_count"] == 1
    assert store.name_identity(identity_id, player_name="Will")["updated_candidates"] == 1
    assert store.candidate("c1000")["player_name"] == "Will"

    restored = identity_model_from_rows(store.list_identities())
    second = analyze_player_event(frames, 600, restored)
    assert second["identity"]["identity_id"] == identity_id
    assert second["identity"]["new_identity"] is False
    assert second["needs_review"] is False
    store.replace_candidates(
        video["id"], [candidate(video["id"])],
        identity_analysis={"results": {"c1000": second}, "model": second["model"]},
    )

    row = store.candidate("c1000")
    assert row["identity_id"] == identity_id
    assert row["player_name"] == "Will"
    assert row["assignment_source"] == "automatic"
    assert store.list_identities()[0]["sample_count"] == 2
