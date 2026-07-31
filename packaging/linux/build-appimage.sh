#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPDIR="${ROOT}/dist/linux/AppDir"
VERSION="${AUTOMATEDUB_VERSION:-0.1.0}"

mkdir -p "${APPDIR}/usr/bin" "${APPDIR}/usr/share/applications" "${APPDIR}/usr/share/icons/hicolor/scalable/apps" "${APPDIR}/usr/share/mime/packages"
cp -R "${ROOT}/dist/linux/AutomateDub Studio/"* "${APPDIR}/usr/bin/"
cp "${ROOT}/packaging/linux/automatedub-studio.desktop" "${APPDIR}/"
cp "${ROOT}/packaging/linux/automatedub-studio.desktop" "${APPDIR}/usr/share/applications/"
cp "${ROOT}/packaging/linux/automatedub-studio.xml" "${APPDIR}/usr/share/mime/packages/"
cp "${ROOT}/automatedub_studio/resources/icons/automatedub-studio.svg" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/automatedub-studio.svg"

ARCH="${ARCH:-x86_64}" VERSION="${VERSION}" appimagetool "${APPDIR}" "${ROOT}/dist/AutomateDub-Studio-${VERSION}-linux.AppImage"
