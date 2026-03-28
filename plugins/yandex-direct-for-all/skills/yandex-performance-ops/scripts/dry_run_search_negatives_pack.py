#!/usr/bin/env python3
"""Dry-run a prepared search-negatives apply pack against live adgroup negatives."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_V501 = "https://api.direct.yandex.com/json/v501"

_SOFT_SUFFIXES = (
    "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "ую", "юю",
    "ой", "ей", "ий", "ый", "ая", "яя", "ое", "ее", "ом", "ем", "ах", "ях",
    "ам", "ям", "ы", "и", "а", "я", "е", "у", "ю", "о",
)


def api_call(token: str, login: str, service: str, method: str, params: dict) -> dict:
    req = urllib.request.Request(
        f"{API_V501}/{service}",
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


def load_pack(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def soft_token(value: str) -> str:
    token = re.sub(r"^[!+]+", "", value.strip()).casefold().replace("ё", "е")
    token = re.sub(r"[^0-9a-zа-я_-]+", "", token)
    if len(token) <= 4:
        return token
    for suffix in _SOFT_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def soft_phrase_key(value: object) -> str:
    tokens: list[str] = []
    for raw in re.split(r"\s+", str(value or "").strip()):
        token = soft_token(raw)
        if token:
            tokens.append(token)
    return " ".join(sorted(tokens))


def get_negative_keywords(row: dict) -> list[str]:
    raw = row.get("NegativeKeywords") or {}
    if isinstance(raw, dict):
        items = raw.get("Items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    result: list[str] = []
    for item in items:
        phrase = " ".join(str(item or "").split()).strip()
        if phrase and phrase not in result:
            result.append(phrase)
    return result


def fetch_adgroups(token: str, login: str, adgroup_ids: list[int]) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for start in range(0, len(adgroup_ids), 200):
        batch = adgroup_ids[start : start + 200]
        payload = api_call(
            token,
            login,
            "adgroups",
            "get",
            {
                "SelectionCriteria": {"Ids": batch},
                "FieldNames": ["Id", "CampaignId", "Name", "NegativeKeywords"],
            },
        )
        for row in payload.get("result", {}).get("AdGroups", payload.get("AdGroups", [])) or []:
            adgroup_id = int(row.get("Id") or 0)
            if adgroup_id:
                result[adgroup_id] = row
    return result


def merge_after(live_items: list[str], add_items: list[str]) -> list[str]:
    merged = list(live_items)
    merged_keys = {soft_phrase_key(item) for item in live_items if soft_phrase_key(item)}
    for phrase in add_items:
        key = soft_phrase_key(phrase)
        if not key or key in merged_keys:
            continue
        merged.append(phrase)
        merged_keys.add(key)
    return merged


def build_results(pack: dict, live_map: dict[int, dict]) -> tuple[list[dict], dict]:
    results: list[dict] = []
    total_add_count = 0
    total_skip_existing = 0
    drift_count = 0
    failure_count = 0
    for op in list(pack.get("operations") or []):
        adgroup_id = int(op.get("adgroup_id") or 0)
        live_row = live_map.get(adgroup_id)
        if not live_row:
            results.append(
                {
                    "campaign_id": int(op.get("campaign_id") or 0),
                    "campaign_name": str(op.get("campaign_name") or ""),
                    "adgroup_id": adgroup_id,
                    "adgroup_name": str(op.get("adgroup_name") or ""),
                    "status": "FAIL",
                    "reason": "adgroup_missing_in_live_read",
                }
            )
            failure_count += 1
            continue
        before_items = list(op.get("before_keywords") or [])
        live_items = get_negative_keywords(live_row)
        before_keys = {soft_phrase_key(item) for item in before_items if soft_phrase_key(item)}
        live_keys = {soft_phrase_key(item) for item in live_items if soft_phrase_key(item)}
        drift = before_keys != live_keys
        if drift:
            drift_count += 1
        add_items = [str(item).strip() for item in list(op.get("phrases_to_add") or op.get("keywords_to_add") or []) if str(item).strip()]
        already_present: list[str] = []
        new_add: list[str] = []
        for phrase in add_items:
            key = soft_phrase_key(phrase)
            if not key:
                continue
            if key in live_keys:
                already_present.append(phrase)
            else:
                new_add.append(phrase)
        total_add_count += len(new_add)
        total_skip_existing += len(already_present)
        after_items = merge_after(live_items, new_add)
        status = "FAIL" if drift else ("SKIP" if not new_add else "DRY_RUN")
        if status == "FAIL":
            failure_count += 1
        results.append(
            {
                "campaign_id": int(op.get("campaign_id") or 0),
                "campaign_name": str(op.get("campaign_name") or ""),
                "adgroup_id": adgroup_id,
                "adgroup_name": str(op.get("adgroup_name") or ""),
                "status": status,
                "drift": drift,
                "baseline_count": len(before_items),
                "live_count": len(live_items),
                "new_add_count": len(new_add),
                "skip_existing_count": len(already_present),
                "after_count": len(after_items),
                "new_add_items": new_add,
                "already_present_items": already_present,
                "drift_missing_from_live": sorted(before_keys - live_keys)[:20],
                "drift_extra_in_live": sorted(live_keys - before_keys)[:20],
            }
        )
    summary = {
        "status": "blocked" if failure_count else "ready",
        "pack_kind": str(pack.get("pack_kind") or "search_negatives"),
        "affected_campaign_count": len({int(row.get("campaign_id") or 0) for row in results if int(row.get("campaign_id") or 0)}),
        "affected_adgroup_count": len(results),
        "drift_count": drift_count,
        "failure_count": failure_count,
        "dry_run_add_count": total_add_count,
        "skip_existing_count": total_skip_existing,
    }
    return results, summary


def render_text(pack: dict, results: list[dict], summary: dict) -> str:
    lines = [
        "MODE\tDRY_RUN",
        f"STATUS\t{summary['status']}",
        f"AFFECTED_CAMPAIGNS\t{summary['affected_campaign_count']}",
        f"AFFECTED_ADGROUPS\t{summary['affected_adgroup_count']}",
        f"DRIFT_COUNT\t{summary['drift_count']}",
        f"DRY_RUN_ADD_COUNT\t{summary['dry_run_add_count']}",
        f"SKIP_EXISTING_COUNT\t{summary['skip_existing_count']}",
    ]
    for row in results:
        lines.append(
            f"\n=== campaign={row['campaign_id']} {row['campaign_name']} / "
            f"adgroup={row['adgroup_id']} {row['adgroup_name']} ==="
        )
        lines.append(f"RESULT\t{row['status']}")
        if row.get("drift"):
            lines.append("DRIFT\ttrue")
            if row.get("drift_missing_from_live"):
                lines.append(f"DRIFT_MISSING\t{', '.join(row['drift_missing_from_live'])}")
            if row.get("drift_extra_in_live"):
                lines.append(f"DRIFT_EXTRA\t{', '.join(row['drift_extra_in_live'])}")
        if row.get("new_add_items"):
            lines.append(f"ADD_ITEMS\t{', '.join(row['new_add_items'])}")
        if row.get("already_present_items"):
            lines.append(f"ALREADY_PRESENT\t{', '.join(row['already_present_items'])}")
        for field in ("baseline_count", "live_count", "new_add_count", "skip_existing_count", "after_count"):
            lines.append(f"{field.upper()}\t{row.get(field)}")
        if row.get("reason"):
            lines.append(f"REASON\t{row['reason']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run a prepared search-negatives pack against live negatives.")
    parser.add_argument("--token", required=True)
    parser.add_argument("--login", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-text", default="")
    args = parser.parse_args()

    pack = load_pack(args.pack)
    adgroup_ids = sorted({int(row.get("adgroup_id") or 0) for row in list(pack.get("operations") or []) if int(row.get("adgroup_id") or 0)})
    live_map = fetch_adgroups(args.token, args.login, adgroup_ids)
    results, summary = build_results(pack, live_map)
    payload = {
        "mode": "DRY_RUN",
        "pack": {
            "pack_kind": pack.get("pack_kind"),
            "affected_campaign_count": pack.get("affected_campaign_count"),
            "affected_adgroup_count": pack.get("affected_adgroup_count"),
            "negative_phrase_count": pack.get("negative_phrase_count"),
            "stop_word_count": pack.get("stop_word_count"),
        },
        "summary": summary,
        "results": results,
    }
    text = render_text(pack, results, summary)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_text:
        Path(args.output_text).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if summary["status"] != "ready":
        sys.exit(1)


if __name__ == "__main__":
    main()
