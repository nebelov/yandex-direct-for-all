#!/usr/bin/env python3
"""Apply a prepared search-negatives pack against live adgroup negatives with read-back."""

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


def build_apply_plan(pack: dict, live_map: dict[int, dict]) -> tuple[list[dict], list[dict]]:
    ready_ops: list[dict] = []
    blocked_ops: list[dict] = []
    for op in list(pack.get("operations") or []):
        adgroup_id = int(op.get("adgroup_id") or 0)
        live_row = live_map.get(adgroup_id)
        if not live_row:
            blocked_ops.append({**op, "status": "FAIL", "reason": "adgroup_missing_in_live_read"})
            continue
        before_items = list(op.get("before_keywords") or [])
        live_items = get_negative_keywords(live_row)
        before_keys = {soft_phrase_key(item) for item in before_items if soft_phrase_key(item)}
        live_keys = {soft_phrase_key(item) for item in live_items if soft_phrase_key(item)}
        if before_keys != live_keys:
            blocked_ops.append(
                {
                    **op,
                    "status": "FAIL",
                    "reason": "drift_detected",
                    "drift_missing_from_live": sorted(before_keys - live_keys)[:20],
                    "drift_extra_in_live": sorted(live_keys - before_keys)[:20],
                }
            )
            continue
        add_items = [str(item).strip() for item in list(op.get("phrases_to_add") or op.get("keywords_to_add") or []) if str(item).strip()]
        final_after = merge_after(live_items, add_items)
        ready_ops.append({**op, "live_items": live_items, "after_keywords": final_after})
    return ready_ops, blocked_ops


def apply_updates(token: str, login: str, ready_ops: list[dict]) -> list[dict]:
    item_errors: list[dict] = []
    for start in range(0, len(ready_ops), 50):
        batch = ready_ops[start : start + 50]
        result = api_call(
            token,
            login,
            "adgroups",
            "update",
            {
                "AdGroups": [
                    {"Id": int(row["adgroup_id"]), "NegativeKeywords": {"Items": list(row["after_keywords"])}}
                    for row in batch
                ]
            },
        )
        for row, outcome in zip(batch, result.get("result", {}).get("UpdateResults", result.get("UpdateResults", [])) or []):
            errors = list(outcome.get("Errors") or [])
            if not errors:
                continue
            item_errors.append(
                {
                    "campaign_id": int(row.get("campaign_id") or 0),
                    "campaign_name": str(row.get("campaign_name") or ""),
                    "adgroup_id": int(row.get("adgroup_id") or 0),
                    "adgroup_name": str(row.get("adgroup_name") or ""),
                    "phrases_to_add": list(row.get("phrases_to_add") or row.get("keywords_to_add") or []),
                    "errors": errors,
                }
            )
    return item_errors


def verify_readback(ready_ops: list[dict], live_map: dict[int, dict]) -> list[dict]:
    missing_rows: list[dict] = []
    for row in ready_ops:
        live_row = live_map.get(int(row.get("adgroup_id") or 0)) or {}
        current_soft = {soft_phrase_key(item) for item in get_negative_keywords(live_row) if soft_phrase_key(item)}
        for phrase in list(row.get("phrases_to_add") or row.get("keywords_to_add") or []):
            soft = soft_phrase_key(phrase)
            if soft and soft not in current_soft:
                missing_rows.append(
                    {
                        "campaign_id": int(row.get("campaign_id") or 0),
                        "campaign_name": str(row.get("campaign_name") or ""),
                        "adgroup_id": int(row.get("adgroup_id") or 0),
                        "adgroup_name": str(row.get("adgroup_name") or ""),
                        "negative_keyword": str(phrase),
                    }
                )
    return missing_rows


def render_text(summary: dict, blocked_ops: list[dict], item_errors: list[dict], missing_rows: list[dict]) -> str:
    lines = [
        "MODE\tAPPLY",
        f"STATUS\t{summary['status']}",
        f"UPDATED_ADGROUPS\t{summary['updated_adgroup_count']}",
        f"AFFECTED_CAMPAIGNS\t{summary['affected_campaign_count']}",
        f"ADD_COUNT\t{summary['applied_add_count']}",
        f"DRIFT_BLOCKED\t{summary['drift_blocked_count']}",
        f"ITEM_ERROR_COUNT\t{summary['item_error_count']}",
        f"READBACK_MISSING\t{summary['readback_missing_count']}",
    ]
    for row in blocked_ops[:30]:
        lines.append(f"BLOCKED\t{row.get('campaign_name')} / {row.get('adgroup_name')} / {row.get('reason')}")
    for row in item_errors[:30]:
        lines.append(f"ERROR\t{row.get('campaign_name')} / {row.get('adgroup_name')} / {row.get('errors')}")
    for row in missing_rows[:30]:
        lines.append(f"MISSING\t{row.get('campaign_name')} / {row.get('adgroup_name')} / {row.get('negative_keyword')}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a prepared search-negatives pack against live negatives.")
    parser.add_argument("--token", required=True)
    parser.add_argument("--login", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-text", default="")
    args = parser.parse_args()

    pack = load_pack(args.pack)
    adgroup_ids = sorted({int(row.get("adgroup_id") or 0) for row in list(pack.get("operations") or []) if int(row.get("adgroup_id") or 0)})
    live_before = fetch_adgroups(args.token, args.login, adgroup_ids)
    ready_ops, blocked_ops = build_apply_plan(pack, live_before)
    item_errors = apply_updates(args.token, args.login, ready_ops) if ready_ops else []
    live_after = fetch_adgroups(args.token, args.login, [int(row.get("adgroup_id") or 0) for row in ready_ops]) if ready_ops else {}
    missing_rows = verify_readback(ready_ops, live_after)
    status = "ready"
    if blocked_ops or item_errors or missing_rows:
        status = "partial" if ready_ops and not item_errors and not missing_rows else "blocked"
    summary = {
        "status": status,
        "pack_kind": str(pack.get("pack_kind") or "search_negatives"),
        "affected_campaign_count": len({int(row.get("campaign_id") or 0) for row in ready_ops if int(row.get("campaign_id") or 0)}),
        "updated_adgroup_count": len(ready_ops),
        "applied_add_count": sum(len(list(row.get("phrases_to_add") or row.get("keywords_to_add") or [])) for row in ready_ops),
        "drift_blocked_count": len(blocked_ops),
        "item_error_count": len(item_errors),
        "readback_missing_count": len(missing_rows),
    }
    payload = {
        "mode": "APPLY",
        "summary": summary,
        "blocked_ops": blocked_ops,
        "item_errors": item_errors,
        "missing_rows": missing_rows,
    }
    text = render_text(summary, blocked_ops, item_errors, missing_rows)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_text:
        Path(args.output_text).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if status == "blocked":
        sys.exit(1)


if __name__ == "__main__":
    main()
