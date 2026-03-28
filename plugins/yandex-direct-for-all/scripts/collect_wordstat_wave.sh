#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

exec node "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/wordstat_collect_wave.js" "$@"
