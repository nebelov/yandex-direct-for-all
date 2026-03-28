#!/usr/bin/env python3
"""Apply or dry-run a no-moderation optimization pack.

Supports:
- search settings tasks.tsv
- search negatives tasks.tsv
- RSYA ExcludedSites after-pack JSON

Built-in safeguards:
- live drift-check for ExcludedSites baseline
- immediate read-back validation after apply
"""

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path


API_V5 = "https://api.direct.yandex.com/json/v5"
API_V501 = "https://api.direct.yandex.com/json/v501"


def api_call(token, login, service, method, params, version="v5"):
    base = API_V501 if version == "v501" else API_V5
    req = urllib.request.Request(
        f"{base}/{service}",
        data=json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": "ru",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {service}.{method}: {detail}") from exc


def load_tasks(path):
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows = []
        for row in reader:
            params = json.loads(row["params_json"])
            row["params"] = params
            row["target_id"] = int(row["target_id"])
            rows.append(row)
        return rows


def count_negative_tokens(value):
    if not isinstance(value, str):
        return 0
    return len([part for part in value.strip().split() if part])


def validate_negative_task_shape(task, allow_phrase_negatives=False):
    params = task["params"]
    phrase = params.get("phrase")
    word = params.get("word")
    if phrase and not allow_phrase_negatives:
        raise RuntimeError(
            "negative task contains params.phrase; default reusable path forbids phrase-level SQR apply. "
            "Reduce manual evidence to short stop-words/safe masks first or pass explicit override."
        )
    if word and not allow_phrase_negatives and count_negative_tokens(word) > 2:
        raise RuntimeError(
            f"negative task contains overlong word/mask '{word}'; reduce it to production-safe short token/mask first."
        )


def settings_map(settings):
    return {item.get("Option"): item.get("Value") for item in settings or []}


def get_campaign(token, login, campaign_id, fields=None, uc_fields=None):
    params = {"SelectionCriteria": {"Ids": [campaign_id]}, "FieldNames": fields or ["Id", "Name"]}
    if uc_fields:
        params["UnifiedCampaignFieldNames"] = uc_fields
    resp = api_call(token, login, "campaigns", "get", params, version="v501")
    campaigns = resp.get("result", {}).get("Campaigns", [])
    if not campaigns:
        raise RuntimeError(f"campaign {campaign_id} not found")
    return campaigns[0]


def plan_settings(token, login, tasks_by_campaign):
    plans = []
    for campaign_id, tasks in sorted(tasks_by_campaign.items()):
        campaign = get_campaign(
            token,
            login,
            campaign_id,
            fields=["Id", "Name"],
            uc_fields=["Settings"],
        )
        live_settings = settings_map((campaign.get("UnifiedCampaign") or {}).get("Settings"))
        changes = []
        for task in tasks:
            option = task["params"]["option"]
            desired = task["params"]["value"]
            current = live_settings.get(option)
            changes.append(
                {
                    "task_id": task["task_id"],
                    "option": option,
                    "current": current,
                    "desired": desired,
                    "changed": current != desired,
                }
            )
        plans.append(
            {
                "type": "settings",
                "campaign_id": campaign_id,
                "campaign_name": campaign.get("Name", ""),
                "changes": changes,
            }
        )
    return plans


def apply_settings(token, login, plan, dry_run):
    desired_items = []
    changed = [change for change in plan["changes"] if change["changed"]]
    for change in changed:
        desired_items.append({"Option": change["option"], "Value": change["desired"]})
    if not changed:
        return {"campaign_id": plan["campaign_id"], "status": "SKIP", "reason": "already matches"}
    if dry_run:
        return {
            "campaign_id": plan["campaign_id"],
            "status": "DRY_RUN",
            "apply_count": len(changed),
            "changes": changed,
        }
    api_call(
        token,
        login,
        "campaigns",
        "update",
        {"Campaigns": [{"Id": plan["campaign_id"], "UnifiedCampaign": {"Settings": desired_items}}]},
        version="v501",
    )
    readback = get_campaign(
        token,
        login,
        plan["campaign_id"],
        fields=["Id", "Name"],
        uc_fields=["Settings"],
    )
    rb_settings = settings_map((readback.get("UnifiedCampaign") or {}).get("Settings"))
    mismatches = []
    for change in changed:
        actual = rb_settings.get(change["option"])
        if actual != change["desired"]:
            mismatches.append({"option": change["option"], "desired": change["desired"], "actual": actual})
    return {
        "campaign_id": plan["campaign_id"],
        "status": "OK" if not mismatches else "FAIL",
        "apply_count": len(changed),
        "mismatches": mismatches,
    }


def get_negative_keywords(campaign):
    nk = campaign.get("NegativeKeywords") or {}
    if isinstance(nk, dict):
        return list(nk.get("Items") or [])
    if isinstance(nk, list):
        return list(nk)
    return []


