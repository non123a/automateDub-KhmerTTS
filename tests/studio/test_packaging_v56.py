from __future__ import annotations

import importlib.util
from pathlib import Path

from automatedub_studio.metadata import (
    APP_DESCRIPTION,
    APP_ID,
    APP_NAME,
    APP_VERSION,
    PROJECT_EXTENSION,
    release_artifact_name,
)
from automatedub_studio.ui.about_dialog import (
    APP_DESCRIPTION as ABOUT_DESCRIPTION,
)
from automatedub_studio.ui.about_dialog import (
    APP_NAME as ABOUT_NAME,
)
from automatedub_studio.ui.about_dialog import (
    APP_VERSION as ABOUT_VERSION,
)

ROOT = Path(__file__).resolve().parents[2]


def _build_module():
    spec = importlib.util.spec_from_file_location(
        "automatedub_packaging_build",
        ROOT / "packaging" / "build.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_application_metadata_is_centralized():
    assert APP_NAME == "AutomateDub Studio"
    assert APP_VERSION == ABOUT_VERSION
    assert APP_NAME == ABOUT_NAME
    assert APP_DESCRIPTION == ABOUT_DESCRIPTION
    assert APP_ID == "com.automatedub.studio"
    assert PROJECT_EXTENSION == ".autodub"


def test_release_artifact_names_are_consistent():
    assert (
        release_artifact_name("windows", "1.2.3", "exe")
        == "AutomateDub-Studio-1.2.3-windows.exe"
    )
    assert (
        release_artifact_name("macos", "1.2.3", ".dmg")
        == "AutomateDub-Studio-1.2.3-macos.dmg"
    )


def test_packaging_build_commands_use_platform_dist_directories():
    build = _build_module()

    windows = build.package_command("windows", clean=True)
    macos = build.package_command("macos", clean=False)
    linux = build.package_command("linux", clean=True)

    assert windows[:2] == ["pyinstaller", "--clean"]
    assert "--distpath" in windows
    assert str(ROOT / "dist" / "windows") in windows
    assert "--clean" not in macos
    assert str(ROOT / "dist" / "macos") in macos
    assert str(ROOT / "dist" / "linux") in linux


def test_packaging_paths_are_resolved_from_the_repository_root():
    spec = (ROOT / "packaging" / "automatedub-studio.spec").read_text(encoding="utf-8")
    macos = (ROOT / "packaging" / "macos" / "create-dmg.sh").read_text(
        encoding="utf-8"
    )
    linux = (ROOT / "packaging" / "linux" / "build-appimage.sh").read_text(
        encoding="utf-8"
    )
    windows = (ROOT / "packaging" / "windows" / "AutomateDubStudio.iss").read_text(
        encoding="utf-8"
    )

    assert 'SPEC_DIR = Path(SPECPATH).resolve()' in spec
    assert 'ROOT = SPEC_DIR.parent' in spec
    assert 'str(ROOT / "automatedub_studio" / "main.py")' in spec
    assert 'name="AutomateDub.app"' in spec
    assert "COLLECT(" in spec
    assert "automatedub-studio.icns" in spec
    assert '"resources" / "runtime"' in spec
    assert 'VERSION_INFO = ROOT / "packaging" / "version_info.txt"' in spec
    assert 'version=str(VERSION_INFO)' in spec
    assert (ROOT / "packaging" / "version_info.txt").is_file()
    assert (
        ROOT / "automatedub_studio" / "resources" / "icons" / "automatedub-studio.icns"
    ).is_file()
    assert '"CFBundleShortVersionString": APP_VERSION' in spec
    assert 'APP="${ROOT}/dist/macos/AutomateDub.app"' in macos
    assert 'APPDIR="${ROOT}/dist/linux/AppDir"' in linux
    assert '"${ROOT}/dist/linux/AutomateDub Studio/"*' in linux
    assert '{#SourcePath}\\..\\..\\dist\\windows\\AutomateDub Studio\\*' in windows


def test_platform_packaging_metadata_declares_file_associations():
    windows = (ROOT / "packaging" / "windows" / "AutomateDubStudio.iss").read_text(
        encoding="utf-8"
    )
    linux_desktop = (
        ROOT / "packaging" / "linux" / "automatedub-studio.desktop"
    ).read_text(encoding="utf-8")
    linux_mime = (ROOT / "packaging" / "linux" / "automatedub-studio.xml").read_text(
        encoding="utf-8"
    )
    spec = (ROOT / "packaging" / "automatedub-studio.spec").read_text(
        encoding="utf-8"
    )

    assert ".autodub" in windows
    assert '""%1"""' in windows
    assert "MimeType=application/x-automatedub-project;" in linux_desktop
    assert '<glob pattern="*.autodub"/>' in linux_mime
    assert "CFBundleDocumentTypes" in spec
    assert "autodub" in spec


def test_release_docs_and_ci_workflows_exist():
    for path in (
        ROOT / "docs" / "BUILD.md",
        ROOT / "docs" / "INSTALL.md",
        ROOT / "docs" / "RELEASE.md",
        ROOT / ".github" / "workflows" / "tests.yml",
        ROOT / ".github" / "workflows" / "package.yml",
        ROOT / "automatedub_studio" / "resources" / "icons" / "automatedub-studio.svg",
    ):
        assert path.is_file()
