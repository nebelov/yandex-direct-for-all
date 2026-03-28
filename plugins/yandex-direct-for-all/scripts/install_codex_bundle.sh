#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="${CODEX_HOME:-$HOME/.codex}"
MARKETPLACE_ROOT="${HOME}/.agents/plugins"
MARKETPLACE_FILE="$MARKETPLACE_ROOT/marketplace.json"
PLUGIN_NAME="yandex-direct-for-all"
TARGET_PLUGIN="$TARGET_ROOT/plugins/$PLUGIN_NAME"
TARGET_SKILLS="$TARGET_ROOT/skills"
TARGET_MCP="$TARGET_ROOT/mcp"

copy_dir() {
  local src="$1"
  local dst="$2"
  rm -rf "$dst"
  mkdir -p "$(dirname "$dst")"
  rsync -a --exclude '__pycache__' --exclude '.venv' "$src/" "$dst/"
}

mkdir -p "$TARGET_SKILLS" "$TARGET_MCP" "$(dirname "$TARGET_PLUGIN")" "$MARKETPLACE_ROOT"

copy_dir "$PLUGIN_DIR" "$TARGET_PLUGIN"

copy_dir "$PLUGIN_DIR/skills/yandex-performance-ops" "$TARGET_SKILLS/yandex-performance-ops"
copy_dir "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle" "$TARGET_SKILLS/yandex-direct-client-lifecycle"
copy_dir "$PLUGIN_DIR/skills/roistat-reports-api" "$TARGET_SKILLS/roistat-reports-api"
copy_dir "$PLUGIN_DIR/skills/amocrm-api-control" "$TARGET_SKILLS/amocrm-api-control"

copy_dir "$PLUGIN_DIR/mcp/yandex-direct" "$TARGET_MCP/yandex-direct"
copy_dir "$PLUGIN_DIR/mcp/yandex-search" "$TARGET_MCP/yandex-search"
copy_dir "$PLUGIN_DIR/mcp/yandex-wordstat" "$TARGET_MCP/yandex-wordstat"

python3 - "$MARKETPLACE_FILE" "$HOME" "$TARGET_PLUGIN" <<'PY'
import json
import sys
from pathlib import Path

marketplace_path = Path(sys.argv[1]).expanduser()
home_root = Path(sys.argv[2]).expanduser()
plugin_root = Path(sys.argv[3]).expanduser()
marketplace_path.parent.mkdir(parents=True, exist_ok=True)

try:
    relative_plugin_path = plugin_root.relative_to(home_root).as_posix()
    source_path = f"./{relative_plugin_path}"
except ValueError:
    source_path = str(plugin_root)

plugin_entry = {
    "name": "yandex-direct-for-all",
    "source": {
        "source": "local",
        "path": source_path,
    },
    "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    },
    "category": "Marketing",
}

if marketplace_path.exists():
    try:
        data = json.loads(marketplace_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid marketplace JSON at {marketplace_path}: {exc}")
else:
    data = {
        "name": "personal-codex-plugins",
        "interface": {"displayName": "Personal Codex Plugins"},
        "plugins": [],
    }

plugins = data.setdefault("plugins", [])
replaced = False
for index, plugin in enumerate(plugins):
    if plugin.get("name") == plugin_entry["name"]:
        plugins[index] = plugin_entry
        replaced = True
        break
if not replaced:
    plugins.append(plugin_entry)

data.setdefault("name", "personal-codex-plugins")
interface = data.setdefault("interface", {})
interface.setdefault("displayName", "Personal Codex Plugins")
marketplace_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

cat <<EOF
Installed personal Codex bundle into:
  plugin: $TARGET_PLUGIN
  skills: $TARGET_SKILLS
  mcp:    $TARGET_MCP
  marketplace: $MARKETPLACE_FILE

Next:
  1. This is an optional home-install path.
  2. Restart Codex so it picks up ~/.agents/plugins/marketplace.json.
  3. Canonical installed plugin root is:
     $TARGET_PLUGIN
  4. Re-running this installer refreshes the managed personal install in place.
  5. No manual .env is required for default Direct/Metrika/Audience OAuth.
  6. Use $TARGET_PLUGIN/examples/yandex.env.example only for overrides or Wordstat/Search API cloud auth.
  7. Validate with:
     bash "$TARGET_PLUGIN/scripts/validate_bundle.sh"
EOF
