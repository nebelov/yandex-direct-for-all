#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ $# -lt 1 ]]; then
  cat <<EOF >&2
Usage:
  $(basename "$0") <command> [args...]

Commands:
  counters
  counter_info
  goals
  conversions
  traffic_summary
  utm_report
  search_engines
EOF
  exit 2
fi

cmd="$1"
shift

case "$cmd" in
  counters|counter_info|goals|conversions|traffic_summary|utm_report|search_engines)
    exec bash "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika/${cmd}.sh" "$@"
    ;;
  *)
    echo "Unknown metrika command: $cmd" >&2
    exit 2
    ;;
esac
