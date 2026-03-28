#!/usr/bin/env python3
"""Build a JSON apply pack for text-ad rotation from a TSV review doc."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


PUNCT = set(r'.,;:!?—-()[]{}«»""\'/\\@#$%^&*+=~<>|₽')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build validated text-rotation apply pack from TSV.")
    parser.add_argument("--rotation-tsv", required=True)
    parser.add_argument("--source-ads-root", required=True)
    parser.add_argument("--ads-root", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-report", default="")
    return parser.parse_args()


def load_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_display(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def base_len(value: Any) -> int:
    return sum(1 for char in str(value or "") if char not in PUNCT)


def parse_key(value: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in str(value or "").split("|")]
    if len(parts) >= 3:
        return parts[0], parts[1], " | ".join(parts[2:]).strip()
    if len(parts) == 2:
        return parts[0], "", parts[1]
    if len(parts) == 1:
        return parts[0], "", ""
    return "", "", ""


def parse_float(value: Any) -> float:
    text = str(value or "").strip().replace(",", ".")
    if text in {"", "--"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def fit_text_base_limit(value: str, limit: int = 80) -> str:
    text = normalize_display(value)
    if base_len(text) <= limit:
        return text
    sentence_split = re_sentence_split(text)
    while len(sentence_split) > 1 and base_len(" ".join(sentence_split)) > limit:
        sentence_split = sentence_split[:-1]
    candidate = normalize_display(" ".join(sentence_split))
    if candidate and base_len(candidate) <= limit:
        return candidate
    words = candidate.split() if candidate else text.split()
    while words and base_len(" ".join(words)) > limit:
        words = words[:-1]
    return normalize_display(" ".join(words))


def re_sentence_split(value: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", str(value or "").strip())
    return [normalize_display(chunk) for chunk in chunks if normalize_display(chunk)]


def load_metrics(root: Path) -> dict[int, dict[int, dict[str, str]]]:
    result: dict[int, dict[int, dict[str, str]]] = {}
    for path in sorted(root.glob("ads_*.tsv")):
        rows = load_tsv(path)
        if not rows:
            continue
        cid = int(rows[0].get("CampaignId") or 0)
        if cid <= 0:
            continue
        result[cid] = {int(row.get("AdId") or 0): row for row in rows if int(row.get("AdId") or 0) > 0}
    return result


def select_by_perf(matches: list[dict[str, Any]], metrics: dict[int, dict[str, str]]) -> dict[str, Any]:
    def score(ad: dict[str, Any]) -> tuple[float, float, float, int]:
        row = metrics.get(int(ad.get("Id") or 0), {})
        return (
            parse_float(row.get("Cost")),
            parse_float(row.get("Clicks")),
            parse_float(row.get("Impressions")),
            int(ad.get("Id") or 0),
        )

    return sorted(matches, key=score, reverse=True)[0]


def find_matches(
    ads: list[dict[str, Any]],
    campaign_id: int,
    title: str,
    title2: str,
    text: str,
) -> list[dict[str, Any]]:
    want = (normalize(title), normalize(title2), normalize(text))
    matched = []
    for ad in ads:
        if int(ad.get("CampaignId") or 0) != campaign_id:
            continue
        text_ad = ad.get("TextAd") or {}
        got = (
            normalize(text_ad.get("Title")),
            normalize(text_ad.get("Title2")),
            normalize(text_ad.get("Text")),
        )
        if got == want:
            matched.append(ad)
    return matched


def duplicate_in_group(
    group_ads: list[dict[str, Any]],
    replace_ad_id: int,
    title: str,
    title2: str,
    text: str,
) -> dict[str, Any] | None:
    want = (normalize(title), normalize(title2), normalize(text))
    for ad in group_ads:
        if int(ad.get("Id") or 0) == replace_ad_id:
            continue
        text_ad = ad.get("TextAd") or {}
        got = (
            normalize(text_ad.get("Title")),
            normalize(text_ad.get("Title2")),
            normalize(text_ad.get("Text")),
        )
        if got == want:
            return ad
    return None


def validate_new_ad(new_ad: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    title = str(new_ad.get("Title") or "")
    title2 = str(new_ad.get("Title2") or "")
    text = str(new_ad.get("Text") or "")
    display = str(new_ad.get("DisplayUrlPath") or "")
    href = str(new_ad.get("Href") or "")
    if not title:
        errors.append("missing Title")
    if len(title) > 56:
        errors.append(f"Title len={len(title)} > 56")
    if title2 and base_len(title2) > 30:
        errors.append(f"Title2 base={base_len(title2)} > 30")
    if not text:
        errors.append("missing Text")
    if text and base_len(text) > 80:
        errors.append(f"Text base={base_len(text)} > 80")
    if display and len(display) > 20:
        errors.append(f"DisplayUrlPath len={len(display)} > 20")
    if not href.startswith("https://"):
        errors.append("Href must start with https://")
    return errors


def compact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            compacted = compact(item)
            if compacted is None:
                continue
            out[key] = compacted
        return out or None
    if isinstance(value, list):
        out = [compact(item) for item in value]
        out = [item for item in out if item is not None]
        return out or None
    if value in {"", None}:
        return None
    return value


def main() -> int:
    args = parse_args()
    rotation_tsv = Path(args.rotation_tsv).resolve()
    source_root = Path(args.source_ads_root).resolve()
    ads_root = Path(args.ads_root).resolve()
    output_json = Path(args.output_json).resolve()
    output_report = Path(args.output_report).resolve() if args.output_report else None

    rows = [row for row in load_tsv(rotation_tsv) if row.get("entity_type") == "text" and row.get("action_mode") == "create_new_ad"]
    all_ads_path = source_root / "all_source_ads.json"
    all_ads = load_json(all_ads_path) if all_ads_path.exists() else []
    metrics = load_metrics(ads_root)
    ads_by_campaign: dict[int, list[dict[str, Any]]] = defaultdict(list)
    ads_by_group: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ad in all_ads:
        cid = int(ad.get("CampaignId") or 0)
        gid = int(ad.get("AdGroupId") or 0)
        if cid > 0:
            ads_by_campaign[cid].append(ad)
        if gid > 0:
            ads_by_group[gid].append(ad)

    dedup: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    report_lines = [
        "# Text Rotation Apply Pack",
        "",
        f"- Source TSV: `{rotation_tsv}`",
        f"- Source ads root: `{source_root}`",
        "",
    ]

    for idx, row in enumerate(rows, start=1):
        campaign_id = int(row.get("campaign_id") or 0)
        campaign_name = normalize_display(row.get("campaign_name"))
        loser_title, loser_title2, loser_text = parse_key(row.get("loser_key", ""))
        winner_title, winner_title2, winner_text = parse_key(row.get("proposed_winner_key", ""))
        loser_matches = find_matches(ads_by_campaign.get(campaign_id, []), campaign_id, loser_title, loser_title2, loser_text)
        if not loser_matches:
            item = {
                "status": "FAIL",
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "row_index": idx,
                "loser_key": row.get("loser_key", ""),
                "errors": ["loser signature not found in source ads"],
            }
            dedup[(campaign_id, f"fail-{idx}", "", "")] = item
            continue

        grouped_matches: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for ad in loser_matches:
            grouped_matches[int(ad.get("AdGroupId") or 0)].append(ad)

        for adgroup_id, group_matches in grouped_matches.items():
            replace_ad = select_by_perf(group_matches, metrics.get(campaign_id, {}))
            control_matches = find_matches(
                ads_by_group.get(adgroup_id, []),
                campaign_id,
                winner_title,
                winner_title2,
                winner_text,
            )
            control_ad = select_by_perf(control_matches, metrics.get(campaign_id, {})) if control_matches else None
            replace_text_ad = replace_ad.get("TextAd") or {}
            new_ad = compact(
                {
                    "Title": normalize_display(row.get("proposed_title")),
                    "Title2": normalize_display(winner_title2) or normalize_display(replace_text_ad.get("Title2")),
                    "Text": fit_text_base_limit(str(row.get("proposed_text") or ""), 80),
                    "Href": replace_text_ad.get("Href"),
                    "DisplayUrlPath": replace_text_ad.get("DisplayUrlPath"),
                    "Mobile": replace_text_ad.get("Mobile"),
                    "SitelinkSetId": replace_text_ad.get("SitelinkSetId"),
                    "AdImageHash": replace_text_ad.get("AdImageHash"),
                    "AdExtensions": replace_text_ad.get("AdExtensions"),
                }
            )
            errors = validate_new_ad(new_ad or {})
            duplicate = duplicate_in_group(
                ads_by_group.get(adgroup_id, []),
                int(replace_ad.get("Id") or 0),
                new_ad.get("Title", ""),
                new_ad.get("Title2", ""),
                new_ad.get("Text", ""),
            )
            status = "OK"
            if errors:
                status = "FAIL"
            elif duplicate:
                status = "SKIP"
            key = (
                adgroup_id,
                normalize(new_ad.get("Title")),
                normalize(new_ad.get("Title2")),
                normalize(new_ad.get("Text")),
            )
            item = {
                "status": status,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "adgroup_id": adgroup_id,
                "adgroup_name": normalize_display((replace_ad.get("AdGroupName") or replace_ad.get("TextAd") or {}).get("Title") if False else ""),
                "row_index": idx,
                "replace_ad_id": int(replace_ad.get("Id") or 0),
                "control_ad_id": int(control_ad.get("Id") or 0) if control_ad else None,
                "new_ad": new_ad,
                "loser_key": row.get("loser_key", ""),
                "proposed_winner_key": row.get("proposed_winner_key", ""),
                "reason": row.get("reason", ""),
                "confidence": row.get("confidence", ""),
                "status_note": row.get("status_note", ""),
                "duplicate_ad_id": int(duplicate.get("Id") or 0) if duplicate else None,
                "errors": errors,
                "warnings": ([] if not duplicate else [f"new copy duplicates existing ad {duplicate.get('Id')} in group {adgroup_id}"]),
                "product_markers": [],
            }
            previous = dedup.get(key)
            if previous is None:
                dedup[key] = item
                continue
            prev_cost = parse_float((metrics.get(campaign_id, {}).get(int(previous.get("replace_ad_id") or 0), {}) or {}).get("Cost"))
            cur_cost = parse_float((metrics.get(campaign_id, {}).get(int(item.get("replace_ad_id") or 0), {}) or {}).get("Cost"))
            if cur_cost > prev_cost:
                dedup[key] = item

    items = list(dedup.values())
    items.sort(key=lambda row: (int(row.get("campaign_id") or 0), int(row.get("adgroup_id") or 0), int(row.get("replace_ad_id") or 0)))
    summary = {
        "rotation_tsv": str(rotation_tsv),
        "source_ads_root": str(source_root),
        "ads_root": str(ads_root),
        "row_count": len(rows),
        "items_total": len(items),
        "ok_count": sum(1 for row in items if row.get("status") == "OK"),
        "skip_count": sum(1 for row in items if row.get("status") == "SKIP"),
        "fail_count": sum(1 for row in items if row.get("status") == "FAIL"),
        "campaign_ids": sorted({int(row.get("campaign_id") or 0) for row in items if int(row.get("campaign_id") or 0) > 0}),
        "items": items,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_lines.extend(
        [
            f"- Source rows: `{summary['row_count']}`",
            f"- Expanded items: `{summary['items_total']}`",
            f"- OK: `{summary['ok_count']}`",
            f"- SKIP duplicate: `{summary['skip_count']}`",
            f"- FAIL: `{summary['fail_count']}`",
            "",
            "## Items",
            "",
        ]
    )
    for item in items:
        report_lines.append(
            f"- `{item.get('status')}` / `{item.get('campaign_id')}` / group `{item.get('adgroup_id')}` / "
            f"replace `{item.get('replace_ad_id')}` / new `{item.get('new_ad', {}).get('Title', '')}`"
        )
        for error in item.get("errors") or []:
            report_lines.append(f"  - ERROR: {error}")
        for warning in item.get("warnings") or []:
            report_lines.append(f"  - WARN: {warning}")
    report_text = "\n".join(report_lines).strip() + "\n"
    if output_report:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(report_text, encoding="utf-8")

    print(json.dumps({"ok": True, "output": str(output_json), "summary": {k: summary[k] for k in ("ok_count", "skip_count", "fail_count", "items_total")}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
