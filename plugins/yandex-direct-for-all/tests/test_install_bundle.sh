#!/usr/bin/env bash
set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
installer="$plugin_root/scripts/install_bundle.sh"
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
original_home="$HOME"
export NPM_CONFIG_CACHE="$original_home/.npm"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$original_home/.cache/uv}"
export UV_NO_PROGRESS=1
if [[ -f "$original_home/.npmrc" ]]; then
  export NPM_CONFIG_USERCONFIG="$original_home/.npmrc"
fi

check_target() {
  local target="$1"
  export HOME="$root/$target/home"
  export CODEX_HOME="$HOME/.codex"
  export CLAUDE_HOME="$HOME/.claude"
  mkdir -p "$HOME"

  local plan first second run_id second_run_id skill plugin state
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
  if [[ "$target" == codex ]]; then
    state="$CODEX_HOME/state/yandex-direct-for-all"
  else
    state="$CLAUDE_HOME/state/yandex-direct-for-all"
  fi
  [[ -f "$state/install-manifest.json" ]]
  [[ -f "$state/runs/$run_id/pre-state.tsv" ]]
  grep -q '"run_id":' "$state/install-manifest.json"
  [[ -f "$plugin/config/yandex_oauth_public_profiles.json" ]]
  [[ -f "$skill" ]]
  [[ -f "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-wordstat/src/index.mjs" ]]
  [[ -x "$plugin/mcp/yandex-search/.venv/bin/python" ]]
  [[ -x "$plugin/mcp/yandex-direct/.venv/bin/python" ]]
  [[ -d "$plugin/mcp/yandex-wordstat/node_modules/@modelcontextprotocol/sdk" ]]
  [[ -x "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-search/.venv/bin/python" ]]
  [[ -x "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-direct/.venv/bin/python" ]]
  [[ -d "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-wordstat/node_modules/@modelcontextprotocol/sdk" ]]
  if [[ "$target" == codex ]]; then
    [[ -f "$HOME/.agents/plugins/marketplace.json" ]]
  fi

  second="$("$installer" --target "$target" --apply)"
  second_run_id="${second##*RUN_ID=}"
  second_run_id="${second_run_id%%$'\n'*}"
  [[ "$second_run_id" != "$run_id" ]]
  cp "$skill" "$root/$target-skill.after-install"
  printf '\nuser change\n' >> "$skill"
  if "$installer" --target "$target" --apply >"$root/$target-conflict.out" 2>&1; then
    echo "Ожидался отказ при пользовательском изменении: $target" >&2
    exit 1
  fi
  grep -q "КОНФЛИКТ" "$root/$target-conflict.out"
  grep -q "user change" "$skill"

  if "$installer" --target "$target" --rollback "$second_run_id" >"$root/$target-unsafe-rollback.out" 2>&1; then
    echo "Ожидался отказ отката поверх пользовательского изменения: $target" >&2
    exit 1
  fi
  grep -q "после установки изменён управляемый путь" "$root/$target-unsafe-rollback.out"
  grep -q "user change" "$skill"

  cp "$root/$target-skill.after-install" "$skill"
  "$installer" --target "$target" --rollback "$second_run_id" >/dev/null
  [[ -e "$plugin" ]]
  MANIFEST_PATH="$state/install-manifest.json" EXPECTED_RUN="$run_id" python3 - <<'PY'
import json
import os
from pathlib import Path

payload = json.loads(Path(os.environ["MANIFEST_PATH"]).read_text(encoding="utf-8"))
assert payload["run_id"] == os.environ["EXPECTED_RUN"]
PY
  if "$installer" --target "$target" --rollback "$second_run_id" >/dev/null 2>&1; then
    echo "Повторный откат той же установки должен быть запрещён: $target" >&2
    exit 1
  fi

  "$installer" --target "$target" --rollback "$run_id" >/dev/null
  [[ ! -e "$plugin" ]]
  [[ ! -e "${plugin%/plugins/yandex-direct-for-all}/mcp/yandex-wordstat" ]]
  [[ ! -e "$state/install-manifest.json" ]]
  if [[ "$target" == codex ]]; then
    [[ ! -e "$HOME/.agents/plugins/marketplace.json" ]]
  fi
}

