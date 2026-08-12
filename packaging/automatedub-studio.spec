# PyInstaller spec for AutomateDub Studio.
#
# Run through:
#   uv run python packaging/build.py --platform <windows|macos|linux>

from pathlib import Path

from automatedub_studio.metadata import APP_NAME, APP_VERSION

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent
MACOS_ICON = (
    ROOT / "automatedub_studio" / "resources" / "icons" / "automatedub-studio.icns"
)
VERSION_INFO = ROOT / "packaging" / "version_info.txt"

a = Analysis(
    [str(ROOT / "automatedub_studio" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "automatedub_studio" / "resources" / "icons"), "automatedub_studio/resources/icons"),
        (str(ROOT / "automatedub_studio" / "resources" / "runtime"), "runtime"),
    ],
    hiddenimports=[
        "automatedub_studio.providers.stt",
        "automatedub_studio.providers.translation",
        "automatedub_studio.providers.tts",
    ],
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
    name="AutomateDub Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(VERSION_INFO),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="AutomateDub Studio",
)

app = BUNDLE(
    coll,
    name="AutomateDub.app",
    icon=str(MACOS_ICON),
    bundle_identifier="com.automatedub.studio",
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "AutomateDub Project",
                "CFBundleTypeExtensions": ["autodub"],
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
            }
        ],
    },
)
