#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  exchange_yandex_user_code.sh --service <direct|metrika|audience> [options]

This is a compatibility wrapper over:
  start_yandex_user_auth.py --mode manual-code.
  The one-time code is requested through hidden input or standard input.
EOF
  exit 0
fi

exec python3 "$SCRIPT_DIR/start_yandex_user_auth.py" --mode manual-code "$@"
