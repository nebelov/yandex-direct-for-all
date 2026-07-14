#!/usr/bin/env bash
set -euo pipefail
plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$plugin_root/mcp/yandex-wordstat/scripts/wordstat_cloud_gateway_collect.py" "$@"
