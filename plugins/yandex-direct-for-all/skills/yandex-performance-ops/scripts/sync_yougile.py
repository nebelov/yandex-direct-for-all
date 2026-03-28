#!/usr/bin/env python3
"""Синхронизация tasks.tsv -> задачи YouGile.
Переиспользуемый скрипт работает через project-local board presets или через явный columns JSON.
Поддерживает оба формата приоритетов: P1-P4 и CRITICAL/HIGH/MEDIUM/LOW.
"""
import argparse, json, csv, urllib.request, urllib.error, sys, os, time
from pathlib import Path

YOUGILE_API = "https://ru.yougile.com/api-v2"

DEFAULT_PRESET_FILES = (
    Path.cwd() / ".codex" / "yougile-board-presets.json",
    Path.cwd() / ".claude" / "yougile-board-presets.json",
    Path.cwd() / "yougile-board-presets.json",
)

# Маппинг priority → колонка (оба формата)
PRIORITY_COLUMN = {
    "CRITICAL": "planning", "P1": "planning",
    "HIGH": "planning", "P2": "backlog",
    "MEDIUM": "backlog", "P3": "backlog",
    "LOW": "future", "P4": "future",
}

# Маппинг category → цвет задачи (оба формата)
CATEGORY_COLOR = {
    "SETTING_CHANGE": "red", "PLACEMENT_CHANGE": "red",
    "NEGATIVE_KEYWORD": "yellow", "AD_COMPONENT": "blue",
    "BID_ADJUSTMENT": "yellow", "STRUCTURE_CHANGE": "violet",
    # Новый формат из агентов анализа
    "scale": "blue", "optimize": "yellow", "review": "turquoise",
    "monitor": "turquoise",
}


def yougile_api(token, method, path, data=None, retries=2):
    url = f"{YOUGILE_API}/{path}"
    body = json.dumps(data).encode() if data else None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                chunks = []
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    chunks.append(chunk)
                return json.loads(b"".join(chunks).decode())
        except (urllib.error.HTTPError, Exception) as e:
            if isinstance(e, urllib.error.HTTPError):
                err = e.read().decode()
                print(f"  YouGile ERROR {e.code}: {err[:200]}", file=sys.stderr)
                return None
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  YouGile NETWORK ERROR: {e}", file=sys.stderr)
            return None


def load_tasks(path, category=None, priority=None):
    tasks = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if category and row["category"] != category:
                continue
            if priority and row["priority"] != priority:
                continue
            tasks.append(row)
    return tasks


def find_existing_tasks(token, column_id):
    """Получить существующие задачи из колонки."""
    r = yougile_api(token, "GET", f"tasks?columnId={column_id}")
    if r and "content" in r:
        return {t["title"]: t["id"] for t in r["content"]}
    return {}


def create_task(token, column_id, title, description, color="yellow"):
    data = {
        "title": title,
        "columnId": column_id,
        "description": description,
        "color": color,
    }
    time.sleep(0.5)  # Rate limit: max 2 req/sec для YouGile API
    return yougile_api(token, "POST", "tasks", data)


def load_board_presets():
    candidates = [os.environ.get("YOUGILE_BOARD_PRESETS_FILE", "").strip()]
    candidates.extend(str(path) for path in DEFAULT_PRESET_FILES)
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise SystemExit(f"Board presets file must contain a JSON object: {path}")
        return data
    return {}


