#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIRECT_PYTHON="${YDFALL_DIRECT_PYTHON:-python3}"

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
require_dir "$PLUGIN_DIR/skills/yandex-direct-unified"
require_dir "$PLUGIN_DIR/skills/yandex-wordstat"
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
require_file "$PLUGIN_DIR/scripts/install_bundle.sh"
require_file "$PLUGIN_DIR/tests/test_install_bundle.sh"
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
require_file "$PLUGIN_DIR/scripts/portable_http.py"
require_file "$PLUGIN_DIR/tests/test_yandex_user_auth.py"
require_file "$PLUGIN_DIR/tests/test_portable_http.py"
require_file "$PLUGIN_DIR/tests/test_portable_scripts.py"
require_file "$PLUGIN_DIR/mcp/yandex-direct/tests/test_read_only_server.py"
require_file "$PLUGIN_DIR/mcp/yandex-direct/pyproject.toml"
require_file "$PLUGIN_DIR/mcp/yandex-direct/uv.lock"
require_file "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/check_access_paths.py"
require_file "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/collect_direct_cabinet_snapshot.py"
require_file "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/collect_direct_management_snapshot.py"
require_file "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/fetch_sqr_parallel.py"
require_file "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika_oauth_verification_code.py"

python3 -m json.tool "$PLUGIN_DIR/.codex-plugin/plugin.json" >/dev/null
python3 -m json.tool "$PLUGIN_DIR/.mcp.json" >/dev/null
python3 -m json.tool "$PLUGIN_DIR/config/yandex_oauth_public_profiles.json" >/dev/null

python3 -m py_compile \
  "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" \
  "$PLUGIN_DIR/scripts/preflight_yandex_user_token.py" \
  "$PLUGIN_DIR/scripts/portable_http.py" \
  "$PLUGIN_DIR/scripts/yandex_auth_common.py" \
  "$PLUGIN_DIR/scripts/render_yandex_token_env.py" \
  "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/oauth_get_token.py" \
  "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/check_access_paths.py" \
  "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/collect_direct_cabinet_snapshot.py" \
  "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/collect_direct_management_snapshot.py" \
  "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/fetch_sqr_parallel.py" \
  "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika_oauth_verification_code.py"
python3 "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/oauth_get_token.py" --help >/dev/null
python3 "$PLUGIN_DIR/scripts/render_yandex_token_env.py" --help >/dev/null
python3 "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" --help >/dev/null
python3 "$PLUGIN_DIR/scripts/preflight_yandex_user_token.py" --help >/dev/null
bash "$PLUGIN_DIR/scripts/start_yandex_user_auth.sh" --help >/dev/null
bash "$PLUGIN_DIR/scripts/exchange_yandex_user_code.sh" --help >/dev/null
python3 "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/check_access_paths.py" --help >/dev/null
python3 "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/collect_direct_cabinet_snapshot.py" --help >/dev/null
python3 "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/collect_direct_management_snapshot.py" --help >/dev/null
python3 "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/fetch_sqr_parallel.py" --help >/dev/null

TMP_AUTH_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_AUTH_ROOT"' EXIT

for service in direct metrika audience; do
  auth_args=()
  if [[ "$service" == direct ]]; then
    auth_args=(--client-login synthetic-advertiser)
  fi
  python3 "$PLUGIN_DIR/scripts/start_yandex_user_auth.py" \
      --service "$service" \
      --auth-root "$TMP_AUTH_ROOT" \
      --print-only \
      --no-browser \
      "${auth_args[@]}" >/dev/null
done

python3 - <<PY
import stat
from pathlib import Path
root = Path("$TMP_AUTH_ROOT")
assert stat.S_IMODE(root.stat().st_mode) == 0o700
for name in [
    "direct_oauth_pending.json",
    "metrika_oauth_pending.json",
    "audience_oauth_pending.json",
]:
    path = root / name
    assert path.is_file(), f"Missing pending file: {path}"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
PY

python3 "$PLUGIN_DIR/tests/test_yandex_user_auth.py" >/dev/null
python3 "$PLUGIN_DIR/tests/test_portable_http.py" >/dev/null
python3 "$PLUGIN_DIR/tests/test_portable_scripts.py" >/dev/null
"$DIRECT_PYTHON" "$PLUGIN_DIR/mcp/yandex-direct/tests/test_read_only_server.py" >/dev/null

for file in \
  "$PLUGIN_DIR/skills/amocrm-api-control/scripts/exchange_amocrm_token.py" \
  "$PLUGIN_DIR/skills/amocrm-api-control/scripts/fetch_amocrm_schema.py" \
  "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/firecrawl_scrape.py" \
  "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/sitemap_probe_batch.py" \
  "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/yandex_search_ads_batch.py" \
  "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/yandex_search_batch.py"; do
  PYTHONNOUSERSITE=1 python3 -I "$file" --help >/dev/null
done

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
node --check "$PLUGIN_DIR/mcp/yandex-wordstat/src/index.mjs" >/dev/null
node --check "$PLUGIN_DIR/mcp/yandex-wordstat/src/convert.mjs" >/dev/null
PYTHONNOUSERSITE=1 python3 -I -S "$PLUGIN_DIR/mcp/yandex-wordstat/scripts/wordstat_cloud_gateway_collect.py" --help >/dev/null
python3 "$PLUGIN_DIR/mcp/yandex-wordstat/tests/test_wordstat_cloud_gateway_collect.py" >/dev/null

python3 - <<PY
import hashlib
import json
from pathlib import Path
profiles = json.loads(Path("$PLUGIN_DIR/config/yandex_oauth_public_profiles.json").read_text(encoding="utf-8"))
assert set(profiles) == {"legacy_direct", "master_yandex"}
expected = {
    "legacy_direct": "fb2a600855d8391966342cf03ae0c5985f08f8bec92c77242bab0a131690429f",
    "master_yandex": "70d6638756dd9802985fb8246838e2af4f77f979fd9fd07c2c1384f874b0291f",
}
for profile in profiles.values():
    assert profile.get("client_id")
    assert "client_secret" not in profile
for name, digest in expected.items():
    assert hashlib.sha256(profiles[name]["client_id"].encode()).hexdigest() == digest
PY

echo "Bundle structure looks valid."
