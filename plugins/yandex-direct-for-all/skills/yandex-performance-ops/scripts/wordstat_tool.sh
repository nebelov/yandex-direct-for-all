#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLOBAL_DIR="$SCRIPT_DIR"

usage() {
  cat <<'EOF'
Usage:
  wordstat_tool.sh where
  wordstat_tool.sh preflight [OUT_DIR]
  wordstat_tool.sh preflight-save [OUT_DIR]
  wordstat_tool.sh collect-wave [collector args...]
  wordstat_tool.sh collect-wave-save [collector args...]

Notes:
  - Canonical Wordstat entrypoint on this Mac.
  - Prefers global yandex-performance-ops scripts.
  - Falls back to project-local .claude skill scripts only if global files are missing.
EOF
}

discover_from_codex_config() {
  local field="$1"
  python3 - "$field" <<'PY'
import os
import pathlib
import sys

field = sys.argv[1]
config_path = pathlib.Path.home() / ".codex" / "config.toml"
if not config_path.exists():
    raise SystemExit(0)

try:
    import tomllib
except ModuleNotFoundError:
    raise SystemExit(0)

try:
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

servers = data.get("mcp_servers", {})
server = servers.get("yandex_wordstat", {})

if field == "token":
    token = server.get("env", {}).get("YANDEX_WORDSTAT_TOKEN", "")
    if token:
        print(token)
elif field == "client":
    args = server.get("args", [])
    if args:
        index_path = pathlib.Path(args[0]).expanduser()
        client_path = index_path.with_name("client.js")
        if client_path.exists():
            print(str(client_path))
PY
}

ensure_wordstat_env() {
  if [[ -z "${YANDEX_WORDSTAT_TOKEN:-}" ]]; then
    local discovered_token
    discovered_token="$(discover_from_codex_config token || true)"
    if [[ -n "$discovered_token" ]]; then
      export YANDEX_WORDSTAT_TOKEN="$discovered_token"
    fi
  fi

  if [[ -z "${YANDEX_WORDSTAT_CLIENT_PATH:-}" ]]; then
    local discovered_client
    discovered_client="$(discover_from_codex_config client || true)"
    if [[ -n "$discovered_client" ]]; then
      export YANDEX_WORDSTAT_CLIENT_PATH="$discovered_client"
    fi
  fi
}

extract_output_dir_from_args() {
  local args=("$@")
  local i=0
  while [[ $i -lt ${#args[@]} ]]; do
    if [[ "${args[$i]}" == "--output-dir" ]]; then
      local next_index=$((i + 1))
      if [[ $next_index -lt ${#args[@]} ]]; then
        printf '%s\n' "${args[$next_index]}"
        return 0
      fi
    fi
    i=$((i + 1))
  done
  return 1
}

run_preflight_save() {
  local out_dir="${1:-$(pwd)/.codex-artifacts/wordstat-preflight}"
  mkdir -p "$out_dir"
  ensure_wordstat_env
  local preflight_path
  preflight_path="$(resolve_script "wordstat_preflight.sh" "YANDEX_WORDSTAT_PREFLIGHT_PATH")"
  bash "$preflight_path" "$out_dir" >"$out_dir/preflight_stdout.log" 2>"$out_dir/preflight_stderr.log"
  cat <<EOF
saved_preflight_dir=$out_dir
saved_stdout=$out_dir/preflight_stdout.log
saved_stderr=$out_dir/preflight_stderr.log
saved_user_info=$out_dir/wordstat_user_info_raw.json
EOF
}

run_collect_wave_save() {
  ensure_wordstat_env
  local output_dir
  output_dir="$(extract_output_dir_from_args "$@" || true)"
  if [[ -z "$output_dir" ]]; then
    echo "ERROR: collect-wave-save requires --output-dir DIR" >&2
    exit 2
  fi
  mkdir -p "$output_dir"
  local collector_path
  collector_path="$(resolve_script "wordstat_collect_wave.js" "YANDEX_WORDSTAT_COLLECTOR_PATH")"
  node "$collector_path" "$@" >"$output_dir/collector_stdout.log" 2>"$output_dir/collector_stderr.log"
  cat <<EOF
saved_wave_dir=$output_dir
saved_stdout=$output_dir/collector_stdout.log
saved_stderr=$output_dir/collector_stderr.log
saved_manifest=$output_dir/_manifest.json
saved_summary=$output_dir/_summary.json
EOF
}

append_candidate() {
  local value="$1"
  [[ -n "$value" ]] || return 0
  WORDSTAT_CANDIDATES+=("$value")
}

resolve_script() {
  local script_name="$1"
  local env_var="$2"
  local env_path="${!env_var:-}"
  local probe="$PWD"
  local seen=""
  WORDSTAT_CANDIDATES=()

  append_candidate "$env_path"
  append_candidate "$GLOBAL_DIR/$script_name"

  while true; do
    append_candidate "$probe/.claude/skills/direct-search-semantics/scripts/$script_name"
    append_candidate "$probe/.claude/skills/yandex-wordstat/scripts/$script_name"
    append_candidate "$probe/scripts/$script_name"
    [[ "$probe" == "/" ]] && break
    probe="$(dirname "$probe")"
  done

  for candidate in "${WORDSTAT_CANDIDATES[@]}"; do
    [[ -f "$candidate" ]] || continue
    if [[ "$seen" == *"|$candidate|"* ]]; then
      continue
    fi
    seen="${seen}|${candidate}|"
    printf '%s\n' "$candidate"
    return 0
  done

  echo "ERROR: unable to find $script_name" >&2
  echo "Checked global dir: $GLOBAL_DIR" >&2
  echo "Checked env override: $env_var" >&2
  echo "Checked project-local .claude skill paths while walking up from: $PWD" >&2
  exit 2
}

SUBCOMMAND="${1:-help}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$SUBCOMMAND" in
  where)
    ensure_wordstat_env
    PREFLIGHT_PATH="$(resolve_script "wordstat_preflight.sh" "YANDEX_WORDSTAT_PREFLIGHT_PATH")"
    COLLECTOR_PATH="$(resolve_script "wordstat_collect_wave.js" "YANDEX_WORDSTAT_COLLECTOR_PATH")"
    cat <<EOF
wrapper=$0
preflight=$PREFLIGHT_PATH
collector=$COLLECTOR_PATH
token=$([[ -n "${YANDEX_WORDSTAT_TOKEN:-}" ]] && echo discovered || echo missing)
client=$([[ -n "${YANDEX_WORDSTAT_CLIENT_PATH:-}" ]] && echo "$YANDEX_WORDSTAT_CLIENT_PATH" || echo missing)
EOF
    ;;
  preflight)
    ensure_wordstat_env
    PREFLIGHT_PATH="$(resolve_script "wordstat_preflight.sh" "YANDEX_WORDSTAT_PREFLIGHT_PATH")"
    exec bash "$PREFLIGHT_PATH" "$@"
    ;;
  preflight-save)
    run_preflight_save "$@"
    ;;
  collect-wave)
    ensure_wordstat_env
    COLLECTOR_PATH="$(resolve_script "wordstat_collect_wave.js" "YANDEX_WORDSTAT_COLLECTOR_PATH")"
    exec node "$COLLECTOR_PATH" "$@"
    ;;
  collect-wave-save)
    run_collect_wave_save "$@"
    ;;
  help|-h|--help|'')
    usage
    ;;
  *)
    echo "ERROR: unknown subcommand: $SUBCOMMAND" >&2
    usage >&2
    exit 2
    ;;
esac
