#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <output_file> <endpoint> [json_file] [--project ID] [--api-key KEY] [--base-url URL]" >&2
  exit 1
}

[[ $# -lt 2 ]] && usage

OUTPUT_FILE="$1"
ENDPOINT="$2"
shift 2

JSON_FILE=""
PROJECT="${ROISTAT_PROJECT:-}"
API_KEY="${ROISTAT_API_KEY:-}"
BASE_URL="${ROISTAT_BASE_URL:-https://cloud.roistat.com/api/v1}"

if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
  JSON_FILE="$1"
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done

[[ -z "$PROJECT" ]] && { echo "ERROR: missing Roistat project. Use --project or ROISTAT_PROJECT." >&2; exit 2; }
[[ -z "$API_KEY" ]] && { echo "ERROR: missing Roistat API key. Use --api-key or ROISTAT_API_KEY." >&2; exit 2; }

mkdir -p "$(dirname "$OUTPUT_FILE")"

if [[ -n "$JSON_FILE" && -f "$JSON_FILE" ]]; then
  BODY="$(cat "$JSON_FILE")"
elif [[ ! -t 0 ]]; then
  BODY="$(cat)"
else
  BODY="{}"
fi

HTTP_CODE=$(curl -s -w "%{http_code}" -o "$OUTPUT_FILE" -X POST \
  "${BASE_URL%/}/${ENDPOINT}?project=${PROJECT}" \
  -H "Content-Type: application/json" \
  -H "Api-key: ${API_KEY}" \
  -d "$BODY")

python3 -m json.tool "$OUTPUT_FILE" > "${OUTPUT_FILE}.tmp" 2>/dev/null \
  && mv "${OUTPUT_FILE}.tmp" "$OUTPUT_FILE" \
  || rm -f "${OUTPUT_FILE}.tmp"

LINES=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
STATUS=$(python3 -c "import json; d=json.load(open('$OUTPUT_FILE')); print(d.get('status','?'))" 2>/dev/null || echo "?")

echo "=== Roistat: ${ENDPOINT} ==="
echo "HTTP: ${HTTP_CODE} | Status: ${STATUS}"
echo "File: ${OUTPUT_FILE} (${LINES} lines, ${SIZE})"

