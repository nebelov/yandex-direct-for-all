#!/usr/bin/env python3
"""Split a TSV batch spec into chunk files with the original header preserved."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-tsv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--prefix", default="chunk")
    args = parser.parse_args()

    input_path = Path(args.input_tsv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError("TSV header is missing")
        rows = list(reader)

    chunk_size = max(args.chunk_size, 1)
    total_chunks = (len(rows) + chunk_size - 1) // chunk_size if rows else 0

    for index in range(total_chunks):
        start = index * chunk_size
        end = start + chunk_size
        chunk_rows = rows[start:end]
        output_path = output_dir / f"{args.prefix}_{index + 1:03d}.tsv"
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(chunk_rows)
        print(f"{output_path}\t{len(chunk_rows)}")

    print(f"rows={len(rows)} chunks={total_chunks} chunk_size={chunk_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
