#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

exec python3 "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/yandex_search_ads_batch.py" "$@"
