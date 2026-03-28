#!/usr/bin/env python3
"""Render organic/ad SERP raw into sorted TSV views and chunks for manual review."""

from __future__ import annotations

import argparse
import csv
import json
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


def as_rank(value: str) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return 999999


def chunk_rows(
    base_dir: Path,
    prefix: str,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    chunk_size: int,
) -> int:
    chunks_dir = base_dir / prefix
    chunks_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for index in range(0, len(rows), chunk_size):
        chunk = rows[index : index + chunk_size]
        total += 1
        write_rows(chunks_dir / f"{prefix}_{total:03d}.tsv", fieldnames, chunk)
    return total


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
            as_rank(row.get("result_rank", "")),
            row.get("result_domain", ""),
            row.get("source_url", ""),
        ),
    )
    by_domain = sorted(
        rows,
        key=lambda row: (
            row.get("result_domain", ""),
            row.get("search_query", ""),
            row.get("search_region", ""),
            as_rank(row.get("result_rank", "")),
            row.get("source_url", ""),
        ),
    )

    write_rows(output_dir / "all_rows_by_query.tsv", fieldnames, by_query)
    write_rows(output_dir / "all_rows_by_domain.tsv", fieldnames, by_domain)

    query_chunks = chunk_rows(output_dir / "chunks", "by_query", fieldnames, by_query, args.chunk_size)
    domain_chunks = chunk_rows(output_dir / "chunks", "by_domain", fieldnames, by_domain, args.chunk_size)

    summary = {
        "rows": len(rows),
        "unique_queries": len({row.get("search_query", "") for row in rows}),
        "unique_domains": len({row.get("result_domain", "") for row in rows}),
        "query_chunks": query_chunks,
        "domain_chunks": domain_chunks,
        "chunk_size": args.chunk_size,
        "output_dir": str(output_dir),
    }
    (output_dir / "_render_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
