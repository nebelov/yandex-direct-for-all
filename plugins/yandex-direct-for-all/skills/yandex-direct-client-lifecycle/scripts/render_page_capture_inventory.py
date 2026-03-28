#!/usr/bin/env python3
"""Render a mechanical page-capture inventory from job specs and output files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


HEADER = [
    "capture_id",
    "source_url",
    "brand",
    "keyword",
    "layer",
    "json_exists",
    "md_exists",
    "html_exists",
    "error_exists",
]


def read_jobs(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader)


def read_manifest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    manifest: dict[str, dict[str, str]] = {}
    for item in data:
        job_id = item.get("job_id", "")
        if job_id:
            manifest[job_id] = item
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs-file", required=True)
    parser.add_argument("--captures-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    jobs = read_jobs(Path(args.jobs_file).expanduser().resolve())
    captures_dir = Path(args.captures_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(captures_dir / "_manifest.json")

    rows: list[dict[str, str]] = []
    for job in jobs:
        capture_id = job.get("capture_id", "")
        manifest_row = manifest.get(capture_id, {})
        prefix = f"{capture_id}__"
        json_exists = any(captures_dir.glob(f"{prefix}*.json")) or bool(manifest_row.get("json_path"))
        if manifest_row.get("status") == "ok":
            json_exists = True
        md_exists = any(captures_dir.glob(f"{prefix}*.md")) or bool(manifest_row.get("md_path"))
        html_exists = any(captures_dir.glob(f"{prefix}*.html")) or bool(manifest_row.get("html_path"))
        error_exists = any(captures_dir.glob(f"{prefix}*.error.txt")) or bool(manifest_row.get("error_path"))
        rows.append(
            {
                "capture_id": capture_id,
                "source_url": job.get("source_url", ""),
                "brand": job.get("brand", ""),
                "keyword": job.get("keyword", ""),
                "layer": job.get("layer", ""),
                "json_exists": "1" if json_exists else "0",
                "md_exists": "1" if md_exists else "0",
                "html_exists": "1" if html_exists else "0",
                "error_exists": "1" if error_exists else "0",
            }
        )

    with (output_dir / "page_capture_inventory.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "jobs": len(rows),
        "json_present": sum(1 for row in rows if row["json_exists"] == "1"),
        "md_present": sum(1 for row in rows if row["md_exists"] == "1"),
        "html_present": sum(1 for row in rows if row["html_exists"] == "1"),
        "error_present": sum(1 for row in rows if row["error_exists"] == "1"),
        "output_dir": str(output_dir),
    }
    (output_dir / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
