#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Использование: $0 --target codex|claude|both [--apply | --rollback RUN_ID]"
  echo "Без --apply команда только показывает план и ничего не записывает."
}

target=""
mode="plan"
rollback_id=""
while (($#)); do
  case "$1" in
    --target) target="${2:-}"; shift 2 ;;
    --apply) mode="apply"; shift ;;
    --rollback) mode="rollback"; rollback_id="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный параметр: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$target" in codex|claude|both) ;; *) echo "Нужно указать --target codex, claude или both" >&2; exit 2 ;; esac
if [[ "$mode" == rollback && -z "$rollback_id" ]]; then
  echo "Для отката нужен RUN_ID" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_source="$(cd "$script_dir/.." && pwd)"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"

managed_paths=(
  "plugins/yandex-direct-for-all"
  "skills/yandex-direct-unified"
  "skills/yandex-wordstat"
  "skills/yandex-performance-ops"
  "skills/yandex-direct-client-lifecycle"
  "skills/roistat-reports-api"
  "skills/amocrm-api-control"
  "skills/commercial-demand-research"
  "skills/yandex-cloud-search-cost-control"
  "mcp/yandex-direct"
  "mcp/yandex-search"
  "mcp/yandex-wordstat"
)

roots=()
[[ "$target" == codex || "$target" == both ]] && roots+=("codex:${CODEX_HOME:-$HOME/.codex}")
[[ "$target" == claude || "$target" == both ]] && roots+=("claude:${CLAUDE_HOME:-$HOME/.claude}")

