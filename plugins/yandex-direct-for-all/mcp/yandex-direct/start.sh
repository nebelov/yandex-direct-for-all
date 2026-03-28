#!/bin/bash
# Start Yandex Direct MCP Server
cd "$(dirname "$0")"
export YD_TOKEN="${YD_TOKEN:-}"
export YD_MCP_PORT="${YD_MCP_PORT:-8765}"
exec python3 server.py sse
