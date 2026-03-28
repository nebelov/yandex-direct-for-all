#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

require_file() {
  local path="$1"
  [[ -f "$path" ]] || { echo "Missing file: $path" >&2; exit 2; }
}

require_dir() {
  local path="$1"
  [[ -d "$path" ]] || { echo "Missing dir: $path" >&2; exit 2; }
}

require_dir "$PLUGIN_DIR/skills/yandex-performance-ops"
require_dir "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle"
require_dir "$PLUGIN_DIR/skills/roistat-reports-api"
require_dir "$PLUGIN_DIR/skills/amocrm-api-control"

require_dir "$PLUGIN_DIR/mcp/yandex-direct"
require_dir "$PLUGIN_DIR/mcp/yandex-search"
require_dir "$PLUGIN_DIR/mcp/yandex-wordstat"
require_dir "$PLUGIN_DIR/docs"
require_dir "$PLUGIN_DIR/examples"
require_dir "$PLUGIN_DIR/config"

require_file "$PLUGIN_DIR/.codex-plugin/plugin.json"
require_file "$PLUGIN_DIR/.mcp.json"
require_file "$PLUGIN_DIR/README.md"
require_file "$PLUGIN_DIR/docs/component-inventory.md"
require_file "$PLUGIN_DIR/docs/codex-plugin-build-notes.md"
require_file "$PLUGIN_DIR/docs/oauth-and-app-setup.md"
require_file "$PLUGIN_DIR/docs/auth-model-matrix.md"
require_file "$PLUGIN_DIR/docs/data-collection-scripts.md"
require_file "$PLUGIN_DIR/docs/operator-auth-launchers.md"
require_file "$PLUGIN_DIR/examples/yandex.env.example"
require_file "$PLUGIN_DIR/config/yandex_oauth_public_profiles.json"
require_file "$PLUGIN_DIR/scripts/install_codex_bundle.sh"
require_file "$PLUGIN_DIR/scripts/install_claude_bundle.sh"
require_file "$PLUGIN_DIR/scripts/list_data_collectors.sh"
require_file "$PLUGIN_DIR/scripts/collect_wordstat_wave.sh"
require_file "$PLUGIN_DIR/scripts/collect_direct_bundle.sh"
require_file "$PLUGIN_DIR/scripts/collect_direct_sqr.sh"
require_file "$PLUGIN_DIR/scripts/collect_metrika.sh"
require_file "$PLUGIN_DIR/scripts/collect_roistat.sh"
require_file "$PLUGIN_DIR/scripts/collect_organic_serp.sh"
require_file "$PLUGIN_DIR/scripts/collect_ad_serp.sh"
require_file "$PLUGIN_DIR/scripts/collect_page_capture.sh"
require_file "$PLUGIN_DIR/scripts/collect_sitemap.sh"
require_file "$PLUGIN_DIR/scripts/render_yandex_token_env.py"
require_file "$PLUGIN_DIR/scripts/start_yandex_user_auth.py"
require_file "$PLUGIN_DIR/scripts/start_yandex_user_auth.sh"
require_file "$PLUGIN_DIR/scripts/exchange_yandex_user_code.sh"
require_file "$PLUGIN_DIR/scripts/preflight_yandex_user_token.py"
require_file "$PLUGIN_DIR/scripts/yandex_auth_common.py"

python3 -m json.tool "$PLUGIN_DIR/.codex-plugin/plugin.json" >/dev/null
python3 -m json.tool "$PLUGIN_DIR/.mcp.json" >/dev/null
python3 -m json.tool "$PLUGIN_DIR/config/yandex_oauth_public_profiles.json" >/dev/null

python3 -m py_compile \
  "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" \
  "$PLUGIN_DIR/scripts/preflight_yandex_user_token.py" \
  "$PLUGIN_DIR/scripts/yandex_auth_common.py" \
  "$PLUGIN_DIR/scripts/render_yandex_token_env.py" \
  "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/oauth_get_token.py"
python3 "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/oauth_get_token.py" --help >/dev/null
python3 "$PLUGIN_DIR/scripts/render_yandex_token_env.py" --help >/dev/null
python3 "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" --help >/dev/null
python3 "$PLUGIN_DIR/scripts/preflight_yandex_user_token.py" --help >/dev/null
bash "$PLUGIN_DIR/scripts/start_yandex_user_auth.sh" --help >/dev/null
bash "$PLUGIN_DIR/scripts/exchange_yandex_user_code.sh" --help >/dev/null

TMP_AUTH_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_AUTH_ROOT"' EXIT

python3 "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" \
    --service direct \
    --mode auto \
    --auth-root "$TMP_AUTH_ROOT" \
    --print-only \
    --no-browser >/dev/null

python3 "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" \
    --service metrika \
    --mode auto \
    --auth-root "$TMP_AUTH_ROOT" \
    --print-only \
    --no-browser >/dev/null

python3 "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" \
    --service audience \
    --mode auto \
    --auth-root "$TMP_AUTH_ROOT" \
    --print-only \
    --no-browser >/dev/null

python3 - <<PY
from pathlib import Path
for name in [
    "direct_oauth_pending.json",
    "metrika_oauth_pending.json",
    "audience_oauth_pending.json",
]:
    path = Path("$TMP_AUTH_ROOT") / name
    assert path.is_file(), f"Missing pending file: {path}"
PY

python3 "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" \
    --service metrika \
    --mode manual-code \
    --auth-root "$TMP_AUTH_ROOT" \
    --code test-code \
    --print-only \
    --no-browser >/dev/null

python3 - <<PY
from pathlib import Path
import json
sample = Path("$TMP_AUTH_ROOT") / "direct_oauth_token.json"
sample.write_text(json.dumps({"access_token": "test-token"}), encoding="utf-8")
PY

  python3 "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" \
    --service direct \
    --mode auto \
    --auth-root "$TMP_AUTH_ROOT" \
    --print-only \
    --no-browser >/dev/null

bash "$PLUGIN_DIR/scripts/exchange_yandex_user_code.sh" \
    --service direct \
    --auth-root "$TMP_AUTH_ROOT" \
    --code test-code \
    --print-only >/dev/null

python3 "$PLUGIN_DIR/scripts/preflight_yandex_user_token.py" \
  --help >/dev/null

python3 - <<PY
import ast
from pathlib import Path

for path in [
    Path("$PLUGIN_DIR/mcp/yandex-direct/server.py"),
    Path("$PLUGIN_DIR/mcp/yandex-search/server.py"),
    Path("$PLUGIN_DIR/scripts/start_yandex_user_auth.py"),
    Path("$PLUGIN_DIR/scripts/preflight_yandex_user_token.py"),
    Path("$PLUGIN_DIR/scripts/yandex_auth_common.py"),
]:
    ast.parse(path.read_text(encoding="utf-8"))
PY
node --check "$PLUGIN_DIR/mcp/yandex-wordstat/dist/index.js" >/dev/null

echo "Bundle structure looks valid."