def plan_negatives(token, login, tasks_by_campaign):
    plans = []
    for campaign_id, tasks in sorted(tasks_by_campaign.items()):
        campaign = get_campaign(token, login, campaign_id, fields=["Id", "Name", "NegativeKeywords"])
        live = get_negative_keywords(campaign)
        live_set = {item.strip().lower() for item in live}
        add = []
        skipped_existing = []
        for task in tasks:
            phrase = (task["params"].get("phrase") or task["params"].get("word") or "").strip()
            if not phrase:
                continue
            if phrase.lower() in live_set:
                skipped_existing.append(phrase)
                continue
            add.append(phrase)
        plans.append(
            {
                "type": "negatives",
                "campaign_id": campaign_id,
                "campaign_name": campaign.get("Name", ""),
                "live_count": len(live),
                "live_items": live,
                "add_items": add,
                "skipped_existing": skipped_existing,
            }
        )
    return plans


def apply_negatives(token, login, plan, dry_run):
    if not plan["add_items"]:
        return {"campaign_id": plan["campaign_id"], "status": "SKIP", "reason": "no new negatives"}
    final = plan["live_items"] + plan["add_items"]
    if dry_run:
        return {
            "campaign_id": plan["campaign_id"],
            "status": "DRY_RUN",
            "add_count": len(plan["add_items"]),
            "final_count": len(final),
            "add_items": plan["add_items"],
            "skipped_existing": plan["skipped_existing"],
        }
    api_call(
        token,
        login,
        "campaigns",
        "update",
        {"Campaigns": [{"Id": plan["campaign_id"], "NegativeKeywords": {"Items": final}}]},
        version="v501",
    )
    readback = get_campaign(token, login, plan["campaign_id"], fields=["Id", "Name", "NegativeKeywords"])
    actual = {item.strip().lower() for item in get_negative_keywords(readback)}
    missing = [item for item in plan["add_items"] if item.lower() not in actual]
    return {
        "campaign_id": plan["campaign_id"],
        "status": "OK" if not missing else "FAIL",
        "add_count": len(plan["add_items"]),
        "missing": missing,
    }


def load_excluded_pack(path):
    pack = json.loads(Path(path).read_text(encoding="utf-8"))
    pack["campaign_id"] = int(pack["campaign_id"])
    pack["current_count"] = int(pack["current_count"])
    pack["after_count"] = int(pack["after_count"])
    pack["add_sites"] = dedupe_excluded_items(pack.get("add_sites") or [])
    pack["after_items"] = dedupe_excluded_items(pack.get("after_items") or [])
    pack["remove_sites"] = dedupe_excluded_items(pack.get("remove_sites") or [])
    return pack


def get_excluded_sites(campaign):
    raw = campaign.get("ExcludedSites")
    if isinstance(raw, dict):
        return list(raw.get("Items") or [])
    if isinstance(raw, list):
        return list(raw)
    return []