check_unknown_identical_path_is_rejected() {
  export HOME="$root/unknown-identical/home"
  export CODEX_HOME="$HOME/.codex"
  export CLAUDE_HOME="$HOME/.claude"
  mkdir -p "$CODEX_HOME/plugins/yandex-direct-for-all"
  rsync -a --exclude node_modules --exclude __pycache__ --exclude .venv "$plugin_root/" "$CODEX_HOME/plugins/yandex-direct-for-all/"
  if "$installer" --target codex >"$root/unknown-identical.out" 2>&1; then
    echo "Неизвестный идентичный каталог должен быть отклонён" >&2
    exit 1
  fi
  grep -q "не зарегистрирован этим установщиком" "$root/unknown-identical.out"
  [[ ! -e "$CODEX_HOME/state/yandex-direct-for-all/install-manifest.json" ]]
}

check_both_rollback_is_validated_before_any_write() {
  export HOME="$root/both/home"
  export CODEX_HOME="$HOME/.codex"
  export CLAUDE_HOME="$HOME/.claude"
  mkdir -p "$HOME"
  local output run_id codex_skill claude_skill codex_before
  output="$("$installer" --target both --apply)"
  run_id="${output##*RUN_ID=}"
  run_id="${run_id%%$'\n'*}"
  codex_skill="$CODEX_HOME/skills/yandex-wordstat/SKILL.md"
  claude_skill="$CLAUDE_HOME/skills/yandex-wordstat/SKILL.md"
  codex_before="$(shasum -a 256 "$codex_skill" | awk '{print $1}')"
  cp "$claude_skill" "$root/both-claude-skill.before"
  printf '\nuser change\n' >> "$claude_skill"
  if "$installer" --target both --rollback "$run_id" >"$root/both-rollback.out" 2>&1; then
    echo "Откат обеих сред должен быть отклонён до первой записи" >&2
    exit 1
  fi
  grep -q "после установки изменён управляемый путь" "$root/both-rollback.out"
  [[ "$(shasum -a 256 "$codex_skill" | awk '{print $1}')" == "$codex_before" ]]
  cp "$root/both-claude-skill.before" "$claude_skill"
  "$installer" --target both --rollback "$run_id" >/dev/null
  [[ ! -e "$CODEX_HOME/plugins/yandex-direct-for-all" ]]
  [[ ! -e "$CLAUDE_HOME/plugins/yandex-direct-for-all" ]]
}

check_apply_failure_restores_original_state() {
  export HOME="$root/apply-failure/home"
  export CODEX_HOME="$HOME/.codex"
  export CLAUDE_HOME="$HOME/.claude"
  mkdir -p "$CODEX_HOME"
  printf '%s\n' "parent blocker" > "$CODEX_HOME/skills"
  if "$installer" --target codex --apply >"$root/apply-failure.out" 2>&1; then
    echo "Ожидался управляемый отказ установки" >&2
    exit 1
  fi
  grep -q "восстановлена после ошибки" "$root/apply-failure.out"
  [[ -f "$CODEX_HOME/skills" ]]
  grep -q "parent blocker" "$CODEX_HOME/skills"
  [[ ! -e "$CODEX_HOME/plugins/yandex-direct-for-all" ]]
  [[ ! -e "$CODEX_HOME/state/yandex-direct-for-all/install-manifest.json" ]]
  local latest_run
  latest_run="$(find "$CODEX_HOME/state/yandex-direct-for-all/runs" -mindepth 1 -maxdepth 1 -type d | head -1)"
  [[ -n "$latest_run" ]]
  [[ "$(cat "$latest_run/status")" == recovered_failed ]]
}

