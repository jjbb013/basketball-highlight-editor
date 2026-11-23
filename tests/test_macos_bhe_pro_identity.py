import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'apps/desktop/macos/Runner'


def test_macos_native_bundle_is_independent_bhe_pro():
    config = {}
    for line in (RUNNER / 'Configs/AppInfo.xcconfig').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('//'):
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    assert config['PRODUCT_NAME'] == 'BHE Pro'
    assert config['PRODUCT_BUNDLE_IDENTIFIER'] == 'com.courtside.bhepro'
    assert config['PRODUCT_COPYRIGHT'].startswith('Copyright © 2026 BHE Pro ')
    with (RUNNER / 'Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    assert plist['CFBundleDisplayName'] == 'BHE Pro'
    assert plist['CFBundleExecutable'] == '$(EXECUTABLE_NAME)'
    assert plist['CFBundleIdentifier'] == '$(PRODUCT_BUNDLE_IDENTIFIER)'


def test_native_window_and_method_channel_keep_their_respective_names():
    source = (RUNNER / 'MainFlutterWindow.swift').read_text()
    assert 'self.title = "BHE Pro"' in source
    assert 'name: "bhe/file_dialog"' in source
