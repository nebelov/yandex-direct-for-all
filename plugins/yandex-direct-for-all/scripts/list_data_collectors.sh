#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

printf 'Yandex Direct For All: фактический перечень сборщиков\n\n'

find "$PLUGIN_DIR/scripts" "$PLUGIN_DIR/skills" "$PLUGIN_DIR/mcp" -type f \
  \( -name 'collect*' -o -name 'fetch*' -o -name '*report*' -o -name '*search*' -o -name '*wordstat*' -o -name '*snapshot*' -o -name 'goals.sh' -o -name 'counters.sh' -o -name 'conversions.sh' \) \
  \( -name '*.sh' -o -name '*.py' -o -name '*.js' -o -name '*.mjs' \) \
  ! -path '*/tests/*' ! -path '*/test/*' ! -path '*/node_modules/*' ! -path '*/__pycache__/*' \
  -print | LC_ALL=C sort | while IFS= read -r path; do
    printf '%s\n' "${path#"$PLUGIN_DIR/"}"
  done
