import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/macos_dmg/BHE-Pro-首次打开修复.command'
GUIDE = ROOT / 'scripts/macos_dmg/BHE-Pro-使用说明.html'
BUILD = ROOT / 'scripts/build_macos_release.sh'


def test_helper_and_guide_never_target_original_bhe():
    helper = HELPER.read_text(encoding='utf-8')
    guide = GUIDE.read_text(encoding='utf-8')
    for text in (helper, guide):
        assert '/Applications/BHE.app' not in text
        assert '/Volumes/BHE/BHE.app' not in text
        assert 'pkill -x BHE ' not in text
        assert 'open -a BHE\n' not in text
    assert 'APP_NAME="BHE Pro.app"' in helper
    assert 'DEST="/Applications/$APP_NAME"' in helper
    assert 'pkill -x "BHE Pro"' in helper
    assert 'ditto "$VOLUME_APP" "$DEST"' in helper
    assert 'codesign --verify --deep --strict "$DEST"' in helper
    assert 'ditto "/Volumes/BHE Pro/BHE Pro.app" "/Applications/BHE Pro.app"' in guide
    assert 'xattr -dr com.apple.quarantine "/Applications/BHE Pro.app"' in guide
    assert 'open "/Applications/BHE Pro.app"' in guide


@pytest.mark.skipif(os.name == 'nt', reason='macOS packaging uses Bash')
def test_build_packages_space_named_app_with_isolated_fake_tools(tmp_path):
    tools = tmp_path / 'tools'
    tools.mkdir()
    calls = tmp_path / 'calls'
    app_dir = tmp_path / 'Release With Spaces'
    runtime = tmp_path / 'Runtime With Spaces'
    python = runtime / 'python/bin/python3'
    python.parent.mkdir(parents=True)
    python.write_text(
        '#!/bin/bash\nprintf "python" >> "$CALL_LOG"\n'
        'printf " <%s>" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
    )
    python.chmod(0o755)
    flutter = tools / 'flutter'
    flutter.write_text(
        '#!/bin/bash\nset -e\nprintf "flutter" >> "$CALL_LOG"\n'
        'printf " <%s>" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
        'mkdir -p "$BHE_APP_DIR/BHE Pro.app/Contents/MacOS"\n'
        'printf executable > "$BHE_APP_DIR/BHE Pro.app/Contents/MacOS/BHE Pro"\n'
    )
    for name in ('codesign', 'ditto'):
        tool = tools / name
        tool.write_text(
            '#!/bin/bash\nprintf "' + name + '" >> "$CALL_LOG"\n'
            'printf " <%s>" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
        )
        tool.chmod(0o755)
    hdiutil = tools / 'hdiutil'
    hdiutil.write_text(
        '#!/bin/bash\nprintf "hdiutil" >> "$CALL_LOG"\n'
        'printf " <%s>" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
        'if [[ "$1" == verify ]]; then exit 0; fi\n'
        'for last; do :; done\nprintf dmg > "$last"\n'
    )
    for tool in (flutter, hdiutil):
        tool.chmod(0o755)
    output = tmp_path / 'output with spaces/BHE-Pro-test.dmg'
    result = subprocess.run(
        ['bash', str(BUILD)],
        env={
            **os.environ,
            'PATH': f'{tools}:{os.environ["PATH"]}',
            'CALL_LOG': str(calls),
            'FLUTTER_BIN': str(flutter),
            'BHE_APP_DIR': str(app_dir),
            'BHE_RUNTIME_OUT': str(runtime),
            'BHE_SKIP_RUNTIME_PREPARE': '1',
            'BHE_BUILD_NAME': '0.1.16-macos.3',
            'BHE_BUILD_NUMBER': '3',
            'BHE_ARCH': 'arm64',
            'BHE_DMG_OUT': str(output),
            'TMPDIR': str(tmp_path),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    log = calls.read_text()
    assert f'ditto <{app_dir}/BHE Pro.app> <' in log
    assert f'codesign <--deep> <--force> <--sign> <-> <{app_dir}/BHE Pro.app>' in log
    assert 'hdiutil <create> <-volname> <BHE Pro>' in log
    assert output.read_bytes() == b'dmg'
    assert output.with_suffix('.dmg.sha256').is_file()
    assert 'BHE Pro.app' in result.stdout
