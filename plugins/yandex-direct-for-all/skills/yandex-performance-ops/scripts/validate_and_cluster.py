#!/usr/bin/env python3
"""Validate target/negative files and build a generic cluster map from routing map."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from typing import Dict, List


def read_tsv(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: str, rows: List[dict], columns: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zа-яё0-9-]+", normalize(text))


def load_routes(path: str) -> Dict[str, dict]:
    routes = {}
    for row in read_tsv(path):
        cluster = normalize(row.get("cluster", ""))
        if not cluster:
            continue
        routes[cluster] = {
            "campaign_name": row.get("campaign_name", ""),
            "adgroup_name": row.get("adgroup_name", ""),
            "match_type": row.get("match_type", "default"),
            "landing_hint": row.get("landing_hint", "/"),
        }
    return routes


def dedupe_targets(rows: List[dict]) -> List[dict]:
    out = []
    seen = set()
    for row in rows:
        phrase = normalize(row.get("phrase", ""))
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        out.append(
            {
                "phrase": phrase,
                "cluster": normalize(row.get("cluster", "")),
                "intent_type": row.get("intent_type", "target"),
                "priority": row.get("priority", "medium"),
                "source_file": row.get("source_file", ""),
                "source_mask": row.get("source_mask", ""),
                "evidence": row.get("evidence", ""),
            }
        )
    return out


def normalize_negative_row(row: dict) -> dict:
    phrase = normalize(row.get("phrase") or row.get("word") or "")
    return {
        "phrase": phrase,
        "level": row.get("level", "campaign"),
        "reason": row.get("reason", ""),
        "risk_blocking": row.get("risk_blocking", ""),
        "source_file": row.get("source_file", ""),
        "evidence": row.get("evidence", ""),
    }


def validate_negatives(rows: List[dict], target_rows: List[dict]) -> tuple[List[dict], List[str]]:
    target_phrases = [row["phrase"] for row in target_rows]
    target_tokens = {token for row in target_rows for token in tokenize(row["phrase"])}
    safe_rows = []
    conflicts = []

    for raw in rows:
        row = normalize_negative_row(raw)
        phrase = row["phrase"]
        if not phrase:
            continue

        neg_tokens = tokenize(phrase)
        phrase_conflict = any(phrase in target or target in phrase for target in target_phrases)
        token_conflict = len(neg_tokens) == 1 and neg_tokens[0] in target_tokens
        conflict = phrase_conflict or token_conflict

        row["conflicts_with_target"] = "yes" if conflict else "no"
        row["risk_blocking"] = "high" if conflict else (row["risk_blocking"] or "low")
        if conflict:
            conflicts.append(phrase)
            continue
        safe_rows.append(row)

    return safe_rows, conflicts


def build_cluster_map(
    target_rows: List[dict],
    routes: Dict[str, dict],
    default_campaign: str,
    default_adgroup: str,
) -> tuple[List[dict], List[str]]:
    cluster_map = []
    unknown_clusters = []

    for row in target_rows:
        cluster = normalize(row.get("cluster", ""))
        route = routes.get(cluster)
        if route is None:
            unknown_clusters.append(cluster)
            route = {
                "campaign_name": default_campaign,
                "adgroup_name": default_adgroup,
                "match_type": "default",
                "landing_hint": "/",
            }
        cluster_map.append(
            {
                "campaign_name": route["campaign_name"],
                "adgroup_name": route["adgroup_name"],
                "phrase": row["phrase"],
                "match_type": route.get("match_type", "default"),
                "landing_hint": route.get("landing_hint", "/"),
            }
        )

    deduped = []
    seen = set()
    for row in cluster_map:
        key = tuple(row[col] for col in ("campaign_name", "adgroup_name", "phrase"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped, sorted({cluster for cluster in unknown_clusters if cluster})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-final", required=True)
    parser.add_argument("--negative-final", required=True)
    parser.add_argument("--routing-map", required=True)
    parser.add_argument("--out-target-validated", required=True)
    parser.add_argument("--out-negative-validated", required=True)
    parser.add_argument("--out-cluster-map", required=True)
    parser.add_argument("--out-validation-report", required=True)
    parser.add_argument("--default-campaign-name", default="Search Campaign")
    parser.add_argument("--default-adgroup-name", default="General")
    args = parser.parse_args()

    target_rows = dedupe_targets(read_tsv(args.target_final))
    negative_rows, conflicts = validate_negatives(read_tsv(args.negative_final), target_rows)
    routes = load_routes(args.routing_map)
    cluster_map, unknown_clusters = build_cluster_map(
        target_rows, routes, args.default_campaign_name, args.default_adgroup_name
    )

    write_tsv(
        args.out_target_validated,
        target_rows,
        ["phrase", "cluster", "intent_type", "priority", "source_file", "source_mask", "evidence"],
    )
    write_tsv(
        args.out_negative_validated,
        negative_rows,
        ["phrase", "level", "reason", "risk_blocking", "conflicts_with_target", "source_file", "evidence"],
    )
    write_tsv(
        args.out_cluster_map,
        cluster_map,
        ["campaign_name", "adgroup_name", "phrase", "match_type", "landing_hint"],
    )

    report = {
        "target_input": len(read_tsv(args.target_final)),
        "target_validated": len(target_rows),
        "negative_input": len(read_tsv(args.negative_final)),
        "negative_validated": len(negative_rows),
        "conflicts_removed": len(conflicts),
        "unknown_clusters": unknown_clusters,
        "status": "PASS" if not conflicts else "REVIEW_REQUIRED",
    }
    os.makedirs(os.path.dirname(args.out_validation_report), exist_ok=True)
    with open(args.out_validation_report, "w", encoding="utf-8") as fh:
        fh.write("# Validation Report\n\n")
        for key, value in report.items():
            fh.write(f"- {key}: {json.dumps(value, ensure_ascii=False)}\n")

    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

