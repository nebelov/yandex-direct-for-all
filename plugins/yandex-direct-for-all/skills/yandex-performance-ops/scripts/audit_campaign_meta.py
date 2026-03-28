#!/usr/bin/env python3
"""Summarize campaign meta from campaigns.get snapshots.

Useful for quick settings/schedule audits from a saved campaigns_meta.json bundle.
"""

import argparse
import json
import sys
from pathlib import Path


def parse_schedule_items(items):
    summary = []
    for raw in items or []:
        parts = raw.split(",")
        if len(parts) < 25:
            continue
        day = int(parts[0])
        weights = [int(x) for x in parts[1:25]]
        summary.append((day, min(weights), max(weights)))
    return summary


def settings_map(items):
    return {item.get("Option"): item.get("Value") for item in items or []}


def format_schedule(summary):
    if not summary:
        return "none"
    chunks = []
    for day, min_w, max_w in summary:
        chunks.append(f"{day}:{min_w}-{max_w}")
    return ";".join(chunks)


def main():
    parser = argparse.ArgumentParser(description="Audit saved campaigns_meta.json")
    parser.add_argument("--input", required=True, help="Path to campaigns_meta.json")
    parser.add_argument("--campaign-ids", default="", help="Comma-separated campaign ids")
    parser.add_argument("--output", default="", help="Optional TSV output path")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    campaigns = data.get("result", {}).get("Campaigns", [])
    wanted = None
    if args.campaign_ids.strip():
        wanted = {int(x.strip()) for x in args.campaign_ids.split(",") if x.strip()}

    lines = [
        "\t".join(
            [
                "campaign_id",
                "name",
                "budget_rub",
                "excluded_sites",
                "tracking_params",
                "alt_texts",
                "area_of_interest",
                "exact_phrase",
                "search_strategy",
                "network_strategy",
                "schedule_minmax",
            ]
        )
    ]

    for campaign in campaigns:
        cid = campaign.get("Id")
        if wanted and cid not in wanted:
            continue
        uc = campaign.get("UnifiedCampaign", {})
        settings = settings_map(uc.get("Settings", []))
        schedule = format_schedule(parse_schedule_items((campaign.get("TimeTargeting") or {}).get("Schedule", {}).get("Items", [])))
        budget = ((campaign.get("DailyBudget") or {}).get("Amount") or 0) // 1_000_000
        excluded_sites = len((campaign.get("ExcludedSites") or []))
        row = [
            str(cid),
            campaign.get("Name", ""),
            str(budget),
            str(excluded_sites),
            "yes" if uc.get("TrackingParams") else "no",
            settings.get("ALTERNATIVE_TEXTS_ENABLED", ""),
            settings.get("ENABLE_AREA_OF_INTEREST_TARGETING", ""),
            settings.get("CAMPAIGN_EXACT_PHRASE_MATCHING_ENABLED", ""),
            ((uc.get("BiddingStrategy") or {}).get("Search") or {}).get("BiddingStrategyType", ""),
            ((uc.get("BiddingStrategy") or {}).get("Network") or {}).get("BiddingStrategyType", ""),
            schedule,
        ]
        lines.append("\t".join(row))

    text = "\n".join(lines) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
