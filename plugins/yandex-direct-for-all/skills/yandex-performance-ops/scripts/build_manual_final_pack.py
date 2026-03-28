#!/usr/bin/env python3
"""Build generic final artifacts from manual target/minus files."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter
from typing import Dict, List


TARGET_COLUMNS = [
    "phrase",
    "cluster",
    "intent_type",
    "priority",
    "source_mask",
    "source_file",
    "evidence",
]

MINUS_WORD_COLUMNS = ["word", "reason", "source", "conflicts_with_target"]

CLUSTER_MAP_COLUMNS = ["campaign_name", "adgroup_name", "phrase", "match_type", "landing_hint"]

TASK_COLUMNS = [
    "task_id",
    "priority",
    "category",
    "scope",
    "target_id",
    "target_name",
    "action",
    "params_json",
    "evidence",
    "savings_30d",
    "description",
]


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


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zа-яё0-9-]+", normalize(text))


def build_target_validated(rows: List[dict]) -> List[dict]:
    seen = set()
    out = []
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
                "source_mask": row.get("source_mask", ""),
                "source_file": row.get("source_file", ""),
                "evidence": row.get("evidence", "manual_review"),
            }
        )
    return out


def build_minus_words_validated(rows: List[dict], target_rows: List[dict]) -> tuple[List[dict], List[dict]]:
    target_tokens = {token for row in target_rows for token in tokenize(row["phrase"])}
    kept = []
    removed = []
    seen = set()

    for row in rows:
        word = normalize(row.get("word") or row.get("phrase") or "")
        tokens = tokenize(word)
        if len(tokens) != 1:
            continue
        word = tokens[0]
        if word in seen or len(word) < 3:
            continue
        seen.add(word)
        out = {
            "word": word,
            "reason": row.get("reason", "manual_minus"),
            "source": row.get("source", "manual_final"),
            "conflicts_with_target": "yes" if word in target_tokens else "no",
        }
        if out["conflicts_with_target"] == "yes":
            removed.append(out)
        else:
            kept.append(out)

    return kept, removed


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


def build_cluster_map(target_rows: List[dict], routes: Dict[str, dict], fallback_campaign: str, fallback_adgroup: str):
    out = []
    unknown_clusters = []
    for row in target_rows:
        cluster = row.get("cluster", "")
        route = routes.get(cluster)
        if route is None:
            unknown_clusters.append(cluster)
            route = {
                "campaign_name": fallback_campaign,
                "adgroup_name": fallback_adgroup,
                "match_type": "default",
                "landing_hint": "/",
            }
        out.append(
            {
                "campaign_name": route["campaign_name"],
                "adgroup_name": route["adgroup_name"],
                "phrase": row["phrase"],
                "match_type": route.get("match_type", "default"),
                "landing_hint": route.get("landing_hint", "/"),
            }
        )

    dedup = []
    seen = set()
    for row in out:
        key = (row["campaign_name"], row["adgroup_name"], row["phrase"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(row)
    return dedup, sorted({cluster for cluster in unknown_clusters if cluster})


def load_campaign_id_map(path: str) -> Dict[str, str]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit("campaign-id-map must be a JSON object: {campaign_name: id}")
    return {str(key): str(value) for key, value in data.items()}


def build_minus_tasks(minus_words: List[dict], campaign_id_map: Dict[str, str], evidence: str) -> List[dict]:
    out = []
    seq = 1
    for campaign_name, campaign_id in sorted(campaign_id_map.items()):
        for minus_word in minus_words:
            out.append(
                {
                    "task_id": f"MW-{campaign_id}-{seq:04d}",
                    "priority": "HIGH",
                    "category": "NEGATIVE_KEYWORD",
                    "scope": "campaign",
                    "target_id": campaign_id,
                    "target_name": campaign_name,
                    "action": "ADD_NEGATIVE_WORD",
                    "params_json": json.dumps(
                        {"word": minus_word["word"], "level": "campaign"},
                        ensure_ascii=False,
                    ),
                    "evidence": evidence,
                    "savings_30d": "0",
                    "description": f"Добавить минус-слово: {minus_word['word']}",
                }
            )
            seq += 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-manual", required=True)
    parser.add_argument("--minus-words-manual", required=True)
    parser.add_argument("--routing-map", required=True)
    parser.add_argument("--out-target-validated", required=True)
    parser.add_argument("--out-minus-words-validated", required=True)
    parser.add_argument("--out-cluster-map", required=True)
    parser.add_argument("--out-minus-tasks", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument("--campaign-id-map", default="")
    parser.add_argument("--fallback-campaign-name", default="Search Campaign")
    parser.add_argument("--fallback-adgroup-name", default="General")
    args = parser.parse_args()

    target_manual = read_tsv(args.target_manual)
    minus_manual = read_tsv(args.minus_words_manual)
    target_validated = build_target_validated(target_manual)
    minus_words_validated, minus_conflicts = build_minus_words_validated(minus_manual, target_validated)
    routes = load_routes(args.routing_map)
    cluster_map, unknown_clusters = build_cluster_map(
        target_validated, routes, args.fallback_campaign_name, args.fallback_adgroup_name
    )
    campaign_id_map = load_campaign_id_map(args.campaign_id_map)
    minus_tasks = build_minus_tasks(
        minus_words_validated,
        campaign_id_map,
        evidence=args.out_minus_words_validated,
    )

    write_tsv(args.out_target_validated, target_validated, TARGET_COLUMNS)
    write_tsv(args.out_minus_words_validated, minus_words_validated, MINUS_WORD_COLUMNS)
    write_tsv(args.out_cluster_map, cluster_map, CLUSTER_MAP_COLUMNS)
    write_tsv(args.out_minus_tasks, minus_tasks, TASK_COLUMNS)

    summary = {
        "target_manual_rows": len(target_manual),
        "target_validated_rows": len(target_validated),
        "minus_words_manual_rows": len(minus_manual),
        "minus_words_validated_rows": len(minus_words_validated),
        "minus_words_removed_conflicts": len(minus_conflicts),
        "cluster_map_rows": len(cluster_map),
        "minus_tasks_rows": len(minus_tasks),
        "unknown_clusters": unknown_clusters,
        "cluster_distribution": dict(sorted(Counter(row["cluster"] for row in target_validated).items())),
        "campaign_distribution": dict(sorted(Counter(row["campaign_name"] for row in cluster_map).items())),
    }

    os.makedirs(os.path.dirname(args.out_summary), exist_ok=True)
    with open(args.out_summary, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
