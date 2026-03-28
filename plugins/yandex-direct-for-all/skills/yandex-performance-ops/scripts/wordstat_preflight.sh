#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-$(pwd)/.codex-artifacts/wordstat-preflight}"
mkdir -p "$OUT_DIR"

if [[ -z "${YANDEX_WORDSTAT_TOKEN:-}" ]]; then
  echo "ERROR: YANDEX_WORDSTAT_TOKEN is not set" >&2
  exit 2
fi

code=$(curl -s -o "$OUT_DIR/wordstat_user_info_raw.json" -w "%{http_code}" \
  -X POST "https://api.wordstat.yandex.net/v1/userInfo" \
  -H "Authorization: Bearer ${YANDEX_WORDSTAT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}')

echo "HTTP=$code"
if [[ "$code" != "200" ]]; then
  cat "$OUT_DIR/wordstat_user_info_raw.json"
  exit 1
fi

cat "$OUT_DIR/wordstat_user_info_raw.json"

