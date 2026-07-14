#!/usr/bin/env bash
set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
installer="$plugin_root/scripts/install_bundle.sh"
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
export HOME="$root/home"
export CODEX_HOME="$HOME/.codex"
export CLAUDE_HOME="$HOME/.claude"
mkdir -p "$HOME"

plan="$("$installer" --target both)"
[[ "$plan" == *"Запись не выполнялась"* ]]
[[ ! -e "$CODEX_HOME/plugins/yandex-direct-for-all" ]]
[[ ! -e "$CLAUDE_HOME/plugins/yandex-direct-for-all" ]]

first="$("$installer" --target both --apply)"
run_id="${first##*RUN_ID=}"
run_id="${run_id%%$'\n'*}"
[[ -f "$CODEX_HOME/plugins/yandex-direct-for-all/config/yandex_oauth_public_profiles.json" ]]
[[ -f "$CODEX_HOME/skills/yandex-direct-unified/SKILL.md" ]]
[[ -f "$CLAUDE_HOME/mcp/yandex-wordstat/src/index.mjs" ]]
[[ -f "$HOME/.agents/plugins/marketplace.json" ]]

"$installer" --target both --apply >/dev/null

printf '\nuser change\n' >> "$CODEX_HOME/skills/yandex-wordstat/SKILL.md"
if "$installer" --target codex --apply >"$root/conflict.out" 2>&1; then
  echo "Ожидался отказ при пользовательском изменении" >&2
  exit 1
fi
grep -q "КОНФЛИКТ" "$root/conflict.out"
grep -q "user change" "$CODEX_HOME/skills/yandex-wordstat/SKILL.md"

"$installer" --target both --rollback "$run_id" >/dev/null
[[ ! -e "$CODEX_HOME/plugins/yandex-direct-for-all" ]]
[[ ! -e "$CLAUDE_HOME/plugins/yandex-direct-for-all" ]]
[[ ! -e "$HOME/.agents/plugins/marketplace.json" ]]
echo "install bundle contract: PASS"
