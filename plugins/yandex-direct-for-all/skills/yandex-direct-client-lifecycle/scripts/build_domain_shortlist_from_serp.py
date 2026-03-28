#!/usr/bin/env python3
"""Собрать сводку доменов по подтвержденной поисковой выдаче Яндекса."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


def clean(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_domain(value: str | None) -> str:
    domain = clean(value).lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def read_lines(path: Path) -> list[str]:
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = clean(line)
        if not value or value.startswith("#"):
            continue
        items.append(value)
    return items


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"search_query", "search_region", "result_rank", "result_domain", "source_url"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"serp results missing columns: {sorted(missing)}")
        return list(reader)


def write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def is_excluded_domain(domain: str, excluded: list[str]) -> bool:
    for blocked in excluded:
        if domain == blocked or domain.endswith("." + blocked):
            return True
    return False


def url_matches_patterns(url: str, patterns: list[str]) -> bool:
    text = clean(url).lower()
    return any(pattern.lower() in text for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serp-results", required=True)
    parser.add_argument("--output-tsv", required=True)
    parser.add_argument("--top-domains-file")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--max-rank-per-query-region", type=int, default=15)
    parser.add_argument("--exclude-domain", action="append", default=[])
    parser.add_argument("--exclude-domains-file")
    parser.add_argument("--exclude-url-pattern", action="append", default=[])
    parser.add_argument("--exclude-url-patterns-file")
    args = parser.parse_args()

    rows = read_rows(Path(args.serp_results).expanduser().resolve())

    excluded_domains = [normalize_domain(item) for item in args.exclude_domain]
    if args.exclude_domains_file:
        excluded_domains.extend(
            normalize_domain(item)
            for item in read_lines(Path(args.exclude_domains_file).expanduser().resolve())
        )

    excluded_patterns = list(args.exclude_url_pattern)
    if args.exclude_url_patterns_file:
        excluded_patterns.extend(read_lines(Path(args.exclude_url_patterns_file).expanduser().resolve()))

    query_region_domain_best_rank: dict[tuple[str, str, str], int] = {}
    domain_rows: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        query = clean(row.get("search_query"))
        region = clean(row.get("search_region"))
        domain = normalize_domain(row.get("result_domain"))
        url = clean(row.get("source_url"))
        if not query or not region or not domain or not url:
            continue
        if is_excluded_domain(domain, excluded_domains):
            continue
        if url_matches_patterns(url, excluded_patterns):
            continue
        try:
            rank = int(clean(row.get("result_rank")) or "999999")
        except ValueError:
            rank = 999999
        if rank > args.max_rank_per_query_region:
            continue
        key = (query, region, domain)
        current = query_region_domain_best_rank.get(key)
        if current is None or rank < current:
            query_region_domain_best_rank[key] = rank
        domain_rows[domain].append(row)

    aggregated: list[dict[str, str]] = []
    for domain, kept_rows in domain_rows.items():
        pair_ranks = {
            pair: rank for pair, rank in query_region_domain_best_rank.items() if pair[2] == domain
        }
        queries: list[str] = []
        query_seen: set[str] = set()
        regions: list[str] = []
        region_seen: set[str] = set()
        sample_urls: list[str] = []
        sample_url_seen: set[str] = set()
        for row in kept_rows:
            query = clean(row.get("search_query"))
            region = clean(row.get("search_region"))
            url = clean(row.get("source_url"))
            if query and query not in query_seen:
                query_seen.add(query)
                queries.append(query)
            if region and region not in region_seen:
                region_seen.add(region)
                regions.append(region)
            if url and url not in sample_url_seen and len(sample_urls) < 5:
                sample_url_seen.add(url)
                sample_urls.append(url)

        pair_values = list(pair_ranks.values())
        avg_rank = sum(pair_values) / len(pair_values) if pair_values else 0.0
        aggregated.append(
            {
                "domain": domain,
                "query_region_pairs": str(len(pair_values)),
                "unique_queries": str(len(queries)),
                "unique_regions": str(len(regions)),
                "rows_kept": str(len(kept_rows)),
                "best_rank": str(min(pair_values) if pair_values else 0),
                "avg_best_rank": f"{avg_rank:.2f}",
                "sample_queries": " | ".join(queries[:5]),
                "sample_urls": " | ".join(sample_urls),
            }
        )

    aggregated.sort(
        key=lambda item: (
            -int(item["query_region_pairs"]),
            -int(item["unique_queries"]),
            -int(item["unique_regions"]),
            float(item["avg_best_rank"]),
            item["domain"],
        )
    )

    output_tsv = Path(args.output_tsv).expanduser().resolve()
    write_tsv(
        output_tsv,
        [
            "domain",
            "query_region_pairs",
            "unique_queries",
            "unique_regions",
            "rows_kept",
            "best_rank",
            "avg_best_rank",
            "sample_queries",
            "sample_urls",
        ],
        aggregated,
    )

    if args.top_domains_file:
        top_domains = [row["domain"] for row in aggregated[: max(args.top_n, 0)]]
        top_path = Path(args.top_domains_file).expanduser().resolve()
        top_path.parent.mkdir(parents=True, exist_ok=True)
        top_path.write_text("\n".join(top_domains) + ("\n" if top_domains else ""), encoding="utf-8")

    print(
        f"domains={len(aggregated)} top_n={args.top_n} "
        f"max_rank_per_query_region={args.max_rank_per_query_region}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
