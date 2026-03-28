#!/usr/bin/env python3
"""Build page-capture and sitemap batch jobs from raw organic SERP rows."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


PAGE_CAPTURE_HEADER = [
    "capture_id",
    "source_url",
    "brand",
    "keyword",
    "layer",
    "enabled",
    "notes",
]

SITEMAP_HEADER = [
    "site_id",
    "base_url",
    "include_keywords",
    "enabled",
    "notes",
]


def clean(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "-", value.strip().lower())
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:80] or "item"


def normalize_domain(domain: str) -> str:
    domain = clean(domain).lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def read_exclude_domains(path: Path) -> list[str]:
    domains: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = clean(line)
        if not value or value.startswith("#"):
            continue
        domains.append(normalize_domain(value))
    return domains


def read_patterns(path: Path) -> list[str]:
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = clean(line)
        if not value or value.startswith("#"):
            continue
        patterns.append(value)
    return patterns


def is_excluded(domain: str, excluded: list[str]) -> bool:
    normalized = normalize_domain(domain)
    for blocked in excluded:
        if normalized == blocked or normalized.endswith("." + blocked):
            return True
    return False


def url_matches_patterns(url: str, patterns: list[str]) -> bool:
    text = clean(url).lower()
    return any(pattern.lower() in text for pattern in patterns)


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


def path_tokens(url: str) -> list[str]:
    parsed = urlparse(url)
    raw = re.split(r"[/_.?=&%-]+", parsed.path.lower())
    tokens: list[str] = []
    for item in raw:
        token = clean(item)
        if not token or len(token) < 4:
            continue
        if token.isdigit():
            continue
        if token in {"html", "php", "catalog", "articles", "article", "blog", "shop", "support", "upload", "news"}:
            continue
        tokens.append(token)
    return tokens


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serp-results", required=True)
    parser.add_argument("--page-capture-out", required=True)
    parser.add_argument("--sitemap-out", required=True)
    parser.add_argument("--exclude-domain", action="append", default=[])
    parser.add_argument("--exclude-domains-file")
    parser.add_argument("--allow-domains-file")
    parser.add_argument("--exclude-url-pattern", action="append", default=[])
    parser.add_argument("--exclude-url-patterns-file")
    parser.add_argument("--top-results-per-query-geo", type=int, default=10)
    parser.add_argument("--max-urls-per-domain", type=int, default=2)
    parser.add_argument("--max-domains", type=int, default=None)
    args = parser.parse_args()

    rows = read_rows(Path(args.serp_results).expanduser().resolve())
    excluded = [normalize_domain(item) for item in args.exclude_domain]
    if args.exclude_domains_file:
        excluded.extend(read_exclude_domains(Path(args.exclude_domains_file).expanduser().resolve()))
    allowed: set[str] | None = None
    if args.allow_domains_file:
        allowed = set(read_exclude_domains(Path(args.allow_domains_file).expanduser().resolve()))
    exclude_url_patterns = list(args.exclude_url_pattern)
    if args.exclude_url_patterns_file:
        exclude_url_patterns.extend(read_patterns(Path(args.exclude_url_patterns_file).expanduser().resolve()))

    query_geo_seen: dict[tuple[str, str], int] = defaultdict(int)
    domain_payload: dict[str, dict[str, object]] = {}

    for row in sorted(rows, key=lambda item: (item["search_query"], item["search_region"], int(item["result_rank"] or "999999"))):
        query = clean(row.get("search_query"))
        geo = clean(row.get("search_region"))
        key = (query, geo)
        query_geo_seen[key] += 1
        if query_geo_seen[key] > args.top_results_per_query_geo:
            continue

        domain = normalize_domain(row.get("result_domain", ""))
        source_url = clean(row.get("source_url"))
        if not domain or not source_url or is_excluded(domain, excluded):
            continue
        if allowed is not None and domain not in allowed:
            continue
        if url_matches_patterns(source_url, exclude_url_patterns):
            continue

        payload = domain_payload.setdefault(
            domain,
            {
                "first_url": source_url,
                "scheme": urlparse(source_url).scheme or "https",
                "keywords": [],
                "keyword_seen": set(),
                "regions": [],
                "region_seen": set(),
                "urls": [],
                "url_seen": set(),
                "path_tokens": [],
                "path_token_seen": set(),
            },
        )

        if source_url not in payload["url_seen"] and len(payload["urls"]) < args.max_urls_per_domain:
            payload["url_seen"].add(source_url)
            payload["urls"].append(source_url)

        for token in path_tokens(source_url):
            if token not in payload["path_token_seen"]:
                payload["path_token_seen"].add(token)
                payload["path_tokens"].append(token)

        if query and query not in payload["keyword_seen"]:
            payload["keyword_seen"].add(query)
            payload["keywords"].append(query)

        if geo and geo not in payload["region_seen"]:
            payload["region_seen"].add(geo)
            payload["regions"].append(geo)

    page_rows: list[dict[str, str]] = []
    sitemap_rows: list[dict[str, str]] = []
    capture_index = 1

    domains = sorted(
        domain_payload,
        key=lambda domain: (
            -len(domain_payload[domain]["keywords"]),
            -len(domain_payload[domain]["regions"]),
            domain,
        ),
    )
    if args.max_domains is not None:
        domains = domains[: max(args.max_domains, 0)]

    for domain in domains:
        payload = domain_payload[domain]
        keywords = payload["keywords"]
        regions = payload["regions"]
        urls = payload["urls"]
        keyword_tokens = payload["path_tokens"]
        base_url = f"{payload['scheme']}://{domain}"
        notes = clean(
            f"domain={domain}; keywords={', '.join(keywords[:8])}; path_tokens={', '.join(keyword_tokens[:12])}; geos={', '.join(regions[:8])}; source=validated-organic-serp"
        )

        sitemap_rows.append(
            {
                "site_id": slugify(domain),
                "base_url": base_url,
                "include_keywords": ",".join(keyword_tokens[:16]),
                "enabled": "1",
                "notes": notes,
            }
        )

        for url in urls:
            page_rows.append(
                {
                    "capture_id": f"kw-{capture_index:03d}",
                    "source_url": url,
                    "brand": domain,
                    "keyword": keywords[0] if keywords else "",
                    "layer": "organic_serp",
                    "enabled": "1",
                    "notes": notes,
                }
            )
            capture_index += 1

    write_tsv(Path(args.page_capture_out).expanduser().resolve(), PAGE_CAPTURE_HEADER, page_rows)
    write_tsv(Path(args.sitemap_out).expanduser().resolve(), SITEMAP_HEADER, sitemap_rows)
    print(
        f"domains={len(sitemap_rows)} page_capture_jobs={len(page_rows)} "
        f"top_results_per_query_geo={args.top_results_per_query_geo} max_urls_per_domain={args.max_urls_per_domain}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
