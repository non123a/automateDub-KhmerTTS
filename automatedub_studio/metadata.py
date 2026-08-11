"""Central application metadata for Studio packaging and UI."""

from __future__ import annotations

APP_NAME = "AutomateDub Studio"
APP_ID = "com.automatedub.studio"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "AI-assisted dubbing editor for AutomateDub."
APP_AUTHOR = "AutomateDub"
APP_LICENSE = "Beta evaluation build"
APP_GITHUB_URL = "https://github.com/non123a/automateDub-KhmerTTS"
APP_WEBSITE_URL = APP_GITHUB_URL
APP_REPORT_BUG_URL = f"{APP_GITHUB_URL}/issues"
PROJECT_EXTENSION = ".autodub"
EXECUTABLE_NAME = "automatedub-studio"


def release_artifact_name(platform: str, version: str = APP_VERSION, suffix: str = "") -> str:
    """Return the normalized release artifact name for a built package."""
    cleaned_suffix = suffix if not suffix or suffix.startswith(".") else f".{suffix}"
    return f"AutomateDub-Studio-{version}-{platform}{cleaned_suffix}"
