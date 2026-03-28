#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().split())


def build_config_lookup(config_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for row in config_rows:
        mask = normalize_text(row["mask"]).lower()
        lookup[mask] = row
    return lookup


def render_rows(
    config_rows: list[dict[str, str]],
    normalized_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    config_lookup = build_config_lookup(config_rows)
    rows: list[dict[str, object]] = []
    for row in normalized_rows:
        phrase_key = normalize_text(row["request_phrase"]).lower()
        config = config_lookup.get(phrase_key)
        if not config:
            continue
        rows.append(
            {
                "order": int(config["order"]),
                "cluster": config["cluster"],
                "mask": normalize_text(config["mask"]),
                "region_id": row["region_id"],
                "region_name": normalize_text(row["region_name"]),
                "count": int(float(row["count"] or 0)),
                "share": float(row["share"] or 0),
                "affinity_index": float(row["affinity_index"] or 0),
                "note": normalize_text(config.get("note", "")),
                "source_file": row["source_file"],
            }
        )
    return sorted(rows, key=lambda item: (int(item["order"]), -int(item["count"]), str(item["region_name"])))


def build_priority_matrix(
    rows: list[dict[str, object]],
    geo_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    geo_labels = [row for row in geo_rows if row.get("enabled", "") == "1" and row["geo_code"] != "rf"]
    geo_lookup = {row["region_id"]: row for row in geo_labels}
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        if row["region_id"] not in geo_lookup:
            continue
        key = str(row["mask"])
        record = grouped.setdefault(
            key,
            {
                "order": int(row["order"]),
                "cluster": row["cluster"],
                "mask": row["mask"],
                "note": row["note"],
            },
        )
        geo = geo_lookup[row["region_id"]]
        code = geo["geo_code"]
        record[f"{code}_count"] = int(row["count"])
        record[f"{code}_affinity"] = round(float(row["affinity_index"]), 1)

    rendered: list[dict[str, object]] = []
    for record in grouped.values():
        for geo in geo_labels:
            code = geo["geo_code"]
            record.setdefault(f"{code}_count", 0)
            record.setdefault(f"{code}_affinity", 0.0)
        rendered.append(record)
    return sorted(rendered, key=lambda item: (int(item["order"]), str(item["mask"])))


def build_top_rows(rows: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    top_rows: list[dict[str, object]] = []
    seen: dict[str, int] = {}
    for row in rows:
        if str(row["region_id"]) == "225":
            continue
        mask = str(row["mask"])
        count = seen.get(mask, 0)
        if count >= limit:
            continue
        seen[mask] = count + 1
        top_rows.append(row)
    return top_rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render Wordstat geography by approved masks from normalized region TSV."
    )
    parser.add_argument("--config", required=True, help="TSV config with exact masks")
    parser.add_argument("--normalized-tsv", required=True, help="Normalized region TSV")
    parser.add_argument("--geo-matrix", required=True, help="Priority geo matrix TSV")
    parser.add_argument("--output-dir", required=True, help="Directory for rendered TSV/JSON files")
    parser.add_argument("--top-limit", type=int, default=8, help="How many strongest rows keep per mask")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    normalized_path = Path(args.normalized_tsv).expanduser().resolve()
    geo_matrix_path = Path(args.geo_matrix).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config_rows = read_tsv(config_path)
    normalized_rows = read_tsv(normalized_path)
    geo_rows = read_tsv(geo_matrix_path)

    rows = render_rows(config_rows, normalized_rows)
    all_fieldnames = [
        "order",
        "cluster",
        "mask",
        "region_id",
        "region_name",
        "count",
        "share",
        "affinity_index",
        "note",
        "source_file",
    ]
    write_tsv(output_dir / "wordstat-geo-all.tsv", rows, all_fieldnames)

    priority_rows = build_priority_matrix(rows, geo_rows)
    priority_fieldnames = ["order", "cluster", "mask"]
    for geo in [row for row in geo_rows if row.get("enabled", "") == "1" and row["geo_code"] != "rf"]:
        priority_fieldnames.extend([f"{geo['geo_code']}_count", f"{geo['geo_code']}_affinity"])
    priority_fieldnames.append("note")
    write_tsv(output_dir / "wordstat-geo-priority.tsv", priority_rows, priority_fieldnames)

    top_rows = build_top_rows(rows, args.top_limit)
    write_tsv(output_dir / "wordstat-geo-top.tsv", top_rows, all_fieldnames)

    summary = {
        "config": str(config_path),
        "normalized_tsv": str(normalized_path),
        "rows_total": len(rows),
        "priority_rows": len(priority_rows),
        "top_rows": len(top_rows),
        "rule": "Скрипт только нормализует и рендерит региональный raw без выводов.",
    }
    (output_dir / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
