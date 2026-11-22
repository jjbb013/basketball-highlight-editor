#!/usr/bin/env python3
"""Load both embedded detectors with the packaged interpreter, offline."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from check_detector import RESULT_PREFIX


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    python = runtime / 'python/bin/python3'
    script = runtime / 'scripts/check_detector.py'
    if not python.is_file() or not script.is_file():
        raise SystemExit('Packaged Python or detector check is missing')
    with tempfile.TemporaryDirectory(prefix='bhe-packaged-models-') as config:
        env = dict(os.environ, YOLO_AUTOINSTALL='false', YOLO_CONFIG_DIR=config,
                   PYTHONDONTWRITEBYTECODE='1')
        for name in ('bball_model.pt', 'yolo11n-pose.pt'):
            model = runtime / 'models' / name
            result = subprocess.run(
                [str(python), str(script), '--model', str(model), '--device', 'cpu'],
                cwd=runtime, env=env, capture_output=True, text=True, timeout=180,
            )
            print(result.stdout, end='')
            print(result.stderr, end='')
            lines = [line for line in result.stdout.splitlines() if line.startswith(RESULT_PREFIX)]
            if result.returncode or not lines:
                raise SystemExit(f'Packaged model failed to load: {name}')
            payload = json.loads(lines[-1][len(RESULT_PREFIX):])
            if payload.get('status') != 'ready':
                raise SystemExit(f'Packaged model is not ready: {name}')
            print(f'PACKAGED_MODEL_OK={name}')


if __name__ == '__main__':
    main()
