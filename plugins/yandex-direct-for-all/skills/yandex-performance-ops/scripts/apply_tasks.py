#!/usr/bin/env python3
"""Применение задач из tasks.tsv к Яндекс.Директ через API.
Парсит TSV, группирует по типам, вызывает соответствующие API методы.
"""
import argparse, json, csv, urllib.request, urllib.error, sys, time, os

def api_call(token, login, service, method, params):
    url = f"https://api.direct.yandex.com/json/v5/{service}"
    body = json.dumps({"method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Client-Login": login,
        "Content-Type": "application/json",
        "Accept-Language": "ru",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  ERROR {e.code}: {err}", file=sys.stderr)
        return None

def load_tasks(path, category=None, priority=None):
    tasks = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if category and row.get("category", "") != category:
                continue
            if priority and row.get("priority", "") != priority:
                continue
            # Поддержка двух форматов: params_json или new_value
            json_str = row.get("params_json") or row.get("new_value", "")
            if not json_str or json_str.strip() == "":
                continue
            try:
                row["params"] = json.loads(json_str)
            except json.JSONDecodeError:
                continue
            # Нормализация полей
            if "description" not in row:
                row["description"] = row.get("comment", "")
            if "savings_30d" not in row:
                row["savings_30d"] = "0"
            tasks.append(row)
    return tasks

def apply_settings(token, login, campaign_id, tasks, dry_run):
    """Применяет SETTING_CHANGE задачи."""
    settings = []
    for t in tasks:
        p = t["params"]
        settings.append({"Option": p["option"], "Value": p["value"]})
        print(f"  {t['task_id']}: {p['option']} → {p['value']}")

    if not settings:
        return
    if dry_run:
        print("  [DRY RUN] не применено")
        return

    r = api_call(token, login, "campaigns", "update", {
        "Campaigns": [{"Id": campaign_id, "UnifiedCampaign": {"Settings": settings}}]
    })
    if r and "result" in r:
        print(f"  OK: {len(settings)} настроек обновлено")
    else:
        print(f"  FAIL: {r}")

def apply_placements(token, login, campaign_id, tasks, dry_run):
    """Применяет PLACEMENT_CHANGE задачи."""
    placements = {}
    for t in tasks:
        p = t["params"]
        placements[p["placement"]] = p["value"]
        print(f"  {t['task_id']}: {p['placement']} → {p['value']}")

    if not placements:
        return

    # Нужно указать ВСЕ плейсменты + стратегию
    all_placements = {"SearchResults": "YES", "ProductGallery": "YES",
                      "DynamicPlaces": "YES", "Maps": "NO", "SearchOrganizationList": "NO"}
    all_placements.update(placements)

    if dry_run:
        print(f"  [DRY RUN] PlacementTypes: {all_placements}")
        return

    r = api_call(token, login, "campaigns", "update", {
        "Campaigns": [{"Id": campaign_id, "UnifiedCampaign": {
            "BiddingStrategy": {
                "Search": {
                    "BiddingStrategyType": "HIGHEST_POSITION",
                    "PlacementTypes": all_placements
                },
                "Network": {"BiddingStrategyType": "SERVING_OFF"}
            }
        }}]
    })
    if r and "result" in r:
        print(f"  OK: плейсменты обновлены")
    else:
        print(f"  FAIL: {r}")

def apply_negatives(token, login, campaign_id, tasks, dry_run):
    """Применяет NEGATIVE_KEYWORD задачи."""
    # Получаем текущие минус-слова
    r = api_call(token, login, "campaigns", "get", {
        "SelectionCriteria": {"Ids": [campaign_id]},
        "FieldNames": ["Id", "NegativeKeywords"],
    })
    existing = []
    if r:
        camp = r["result"]["Campaigns"][0]
        nk = camp.get("NegativeKeywords")
        if nk and nk.get("Items"):
            existing = nk["Items"]

    existing_set = set(w.lower() for w in existing)
    new_words = []
    for t in tasks:
        p = t["params"]
        if p.get("level") != "campaign":
            print(f"  {t['task_id']}: SKIP (level={p.get('level')}, не campaign)")
            continue
        word = p.get("word") or p.get("phrase", "")
        if word.lower() in existing_set:
            print(f"  {t['task_id']}: SKIP ('{word}' уже есть)")
            continue
        new_words.append(word)
        print(f"  {t['task_id']}: +'{word}' ({t['description'][:50]})")

    if not new_words:
        print("  Нечего добавлять")
        return

    all_neg = existing + new_words
    print(f"  Итого: {len(existing)} существующих + {len(new_words)} новых = {len(all_neg)}")

    if dry_run:
        print("  [DRY RUN] не применено")
        return

    r = api_call(token, login, "campaigns", "update", {
        "Campaigns": [{"Id": campaign_id, "NegativeKeywords": {"Items": all_neg}}]
    })
    if r and "result" in r:
        print(f"  OK: минус-слова обновлены ({len(all_neg)} шт)")
    else:
        print(f"  FAIL: {r}")

def apply_ad_components(token, login, tasks, dry_run):
    """Применяет AD_COMPONENT задачи (информационно — требует ручного создания)."""
    for t in tasks:
        p = t["params"]
        print(f"  {t['task_id']}: Ad {p['ad_id']} → {t['action']}")
        print(f"    old: {p.get('old', '?')}")
        print(f"    new: {p.get('new', '?')}")
    if tasks:
        print("  NOTE: Замена компонентов объявлений требует создания нового объявления")
        print("  и архивации старого. Это делается через ads.add + ads.archive.")
        print("  Автоматическое применение НЕ реализовано — создайте задачи в YouGile.")

def apply_bids(token, login, tasks, dry_run):
    """Применяет BID_ADJUSTMENT (информационно)."""
    for t in tasks:
        p = t["params"]
        print(f"  {t['task_id']}: Criterion {p.get('criterion_id')} → {p.get('recommendation')}")
        print(f"    evidence: {t['evidence']}")
    if tasks:
        print("  NOTE: Ставки в HIGHEST_POSITION управляются Яндексом автоматически.")
        print("  Для ручного управления нужно сменить стратегию. Создайте задачи в YouGile.")

def main():
    p = argparse.ArgumentParser(description="Применение задач из tasks.tsv к Яндекс.Директ")
    p.add_argument("--token", required=True)
    p.add_argument("--login", required=True)
    p.add_argument("--campaign-id", type=int, required=True)
    p.add_argument("--tasks-file", required=True, help="Путь к tasks.tsv")
    p.add_argument("--category", help="Фильтр по категории")
    p.add_argument("--priority", help="Фильтр по приоритету")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not os.path.exists(args.tasks_file):
        print(f"Файл не найден: {args.tasks_file}")
        sys.exit(1)

    tasks = load_tasks(args.tasks_file, args.category, args.priority)
    print(f"Загружено задач: {len(tasks)}")

    # Группируем по категориям
    by_cat = {}
    for t in tasks:
        by_cat.setdefault(t["category"], []).append(t)

    for cat in ["SETTING_CHANGE", "PLACEMENT_CHANGE", "NEGATIVE_KEYWORD",
                "AD_COMPONENT", "BID_ADJUSTMENT", "STRUCTURE_CHANGE"]:
        cat_tasks = by_cat.get(cat, [])
        if not cat_tasks:
            continue
        print(f"\n=== {cat} ({len(cat_tasks)} задач) ===")

        if cat == "SETTING_CHANGE":
            apply_settings(args.token, args.login, args.campaign_id, cat_tasks, args.dry_run)
        elif cat == "PLACEMENT_CHANGE":
            apply_placements(args.token, args.login, args.campaign_id, cat_tasks, args.dry_run)
        elif cat == "NEGATIVE_KEYWORD":
            apply_negatives(args.token, args.login, args.campaign_id, cat_tasks, args.dry_run)
        elif cat == "AD_COMPONENT":
            apply_ad_components(args.token, args.login, cat_tasks, args.dry_run)
        elif cat == "BID_ADJUSTMENT":
            apply_bids(args.token, args.login, cat_tasks, args.dry_run)
        elif cat == "STRUCTURE_CHANGE":
            print("  NOTE: Структурные изменения требуют ручной реализации.")
            for t in cat_tasks:
                print(f"  {t['task_id']}: {t['action']} — {t['description']}")

    print("\nГотово.")

if __name__ == "__main__":
    main()
