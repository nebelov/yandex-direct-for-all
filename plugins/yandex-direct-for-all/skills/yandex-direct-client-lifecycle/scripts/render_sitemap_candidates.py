#!/usr/bin/env python3
"""Render sitemap candidate URLs into sorted TSV views for manual review."""

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


def chunk_rows(output_dir: Path, prefix: str, fieldnames: list[str], rows: list[dict[str, str]], chunk_size: int) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for index in range(0, len(rows), chunk_size):
        total += 1
        chunk = rows[index : index + chunk_size]
        write_rows(output_dir / f"{prefix}_{total:03d}.tsv", fieldnames, chunk)
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

    by_site = sorted(rows, key=lambda row: (row.get("site_id", ""), row.get("candidate_url", "")))
    by_url = sorted(rows, key=lambda row: (row.get("candidate_url", ""), row.get("site_id", "")))

    write_rows(output_dir / "all_rows_by_site.tsv", fieldnames, by_site)
    write_rows(output_dir / "all_rows_by_url.tsv", fieldnames, by_url)
    site_chunks = chunk_rows(output_dir / "chunks" / "by_site", "by_site", fieldnames, by_site, args.chunk_size)
    url_chunks = chunk_rows(output_dir / "chunks" / "by_url", "by_url", fieldnames, by_url, args.chunk_size)

    summary = {
        "rows": len(rows),
        "unique_sites": len({row.get("site_id", "") for row in rows}),
        "site_chunks": site_chunks,
        "url_chunks": url_chunks,
        "chunk_size": args.chunk_size,
        "output_dir": str(output_dir),
    }
    (output_dir / "_render_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
