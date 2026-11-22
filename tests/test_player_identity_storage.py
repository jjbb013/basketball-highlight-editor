import json
from pathlib import Path

import pytest

from engine.python.basketball_engine.service import EngineService
from engine.python.basketball_engine.storage import ProjectStore


def candidate(video_id, event_ms):
    return {
        "id": f"c{event_ms}",
        "video_id": video_id,
        "event_time_ms": event_ms,
        "default_start_ms": event_ms - 500,
        "default_end_ms": event_ms + 500,
        "detector_version": "test",
        "confidence": "review",
        "evidence_json": "{}",
    }


@pytest.fixture()
def identity_project(tmp_path: Path):
    root = tmp_path / "project"
    source = tmp_path / "game.mp4"
    source.write_bytes(b"synthetic test source")
    store = ProjectStore(root)
    store.initialize()
    store.create_project("project_test", "Test")
    video = store.link_video({
        "source_path": str(source),
        "source_size_bytes": source.stat().st_size,
        "source_mtime_ns": source.stat().st_mtime_ns,
        "duration_ms": 8000,
    })
    store.replace_candidates(video["id"], [candidate(video["id"], ms) for ms in (1000, 3000, 5000)])
    identity = store.create_identity(identity_id="identity_will")
    for candidate_id in ("c1000", "c3000", "c5000"):
        store.upsert_identity_assignment(
            candidate_id,
            identity["id"],
            {"touch_time_ms": int(candidate_id[1:]) - 500, "status": "identified"},
            0.8,
        )
    other = store.create_player("Other")
    store.set_candidate_player("c5000", other["id"])
    return store, identity["id"], ["c1000", "c3000"], "c5000"


def test_naming_identity_updates_all_automatic_candidates_only(identity_project):
    store, identity_id, automatic_ids, manual_id = identity_project
    result = store.name_identity(identity_id, player_name="Will")
    assert result["updated_candidates"] == 2
    assert result["player"]["name"] == "Will"
    assert all(store.candidate(item)["player_name"] == "Will" for item in automatic_ids)
    assert store.candidate(manual_id)["player_name"] == "Other"
    assert store.candidate(manual_id)["assignment_source"] == "manual"


def test_manual_clear_is_not_repainted_by_identity_naming(identity_project):
    store, identity_id, automatic_ids, _ = identity_project
    store.set_candidate_player(automatic_ids[0], None)
    store.name_identity(identity_id, player_name="Will")
    assert store.candidate(automatic_ids[0])["player_name"] is None
    assert store.candidate(automatic_ids[0])["assignment_source"] == "manual"
    assert store.candidate(automatic_ids[1])["player_name"] == "Will"


def test_external_project_cannot_supply_player_id(identity_project):
    store, identity_id, _, _ = identity_project
    with pytest.raises(LookupError, match="PLAYER_NOT_FOUND"):
        store.name_identity(identity_id, player_id="player_external")


def test_identity_cannot_be_assigned_to_candidate_from_another_project(identity_project, tmp_path):
    store, _, automatic_ids, _ = identity_project
    other = ProjectStore(tmp_path / "other")
    other.initialize()
    other.create_project("project_other", "Other")
    other_identity = other.create_identity(identity_id="identity_other")
    with pytest.raises(LookupError, match="IDENTITY_NOT_FOUND"):
        store.upsert_identity_assignment(automatic_ids[0], other_identity["id"], {}, 0.5)


def test_reanalysis_preserves_identity_and_manual_override(identity_project):
    store, identity_id, automatic_ids, manual_id = identity_project
    rows = store.list_candidates()
    store.replace_candidates(rows[0]["video_id"], rows)
    assert store.candidate(automatic_ids[0])["identity_id"] == identity_id
    assert store.candidate(automatic_ids[0])["assignment_source"] == "automatic"
    assert store.candidate(manual_id)["assignment_source"] == "manual"
    store.name_identity(identity_id, player_name="Will")
    assert store.candidate(manual_id)["player_name"] == "Other"


def test_automatic_assignment_uses_existing_identity_name(identity_project):
    store, identity_id, automatic_ids, _ = identity_project
    player = store.name_identity(identity_id, player_name="Will")["player"]
    store.upsert_identity_assignment(automatic_ids[0], identity_id, {"touch_time_ms": 600}, 0.9)
    row = store.candidate(automatic_ids[0])
    assert row["player_id"] == player["id"]
    assert row["touch_time_ms"] == 600
    assert row["identity_confidence"] == 0.9


def test_name_identity_protocol_returns_updated_count(identity_project):
    store, identity_id, _, _ = identity_project
    service = EngineService()
    result = service.handle("name_identity", {
        "project_root": str(store.root),
        "identity_id": identity_id,
        "player_name": "Will",
    })
    assert result["updated_candidates"] == 2
    assert result["identity"]["player_id"] == result["player"]["id"]


def test_existing_database_gain_identity_tables_on_connect(identity_project):
    store, _, _, _ = identity_project
    with store.connect() as connection:
        connection.execute("DROP TABLE candidate_player_assignments")
        connection.execute("DROP TABLE player_identities")
    with store.connect() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"player_identities", "candidate_player_assignments"} <= tables
