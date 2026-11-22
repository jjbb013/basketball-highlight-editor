from pathlib import Path
import hashlib
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_pose_runtime_is_pinned_and_copied_without_runtime_download():
    script = (ROOT / 'scripts/prepare_macos_runtime.sh').read_text(encoding='utf-8')
    expected = '869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0'
    pose = ROOT / 'models/yolo11n-pose.pt'
    assert hashlib.sha256(pose.read_bytes()).hexdigest() == expected
    assert f'POSE_SHA256="${{BHE_POSE_SHA256:-{expected}}}"' in script
    assert 'shasum -a 256 --check' in script
    assert 'cp "$POSE_MODEL" "$OUT/models/yolo11n-pose.pt"' in script
    subprocess.run(['bash', '-n', str(ROOT / 'scripts/prepare_macos_runtime.sh')], check=True)


def test_packaged_ball_and_pose_models_are_loaded_before_dmg_creation():
    script = (ROOT / 'scripts/build_macos_release.sh').read_text(encoding='utf-8')
    pose_check = '"$APP_RUNTIME/scripts/check_detector.py" --model "$APP_RUNTIME/models/yolo11n-pose.pt" --device cpu'
    ball_check = '"$APP_RUNTIME/scripts/check_detector.py" --model "$APP_RUNTIME/models/bball_model.pt" --device cpu'
    assert pose_check in script
    assert ball_check in script
    assert script.index(ball_check) < script.index('codesign --deep')
    assert script.index(pose_check) < script.index('codesign --deep')
    subprocess.run(['bash', '-n', str(ROOT / 'scripts/build_macos_release.sh')], check=True)


def test_ci_smoke_loads_both_packaged_models_without_network_repair():
    workflow = yaml.safe_load((ROOT / '.github/workflows/release-packages.yml').read_text())
    build = next(step for step in workflow['jobs']['macos']['steps'] if step.get('name') == 'Build macOS package')
    script = build['run']
    assert 'scripts/check_packaged_models.py --runtime' in script
    assert 'BHE.app/Contents/Resources/runtime' in script
    assert 'YOLO_AUTOINSTALL=false' in script
    subprocess.run(['bash', '-n'], input=script, text=True, check=True)