source_for() {
  case "$1" in
    plugins/yandex-direct-for-all) printf '%s\n' "$plugin_source" ;;
    skills/*) printf '%s/skills/%s\n' "$plugin_source" "${1#skills/}" ;;
    mcp/*) printf '%s/mcp/%s\n' "$plugin_source" "${1#mcp/}" ;;
    *) return 1 ;;
  esac
}

tree_hash() {
  local path="$1"
  if [[ -f "$path" ]]; then
    shasum -a 256 "$path" | awk '{print $1}'
    return
  fi
  (
    cd "$path"
    find . \( -type d \( -name node_modules -o -name __pycache__ -o -name .venv \) -prune \) -o -type f -print0 |
      LC_ALL=C sort -z |
      xargs -0 shasum -a 256
  ) | shasum -a 256 | awk '{print $1}'
}

manifest_value() {
  local manifest="$1" rel="$2"
  [[ -f "$manifest" ]] || return 0
  awk -F '\t' -v key="$rel" '$1 == key {print $2; exit}' "$manifest"
}

check_target() {
  local kind="$1" root="$2"
  local manifest="$root/.ydfall-install/manifest.tsv"
  local conflicts=0
  echo "Среда: $kind ($root)"
  for rel in "${managed_paths[@]}"; do
    local src dest src_hash current_hash previous_hash
    src="$(source_for "$rel")"
    if [[ ! -e "$src" ]]; then
      echo "  ПРОПУСК  $rel (ещё не входит в эту версию)"
      continue
    fi
    dest="$root/$rel"
    src_hash="$(tree_hash "$src")"
    if [[ ! -e "$dest" ]]; then
      echo "  СОЗДАТЬ  $rel"
      continue
    fi
    current_hash="$(tree_hash "$dest")"
    previous_hash="$(manifest_value "$manifest" "$rel")"
    if [[ "$current_hash" == "$src_hash" ]]; then
      echo "  БЕЗ ИЗМЕНЕНИЙ  $rel"
    elif [[ -n "$previous_hash" && "$current_hash" == "$previous_hash" ]]; then
      echo "  ОБНОВИТЬ  $rel"
    else
      echo "  КОНФЛИКТ  $rel (найдены неуправляемые изменения)" >&2
      conflicts=1
    fi
  done
  return "$conflicts"
}

write_marketplace() {
  local destination="$HOME/.agents/plugins/marketplace.json"
  mkdir -p "$(dirname "$destination")"
  MARKETPLACE_PATH="$destination" PLUGIN_PATH="${CODEX_HOME:-$HOME/.codex}/plugins/yandex-direct-for-all" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["MARKETPLACE_PATH"])
if path.exists():
    payload = json.loads(path.read_text(encoding="utf-8"))
else:
    payload = {"name": "local-marketplace", "plugins": []}
plugins = payload.setdefault("plugins", [])
entry = {
    "name": "yandex-direct-for-all",
    "source": {"source": "local", "path": os.environ["PLUGIN_PATH"]},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Marketing",
}
plugins[:] = [item for item in plugins if item.get("name") != entry["name"]]
plugins.append(entry)
temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
temporary.replace(path)
PY
}

install_target() {
  local kind="$1" root="$2"
  local state="$root/.ydfall-install"
  local run="$root/.ydfall-install/runs/$run_id"
  local previous_manifest="$state/manifest.tsv"
  local next_manifest="$run/manifest.after.tsv"
  mkdir -p "$run/backups"
  chmod 700 "$state" "$state/runs" "$run" "$run/backups"
  [[ -f "$previous_manifest" ]] && cp "$previous_manifest" "$run/manifest.before.tsv" || : > "$run/manifest.before.absent"
  : > "$run/operations.tsv"
  : > "$next_manifest"
  chmod 600 "$run/operations.tsv" "$next_manifest"

  local index=0
  for rel in "${managed_paths[@]}"; do
    local src dest parent stage src_hash existed
    src="$(source_for "$rel")"
    [[ -e "$src" ]] || continue
    dest="$root/$rel"
    parent="$(dirname "$dest")"
    mkdir -p "$parent"
    index=$((index + 1))
    existed=0
    if [[ -e "$dest" ]]; then
      existed=1
      mv "$dest" "$run/backups/$index"
    fi
    stage="$parent/.ydfall-stage-$run_id-$index"
    rm -rf "$stage"
    if [[ -d "$src" ]]; then
      mkdir -p "$stage"
      rsync -a --exclude node_modules --exclude __pycache__ --exclude .venv "$src/" "$stage/"
    else
      cp "$src" "$stage"
    fi
    src_hash="$(tree_hash "$src")"
    [[ "$(tree_hash "$stage")" == "$src_hash" ]] || {
      echo "Ошибка проверки подготовленной копии: $rel" >&2
      exit 4
    }
    mv "$stage" "$dest"
    printf '%s\t%s\t%s\n' "$rel" "$existed" "$index" >> "$run/operations.tsv"
    printf '%s\t%s\n' "$rel" "$src_hash" >> "$next_manifest"
  done
  cp "$next_manifest" "$previous_manifest"
  chmod 600 "$previous_manifest"

  if [[ "$kind" == codex ]]; then
    local marketplace="$HOME/.agents/plugins/marketplace.json"
    if [[ -f "$marketplace" ]]; then
      cp "$marketplace" "$run/marketplace.before.json"
    else
      : > "$run/marketplace.before.absent"
    fi
    write_marketplace
  fi
  printf '%s\n' "applied" > "$run/status"
  chmod 600 "$run/status"
}

rollback_target() {
  local kind="$1" root="$2"
  local run="$root/.ydfall-install/runs/$rollback_id"
  [[ -d "$run" ]] || { echo "Нет записи отката $rollback_id для $kind" >&2; return 5; }
  [[ "$(cat "$run/status" 2>/dev/null || true)" == applied ]] || {
    echo "Запись $rollback_id уже использована или неполна" >&2
    return 5
  }
  while IFS=$'\t' read -r rel existed index; do
    [[ -n "$rel" ]] || continue
    rm -rf "$root/$rel"
    if [[ "$existed" == 1 ]]; then
      mkdir -p "$(dirname "$root/$rel")"
      mv "$run/backups/$index" "$root/$rel"
    fi
  done < "$run/operations.tsv"
  if [[ -f "$run/manifest.before.tsv" ]]; then
    cp "$run/manifest.before.tsv" "$root/.ydfall-install/manifest.tsv"
  else
    rm -f "$root/.ydfall-install/manifest.tsv"
  fi
  if [[ "$kind" == codex ]]; then
    local marketplace="$HOME/.agents/plugins/marketplace.json"
    if [[ -f "$run/marketplace.before.json" ]]; then
      mkdir -p "$(dirname "$marketplace")"
      cp "$run/marketplace.before.json" "$marketplace"
    else
      rm -f "$marketplace"
    fi
  fi
  printf '%s\n' "rolled_back" > "$run/status"
  echo "ОТКАЧЕНО: $kind"
}

if [[ "$mode" == rollback ]]; then
  for item in "${roots[@]}"; do
    rollback_target "${item%%:*}" "${item#*:}"
  done
  exit 0
fi

conflict=0
for item in "${roots[@]}"; do
  check_target "${item%%:*}" "${item#*:}" || conflict=1
done
((conflict == 0)) || { echo "Применение отменено: сначала разберите конфликты." >&2; exit 3; }

if [[ "$mode" == plan ]]; then
  echo "ПЛАН ГОТОВ. Запись не выполнялась. Для применения добавьте --apply."
  exit 0
fi

for item in "${roots[@]}"; do
  install_target "${item%%:*}" "${item#*:}"
done
echo "УСТАНОВЛЕНО. RUN_ID=$run_id"
echo "Откат: $0 --target $target --rollback $run_id"
