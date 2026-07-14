#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec python3 "$ROOT/skills/yandex-performance-ops/scripts/collect_direct_cabinet_snapshot.py" "$@"
