#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


PACKAGE_LIKE_RE = re.compile(r"^(?:com|ru|io|net|org|air)\.[a-z0-9_.-]+$", re.IGNORECASE)
DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$", re.IGNORECASE)

DEFAULT_FORMULA = {
    "vpn_block": {"min_clicks": 3, "min_cost": 20.0, "min_ctr": 10.0},
    "retarget_app_block": {"min_clicks": 5, "min_cost": 20.0, "min_ctr": 10.0},
    "prospecting_app_block": {"min_clicks": 8, "min_cost": 60.0, "min_ctr": 12.0},
    "retarget_site_block": {"min_clicks": 3, "min_cost": 35.0, "min_ctr": 5.0},
    "prospecting_site_block": {"min_clicks": 4, "min_cost": 70.0, "min_ctr": 5.0},
}

VPN_HINTS = ("vpn", "proxy", "unblock", "secure")
GAME_HINTS = (
    "game", "games", "puzzle", "match", "solitaire", "mahjong", "craft",
    "simulator", "chess", "checkers", "durak", "bubble", "rope", "birdsort",
    "jigsaw", "coloring", "arrowout", "block", "line98", "deeer", "stress",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve RSYA prefilter tail into deterministic block/keep decisions.")
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--merge-into", type=Path)
    return parser.parse_args()


def load_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def load_rules(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def to_float(value: str | None) -> float:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def normalize(value: str) -> str:
    return str(value or "").strip().casefold()


def is_resolved(row: dict[str, str]) -> bool:
    return bool(str(row.get("assistant_status") or "").strip())


def is_retarget_campaign(campaign_name: str) -> bool:
    text = normalize(campaign_name)
    return "ретаргет" in text or "retarget" in text


def classify_placement(placement: str, rules: dict) -> set[str]:
    placement_norm = normalize(placement)
    labels: set[str] = set()

    if placement_norm in {normalize(item) for item in rules.get("safe_exact_placements", [])}:
        labels.add("exact_safe_block")
    if placement_norm in {normalize(item) for item in rules.get("yandex_root_blocklist", [])}:
        labels.add("yandex_root")
    if any(hint in placement_norm for hint in map(normalize, rules.get("protected_platform_hints", []))):
        labels.add("protected")
    if any(hint in placement_norm for hint in map(normalize, rules.get("yandex_hints", []))):
        labels.add("yandex")

    if PACKAGE_LIKE_RE.match(placement_norm):
        labels.add("app_like")
    elif DOMAIN_RE.match(placement_norm):
        labels.add("site")

    if any(hint in placement_norm for hint in VPN_HINTS):
        labels.add("vpn")
    if any(hint in placement_norm for hint in GAME_HINTS):
        labels.add("game")
    if any(hint in placement_norm for hint in map(normalize, rules.get("content_hints", []))):
        labels.add("content")

    return labels


def block_action(row: dict[str, str]) -> str:
    campaign_name = str(row.get("campaign_name") or "").strip()
    return f"Добавить в список запрещённых площадок кампании `{campaign_name}`."


def keep_action() -> str:
    return "Оставить без изменений."


def merge_decisions(existing_path: Path, new_rows: list[dict[str, str]]) -> None:
    existing_rows: list[dict[str, str]] = []
    fields = ["candidate_id", "assistant_status", "assistant_action", "assistant_reason"]
    if existing_path.exists():
        existing_rows, loaded_fields = load_tsv(existing_path)
        if loaded_fields:
            fields = loaded_fields
    new_by_id = {str(row.get("candidate_id") or "").strip(): row for row in new_rows if str(row.get("candidate_id") or "").strip()}
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in existing_rows:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id in new_by_id:
            merged.append(new_by_id[candidate_id])
            seen.add(candidate_id)
        else:
            merged.append(row)
            if candidate_id:
                seen.add(candidate_id)
    for candidate_id, row in new_by_id.items():
        if candidate_id not in seen:
            merged.append(row)
    write_tsv(existing_path, merged, fields)


def choose_branch(row: dict[str, str], labels: set[str], formula: dict) -> tuple[str, str, str]:
    clicks = to_float(row.get("clicks"))
    cost = to_float(row.get("cost"))
    ctr = to_float(row.get("ctr"))
    conversions = to_float(row.get("conversions"))
    placement = str(row.get("placement") or "").strip()
    campaign_name = str(row.get("campaign_name") or "").strip()
    retarget = is_retarget_campaign(campaign_name)

    if conversions > 0:
        return (
            "keep_monitor",
            keep_action(),
            "По этой площадке уже есть конверсии. Автоформула не даёт её блокировать.",
        )

    if labels & {"protected", "yandex", "yandex_root"}:
        return (
            "keep_monitor",
            keep_action(),
            "Protected/Yandex inventory держу в monitor-режиме. Формула не делает blind-stop по этой ветке.",
        )

    if "exact_safe_block" in labels:
        return (
            "manual_block_ready",
            block_action(row),
            "Площадка входит в подтверждённый exact safe blocklist клиента. Формула переводит её сразу в block-ready.",
        )

    if "vpn" in labels:
        cfg = formula["vpn_block"]
        if clicks >= cfg["min_clicks"] or cost >= cfg["min_cost"] or (clicks >= 2 and ctr >= cfg["min_ctr"]):
            return (
                "manual_block_ready",
                block_action(row),
                f"VPN/proxy-инвентарь без конверсий. Формула: clicks >= {cfg['min_clicks']}, cost >= {cfg['min_cost']:.2f} или clicks >= 2 при CTR >= {cfg['min_ctr']:.2f}.",
            )
        return (
            "keep_monitor",
            keep_action(),
            "VPN/proxy-инвентарь ещё короткий по собственному сигналу; оставляю в monitor-слое.",
        )

    if "app_like" in labels:
        cfg = formula["retarget_app_block" if retarget else "prospecting_app_block"]
        if clicks >= cfg["min_clicks"] or cost >= cfg["min_cost"] or (clicks >= 3 and ctr >= cfg["min_ctr"]):
            branch = "ретаргет" if retarget else "поиск новой аудитории"
            return (
                "manual_block_ready",
                block_action(row),
                f"App-like инвентарь без конверсий. Формула {branch}: clicks >= {cfg['min_clicks']}, cost >= {cfg['min_cost']:.2f} или clicks >= 3 при CTR >= {cfg['min_ctr']:.2f}.",
            )
        return (
            "keep_monitor",
            keep_action(),
            "App-like инвентарь пока ниже порога formula-v3; строка остаётся в monitor-слое, не идёт в stop-pack.",
        )

    if labels & {"site", "content", "game"}:
        cfg = formula["retarget_site_block" if retarget else "prospecting_site_block"]
        if (clicks >= cfg["min_clicks"] and cost >= cfg["min_cost"]) or (clicks >= max(cfg["min_clicks"], 3) and ctr >= cfg["min_ctr"]):
            branch = "ретаргет" if retarget else "новая аудитория"
            return (
                "manual_block_ready",
                block_action(row),
                f"Site/content inventory без конверсий. Формула {branch}: clicks >= {cfg['min_clicks']} и cost >= {cfg['min_cost']:.2f}, либо clicks >= {max(cfg['min_clicks'], 3)} при CTR >= {cfg['min_ctr']:.2f}.",
            )
        return (
            "keep_monitor",
            keep_action(),
            "Site/content inventory ещё ниже порога formula-v3; оставляю под мониторинг.",
        )

    return (
        "keep_monitor",
        keep_action(),
        f"Placement `{placement}` не попал в риск-класс formula-v3; оставляю под мониторинг.",
    )


def main() -> int:
    args = parse_args()
    queue_rows, queue_fields = load_tsv(args.queue.expanduser().resolve())
    rules = load_rules(args.rules.expanduser().resolve() if args.rules else None)
    formula = dict(DEFAULT_FORMULA)
    formula.update((rules.get("tail_formula_v3") or {}))
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    decision_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    unresolved_rows: list[dict[str, str]] = []

    audit_fields = queue_fields + ["formula_labels", "formula_branch", "formula_reason"]

    for row in queue_rows:
        if is_resolved(row):
            continue
        labels = classify_placement(str(row.get("placement") or ""), rules)
        branch, action, reason = choose_branch(row, labels, formula)
        annotated = dict(row)
        annotated["formula_labels"] = ",".join(sorted(labels))
        annotated["formula_branch"] = branch
        annotated["formula_reason"] = reason
        audit_rows.append(annotated)
        if branch not in {"manual_block_ready", "keep_monitor"}:
            unresolved_rows.append(dict(row))
            continue
        decision_rows.append(
            {
                "candidate_id": row.get("candidate_id", ""),
                "assistant_status": "approve",
                "assistant_action": action,
                "assistant_reason": reason,
            }
        )

    decisions_path = output_dir / "rsya_formula_v3_decisions.tsv"
    audit_path = output_dir / "rsya_formula_v3_audit.tsv"
    unresolved_path = output_dir / "rsya_formula_v3_unresolved.tsv"
    write_tsv(decisions_path, decision_rows, ["candidate_id", "assistant_status", "assistant_action", "assistant_reason"])
    write_tsv(audit_path, audit_rows, audit_fields)
    write_tsv(unresolved_path, unresolved_rows, queue_fields)

    if args.merge_into:
        merge_decisions(args.merge_into.expanduser().resolve(), decision_rows)

    summary = {
        "queue": str(args.queue.expanduser().resolve()),
        "rules": str(args.rules.expanduser().resolve()) if args.rules else None,
        "decision_rows": len(decision_rows),
        "block_ready_rows": sum(1 for row in audit_rows if row["formula_branch"] == "manual_block_ready"),
        "keep_monitor_rows": sum(1 for row in audit_rows if row["formula_branch"] == "keep_monitor"),
        "unresolved_rows": len(unresolved_rows),
    }
    (output_dir / "rsya_formula_v3_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
