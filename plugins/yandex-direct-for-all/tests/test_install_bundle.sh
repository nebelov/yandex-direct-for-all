#!/usr/bin/env bash
set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
installer="$plugin_root/scripts/install_bundle.sh"
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
original_home="$HOME"
export NPM_CONFIG_CACHE="$original_home/.npm"
if [[ -f "$original_home/.npmrc" ]]; then
  export NPM_CONFIG_USERCONFIG="$original_home/.npmrc"
fi

check_target() {
  local target="$1"
  export HOME="$root/$target/home"
  export CODEX_HOME="$HOME/.codex"
  export CLAUDE_HOME="$HOME/.claude"
  mkdir -p "$HOME"

  local plan first run_id skill plugin
  plan="$("$installer" --target "$target")"
  [[ "$plan" == *"Запись не выполнялась"* ]]
  if [[ "$target" == codex ]]; then
    plugin="$CODEX_HOME/plugins/yandex-direct-for-all"
    skill="$CODEX_HOME/skills/yandex-wordstat/SKILL.md"
  else
    plugin="$CLAUDE_HOME/plugins/yandex-direct-for-all"
    skill="$CLAUDE_HOME/skills/yandex-wordstat/SKILL.md"
  fi
  [[ ! -e "$plugin" ]]

  first="$("$installer" --target "$target" --apply)"
  run_id="${first##*RUN_ID=}"
  run_id="${run_id%%$'\n'*}"
  [[ -f "$plugin/config/yandex_oauth_public_profiles.json" ]]
  [[ -f "$skill" ]]
  [[ -f "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-wordstat/src/index.mjs" ]]
  [[ -x "$plugin/mcp/yandex-search/.venv/bin/python" ]]
  [[ -d "$plugin/mcp/yandex-wordstat/node_modules/@modelcontextprotocol/sdk" ]]
  [[ -x "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-search/.venv/bin/python" ]]
  [[ -d "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-wordstat/node_modules/@modelcontextprotocol/sdk" ]]
  if [[ "$target" == codex ]]; then
    [[ -f "$HOME/.agents/plugins/marketplace.json" ]]
  fi

  "$installer" --target "$target" --apply >/dev/null
  printf '\nuser change\n' >> "$skill"
  if "$installer" --target "$target" --apply >"$root/$target-conflict.out" 2>&1; then
    echo "Ожидался отказ при пользовательском изменении: $target" >&2
    exit 1
  fi
  grep -q "КОНФЛИКТ" "$root/$target-conflict.out"
  grep -q "user change" "$skill"

  "$installer" --target "$target" --rollback "$run_id" >/dev/null
  [[ ! -e "$plugin" ]]
  [[ ! -e "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-wordstat" ]]
  if [[ "$target" == codex ]]; then
    [[ ! -e "$HOME/.agents/plugins/marketplace.json" ]]
  fi
}

check_target codex
check_target claude
echo "install bundle contract: PASS"