def normalize_excluded_identifier(value):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if normalized.startswith("http://"):
        normalized = normalized[7:]
    elif normalized.startswith("https://"):
        normalized = normalized[8:]
    normalized = normalized.rstrip("/")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def dedupe_excluded_items(values):
    seen = set()
    items = []
    for value in values:
        normalized = normalize_excluded_identifier(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def plan_excluded(token, login, packs):
    plans = []
    for pack in packs:
        campaign = get_campaign(token, login, pack["campaign_id"], fields=["Id", "Name", "ExcludedSites"])
        live_items = dedupe_excluded_items(get_excluded_sites(campaign))
        live_set = set(live_items)
        add_set = set(pack["add_sites"])
        remove_set = set(pack.get("remove_sites", []))
        baseline_set = set(pack["after_items"]) - set(pack["add_sites"])
        drift = live_set != baseline_set
        merged_after_items = sorted((live_set | add_set) - remove_set)
        plans.append(
            {
                "type": "excluded_sites",
                "campaign_id": pack["campaign_id"],
                "campaign_name": campaign.get("Name", ""),
                "pack": pack,
                "live_count": len(live_items),
                "baseline_count": len(baseline_set),
                "drift": drift,
                "missing_from_live": sorted(baseline_set - live_set),
                "extra_in_live": sorted(live_set - baseline_set),
                "merged_after_items": merged_after_items,
                "merged_after_count": len(merged_after_items),
                "merged_overflow": len(merged_after_items) > 1000,
            }
        )
    return plans


def apply_excluded(token, login, plan, dry_run):
    pack = plan["pack"]
    if plan["merged_overflow"]:
        return {
            "campaign_id": plan["campaign_id"],
            "status": "FAIL",
            "reason": "ExcludedSites overflow after live merge",
            "merged_after_count": plan["merged_after_count"],
            "missing_from_live": plan["missing_from_live"][:20],
            "extra_in_live": plan["extra_in_live"][:20],
        }
    if dry_run:
        return {
            "campaign_id": plan["campaign_id"],
            "status": "DRY_RUN",
            "current_count": plan["live_count"],
            "after_count": plan["merged_after_count"],
            "add_sites": pack["add_sites"],
            "drift": plan["drift"],
        }
    api_call(
        token,
        login,
        "campaigns",
        "update",
        {"Campaigns": [{"Id": plan["campaign_id"], "ExcludedSites": {"Items": plan["merged_after_items"]}}]},
        version="v501",
    )
    readback = get_campaign(token, login, plan["campaign_id"], fields=["Id", "Name", "ExcludedSites"])
    actual = dedupe_excluded_items(get_excluded_sites(readback))
    actual_set = set(actual)
    expected_set = set(plan["merged_after_items"])
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    return {
        "campaign_id": plan["campaign_id"],
        "status": "OK" if not missing and not extra else "FAIL",
        "after_count": len(actual),
        "missing": missing[:20],
        "extra": extra[:20],
        "drift": plan["drift"],
    }


def render_text(plans, results, dry_run):
    lines = [f"MODE\t{'DRY_RUN' if dry_run else 'APPLY'}"]
    for plan in plans:
        lines.append(f"\n=== {plan['type'].upper()} campaign={plan['campaign_id']} {plan['campaign_name']} ===")
        if plan["type"] == "settings":
            for change in plan["changes"]:
                lines.append(
                    f"SETTING\t{change['option']}\tcurrent={change['current']}\tdesired={change['desired']}\tchanged={change['changed']}"
                )
        elif plan["type"] == "negatives":
            lines.append(f"LIVE_COUNT\t{plan['live_count']}")
            lines.append(f"ADD_COUNT\t{len(plan['add_items'])}")
            if plan["add_items"]:
                lines.append(f"ADD_ITEMS\t{', '.join(plan['add_items'])}")
            if plan["skipped_existing"]:
                lines.append(f"SKIP_EXISTING\t{', '.join(plan['skipped_existing'])}")
        elif plan["type"] == "excluded_sites":
            lines.append(
                f"EXCLUDED\tlive={plan['live_count']}\tbaseline={plan['baseline_count']}\tdrift={plan['drift']}\t"
                f"after={plan['pack']['after_count']}"
            )
            lines.append(f"ADD_SITES\t{', '.join(plan['pack']['add_sites'])}")
            if plan["missing_from_live"]:
                lines.append(f"DRIFT_MISSING\t{', '.join(plan['missing_from_live'][:20])}")
            if plan["extra_in_live"]:
                lines.append(f"DRIFT_EXTRA\t{', '.join(plan['extra_in_live'][:20])}")
        result = results.get((plan["type"], plan["campaign_id"]))
        if result:
            lines.append(f"RESULT\t{result['status']}")
            for key in sorted(result):
                if key in {"campaign_id", "status"}:
                    continue
                lines.append(f"  {key}={result[key]}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Apply or dry-run no-moderation pack")
    parser.add_argument("--token", required=True)
    parser.add_argument("--login", required=True)
    parser.add_argument("--settings-tasks", action="append", default=[])
    parser.add_argument("--negative-tasks", action="append", default=[])
    parser.add_argument("--excluded-pack", action="append", default=[])
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-text", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-phrase-negatives", action="store_true")
    args = parser.parse_args()

    all_plans = []
    results = {}

    if args.settings_tasks:
        grouped = defaultdict(list)
        for path in args.settings_tasks:
            for task in load_tasks(path):
                grouped[task["target_id"]].append(task)
        plans = plan_settings(args.token, args.login, grouped)
        all_plans.extend(plans)
        for plan in plans:
            results[(plan["type"], plan["campaign_id"])] = apply_settings(args.token, args.login, plan, args.dry_run)

    if args.negative_tasks:
        grouped = defaultdict(list)
        for path in args.negative_tasks:
            for task in load_tasks(path):
                validate_negative_task_shape(task, allow_phrase_negatives=args.allow_phrase_negatives)
                grouped[task["target_id"]].append(task)
        plans = plan_negatives(args.token, args.login, grouped)
        all_plans.extend(plans)
        for plan in plans:
            results[(plan["type"], plan["campaign_id"])] = apply_negatives(args.token, args.login, plan, args.dry_run)

    if args.excluded_pack:
        packs = [load_excluded_pack(path) for path in args.excluded_pack]
        plans = plan_excluded(args.token, args.login, packs)
        all_plans.extend(plans)
        for plan in plans:
            results[(plan["type"], plan["campaign_id"])] = apply_excluded(args.token, args.login, plan, args.dry_run)

    payload = {
        "mode": "DRY_RUN" if args.dry_run else "APPLY",
        "plans": all_plans,
        "results": list(results.values()),
    }
    text = render_text(all_plans, results, args.dry_run)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_text:
        Path(args.output_text).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if any(result["status"] == "FAIL" for result in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
