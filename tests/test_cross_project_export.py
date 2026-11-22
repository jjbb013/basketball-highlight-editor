import hashlib
import sqlite3
from pathlib import Path

import pytest

import engine.python.basketball_engine.service as module
from engine.python.basketball_engine.protocol import ProtocolError
from engine.python.basketball_engine.service import EngineService
from engine.python.basketball_engine.storage import ProjectStore
from tests.test_export_job_validation import setup_export, wait_job


def add_project(root: Path, source: Path, player_name: str):
    service = EngineService()
    service.create_project({'name': root.name, 'root_path': str(root)})
    source.write_bytes(f'video for {root.name}'.encode())
    stat = source.stat()
    store = ProjectStore(root)
    video = store.link_video({
        'source_path': str(source), 'source_size_bytes': stat.st_size,
        'source_mtime_ns': stat.st_mtime_ns, 'duration_ms': 2000,
        'width': 64, 'height': 64, 'video_codec': 'h264',
    })
    store.replace_candidates(video['id'], [{
        'id': f'candidate-{root.name}', 'video_id': video['id'],
        'event_time_ms': 500, 'default_start_ms': 0, 'default_end_ms': 1000,
        'review_start_ms': 0, 'review_end_ms': 1000, 'detector_version': 'test',
        'score': 0.8, 'confidence': 'review', 'evidence_json': '{}',
    }])
    if player_name:
        player = store.create_player(player_name)
        store.set_candidate_player(f'candidate-{root.name}', player['id'])
    return service, store


def test_read_only_snapshot_does_not_migrate_or_modify_source(tmp_path):
    _, store = add_project(tmp_path / 'history', tmp_path / 'history.mp4', 'Will')
    before = hashlib.sha256(store.db_path.read_bytes()).hexdigest()
    stat = store.db_path.stat()

    snapshot = store.read_export_snapshot()

    assert snapshot['project']['name'] == 'history'
    assert snapshot['candidates'][0]['player_name'] == 'Will'
    assert snapshot['videos'][0]['source_path'].endswith('history.mp4')
    assert hashlib.sha256(store.db_path.read_bytes()).hexdigest() == before
    after = store.db_path.stat()
    assert (after.st_size, after.st_mtime_ns) == (stat.st_size, stat.st_mtime_ns)
    with store.connect_read_only() as connection:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            connection.execute('CREATE TABLE must_not_exist (id INTEGER)')
        assert connection.execute('SELECT COUNT(*) FROM candidates').fetchone()[0] == 1


def test_same_normalized_name_merges_but_other_names_stay_separate(tmp_path, monkeypatch):
    service, primary, _, payload = setup_export(tmp_path / 'primary-data')
    player = primary.create_player('Will')
    primary.set_candidate_player('c1', player['id'])
    _, external = add_project(
        tmp_path / 'day-two', tmp_path / 'day-two.mp4', ' ｗｉｌｌ ',
    )
    _, other = add_project(
        tmp_path / 'day-three', tmp_path / 'day-three.mp4', 'Willow',
    )
    payload['source_projects'] = [
        {'project_root': str(external.root)},
        {'project_root': str(other.root)},
    ]
    payload['mode'] = 'merge_by_player'
    payload.pop('output_path')
    before = hashlib.sha256(external.db_path.read_bytes()).hexdigest()
    groups = []

    def fake_export(candidates, output_dir, mode, output_path, **kwargs):
        groups.append(candidates)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b'new export')
        return {'files': [str(output_path)], 'clip_files': [], 'duration_ms': 1000,
                'processing_ms': 1, 'merged_overlap_count': 0}

    monkeypatch.setattr(module, 'export_goal_clips', fake_export)
    monkeypatch.setattr(service, 'inspect_video', lambda payload: {})
    started = service.start_export(payload)['job']
    assert wait_job(primary, started['id'])['state'] == 'completed'

    assert sorted(group[0]['player_name'] for group in groups) == ['Will', 'Willow']
    will = next(group for group in groups if group[0]['player_name'] == 'Will')
    assert len(will) == 2
    assert len({candidate['source_project']['id'] for candidate in will}) == 2
    assert all(candidate.get('source_video') for candidate in will)
    assert sorted(path.name for path in Path(payload['output_dir']).glob('*.mp4')) == [
        'Will.mp4', 'Willow.mp4',
    ]
    assert hashlib.sha256(external.db_path.read_bytes()).hexdigest() == before
    service.shutdown()


def test_unnamed_players_never_merge_across_projects(tmp_path):
    service, primary, _ = setup_export(tmp_path / 'primary-data')[:3]
    _, external = add_project(tmp_path / 'day-two', tmp_path / 'day-two.mp4', None)
    candidates = service._export_candidate_snapshot(primary, primary.list_videos()[0]['id'], {})[2]
    candidates.extend(service._external_candidate_snapshots(
        primary, {'source_projects': [{'project_root': str(external.root)}]},
    ))
    from engine.python.basketball_engine.adapters.project_sources import group_player_candidates

    groups = group_player_candidates(candidates)
    assert len(groups) == 2
    assert {group[0]['source_project']['id'] for group in groups.values()} == {
        primary.project()['id'], external.project()['id'],
    }


def test_external_project_change_cleans_new_outputs(tmp_path, monkeypatch):
    service, primary, _, payload = setup_export(tmp_path / 'primary-data')
    _, external = add_project(tmp_path / 'day-two', tmp_path / 'day-two.mp4', 'Will')
    payload['source_projects'] = [{'project_root': str(external.root)}]
    target = Path(payload['output_path'])
    target.write_bytes(b'previous export')
    monkeypatch.setattr(service, 'inspect_video', lambda payload: {})

    def change_source_project(candidates, output_dir, mode, output_path, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b'new output')
        external.create_player('changed while exporting')
        return {'files': [str(output_path)], 'clip_files': [], 'duration_ms': 1000,
                'processing_ms': 1, 'merged_overlap_count': 0}

    monkeypatch.setattr(module, 'export_goal_clips', change_source_project)
    started = service.start_export(payload)['job']
    finished = wait_job(primary, started['id'])
    assert finished['state'] == 'failed'
    assert finished['error_code'] == 'PROJECT_CHANGED'
    assert target.read_bytes() == b'previous export'
    assert primary.list_exports(primary.project()['id']) == []
    service.shutdown()


def test_source_projects_must_be_valid_and_unique(tmp_path):
    service, primary, _, payload = setup_export(tmp_path)
    payload['source_projects'] = [{'project_root': str(primary.root)}]
    with pytest.raises(ProtocolError, match='不能重复') as error:
        service.start_export(payload)
    assert error.value.code == 'INVALID_REQUEST'
    assert primary.list_jobs(primary.project()['id'], states=('queued', 'running')) == []
    service.shutdown()
