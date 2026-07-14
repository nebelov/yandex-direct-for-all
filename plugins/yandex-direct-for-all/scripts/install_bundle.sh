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

require_runtime_tools() {
  local missing=0
  for command in uv node npm; do
    if ! command -v "$command" >/dev/null 2>&1; then
      echo "Не найдена обязательная команда для готовой установки: $command" >&2
      missing=1
    fi
  done
  ((missing == 0))
}

prepare_mcp_runtime() {
  local search_dir="$1" wordstat_dir="$2"
  if [[ -d "$search_dir" ]]; then
    (cd "$search_dir" && uv sync --frozen)
  fi
  if [[ -d "$wordstat_dir" ]]; then
    (cd "$wordstat_dir" && npm ci --omit=dev --ignore-scripts --prefer-offline)
  fi
}

prepare_runtime() {
  local rel="$1" stage="$2"
  case "$rel" in
    plugins/yandex-direct-for-all)
      prepare_mcp_runtime "$stage/mcp/yandex-search" "$stage/mcp/yandex-wordstat"
      ;;
    mcp/yandex-search)
      prepare_mcp_runtime "$stage" ""
      ;;
    mcp/yandex-wordstat)
      prepare_mcp_runtime "" "$stage"
      ;;
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
  MANIFEST_PATH="$manifest" MANAGED_PATH="$rel" python3 - <<'PY'
import json
import os
from pathlib import Path

payload = json.loads(Path(os.environ["MANIFEST_PATH"]).read_text(encoding="utf-8"))
for item in payload.get("paths", []):
    if item.get("path") == os.environ["MANAGED_PATH"]:
        print(item.get("installed_sha256", item.get("sha256", "")))
        break
PY
}

manifest_run_id() {
  local manifest="$1"
  [[ -f "$manifest" ]] || return 0
  MANIFEST_PATH="$manifest" python3 - <<'PY'
import json
import os
from pathlib import Path

print(json.loads(Path(os.environ["MANIFEST_PATH"]).read_text(encoding="utf-8")).get("run_id", ""))
PY
}

write_manifest_json() {
  local rows="$1" destination="$2" owning_run_id="$3"
  MANIFEST_ROWS="$rows" MANIFEST_PATH="$destination" MANIFEST_RUN_ID="$owning_run_id" python3 - <<'PY'
import json
import os
from pathlib import Path

rows = []
for line in Path(os.environ["MANIFEST_ROWS"]).read_text(encoding="utf-8").splitlines():
    if not line:
        continue
    parts = line.split("\t")
    if len(parts) == 2:
        rel, source_digest = parts
        installed_digest = source_digest
    else:
        rel, source_digest, installed_digest = parts
    rows.append({
        "path": rel,
        "source_sha256": source_digest,
        "installed_sha256": installed_digest,
    })
destination = Path(os.environ["MANIFEST_PATH"])
temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
temporary.write_text(
    json.dumps(
        {"schema_version": 1, "run_id": os.environ["MANIFEST_RUN_ID"], "paths": rows},
        ensure_ascii=False,
        indent=2,
    ) + "\n",
    encoding="utf-8",
)
os.chmod(temporary, 0o600)
temporary.replace(destination)
PY
}

check_target() {
  local kind="$1" root="$2"
  local manifest="$root/state/yandex-direct-for-all/install-manifest.json"
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
    if [[ -z "$previous_hash" ]]; then
      echo "  КОНФЛИКТ  $rel (существующий путь не зарегистрирован этим установщиком)" >&2
      conflicts=1
    elif [[ "$current_hash" == "$src_hash" ]]; then
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
  local state="$root/state/yandex-direct-for-all"
  local run="$state/runs/$run_id"
  local backup="$root/backups/yandex-direct-for-all/$run_id"
  local previous_manifest="$state/install-manifest.json"
  local next_manifest="$run/manifest.after.tsv"
  mkdir -p "$run/stages" "$backup"
  chmod 700 "$state" "$state/runs" "$run" "$run/stages" "$root/backups" "$root/backups/yandex-direct-for-all" "$backup"
  [[ -f "$previous_manifest" ]] && cp "$previous_manifest" "$run/install-manifest.before.json" || : > "$run/install-manifest.before.absent"
  : > "$run/operations.tsv"
  : > "$run/pre-state.tsv"
  : > "$run/prepared.tsv"
  : > "$next_manifest"
  chmod 600 "$run/operations.tsv" "$run/pre-state.tsv" "$run/prepared.tsv" "$next_manifest"

  local index=0
  for rel in "${managed_paths[@]}"; do
    local src stage src_hash
    src="$(source_for "$rel")"
    [[ -e "$src" ]] || continue
    index=$((index + 1))
    stage="$run/stages/$index"
    if [[ -d "$src" ]]; then
      mkdir -p "$stage"
      rsync -a --exclude node_modules --exclude __pycache__ --exclude .venv "$src/" "$stage/"
    else
      cp "$src" "$stage"
    fi
    if ! prepare_runtime "$rel" "$stage"; then
      rm -rf "$stage"
      echo "Не удалось подготовить зависимости: $rel" >&2
      exit 4
    fi
    src_hash="$(tree_hash "$src")"
    [[ "$(tree_hash "$stage")" == "$src_hash" ]] || {
      echo "Ошибка проверки подготовленной копии: $rel" >&2
      exit 4
    }
    printf '%s\t%s\t%s\n' "$rel" "$index" "$src_hash" >> "$run/prepared.tsv"
  done

  while IFS=$'\t' read -r rel index src_hash; do
    local dest parent stage existed old_hash
    [[ -n "$rel" ]] || continue
    dest="$root/$rel"
    parent="$(dirname "$dest")"
    stage="$run/stages/$index"
    mkdir -p "$parent"
    existed=0
    if [[ -e "$dest" ]]; then
      existed=1
      old_hash="$(tree_hash "$dest")"
      printf '%s\tpresent\tdirectory\t%s\t%s\n' "$rel" "$old_hash" "$index" >> "$run/pre-state.tsv"
      mv "$dest" "$backup/$index"
    else
      printf '%s\tabsent\t-\t-\t%s\n' "$rel" "$index" >> "$run/pre-state.tsv"
    fi
    mv "$stage" "$dest"
    printf '%s\t%s\t%s\n' "$rel" "$existed" "$index" >> "$run/operations.tsv"
    local installed_hash
    installed_hash="$(tree_hash "$dest")"
    [[ "$installed_hash" == "$src_hash" ]] || {
      echo "Ошибка проверки установленного пути: $rel" >&2
      exit 4
    }
    printf '%s\t%s\t%s\n' "$rel" "$src_hash" "$installed_hash" >> "$next_manifest"
  done < "$run/prepared.tsv"
  write_manifest_json "$next_manifest" "$previous_manifest" "$run_id"

  if [[ "$kind" == codex ]]; then
    local marketplace="$HOME/.agents/plugins/marketplace.json"
    if [[ -f "$marketplace" ]]; then
      cp "$marketplace" "$run/marketplace.before.json"
    else
      : > "$run/marketplace.before.absent"
    fi
    write_marketplace
    shasum -a 256 "$marketplace" | awk '{print $1}' > "$run/marketplace.after.sha256"
  fi
  printf '%s\n' "applied" > "$run/status"
  chmod 600 "$run/status"
}

