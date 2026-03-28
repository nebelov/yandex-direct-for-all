#!/usr/bin/env python3
"""Merge chunked sitemap batch outputs into one normalized wave directory."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


MANIFEST_HEADER = [
    "site_id",
    "base_url",
    "robots_url",
    "robots_status",
    "sitemap_url",
    "status",
    "child_sitemaps",
    "urls_found",
    "relevant_urls",
    "notes",
]

CANDIDATE_HEADER = [
    "site_id",
    "base_url",
    "candidate_url",
    "matched_keywords",
    "source_sitemap",
    "notes",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader)


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    chunks_dir = Path(args.chunks_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, str]] = []
    candidate_rows: list[dict[str, str]] = []
    seen_manifest: set[tuple[str, str]] = set()
    seen_candidate: set[tuple[str, str]] = set()
    chunk_count = 0

    for chunk_dir in sorted(path for path in chunks_dir.iterdir() if path.is_dir()):
        chunk_count += 1
        for row in read_tsv(chunk_dir / "sitemap_manifest.tsv"):
            key = (row.get("site_id", ""), row.get("sitemap_url", ""))
            if key in seen_manifest:
                continue
            seen_manifest.add(key)
            manifest_rows.append(row)
        for row in read_tsv(chunk_dir / "candidate_urls.tsv"):
            key = (row.get("site_id", ""), row.get("candidate_url", ""))
            if key in seen_candidate:
                continue
            seen_candidate.add(key)
            candidate_rows.append(row)

    manifest_rows.sort(key=lambda row: (row.get("site_id", ""), row.get("sitemap_url", "")))
    candidate_rows.sort(key=lambda row: (row.get("site_id", ""), row.get("candidate_url", "")))

    write_tsv(output_dir / "sitemap_manifest.tsv", MANIFEST_HEADER, manifest_rows)
    write_tsv(output_dir / "candidate_urls.tsv", CANDIDATE_HEADER, candidate_rows)
    (output_dir / "_summary.json").write_text(
        json.dumps(
            {
                "chunks_merged": chunk_count,
                "manifest_rows": len(manifest_rows),
                "candidate_rows": len(candidate_rows),
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(str(output_dir / "candidate_urls.tsv"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