def load_columns(board_name, columns_json):
    if columns_json:
        if os.path.exists(columns_json):
            with open(columns_json, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(columns_json)
        if not isinstance(data, dict) or not data:
            raise SystemExit("--columns-json must be a JSON object with column aliases")
        return data
    presets = load_board_presets()
    if not board_name:
        raise SystemExit(
            "Provide --board preset or --columns-json. "
            "Project-local presets can live in ./.codex/yougile-board-presets.json "
            "or path from YOUGILE_BOARD_PRESETS_FILE."
        )
    if board_name not in presets:
        available = ", ".join(sorted(presets)) or "none"
        raise SystemExit(
            f"Unknown board preset: {board_name}. "
            f"Available presets: {available}. "
            "Use --columns-json or provide project-local presets."
        )
    return presets[board_name]


def main():
    p = argparse.ArgumentParser(description="Синхронизация tasks.tsv -> YouGile")
    p.add_argument("--yougile-token", required=True, help="YouGile API token")
    p.add_argument("--tasks-file", required=True, help="Путь к tasks.tsv")
    p.add_argument("--campaign-name", default="Директ", help="Префикс задач")
    p.add_argument("--board", default="", help="Имя project-local пресета доски")
    p.add_argument("--columns-json", default="", help="Path to JSON or inline JSON with YouGile columns map")
    p.add_argument("--category", help="Фильтр по категории")
    p.add_argument("--priority", help="Фильтр по приоритету")
    p.add_argument("--skip-dedup", action="store_true", help="Пропустить проверку дублей")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    columns = load_columns(args.board, args.columns_json)

    tasks = load_tasks(args.tasks_file, args.category, args.priority)
    print(f"Загружено задач: {len(tasks)}")

    if not tasks:
        print("Нет задач для синхронизации")
        return

    # Проверка дублей в целевых колонках
    existing = {}
    if not args.skip_dedup:
        for col_key, col_id in columns.items():
            found = find_existing_tasks(args.yougile_token, col_id)
            if found:
                existing.update(found)
        print(f"Существующих задач в YouGile: {len(existing)}")

    created = 0
    skipped = 0

    for t in tasks:
        # Универсальное определение описания из разных форматов TSV
        task_desc = (t.get('description') or t.get('rationale')
                     or t.get('notes') or t.get('expected_impact') or t['action'])
        title = f"[{args.campaign_name}] {t['task_id']}: {task_desc[:60]}"
        col_key = PRIORITY_COLUMN.get(t["priority"], "backlog")
        col_id = columns.get(col_key, columns.get("backlog", list(columns.values())[0]))
        # Универсальное определение категории
        cat = t.get("category") or t.get("type") or "unknown"
        color = CATEGORY_COLOR.get(cat, "yellow")

        # Проверка дублей по task_id в названии
        if not args.skip_dedup:
            is_dup = any(t["task_id"] in existing_title for existing_title in existing)
            if is_dup:
                print(f"  SKIP (дубль): {title}")
                skipped += 1
                continue

        # Универсальная сборка описания из доступных полей
        params = t.get('params_json') or t.get('params') or ''
        evidence = t.get('evidence') or t.get('rationale') or t.get('expected_impact') or ''
        savings = t.get('savings_30d') or ''
        target_name = t.get('target_name') or t.get('entity') or ''
        target_id = t.get('target_id') or t.get('entity_id') or ''
        scope = t.get('scope') or ''

        desc = f"<p><b>{cat}</b> | Priority: {t['priority']}</p>"
        desc += f"<p><b>Действие:</b> {t['action']}</p>"
        if params:
            desc += f"<p><b>Параметры:</b> <code>{params}</code></p>"
        if evidence:
            desc += f"<p><b>Обоснование:</b> {evidence}</p>"
        if savings:
            desc += f"<p><b>Экономия 30д:</b> {savings}р</p>"
        if target_name:
            desc += f"<p><b>Цель:</b> {target_name} (ID: {target_id})</p>"

        if args.dry_run:
            print(f"  [DRY] {title} → {col_key} ({color})")
        else:
            r = create_task(args.yougile_token, col_id, title, desc, color)
            if r and r.get("id"):
                print(f"  OK: {title}")
                created += 1
            else:
                print(f"  FAIL: {title}")

    print(f"\nИтого: создано={created}, пропущено={skipped}, всего={len(tasks)}")


if __name__ == "__main__":
    main()