validate_rollback_target() {
  local kind="$1" root="$2"
  local state="$root/state/yandex-direct-for-all"
  local run="$state/runs/$rollback_id"
  local current_manifest="$state/install-manifest.json"
  [[ -d "$run" ]] || { echo "Нет записи отката $rollback_id для $kind" >&2; return 5; }
  [[ "$(cat "$run/status" 2>/dev/null || true)" == applied ]] || {
    echo "Запись $rollback_id уже использована или неполна" >&2
    return 5
  }
  [[ "$(manifest_run_id "$current_manifest")" == "$rollback_id" ]] || {
    echo "Откат запрещён: $rollback_id не является последней установленной версией для $kind" >&2
    return 5
  }

  # Сначала проверяем всё состояние; до завершения этой проверки ничего не меняется.
  while IFS=$'\t' read -r rel _ expected_hash; do
    [[ -n "$rel" ]] || continue
    if [[ ! -e "$root/$rel" || "$(tree_hash "$root/$rel")" != "$expected_hash" ]]; then
      echo "Откат запрещён: после установки изменён управляемый путь $rel" >&2
      return 5
    fi
  done < "$run/manifest.after.tsv"
  if [[ "$kind" == codex ]]; then
    local marketplace="$HOME/.agents/plugins/marketplace.json"
    if [[ ! -f "$marketplace" || "$(shasum -a 256 "$marketplace" | awk '{print $1}')" != "$(cat "$run/marketplace.after.sha256")" ]]; then
      echo "Откат запрещён: после установки изменён marketplace.json" >&2
      return 5
    fi
  fi
}

rollback_target() {
  local kind="$1" root="$2"
  local state="$root/state/yandex-direct-for-all"
  local run="$state/runs/$rollback_id"
  local backup="$root/backups/yandex-direct-for-all/$rollback_id"
  local current_manifest="$state/install-manifest.json"
  local marketplace="$HOME/.agents/plugins/marketplace.json"

  while IFS=$'\t' read -r rel existed index; do
    [[ -n "$rel" ]] || continue
    rm -rf "$root/$rel"
    if [[ "$existed" == 1 ]]; then
      mkdir -p "$(dirname "$root/$rel")"
      mv "$backup/$index" "$root/$rel"
    fi
  done < "$run/operations.tsv"
  if [[ -f "$run/install-manifest.before.json" ]]; then
    cp "$run/install-manifest.before.json" "$current_manifest"
  else
    rm -f "$current_manifest"
  fi
  if [[ "$kind" == codex ]]; then
    if [[ -f "$run/marketplace.before.json" ]]; then
      mkdir -p "$(dirname "$marketplace")"
      cp "$run/marketplace.before.json" "$marketplace"
    else
      rm -f "$marketplace"
    fi
  fi

  while IFS=$'\t' read -r rel old_state _ old_hash _; do
    [[ -n "$rel" ]] || continue
    if [[ "$old_state" == absent ]]; then
      [[ ! -e "$root/$rel" ]] || { echo "Ошибка проверки отката: $rel должен отсутствовать" >&2; return 6; }
    else
      [[ -e "$root/$rel" && "$(tree_hash "$root/$rel")" == "$old_hash" ]] || {
        echo "Ошибка проверки отката: $rel не совпал с исходным состоянием" >&2
        return 6
      }
    fi
  done < "$run/pre-state.tsv"
  printf '%s\n' "rolled_back" > "$run/status"
  echo "ОТКАЧЕНО: $kind"
}

if [[ "$mode" == rollback ]]; then
  # Для нескольких сред сначала проверяем их все. Ни одна запись не начинается,
  # пока откат не признан безопасным одновременно для Codex и Claude.
  for item in "${roots[@]}"; do
    validate_rollback_target "${item%%:*}" "${item#*:}"
  done
  for item in "${roots[@]}"; do
    rollback_target "${item%%:*}" "${item#*:}"
  done
  exit 0
fi

if [[ "$mode" == apply ]]; then
  require_runtime_tools || exit 2
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
