#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${AUTOMATEDUB_VERSION:-0.1.0}"
APP="${ROOT}/dist/macos/AutomateDub.app"
DMG="${ROOT}/dist/AutomateDub-Studio-${VERSION}-macos.dmg"

hdiutil create -volname "AutomateDub Studio" -srcfolder "${APP}" -ov -format UDZO "${DMG}"
