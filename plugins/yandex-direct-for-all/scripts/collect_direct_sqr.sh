#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec "$ROOT/skills/yandex-performance-ops/scripts/fetch_sqr.sh" "$@"
