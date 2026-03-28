#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


RULE_FIELDS = [
    "rule_id",
    "rule_source",
    "decision",
    "marker_kind",
    "match_mode",
    "marker_norm",
    "marker_display",
    "scope_level",
    "campaign_id",
    "ad_group_name",
    "ad_group_name_regex",
    "include_pattern",
    "exclude_pattern",
    "assistant_action",
    "assistant_reason",
    "source_reference",
]

TOKEN_RE = re.compile(r"[a-zа-яё0-9-]+", re.IGNORECASE)
COMMON_RUSSIAN_ENDINGS = [
    "иями", "ями", "ами", "его", "ого", "ему", "ому", "ыми", "ими", "иях", "ях", "ах",
    "ию", "ью", "ия", "ья", "ие", "ье", "ий", "ый", "ой", "ая", "яя", "ое", "ее", "ые", "ие",
    "ым", "им", "ом", "ем", "ую", "юю", "ов", "ев", "ей", "ам", "ям", "ы", "и", "а", "я", "е", "о", "у", "ю",
]

DECISION_PRIORITY = {
    "growth": 0,
    "hold": 1,
    "exclude": 2,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply reviewed Search marker cards to queue rows.")
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--cards", required=True, type=Path)
    parser.add_argument("--marker-decisions", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--merge-into", type=Path)
    parser.add_argument("--base-rules", type=Path)
    parser.add_argument("--output-combined-rules", type=Path)
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


def normalize_text(value: str) -> str:
    lowered = (value or "").strip().casefold().replace("ё", "е")
    lowered = re.sub(r"[^0-9a-zа-я_-]+", " ", lowered)
    return " ".join(lowered.split())


def token_surface(value: str) -> list[str]:
    return [token.casefold().replace("ё", "е") for token in TOKEN_RE.findall(value or "")]


def light_stem(token: str) -> str:
    token = normalize_text(token).replace(" ", "")
    if len(token) <= 4 or re.fullmatch(r"\d+", token):
        return token
    for ending in COMMON_RUSSIAN_ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 4:
            return token[: -len(ending)]
    return token


def extract_token_stems(text: str) -> set[str]:
    return {light_stem(token) for token in token_surface(text) if token}


def build_row_phrase_stems(text: str, max_len: int = 3) -> set[str]:
    surfaces = token_surface(text)
    phrases: set[str] = set()
    for size in range(2, max_len + 1):
        for idx in range(0, len(surfaces) - size + 1):
            window = surfaces[idx : idx + size]
            if any(len(token) < 2 for token in window):
                continue
            stems = [light_stem(token) for token in window]
            phrases.add(" ".join(stems))
    return phrases


def candidate_resolved(row: dict[str, str]) -> bool:
    return bool((row.get("assistant_status") or "").strip())


def merge_decisions(existing_path: Path, new_rows: list[dict[str, str]]) -> None:
    new_by_id = {str(row.get("candidate_id") or "").strip(): row for row in new_rows if str(row.get("candidate_id") or "").strip()}
    existing_rows: list[dict[str, str]] = []
    existing_fields = ["candidate_id", "assistant_status", "assistant_action", "assistant_reason"]
    if existing_path.exists():
        existing_rows, loaded_fields = load_tsv(existing_path)
        if loaded_fields:
            existing_fields = loaded_fields
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
        if candidate_id in seen:
            continue
        merged.append(row)
    write_tsv(existing_path, merged, existing_fields)


def build_rule_row(**kwargs: str) -> dict[str, str]:
    row = {field: "" for field in RULE_FIELDS}
    for key, value in kwargs.items():
        if key in row:
            row[key] = value
    return row


def load_marker_rules(cards: list[dict[str, str]], decisions: list[dict[str, str]]) -> list[dict[str, str]]:
    cards_by_id = {row["marker_id"]: row for row in cards}
    rules: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in decisions:
        marker_id = str(row.get("marker_id") or "").strip()
        decision = str(row.get("decision") or "").strip().lower()
        action = str(row.get("assistant_action") or "").strip()
        reason = str(row.get("assistant_reason") or "").strip()
        if not marker_id or decision not in DECISION_PRIORITY or not action or not reason:
            continue
        card = cards_by_id.get(marker_id)
        if not card:
            raise SystemExit(f"Marker decision references unknown marker_id: {marker_id}")
        if marker_id in seen:
            raise SystemExit(f"Duplicate marker decision for marker_id: {marker_id}")
        seen.add(marker_id)
        marker_kind = str(card.get("marker_kind") or "").strip().lower()
        match_mode = "phrase_stem" if marker_kind == "phrase" else "token_stem"
        rule_decision = {
            "exclude": "exclude",
            "growth": "park_growth",
            "hold": "park_hold",
        }[decision]
        rules.append(
            build_rule_row(
                rule_id=f"marker-review:{marker_id}",
                rule_source="marker_review.manual",
                decision=rule_decision,
                marker_kind=marker_kind,
                match_mode=match_mode,
                marker_norm=str(card.get("marker_norm") or "").strip(),
                marker_display=str(card.get("marker_display") or "").strip(),
                scope_level="adgroup",
                campaign_id=str(card.get("campaign_id") or "").strip(),
                ad_group_name=str(card.get("ad_group_name") or "").strip(),
                assistant_action=action,
                assistant_reason=reason,
                source_reference=marker_id,
            )
        )
    return rules


def choose_match(matches: list[dict[str, str]]) -> dict[str, str]:
    def sort_key(rule: dict[str, str]) -> tuple[int, int, int, str]:
        decision = str(rule.get("decision") or "")
        marker_kind = str(rule.get("marker_kind") or "")
        marker_norm = str(rule.get("marker_norm") or "")
        return (
            0 if marker_kind == "phrase" else 1,
            -len(marker_norm),
            DECISION_PRIORITY.get(
                {
                    "park_growth": "growth",
                    "park_hold": "hold",
                    "exclude": "exclude",
                }.get(decision, "exclude"),
                9,
            ),
            str(rule.get("rule_id") or ""),
        )
    return sorted(matches, key=sort_key)[0]


def rule_matches_row(rule: dict[str, str], row: dict[str, str]) -> bool:
    if str(rule.get("campaign_id") or "").strip() and str(row.get("campaign_id") or "").strip() != str(rule.get("campaign_id") or "").strip():
        return False
    if normalize_text(row.get("ad_group_name") or "") != normalize_text(rule.get("ad_group_name") or ""):
        return False
    query = row.get("query") or ""
    marker_kind = str(rule.get("marker_kind") or "").strip()
    marker_norm = str(rule.get("marker_norm") or "").strip()
    if marker_kind == "phrase":
        return marker_norm in build_row_phrase_stems(query)
    if marker_kind == "token":
        return marker_norm in extract_token_stems(query)
    return False


def rule_to_decision_row(rule: dict[str, str], row: dict[str, str]) -> dict[str, str]:
    return {
        "candidate_id": row.get("candidate_id", ""),
        "assistant_status": "approve",
        "assistant_action": str(rule.get("assistant_action") or "").strip(),
        "assistant_reason": str(rule.get("assistant_reason") or "").strip(),
    }


def main() -> int:
    args = parse_args()
    queue_rows, queue_fields = load_tsv(args.queue.expanduser().resolve())
    card_rows, card_fields = load_tsv(args.cards.expanduser().resolve())
    decision_rows, _ = load_tsv(args.marker_decisions.expanduser().resolve())
    args.output_dir = args.output_dir.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    marker_rules = load_marker_rules(card_rows, decision_rows)
    marker_rule_path = args.output_dir / "search_marker_review_rules.tsv"
    write_tsv(marker_rule_path, marker_rules, RULE_FIELDS)

    combined_rules: list[dict[str, str]] = []
    if args.base_rules:
        base_rows, _ = load_tsv(args.base_rules.expanduser().resolve())
        combined_rules.extend(base_rows)
    combined_rules.extend(marker_rules)
    if args.output_combined_rules:
        write_tsv(args.output_combined_rules.expanduser().resolve(), combined_rules, RULE_FIELDS)

    active_rows: list[dict[str, str]] = []
    excluded_rows: list[dict[str, str]] = []
    growth_rows: list[dict[str, str]] = []
    hold_rows: list[dict[str, str]] = []
    decision_out: list[dict[str, str]] = []

    audit_fields = queue_fields + ["matched_rule_id", "matched_rule_source", "matched_rule_decision", "matched_action", "matched_reason"]

    for row in queue_rows:
        if candidate_resolved(row):
            active_rows.append(dict(row))
            continue
        matches = [rule for rule in marker_rules if rule_matches_row(rule, row)]
        if not matches:
            active_rows.append(dict(row))
            continue
        chosen = choose_match(matches)
        bucketed = dict(row)
        bucketed["matched_rule_id"] = chosen.get("rule_id", "")
        bucketed["matched_rule_source"] = chosen.get("rule_source", "")
        bucketed["matched_rule_decision"] = chosen.get("decision", "")
        bucketed["matched_action"] = chosen.get("assistant_action", "")
        bucketed["matched_reason"] = chosen.get("assistant_reason", "")
        decision_value = str(chosen.get("decision") or "").strip()
        if decision_value == "exclude":
            excluded_rows.append(bucketed)
        elif decision_value == "park_growth":
            growth_rows.append(bucketed)
        else:
            hold_rows.append(bucketed)
        decision_out.append(rule_to_decision_row(chosen, row))

    decisions_path = args.output_dir / "search_marker_review_decisions.tsv"
    write_tsv(decisions_path, decision_out, ["candidate_id", "assistant_status", "assistant_action", "assistant_reason"])
    write_tsv(args.output_dir / "search_marker_review_active.tsv", active_rows, queue_fields)
    write_tsv(args.output_dir / "search_marker_review_excluded.tsv", excluded_rows, audit_fields)
    write_tsv(args.output_dir / "search_marker_review_growth.tsv", growth_rows, audit_fields)
    write_tsv(args.output_dir / "search_marker_review_hold.tsv", hold_rows, audit_fields)

    if args.merge_into:
        merge_decisions(args.merge_into.expanduser().resolve(), decision_out)

    summary = {
        "queue": str(args.queue.expanduser().resolve()),
        "cards": str(args.cards.expanduser().resolve()),
        "marker_decisions": str(args.marker_decisions.expanduser().resolve()),
        "marker_rules": str(marker_rule_path),
        "decision_rows": len(decision_out),
        "excluded_rows": len(excluded_rows),
        "growth_rows": len(growth_rows),
        "hold_rows": len(hold_rows),
        "remaining_active_rows": len([row for row in active_rows if not candidate_resolved(row)]),
    }
    (args.output_dir / "search_marker_review_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