check_second_target_failure_restores_both() {
  export HOME="$root/both-apply-failure/home"
  export CODEX_HOME="$HOME/.codex"
  export CLAUDE_HOME="$HOME/.claude"
  mkdir -p "$CODEX_HOME" "$CLAUDE_HOME"
  printf '%s\n' "claude blocker" > "$CLAUDE_HOME/skills"
  if "$installer" --target both --apply >"$root/both-apply-failure.out" 2>&1; then
    echo "Ожидался отказ второй среды" >&2
    exit 1
  fi
  grep -q "все затронутые среды восстановлены" "$root/both-apply-failure.out"
  [[ ! -e "$CODEX_HOME/plugins/yandex-direct-for-all" ]]
  [[ ! -e "$CODEX_HOME/state/yandex-direct-for-all/install-manifest.json" ]]
  [[ ! -e "$HOME/.agents/plugins/marketplace.json" ]]
  [[ -f "$CLAUDE_HOME/skills" ]]
  grep -q "claude blocker" "$CLAUDE_HOME/skills"
  [[ ! -e "$CLAUDE_HOME/plugins/yandex-direct-for-all" ]]
  [[ ! -e "$CLAUDE_HOME/state/yandex-direct-for-all/install-manifest.json" ]]
}

check_next_apply_recovers_stale_transaction() {
  export HOME="$root/stale-transaction/home"
  export CODEX_HOME="$HOME/.codex"
  export CLAUDE_HOME="$HOME/.claude"
  mkdir -p "$HOME"
  local first first_run second second_run
  first="$("$installer" --target codex --apply)"
  first_run="${first##*RUN_ID=}"
  first_run="${first_run%%$'\n'*}"
  printf '%s\n' "applied_pending" > "$CODEX_HOME/state/yandex-direct-for-all/runs/$first_run/status"
  second="$("$installer" --target codex --apply 2>"$root/stale-transaction.err")"
  second_run="${second##*RUN_ID=}"
  second_run="${second_run%%$'\n'*}"
  grep -q "Восстановлена незавершённая установка" "$root/stale-transaction.err"
  [[ "$(cat "$CODEX_HOME/state/yandex-direct-for-all/runs/$first_run/status")" == recovered_failed ]]
  [[ "$(cat "$CODEX_HOME/state/yandex-direct-for-all/runs/$second_run/status")" == applied ]]
  [[ "$(manifest_run_id_for_test "$CODEX_HOME/state/yandex-direct-for-all/install-manifest.json")" == "$second_run" ]]
  "$installer" --target codex --rollback "$second_run" >/dev/null
}

check_stale_transaction_preserves_user_change() {
  export HOME="$root/stale-user-change/home"
  export CODEX_HOME="$HOME/.codex"
  export CLAUDE_HOME="$HOME/.claude"
  mkdir -p "$HOME"
  local first first_run skill
  first="$("$installer" --target codex --apply)"
  first_run="${first##*RUN_ID=}"
  first_run="${first_run%%$'\n'*}"
  printf '%s\n' "applied_pending" > "$CODEX_HOME/state/yandex-direct-for-all/runs/$first_run/status"
  skill="$CODEX_HOME/skills/yandex-wordstat/SKILL.md"
  printf '\nuser change after interruption\n' >> "$skill"
  if "$installer" --target codex --apply >"$root/stale-user-change.out" 2>&1; then
    echo "Автовосстановление не должно затирать пользовательское изменение" >&2
    exit 1
  fi
  grep -q "Автоматическое восстановление остановлено" "$root/stale-user-change.out"
  grep -q "user change after interruption" "$skill"
  [[ "$(cat "$CODEX_HOME/state/yandex-direct-for-all/runs/$first_run/status")" == applied_pending ]]
}

manifest_run_id_for_test() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["run_id"])' "$1"
}

check_unknown_identical_path_is_rejected
check_target codex
check_target claude
check_both_rollback_is_validated_before_any_write
check_apply_failure_restores_original_state
check_second_target_failure_restores_both
check_next_apply_recovers_stale_transaction
check_stale_transaction_preserves_user_change
echo "install bundle contract: PASS"
