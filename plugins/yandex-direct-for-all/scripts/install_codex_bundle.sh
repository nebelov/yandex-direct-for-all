#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="${CODEX_HOME:-$HOME/.codex}"
TARGET_SKILLS="$TARGET_ROOT/skills"
TARGET_MCP="$TARGET_ROOT/mcp"
FORCE="${1:-}"

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

mkdir -p "$TARGET_SKILLS" "$TARGET_MCP"

copy_dir "$PLUGIN_DIR/skills/yandex-performance-ops" "$TARGET_SKILLS/yandex-performance-ops"
copy_dir "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle" "$TARGET_SKILLS/yandex-direct-client-lifecycle"
copy_dir "$PLUGIN_DIR/skills/roistat-reports-api" "$TARGET_SKILLS/roistat-reports-api"
copy_dir "$PLUGIN_DIR/skills/amocrm-api-control" "$TARGET_SKILLS/amocrm-api-control"

copy_dir "$PLUGIN_DIR/mcp/yandex-direct" "$TARGET_MCP/yandex-direct"
copy_dir "$PLUGIN_DIR/mcp/yandex-search" "$TARGET_MCP/yandex-search"
copy_dir "$PLUGIN_DIR/mcp/yandex-wordstat" "$TARGET_MCP/yandex-wordstat"

cat <<EOF
Installed bundle into:
  skills: $TARGET_SKILLS
  mcp:    $TARGET_MCP

Next:
  1. No manual .env is required for default Direct/Metrika/Audience OAuth.
  2. Use $PLUGIN_DIR/examples/yandex.env.example only for overrides or Wordstat/Search API cloud auth.
  3. Configure your MCP client using plugins/yandex-direct-for-all/.mcp.json
  4. Validate with:
     bash "$PLUGIN_DIR/scripts/validate_bundle.sh"
  5. Read bundle notes:
     $PLUGIN_DIR/README.md
EOF
