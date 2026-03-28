#!/bin/bash
# fetch_sqr.sh — Сбор Search Query Report для списка кампаний Яндекс.Директ
# v1.0 2026-03-02
#
# Использование:
#   ./fetch_sqr.sh --token TOKEN --login LOGIN --campaigns "ID1,ID2,..." --from YYYY-MM-DD --to YYYY-MM-DD --output-dir ./sqr
#   ./fetch_sqr.sh --token TOKEN --login LOGIN --campaigns-file campaigns.txt --days 30 --output-dir ./sqr
#
# Создаёт:
#   output-dir/sqr_{CID}.tsv    — SQR для каждой кампании
#   output-dir/all_sqr.tsv      — объединённый файл всех SQR
#
# Reports API возвращает 201/202 (отчёт строится) — скрипт автоматически ретраит.

set -euo pipefail

TOKEN=""
LOGIN=""
CAMPAIGNS=""
CAMPAIGNS_FILE=""
DATE_FROM=""
DATE_TO=""
DAYS=""
OUTPUT_DIR="./sqr"
MAX_RETRIES=10
RETRY_DELAY=2

show_usage() {
  echo "Usage: $0 --token TOKEN --login LOGIN [--campaigns ID1,ID2,...] [--campaigns-file FILE] [--from YYYY-MM-DD --to YYYY-MM-DD | --days N] [--output-dir DIR]"
  echo ""
  echo "Defaults:"
  echo "  --days N   means the last N completed days (yesterday inclusive)"
  echo "  no dates   means the last 7 completed days"
}

usage() {
  show_usage
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) show_usage; exit 0;;
    --token) TOKEN="$2"; shift 2;;
    --login) LOGIN="$2"; shift 2;;
    --campaigns) CAMPAIGNS="$2"; shift 2;;
    --campaigns-file) CAMPAIGNS_FILE="$2"; shift 2;;
    --from) DATE_FROM="$2"; shift 2;;
    --to) DATE_TO="$2"; shift 2;;
    --days) DAYS="$2"; shift 2;;
    --output-dir) OUTPUT_DIR="$2"; shift 2;;
    *) echo "Unknown option: $1"; usage;;
  esac
done

[[ -z "$TOKEN" ]] && { echo "ERROR: --token required"; usage; }
[[ -z "$LOGIN" ]] && { echo "ERROR: --login required"; usage; }

# Определяем даты
if [[ -n "$DAYS" ]]; then
  DATE_TO=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)
  DATE_FROM=$(date -v-${DAYS}d +%Y-%m-%d 2>/dev/null || date -d "-${DAYS} days" +%Y-%m-%d)
fi
[[ -z "$DATE_FROM" ]] && DATE_FROM=$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d "-7 days" +%Y-%m-%d)
[[ -z "$DATE_TO" ]] && DATE_TO=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)

# Список кампаний
if [[ -n "$CAMPAIGNS_FILE" ]] && [[ -f "$CAMPAIGNS_FILE" ]]; then
  IFS=$'\n' read -d '' -r -a CAMP_ARRAY < "$CAMPAIGNS_FILE" || true
elif [[ -n "$CAMPAIGNS" ]]; then
  IFS=',' read -r -a CAMP_ARRAY <<< "$CAMPAIGNS"
else
  echo "ERROR: --campaigns or --campaigns-file required"; usage
fi

mkdir -p "$OUTPUT_DIR"

echo "=== fetch_sqr.sh v1.0 ==="
echo "Period: $DATE_FROM — $DATE_TO"
echo "Campaigns: ${#CAMP_ARRAY[@]}"
echo "Output: $OUTPUT_DIR"
echo ""

TOTAL=0
ERRORS=0

for CID in "${CAMP_ARRAY[@]}"; do
  CID=$(echo "$CID" | tr -d '[:space:]')
  [[ -z "$CID" ]] && continue

  REPORT_NAME="SQR_${CID}_$(date +%s)_${RANDOM}"
  OUTFILE="$OUTPUT_DIR/sqr_${CID}.tsv"

  BODY="{\"params\":{\"SelectionCriteria\":{\"DateFrom\":\"$DATE_FROM\",\"DateTo\":\"$DATE_TO\",\"Filter\":[{\"Field\":\"CampaignId\",\"Operator\":\"EQUALS\",\"Values\":[\"$CID\"]},{\"Field\":\"Impressions\",\"Operator\":\"GREATER_THAN\",\"Values\":[\"0\"]}]},\"FieldNames\":[\"CampaignId\",\"AdGroupName\",\"Query\",\"Criterion\",\"CriterionType\",\"Impressions\",\"Clicks\",\"Ctr\",\"Cost\",\"AvgCpc\"],\"ReportName\":\"$REPORT_NAME\",\"ReportType\":\"SEARCH_QUERY_PERFORMANCE_REPORT\",\"DateRangeType\":\"CUSTOM_DATE\",\"Format\":\"TSV\",\"IncludeVAT\":\"YES\"}}"

  SUCCESS=false
  for ATTEMPT in $(seq 1 $MAX_RETRIES); do
    HTTP_CODE=$(curl -s -o "$OUTFILE" -w "%{http_code}" -X POST "https://api.direct.yandex.com/json/v5/reports" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Client-Login: $LOGIN" \
      -H "Accept-Language: ru" \
      -H "Content-Type: application/json" \
      -H "processingMode: auto" \
      -H "returnMoneyInMicros: false" \
      -H "skipReportHeader: true" \
      -H "skipColumnHeader: false" \
      -H "skipReportSummary: true" \
      -d "$BODY")

    if [[ "$HTTP_CODE" == "200" ]]; then
      LINES=$(wc -l < "$OUTFILE" | tr -d ' ')
      QUERIES=$((LINES - 1))
      echo "  $CID: OK ($QUERIES queries)"
      TOTAL=$((TOTAL + QUERIES))
      SUCCESS=true
      break
    elif [[ "$HTTP_CODE" == "201" ]] || [[ "$HTTP_CODE" == "202" ]]; then
      sleep $RETRY_DELAY
    else
      echo "  $CID: ERROR HTTP $HTTP_CODE (attempt $ATTEMPT)"
      if [[ $ATTEMPT -eq $MAX_RETRIES ]]; then
        echo "  $CID: FAILED after $MAX_RETRIES attempts"
        ERRORS=$((ERRORS + 1))
        cat "$OUTFILE" 2>/dev/null
      fi
      sleep 1
    fi
  done

  [[ "$SUCCESS" != "true" ]] && ERRORS=$((ERRORS + 1))
  sleep 0.3
done

# Merge all SQR into one file
echo ""
echo "Merging all SQR files..."
FIRST=true
for f in "$OUTPUT_DIR"/sqr_*.tsv; do
  [[ ! -f "$f" ]] && continue
  if $FIRST; then
    head -1 "$f" > "$OUTPUT_DIR/all_sqr.tsv"
    FIRST=false
  fi
  tail -n +2 "$f" >> "$OUTPUT_DIR/all_sqr.tsv"
done

MERGED_LINES=$(wc -l < "$OUTPUT_DIR/all_sqr.tsv" | tr -d ' ')
echo ""
echo "=== DONE ==="
echo "Total queries: $TOTAL"
echo "Merged file: $OUTPUT_DIR/all_sqr.tsv ($MERGED_LINES lines)"
echo "Errors: $ERRORS"
