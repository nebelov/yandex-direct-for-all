#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FORCE="${1:-}"

CODEX_TARGET="${CODEX_HOME:-$HOME/.codex}"
CLAUDE_TARGET="${CLAUDE_HOME:-$HOME/.claude}"

bash "$SCRIPT_DIR/install_codex_bundle.sh" "$FORCE"

copy_dir() {
  local src="$1"
  local dst="$2"
  if [[ -e "$dst" && "$FORCE" != "--force" ]]; then
    echo "ERROR: target already exists: $dst"
    echo "Re-run with --force to overwrite."
    exit 2
  fi
  rm -rf "$dst"
  mkdir -p "$(dirname "$dst")"
  rsync -a --exclude '__pycache__' --exclude '.venv' "$src/" "$dst/"
}

mkdir -p "$CLAUDE_TARGET/skills" "$CLAUDE_TARGET/mcp"

copy_dir "$PLUGIN_DIR/skills/yandex-performance-ops" "$CLAUDE_TARGET/skills/yandex-performance-ops"
copy_dir "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle" "$CLAUDE_TARGET/skills/yandex-direct-client-lifecycle"
copy_dir "$PLUGIN_DIR/skills/roistat-reports-api" "$CLAUDE_TARGET/skills/roistat-reports-api"
copy_dir "$PLUGIN_DIR/skills/amocrm-api-control" "$CLAUDE_TARGET/skills/amocrm-api-control"

copy_dir "$PLUGIN_DIR/mcp/yandex-direct" "$CLAUDE_TARGET/mcp/yandex-direct"
copy_dir "$PLUGIN_DIR/mcp/yandex-search" "$CLAUDE_TARGET/mcp/yandex-search"
copy_dir "$PLUGIN_DIR/mcp/yandex-wordstat" "$CLAUDE_TARGET/mcp/yandex-wordstat"

cat <<EOF
Installed bundle into:
  Codex:  $CODEX_TARGET
  Claude: $CLAUDE_TARGET
EOF
