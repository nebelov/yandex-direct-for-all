#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -d node_modules ]] || npm ci --omit=dev --ignore-scripts --no-audit --no-fund >&2
exec node src/index.mjs
