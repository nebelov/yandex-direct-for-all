#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

for argument in "$@"; do
  if [[ "$argument" == "--api-key" ]]; then
    echo "Сырой ключ Roistat в командной строке запрещён; используйте ROISTAT_API_KEY или --credentials-file" >&2
    exit 2
  fi
done

exec bash "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/roistat_query.sh" "$@"
