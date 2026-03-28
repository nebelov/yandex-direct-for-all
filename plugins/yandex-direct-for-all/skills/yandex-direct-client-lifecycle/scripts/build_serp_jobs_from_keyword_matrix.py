#!/usr/bin/env python3
"""Build organic/ad discovery jobs from a validated keyword x geo matrix."""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


ORGANIC_HEADER = [
    "job_id",
    "layer",
    "purpose",
    "search_query",
    "search_region",
    "region_id",
    "page",
    "groups_on_page",
    "docs_in_group",
    "search_type",
    "l10n",
    "response_format",
    "group_mode",
    "family_mode",
    "fix_typo_mode",
    "sort_mode",
    "sort_order",
    "max_passages",
    "x_forwarded_for_y",
    "user_agent",
    "enabled",
    "notes",
]

AD_HEADER = [
    "job_id",
    "layer",
    "purpose",
    "search_query",
    "search_region",
    "region_id",
    "enabled",
    "notes",
]


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def slugify(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "-", value.strip().lower())
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:80] or "item"


def is_enabled(value: str | None, default: bool = True) -> bool:
    normalized = clean(value)
    if not normalized:
        return default
    return normalized.lower() not in {"0", "false", "no", "off", "disabled"}


def truthy(value: str | None, default: bool = True) -> bool:
    normalized = clean(value).lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on", "accepted", "accept"}


@dataclass
class KeywordRow:
    keyword_id: str
    cluster: str
    keyword: str
    intent: str
    status: str
    collect_organic: bool
    collect_ad: bool
    notes: str


@dataclass
class GeoRow:
    geo_code: str
    geo_label: str
    region_id: str
    enabled: bool


def read_keyword_matrix(path: Path) -> list[KeywordRow]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"cluster", "keyword", "status"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"keyword matrix missing columns: {sorted(missing)}")
        rows: list[KeywordRow] = []
        for index, row in enumerate(reader, start=1):
            keyword = clean(row.get("keyword"))
            if not keyword:
                continue
            status = clean(row.get("status")).lower()
            if status not in {"accepted", "accept", "active"}:
                continue
            cluster = clean(row.get("cluster")) or "general"
            rows.append(
                KeywordRow(
                    keyword_id=clean(row.get("keyword_id")) or f"kw-{index:03d}",
                    cluster=cluster,
                    keyword=keyword,
                    intent=clean(row.get("intent")) or "commercial",
                    status=status,
                    collect_organic=truthy(row.get("collect_organic"), True),
                    collect_ad=truthy(row.get("collect_ad"), True),
                    notes=clean(row.get("notes")),
                )
            )
    return rows


def read_geo_matrix(path: Path) -> list[GeoRow]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"geo_code", "geo_label", "region_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"geo matrix missing columns: {sorted(missing)}")
        rows: list[GeoRow] = []
        for row in reader:
            if not is_enabled(row.get("enabled"), True):
                continue
            region_id = clean(row.get("region_id"))
            geo_code = clean(row.get("geo_code"))
            if not region_id or not geo_code:
                continue
            rows.append(
                GeoRow(
                    geo_code=geo_code,
                    geo_label=clean(row.get("geo_label")) or geo_code,
                    region_id=region_id,
                    enabled=True,
                )
            )
    return rows


def organic_row(keyword: KeywordRow, geo: GeoRow) -> dict[str, str]:
    return {
        "job_id": f"org-{geo.geo_code}-{slugify(keyword.cluster)}-{slugify(keyword.keyword_id)}",
        "layer": "organic_serp",
        "purpose": "competitor_discovery",
        "search_query": keyword.keyword,
        "search_region": geo.geo_code,
        "region_id": geo.region_id,
        "page": "0",
        "groups_on_page": "20",
        "docs_in_group": "1",
        "search_type": "SEARCH_TYPE_RU",
        "l10n": "LOCALIZATION_RU",
        "response_format": "FORMAT_XML",
        "group_mode": "GROUP_MODE_FLAT",
        "family_mode": "FAMILY_MODE_MODERATE",
        "fix_typo_mode": "FIX_TYPO_MODE_ON",
        "sort_mode": "SORT_MODE_BY_RELEVANCE",
        "sort_order": "SORT_ORDER_DESC",
        "max_passages": "4",
        "x_forwarded_for_y": "",
        "user_agent": "",
        "enabled": "1",
        "notes": clean(f"{keyword.cluster}; {keyword.intent}; {geo.geo_label}; {keyword.notes}").strip("; "),
    }


def ad_row(keyword: KeywordRow, geo: GeoRow) -> dict[str, str]:
    return {
        "job_id": f"ads-{geo.geo_code}-{slugify(keyword.cluster)}-{slugify(keyword.keyword_id)}",
        "layer": "ad_serp",
        "purpose": "competitor_ads_capture",
        "search_query": keyword.keyword,
        "search_region": geo.geo_code,
        "region_id": geo.region_id,
        "enabled": "1",
        "notes": clean(f"{keyword.cluster}; {keyword.intent}; {geo.geo_label}; {keyword.notes}").strip("; "),
    }


def write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyword-matrix", required=True)
    parser.add_argument("--geo-matrix", required=True)
    parser.add_argument("--organic-out", required=True)
    parser.add_argument("--ad-out")
    args = parser.parse_args()

    keywords = read_keyword_matrix(Path(args.keyword_matrix).expanduser().resolve())
    geos = read_geo_matrix(Path(args.geo_matrix).expanduser().resolve())

    organic_rows: list[dict[str, str]] = []
    ad_rows: list[dict[str, str]] = []
    for keyword in keywords:
        for geo in geos:
            if keyword.collect_organic:
                organic_rows.append(organic_row(keyword, geo))
            if keyword.collect_ad:
                ad_rows.append(ad_row(keyword, geo))

    write_tsv(Path(args.organic_out).expanduser().resolve(), ORGANIC_HEADER, organic_rows)
    if args.ad_out:
        write_tsv(Path(args.ad_out).expanduser().resolve(), AD_HEADER, ad_rows)

    print(
        f"keywords={len(keywords)} geos={len(geos)} "
        f"organic_jobs={len(organic_rows)} ad_jobs={len(ad_rows) if args.ad_out else 0}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
