#!/usr/bin/env python3
"""Verify that the research bundle is present before manual analysis starts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def pick_first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def count_tsv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        rows = list(reader)
    return max(len(rows) - 1, 0)


def count_json_files(path: Path) -> int:
    if not path.exists():
        return 0
    return len(list(path.glob("*.json")))


def count_dirs(path: Path) -> int:
    if not path.exists():
        return 0
    return len([item for item in path.iterdir() if item.is_dir()])


def count_chunk_raw_dirs(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for chunk_dir in path.iterdir():
        raw_dir = chunk_dir / "raw"
        if chunk_dir.is_dir() and raw_dir.exists():
            total += count_dirs(raw_dir)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    root = Path(args.project_dir).expanduser().resolve()
    firecrawl_wave_dir = pick_first_existing(
        [
            root / "research/raw/competitors/firecrawl/validated-keywords-wave-02",
            root / "research/raw/competitors/firecrawl/validated-keywords-wave-01",
        ]
    )
    sitemap_wave_dir = pick_first_existing(
        [
            root / "research/raw/competitors/sitemaps/validated-keywords-wave-03",
            root / "research/raw/competitors/sitemaps/validated-keywords-wave-02",
            root / "research/raw/competitors/sitemaps/validated-keywords-wave-01",
        ]
    )
    sitemap_chunk_dir = root / "research/raw/competitors/sitemaps/validated-keywords-wave-03-chunks"
    sitemap_raw_dirs = count_dirs(sitemap_wave_dir / "raw")
    if sitemap_raw_dirs == 0:
        sitemap_raw_dirs = count_chunk_raw_dirs(sitemap_chunk_dir)

    checks = [
        ("client_kb", root / "client-kb.md", (root / "client-kb.md").exists()),
        ("company_footprint", root / "research/analysis/company-footprint.md", (root / "research/analysis/company-footprint.md").exists()),
        ("landing_inventory", root / "research/analysis/landing-inventory.md", (root / "research/analysis/landing-inventory.md").exists()),
        ("direct_inventory", root / "research/analysis/direct-account-inventory.md", (root / "research/analysis/direct-account-inventory.md").exists()),
        ("metrika_inventory", root / "research/analysis/metrika-goals-inventory.md", (root / "research/analysis/metrika-goals-inventory.md").exists()),
        ("wordstat_wave1_summary", root / "research/semantics/nevgroup-lighting/raw/wordstat_wave1_single_token/_summary.json", (root / "research/semantics/nevgroup-lighting/raw/wordstat_wave1_single_token/_summary.json").exists()),
        ("wordstat_wave2_summary", root / "research/semantics/nevgroup-lighting/raw/wordstat_wave2_two_token/_summary.json", (root / "research/semantics/nevgroup-lighting/raw/wordstat_wave2_two_token/_summary.json").exists()),
        ("wordstat_wave1_render", root / "research/semantics/nevgroup-lighting/render/wordstat_wave1_single_token/all_rows_by_count.tsv", (root / "research/semantics/nevgroup-lighting/render/wordstat_wave1_single_token/all_rows_by_count.tsv").exists()),
        ("wordstat_wave2_render", root / "research/semantics/nevgroup-lighting/render/wordstat_wave2_two_token/all_rows_by_count.tsv", (root / "research/semantics/nevgroup-lighting/render/wordstat_wave2_two_token/all_rows_by_count.tsv").exists()),
        ("validated_keyword_matrix", root / "research/analysis/validated-keyword-matrix.tsv", (root / "research/analysis/validated-keyword-matrix.tsv").exists()),
        ("geo_matrix", root / "research/jobs/geo-matrix.tsv", (root / "research/jobs/geo-matrix.tsv").exists()),
        ("organic_jobs", root / "research/jobs/organic-serp-jobs.tsv", (root / "research/jobs/organic-serp-jobs.tsv").exists()),
        ("ad_jobs_optional", root / "research/jobs/ad-serp-jobs.tsv", True),
        ("organic_serp_results", root / "research/raw/competitor-search/api-wave-02-validated-keywords/serp_results.tsv", (root / "research/raw/competitor-search/api-wave-02-validated-keywords/serp_results.tsv").exists()),
        ("page_capture_jobs", root / "research/jobs/page-capture-jobs.tsv", (root / "research/jobs/page-capture-jobs.tsv").exists()),
        ("sitemap_jobs", root / "research/jobs/sitemap-jobs.tsv", (root / "research/jobs/sitemap-jobs.tsv").exists()),
        ("firecrawl_validated_wave", firecrawl_wave_dir, count_json_files(firecrawl_wave_dir) > 0),
        (
            "sitemap_validated_wave",
            sitemap_wave_dir,
            sitemap_raw_dirs > 0 and count_tsv_rows(sitemap_wave_dir / "candidate_urls.tsv") > 0,
        ),
        ("analysis_chain", root / "research/analysis/analysis-chain.md", (root / "research/analysis/analysis-chain.md").exists()),
        ("analysis_prompt_pack", root / "research/analysis/analysis-prompt-pack.md", (root / "research/analysis/analysis-prompt-pack.md").exists()),
    ]

    metrics = {
        "competitor_register_rows": count_tsv_rows(root / "competitor-raw-register.tsv"),
        "organic_rows_current": count_tsv_rows(root / "research/raw/competitor-search/api-wave-02-validated-keywords/serp_results.tsv"),
        "company_footprint_rows": count_tsv_rows(root / "research/raw/company-footprint/api-wave-01-full/serp_results.tsv"),
        "competitor_footprint_rows": count_tsv_rows(root / "research/raw/competitor-footprint/api-wave-01-full/serp_results.tsv"),
        "wordstat_wave1_files": count_json_files(root / "research/semantics/nevgroup-lighting/raw/wordstat_wave1_single_token"),
        "wordstat_wave2_files": count_json_files(root / "research/semantics/nevgroup-lighting/raw/wordstat_wave2_two_token"),
        "validated_keyword_rows": count_tsv_rows(root / "research/analysis/validated-keyword-matrix.tsv"),
        "organic_job_rows": count_tsv_rows(root / "research/jobs/organic-serp-jobs.tsv"),
        "ad_job_rows": count_tsv_rows(root / "research/jobs/ad-serp-jobs.tsv"),
        "page_capture_job_rows": count_tsv_rows(root / "research/jobs/page-capture-jobs.tsv"),
        "sitemap_job_rows": count_tsv_rows(root / "research/jobs/sitemap-jobs.tsv"),
        "firecrawl_json_files": count_json_files(firecrawl_wave_dir),
        "firecrawl_error_files": len(list(firecrawl_wave_dir.glob("*.error.txt"))) if firecrawl_wave_dir.exists() else 0,
        "sitemap_site_dirs": sitemap_raw_dirs,
        "sitemap_candidate_rows": count_tsv_rows(sitemap_wave_dir / "candidate_urls.tsv"),
    }

    status = {
        "checks": [
            {"name": name, "path": str(path), "ok": ok}
            for name, path, ok in checks
        ],
        "metrics": metrics,
        "ready_for_manual_analysis": all(ok for _, _, ok in checks),
    }

    output_json = Path(args.output_json).expanduser().resolve()
    output_md = Path(args.output_md).expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Pre-Analysis Verification",
        "",
        f"Ready for manual analysis: `{'yes' if status['ready_for_manual_analysis'] else 'no'}`",
        "",
        "## Checks",
        "",
    ]
    for item in status["checks"]:
        lines.append(f"- `{item['name']}`: `{'ok' if item['ok'] else 'missing'}` -> `{item['path']}`")
    lines.extend(["", "## Metrics", ""])
    for key, value in metrics.items():
        lines.append(f"- `{key}`: `{value}`")
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"ready_for_manual_analysis": status["ready_for_manual_analysis"], **metrics}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
