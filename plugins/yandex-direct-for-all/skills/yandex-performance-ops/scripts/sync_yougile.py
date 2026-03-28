#!/usr/bin/env python3
"""Синхронизация tasks.tsv → задачи YouGile.
Переиспользуемый скрипт — работает через preset board или через явный columns JSON.
Поддерживает оба формата приоритетов: P1-P4 и CRITICAL/HIGH/MEDIUM/LOW.
"""
import argparse, json, csv, urllib.request, urllib.error, sys, os, time

YOUGILE_API = "https://ru.yougile.com/api-v2"

# Пресеты досок
BOARD_PRESETS = {
    "tenevoy": {
        "backlog": "640b7463-024d-4c60-88a5-ec6f05d58ac7",
        "planning": "46a8a939-8791-4400-b4fa-7112fdf21c8b",  # В работе
        "monitoring": "3bd5c58d-23d5-4144-b09e-27308acbe0cf",
        "waiting": "cc0aa037-3e6a-435a-b19e-0aa4689a6c51",  # Ожидает проверки
        "done": "f1f09de8-8ee1-401e-9c48-2596093cb540",
        "future": "e14545d0-8cfa-440f-bd35-ac1128fc5709",
    },
    "kartinium": {
        "backlog": "decd6bad-fa05-4b55-b498-6a8f5a1e2a6f",
        "planning": "3b90456a-5eeb-470e-9ce8-9c1e4acebe2d",
        "in_work": "6c814dec-dc59-4a8f-a2fa-0e6ac0f05a89",
    },
    "siz": {
        "backlog": "0d45fbd2-b01e-4c6e-8df4-1725abe8f37c",
        "planning": "55d0204b-f001-4cd1-80eb-eecf34044133",  # В работе
        "monitoring": "c9d265c3-79dc-48f8-8896-e00ef07c24f6",
        "waiting": "0f5cb12d-2558-4250-89ed-97e5b444aed3",  # Проверка результатов
        "done": "f49a6052-8619-4818-88c3-6006f8b094fc",
        "future": "5a08a3ec-3a3c-4e07-9c48-4f921101b9ea",  # Ледник
    },
}

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
    if not board_name:
        raise SystemExit("Provide --board preset or --columns-json")
    return BOARD_PRESETS[board_name]


def main():
    p = argparse.ArgumentParser(description="Синхронизация tasks.tsv → YouGile")
    p.add_argument("--yougile-token", required=True, help="YouGile API token")
    p.add_argument("--tasks-file", required=True, help="Путь к tasks.tsv")
    p.add_argument("--campaign-name", default="Директ", help="Префикс задач")
    p.add_argument("--board", default="", choices=[""] + list(BOARD_PRESETS.keys()), help="Пресет доски")
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
