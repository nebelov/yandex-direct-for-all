#!/usr/bin/env bash
set -euo pipefail
# Start the read-only Yandex Direct MCP server.
cd "$(dirname "$0")"
export YD_MCP_PORT="${YD_MCP_PORT:-8765}"
transport="${1:-${YANDEX_DIRECT_TRANSPORT:-stdio}}"
if [[ "$transport" != "stdio" && "$transport" != "sse" ]]; then
  echo "Допустимый транспорт: stdio или sse" >&2
  exit 2
fi
exec uv run --frozen python server.py "$transport"
