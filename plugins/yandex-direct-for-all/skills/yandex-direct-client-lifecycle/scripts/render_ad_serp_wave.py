#!/usr/bin/env python3
"""Render search ad SERP rows into review-friendly summaries without conclusions."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        return fieldnames, list(reader)


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def chunk_rows(base_dir: Path, prefix: str, fieldnames: list[str], rows: list[dict[str, str]], chunk_size: int) -> int:
    base_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for index in range(0, len(rows), chunk_size):
        total += 1
        write_rows(base_dir / f"{prefix}_{total:03d}.tsv", fieldnames, rows[index : index + chunk_size])
    return total


def as_int(value: str) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return 999999


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-tsv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--chunk-size", type=int, default=500)
    args = parser.parse_args()

    input_path = Path(args.input_tsv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    fieldnames, rows = read_rows(input_path)

    by_query = sorted(
        rows,
        key=lambda row: (
            row.get("search_query", ""),
            row.get("search_region", ""),
            as_int(row.get("result_rank", "")),
            row.get("result_domain", ""),
            row.get("source_url", ""),
        ),
    )
    by_domain = sorted(
        rows,
        key=lambda row: (
            row.get("result_domain", ""),
            row.get("search_region", ""),
            row.get("search_query", ""),
            as_int(row.get("result_rank", "")),
            row.get("source_url", ""),
        ),
    )
    write_rows(output_dir / "all_rows_by_query.tsv", fieldnames, by_query)
    write_rows(output_dir / "all_rows_by_domain.tsv", fieldnames, by_domain)

    query_chunks = chunk_rows(output_dir / "chunks_by_query", "chunk", fieldnames, by_query, args.chunk_size)
    domain_chunks = chunk_rows(output_dir / "chunks_by_domain", "chunk", fieldnames, by_domain, args.chunk_size)

    domain_counter = Counter(row.get("result_domain", "") for row in rows if row.get("result_domain"))
    region_domain_counter: dict[tuple[str, str], int] = Counter(
        (row.get("search_region", ""), row.get("result_domain", ""))
        for row in rows
        if row.get("search_region") and row.get("result_domain")
    )
    query_region_counter: dict[tuple[str, str, str], int] = Counter(
        (row.get("search_query", ""), row.get("search_region", ""), row.get("result_domain", ""))
        for row in rows
        if row.get("search_query") and row.get("search_region") and row.get("result_domain")
    )
    query_counter: dict[tuple[str, str], int] = Counter(
        (row.get("search_query", ""), row.get("search_region", ""))
        for row in rows
        if row.get("search_query") and row.get("search_region")
    )

    domain_rows = [
        {"domain": domain, "ad_hits": str(count)}
        for domain, count in sorted(domain_counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    write_rows(output_dir / "domain_counts.tsv", ["domain", "ad_hits"], domain_rows)

    region_rows = [
        {"search_region": region, "domain": domain, "ad_hits": str(count)}
        for (region, domain), count in sorted(region_domain_counter.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    ]
    write_rows(output_dir / "region_domain_counts.tsv", ["search_region", "domain", "ad_hits"], region_rows)

    query_rows = [
        {"search_query": query, "search_region": region, "ad_hits": str(count)}
        for (query, region), count in sorted(query_counter.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    ]
    write_rows(output_dir / "query_counts.tsv", ["search_query", "search_region", "ad_hits"], query_rows)

    leaders_map: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for (query, region, domain), count in query_region_counter.items():
        leaders_map[(query, region)].append((domain, count))
    leader_rows: list[dict[str, str]] = []
    for (query, region), items in sorted(leaders_map.items(), key=lambda item: (item[0][0], item[0][1])):
        items.sort(key=lambda value: (-value[1], value[0]))
        for rank, (domain, count) in enumerate(items[:10], start=1):
            leader_rows.append(
                {
                    "search_query": query,
                    "search_region": region,
                    "leader_rank": str(rank),
                    "domain": domain,
                    "ad_hits": str(count),
                }
            )
    write_rows(output_dir / "query_region_domain_leaders.tsv", ["search_query", "search_region", "leader_rank", "domain", "ad_hits"], leader_rows)

    summary = {
        "rows": len(rows),
        "unique_queries": len({row.get("search_query", "") for row in rows}),
        "unique_regions": len({row.get("search_region", "") for row in rows}),
        "unique_domains": len(domain_counter),
        "query_chunks": query_chunks,
        "domain_chunks": domain_chunks,
        "chunk_size": args.chunk_size,
        "output_dir": str(output_dir),
    }
    (output_dir / "_render_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
