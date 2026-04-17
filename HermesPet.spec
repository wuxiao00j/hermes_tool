# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path.cwd()
APP_DIR = ROOT / '11'
ICON_PATH = ROOT / 'hermes_pet_generated.icns'


a = Analysis(
    ['hermes_pet_v3.py'],
    pathex=[str(ROOT), str(APP_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=['ui', 'config', 'monitor'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HermesPet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ICON_PATH)],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HermesPet',
)
app = BUNDLE(
    coll,
    name='HermesPet.app',
    icon=str(ICON_PATH),
    bundle_identifier='com.wuxiao00j.hermestool',
    info_plist={
        'LSUIElement': True,
        'CFBundleDisplayName': 'HermesTool',
        'CFBundleName': 'HermesTool',
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '1',
        'NSHighResolutionCapable': True,
    },
)
