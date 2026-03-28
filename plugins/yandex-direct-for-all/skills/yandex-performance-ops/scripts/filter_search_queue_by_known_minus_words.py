#!/usr/bin/env python3
"""Reduce a manual SQR queue by exact carry-forward of known minus words.

This script is intentionally conservative:
- it extracts only explicit `стоп-слово `...`` decisions from prior manual files;
- it matches exact single-word tokens only;
- it writes an audit file for every excluded row;
- it does not generate any new verdicts.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


STOP_WORD_RE = re.compile(r"стоп-слово `([^`]+)`", re.IGNORECASE)
TOKEN_BOUNDARY_TEMPLATE = r"(?<![A-Za-zА-Яа-яЁё0-9]){token}(?![A-Za-zА-Яа-яЁё0-9])"


def load_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def normalize_word(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def normalize_float(value: str) -> float:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


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
        override = overrides.get(candidate_id)
        merged = dict(row)
        if override:
            for field in ("assistant_status", "assistant_action", "assistant_reason"):
                merged[field] = (override.get(field) or merged.get(field) or "").strip()
        result.append(merged)
    return result


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
        current_resolved = bool((current.get("assistant_status") or "").strip())
        candidate_resolved = bool((row.get("assistant_status") or "").strip())
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


def load_known_minus_words(paths: list[Path], single_word_only: bool) -> dict[str, set[str]]:
    known: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        for row in load_tsv(path):
            action = row.get("assistant_action", "")
            for match in STOP_WORD_RE.findall(action):
                word = normalize_word(match)
                if not word:
                    continue
                if single_word_only and " " in word:
                    continue
                known[word].add(str(path))
    return dict(sorted(known.items()))


def compile_patterns(words: list[str]) -> dict[str, re.Pattern[str]]:
    return {
        word: re.compile(TOKEN_BOUNDARY_TEMPLATE.format(token=re.escape(word)), re.IGNORECASE)
        for word in words
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--decisions", required=True, nargs="+", type=Path)
    parser.add_argument("--output-remaining", required=True, type=Path)
    parser.add_argument("--output-excluded", required=True, type=Path)
    parser.add_argument("--output-known-words", type=Path, default=None)
    parser.add_argument(
        "--match-fields",
        default="query,criterion",
        help="Comma-separated queue fields to scan. Default: query,criterion",
    )
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="Also pass through already resolved rows into output-remaining.",
    )
    parser.add_argument(
        "--allow-multiword",
        action="store_true",
        help="Also extract multiword negatives. Off by default to avoid phrase-level carry-forward.",
    )
    args = parser.parse_args()

    queue_rows = load_tsv(args.queue)
    decision_overrides = load_decision_overrides(args.decisions)
    queue_rows = apply_decision_overrides(queue_rows, decision_overrides)
    queue_rows, collapsed_duplicates = collapse_queue_rows(queue_rows)
    known_words = load_known_minus_words(args.decisions, single_word_only=not args.allow_multiword)
    patterns = compile_patterns(list(known_words.keys()))
    match_fields = [field.strip() for field in args.match_fields.split(",") if field.strip()]

    remaining_rows: list[dict[str, str]] = []
    excluded_rows: list[dict[str, str]] = []

    for row in queue_rows:
        resolved = bool((row.get("assistant_status") or "").strip())
        if resolved and not args.include_resolved:
            continue

        haystack = " ".join((row.get(field, "") or "") for field in match_fields).strip()
        hits = sorted(word for word, pattern in patterns.items() if pattern.search(haystack))
        if hits:
            excluded = dict(row)
            excluded["matched_minus_words"] = ", ".join(hits)
            excluded["matched_decision_files"] = " | ".join(
                sorted({src for hit in hits for src in known_words.get(hit, set())})
            )
            excluded_rows.append(excluded)
            continue

        remaining_rows.append(dict(row))

    queue_fields = list(queue_rows[0].keys()) if queue_rows else []
    excluded_fields = [*queue_fields, "matched_minus_words", "matched_decision_files"]
    write_tsv(args.output_remaining, remaining_rows, queue_fields)
    write_tsv(args.output_excluded, excluded_rows, excluded_fields)

    if args.output_known_words:
        known_rows = [
            {"minus_word": word, "source_files": " | ".join(sorted(source_files))}
            for word, source_files in known_words.items()
        ]
        write_tsv(args.output_known_words, known_rows, ["minus_word", "source_files"])

    print(
        {
            "known_minus_words": len(known_words),
            "decision_overrides": len(decision_overrides),
            "collapsed_duplicate_rows": collapsed_duplicates,
            "remaining_rows": len(remaining_rows),
            "excluded_rows": len(excluded_rows),
            "include_resolved": args.include_resolved,
            "match_fields": match_fields,
        }
    )


if __name__ == "__main__":
    main()
