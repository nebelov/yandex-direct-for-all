#!/usr/bin/env python3
"""Propagate manual-approved Search decisions by exact, scope-safe rules.

This script is intentionally conservative:
- it never invents new actions;
- it derives reusable rules only from already-approved manual decisions;
- it applies rules only inside the same ad group name scope;
- it supports four deterministic rule kinds:
  1) exact query match inside the same ad group name;
  2) exact single-word stop-word token;
  3) exact phrase-minus substring;
  4) exact growth token/phrase from explicitly approved growth actions;
- it writes a rulebook, auto-applied decisions, remaining rows, and conflicts.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


STOP_WORD_RE = re.compile(r"стоп-слово `([^`]+)`", re.IGNORECASE)
PHRASE_MINUS_RE = re.compile(r"фразовый минус `([^`]+)`", re.IGNORECASE)
GROWTH_RE = re.compile(r"(?:growth-тест|Выделить) `([^`]+)`", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-zа-яё0-9-]+", re.IGNORECASE)
FUNCTION_WORDS = {
    "а",
    "без",
    "в",
    "во",
    "где",
    "для",
    "до",
    "и",
    "из",
    "или",
    "как",
    "к",
    "ко",
    "ли",
    "на",
    "над",
    "не",
    "но",
    "о",
    "об",
    "от",
    "по",
    "под",
    "при",
    "про",
    "с",
    "со",
    "у",
    "что",
    "это",
}


def load_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def normalize_text(value: str) -> str:
    lowered = (value or "").casefold().replace("ё", "е")
    lowered = re.sub(r"[^0-9a-zа-я_-]+", " ", lowered)
    return " ".join(lowered.split()).strip()


def normalize_token(value: str) -> str:
    token = normalize_text(value).replace(" ", "")
    return token


def tokenize_text(value: str) -> list[str]:
    return [normalize_token(token) for token in TOKEN_RE.findall(value or "")]


def content_token_count(value: str) -> int:
    return sum(1 for token in normalize_text(value).split() if token and token not in FUNCTION_WORDS)


def is_phrase_rule_safe(value: str) -> bool:
    normalized = normalize_text(value)
    tokens = normalized.split()
    if len(tokens) < 2:
        return False
    return content_token_count(normalized) >= 2


def parse_candidate_id(candidate_id: str) -> tuple[str, str, str]:
    parts = (candidate_id or "").split("||", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


def decision_has_verdict(row: dict[str, str]) -> bool:
    return bool((row.get("assistant_status") or "").strip())


def load_decision_overrides(paths: list[Path]) -> dict[str, dict[str, str]]:
    overrides: dict[str, dict[str, str]] = {}
    for path in paths:
        for row in load_tsv(path):
            candidate_id = (row.get("candidate_id") or "").strip()
            if not candidate_id:
                continue
            overrides[candidate_id] = row
    return overrides


def apply_decision_overrides(
    queue_rows: list[dict[str, str]],
    overrides: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row in queue_rows:
        candidate_id = (row.get("candidate_id") or "").strip()
        merged = dict(row)
        override = overrides.get(candidate_id)
        if override:
            for field in ("assistant_status", "assistant_action", "assistant_reason"):
                merged[field] = (override.get(field) or merged.get(field) or "").strip()
        result.append(merged)
    return result


def normalize_float(value: str) -> float:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def collapse_queue_rows(queue_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    by_id: dict[str, dict[str, str]] = {}
    duplicate_count = 0
    for row in queue_rows:
        candidate_id = (row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        current = by_id.get(candidate_id)
        if current is None:
            by_id[candidate_id] = dict(row)
            continue
        duplicate_count += 1
        current_resolved = decision_has_verdict(current)
        candidate_resolved = decision_has_verdict(row)
        if candidate_resolved != current_resolved:
            by_id[candidate_id] = dict(row) if candidate_resolved else current
            continue
        current_score = (
            normalize_float(current.get("cost", "")),
            normalize_float(current.get("clicks", "")),
            normalize_float(current.get("impressions", "")),
            len((current.get("criterion") or "").strip()),
        )
        candidate_score = (
            normalize_float(row.get("cost", "")),
            normalize_float(row.get("clicks", "")),
            normalize_float(row.get("impressions", "")),
            len((row.get("criterion") or "").strip()),
        )
        if candidate_score > current_score:
            by_id[candidate_id] = dict(row)
    return list(by_id.values()), duplicate_count


def build_rule_row(
    *,
    rule_kind: str,
    scope_ad_group_name: str,
    match_value: str,
    display_match_value: str,
    source_candidate_id: str,
    source_status: str,
    source_action: str,
    source_reason: str,
    source_file: str,
) -> dict[str, str]:
    _, source_group, source_query = parse_candidate_id(source_candidate_id)
    return {
        "rule_kind": rule_kind,
        "scope_ad_group_name": scope_ad_group_name.strip(),
        "match_value": match_value.strip(),
        "display_match_value": display_match_value.strip(),
        "source_candidate_id": source_candidate_id.strip(),
        "source_ad_group_name": source_group.strip(),
        "source_query": source_query.strip(),
        "assistant_status": source_status.strip(),
        "assistant_action": source_action.strip(),
        "assistant_reason": source_reason.strip(),
        "source_file": source_file,
    }


def extract_rule_candidates(decision_paths: list[Path]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    candidates: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for path in decision_paths:
        for row in load_tsv(path):
            if not decision_has_verdict(row):
                continue
            candidate_id = (row.get("candidate_id") or "").strip()
            if not candidate_id:
                continue
            _campaign_id, source_group, source_query = parse_candidate_id(candidate_id)
            status = (row.get("assistant_status") or "").strip()
            action = (row.get("assistant_action") or "").strip()
            reason = (row.get("assistant_reason") or "").strip()
            source_file = str(path)
            if not source_group:
                skipped.append(
                    {
                        "candidate_id": candidate_id,
                        "skip_reason": "missing_ad_group_name_in_candidate_id",
                        "source_file": source_file,
                    }
                )
                continue

            if source_query:
                normalized_query = normalize_text(source_query)
                if normalized_query:
                    candidates.append(
                        build_rule_row(
                            rule_kind="exact_query",
                            scope_ad_group_name=source_group,
                            match_value=normalized_query,
                            display_match_value=source_query,
                            source_candidate_id=candidate_id,
                            source_status=status,
                            source_action=action,
                            source_reason=reason,
                            source_file=source_file,
                        )
                    )

            stop_matches = STOP_WORD_RE.findall(action)
            for word in stop_matches:
                normalized_word = normalize_token(word)
                if not normalized_word or " " in normalize_text(word):
                    continue
                candidates.append(
                    build_rule_row(
                        rule_kind="stop_word_token",
                        scope_ad_group_name=source_group,
                        match_value=normalized_word,
                        display_match_value=word,
                        source_candidate_id=candidate_id,
                        source_status=status,
                        source_action=action,
                        source_reason=reason,
                        source_file=source_file,
                    )
                )

            for phrase in PHRASE_MINUS_RE.findall(action):
                normalized_phrase = normalize_text(phrase)
                if not normalized_phrase:
                    continue
                if not is_phrase_rule_safe(phrase):
                    skipped.append(
                        {
                            "candidate_id": candidate_id,
                            "skip_reason": f"phrase_minus_too_broad:{phrase}",
                            "source_file": source_file,
                        }
                    )
                    continue
                candidates.append(
                    build_rule_row(
                        rule_kind="phrase_minus_exact",
                        scope_ad_group_name=source_group,
                        match_value=normalized_phrase,
                        display_match_value=phrase,
                        source_candidate_id=candidate_id,
                        source_status=status,
                        source_action=action,
                        source_reason=reason,
                        source_file=source_file,
                    )
                )

            for growth_phrase in GROWTH_RE.findall(action):
                normalized_growth = normalize_text(growth_phrase)
                if not normalized_growth:
                    continue
                if " " in normalized_growth and not is_phrase_rule_safe(growth_phrase):
                    skipped.append(
                        {
                            "candidate_id": candidate_id,
                            "skip_reason": f"growth_phrase_too_broad:{growth_phrase}",
                            "source_file": source_file,
                        }
                    )
                    continue
                rule_kind = "growth_token" if " " not in normalized_growth else "growth_phrase_exact"
                candidates.append(
                    build_rule_row(
                        rule_kind=rule_kind,
                        scope_ad_group_name=source_group,
                        match_value=normalized_growth,
                        display_match_value=growth_phrase,
                        source_candidate_id=candidate_id,
                        source_status=status,
                        source_action=action,
                        source_reason=reason,
                        source_file=source_file,
                    )
                )
    return candidates, skipped


def materialize_rulebook(
    rule_candidates: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rule_candidates:
        key = (
            row["scope_ad_group_name"],
            row["rule_kind"],
            row["match_value"],
        )
        grouped[key].append(row)

    rulebook_rows: list[dict[str, str]] = []
    conflict_rows: list[dict[str, str]] = []
    for idx, key in enumerate(sorted(grouped.keys()), start=1):
        rows = grouped[key]
        signatures = {
            (
                row["assistant_status"],
                row["assistant_action"],
                row["assistant_reason"],
            )
            for row in rows
        }
        if len(signatures) > 1:
            conflict_rows.append(
                {
                    "scope_ad_group_name": key[0],
                    "rule_kind": key[1],
                    "match_value": key[2],
                    "display_match_values": " | ".join(sorted({row["display_match_value"] for row in rows})),
                    "source_candidate_ids": " | ".join(sorted({row["source_candidate_id"] for row in rows})),
                    "source_files": " | ".join(sorted({row["source_file"] for row in rows})),
                    "conflicting_actions": " | ".join(
                        sorted({row["assistant_action"] for row in rows})
                    ),
                    "conflicting_reasons": " | ".join(
                        sorted({row["assistant_reason"] for row in rows})
                    ),
                }
            )
            continue

        sample = rows[0]
        rulebook_rows.append(
            {
                "rule_id": f"srule-{idx:05d}",
                "scope_ad_group_name": sample["scope_ad_group_name"],
                "rule_kind": sample["rule_kind"],
                "match_value": sample["match_value"],
                "display_match_value": sample["display_match_value"],
                "assistant_status": sample["assistant_status"],
                "assistant_action": sample["assistant_action"],
                "assistant_reason": sample["assistant_reason"],
                "source_candidate_ids": " | ".join(sorted({row["source_candidate_id"] for row in rows})),
                "source_files": " | ".join(sorted({row["source_file"] for row in rows})),
                "supporting_decision_count": str(len(rows)),
            }
        )

    return rulebook_rows, conflict_rows


def contains_phrase(needle: str, haystack: str) -> bool:
    if not needle or not haystack:
        return False
    return f" {needle} " in f" {haystack} "


def match_rules_for_row(
    row: dict[str, str],
    exact_query_rules: dict[tuple[str, str], list[dict[str, str]]],
    token_rules: dict[str, list[dict[str, str]]],
    phrase_rules: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    scope = (row.get("ad_group_name") or "").strip()
    if not scope:
        return []

    query_norm = normalize_text(row.get("query", ""))
    criterion_norm = normalize_text(row.get("criterion", ""))
    combined_tokens = set(tokenize_text(f"{row.get('query', '')} {row.get('criterion', '')}"))

    matches: list[dict[str, str]] = []
    matches.extend(exact_query_rules.get((scope, query_norm), []))

    for rule in token_rules.get(scope, []):
        if rule["match_value"] in combined_tokens:
            matches.append(rule)

    for rule in phrase_rules.get(scope, []):
        phrase = rule["match_value"]
        if contains_phrase(phrase, query_norm) or contains_phrase(phrase, criterion_norm):
            matches.append(rule)

    return matches


def unique_signature(rule: dict[str, str]) -> tuple[str, str, str]:
    return (
        rule["assistant_status"],
        rule["assistant_action"],
        rule["assistant_reason"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--decisions", required=True, nargs="+", type=Path)
    parser.add_argument("--output-rulebook", required=True, type=Path)
    parser.add_argument("--output-rule-conflicts", required=True, type=Path)
    parser.add_argument("--output-rule-skipped", required=True, type=Path)
    parser.add_argument("--output-auto-decisions", required=True, type=Path)
    parser.add_argument("--output-remaining", required=True, type=Path)
    parser.add_argument("--output-match-conflicts", required=True, type=Path)
    args = parser.parse_args()

    queue_rows = load_tsv(args.queue)
    decision_overrides = load_decision_overrides(args.decisions)
    queue_rows = apply_decision_overrides(queue_rows, decision_overrides)
    queue_rows, collapsed_duplicates = collapse_queue_rows(queue_rows)

    rule_candidates, skipped_rules = extract_rule_candidates(args.decisions)
    rulebook_rows, rule_conflicts = materialize_rulebook(rule_candidates)

    exact_query_rules: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    token_rules: dict[str, list[dict[str, str]]] = defaultdict(list)
    phrase_rules: dict[str, list[dict[str, str]]] = defaultdict(list)
    for rule in rulebook_rows:
        scope = rule["scope_ad_group_name"]
        kind = rule["rule_kind"]
        if kind == "exact_query":
            exact_query_rules[(scope, rule["match_value"])].append(rule)
        elif kind in {"stop_word_token", "growth_token"}:
            token_rules[scope].append(rule)
        else:
            phrase_rules[scope].append(rule)

    auto_decisions: list[dict[str, str]] = []
    remaining_rows: list[dict[str, str]] = []
    match_conflicts: list[dict[str, str]] = []

    for row in queue_rows:
        if decision_has_verdict(row):
            continue
        matches = match_rules_for_row(row, exact_query_rules, token_rules, phrase_rules)
        if not matches:
            remaining_rows.append(dict(row))
            continue
        signatures = {unique_signature(rule) for rule in matches}
        if len(signatures) > 1:
            match_conflicts.append(
                {
                    "candidate_id": (row.get("candidate_id") or "").strip(),
                    "ad_group_name": (row.get("ad_group_name") or "").strip(),
                    "query": (row.get("query") or "").strip(),
                    "criterion": (row.get("criterion") or "").strip(),
                    "matched_rule_ids": " | ".join(sorted({rule["rule_id"] for rule in matches})),
                    "matched_rule_kinds": " | ".join(sorted({rule["rule_kind"] for rule in matches})),
                    "matched_values": " | ".join(sorted({rule["display_match_value"] for rule in matches})),
                    "matched_actions": " | ".join(sorted({rule["assistant_action"] for rule in matches})),
                }
            )
            remaining_rows.append(dict(row))
            continue

        chosen = sorted(matches, key=lambda item: item["rule_id"])[0]
        auto_decisions.append(
            {
                "candidate_id": (row.get("candidate_id") or "").strip(),
                "assistant_status": chosen["assistant_status"],
                "assistant_action": chosen["assistant_action"],
                "assistant_reason": f"{chosen['assistant_reason']} Автоприменено по manual-approved rulebook {chosen['rule_id']}.",
                "rule_id": chosen["rule_id"],
                "rule_kind": chosen["rule_kind"],
                "rule_match_value": chosen["display_match_value"],
                "rule_scope_ad_group_name": chosen["scope_ad_group_name"],
                "rule_source_candidate_ids": chosen["source_candidate_ids"],
            }
        )

    queue_fields = list(queue_rows[0].keys()) if queue_rows else []
    rulebook_fields = [
        "rule_id",
        "scope_ad_group_name",
        "rule_kind",
        "match_value",
        "display_match_value",
        "assistant_status",
        "assistant_action",
        "assistant_reason",
        "source_candidate_ids",
        "source_files",
        "supporting_decision_count",
    ]
    auto_decision_fields = [
        "candidate_id",
        "assistant_status",
        "assistant_action",
        "assistant_reason",
        "rule_id",
        "rule_kind",
        "rule_match_value",
        "rule_scope_ad_group_name",
        "rule_source_candidate_ids",
    ]
    rule_conflict_fields = [
        "scope_ad_group_name",
        "rule_kind",
        "match_value",
        "display_match_values",
        "source_candidate_ids",
        "source_files",
        "conflicting_actions",
        "conflicting_reasons",
    ]
    skipped_rule_fields = ["candidate_id", "skip_reason", "source_file"]
    match_conflict_fields = [
        "candidate_id",
        "ad_group_name",
        "query",
        "criterion",
        "matched_rule_ids",
        "matched_rule_kinds",
        "matched_values",
        "matched_actions",
    ]

    write_tsv(args.output_rulebook, rulebook_rows, rulebook_fields)
    write_tsv(args.output_rule_conflicts, rule_conflicts, rule_conflict_fields)
    write_tsv(args.output_rule_skipped, skipped_rules, skipped_rule_fields)
    write_tsv(args.output_auto_decisions, auto_decisions, auto_decision_fields)
    write_tsv(args.output_remaining, remaining_rows, queue_fields)
    write_tsv(args.output_match_conflicts, match_conflicts, match_conflict_fields)

    print(
        {
            "decision_overrides": len(decision_overrides),
            "collapsed_duplicate_rows": collapsed_duplicates,
            "rule_candidates": len(rule_candidates),
            "rulebook_rules": len(rulebook_rows),
            "rule_conflicts": len(rule_conflicts),
            "auto_decisions": len(auto_decisions),
            "match_conflicts": len(match_conflicts),
            "remaining_rows": len(remaining_rows),
        }
    )


if __name__ == "__main__":
    main()
