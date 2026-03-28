#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

exec bash "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/roistat_query.sh" "$@"
