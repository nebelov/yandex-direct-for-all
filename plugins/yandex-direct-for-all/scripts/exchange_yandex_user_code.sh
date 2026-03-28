#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  exchange_yandex_user_code.sh --service <direct|metrika|audience> --code <confirmation-code> [options]

This is a compatibility wrapper over:
  start_yandex_user_auth.py --mode manual-code
EOF
  exit 0
fi

exec python3 "$SCRIPT_DIR/start_yandex_user_auth.py" --mode manual-code "$@"
