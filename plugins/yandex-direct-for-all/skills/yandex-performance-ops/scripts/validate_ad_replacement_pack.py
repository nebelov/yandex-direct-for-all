#!/usr/bin/env python3
"""Validate markdown ad replacement pack against source ads and text limits."""

import argparse
import csv
import json
import re
import sys
from pathlib import Path


ENTRY_RE = re.compile(r"^### `(?P<campaign_id>\d+)` / AdGroup `(?P<adgroup_id>\d+)` / replace `(?P<replace_ad_id>\d+)`$")
CONTROL_RE = re.compile(r"^- Control ad: `(?P<control_ad_id>\d+)`$")
FIELD_RE = re.compile(r"^- `(?P<field>[^`]+)`: (?P<value>.+)$")


def normalize_text(value):
    return " ".join((value or "").strip().lower().split())


def base_len(value):
    punct = set(r'.,;:!?—-()[]{}«»""\'/\\@#$%^&*+=~<>|₽')
    return sum(1 for char in value if char not in punct)


def parse_replacement_pack(path):
    section = ""
    current = None
    entries = []
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        match = ENTRY_RE.match(line)
        if match:
            if current:
                entries.append(current)
            current = {
                "section": section,
                "campaign_id": int(match.group("campaign_id")),
                "adgroup_id": int(match.group("adgroup_id")),
                "replace_ad_id": int(match.group("replace_ad_id")),
                "fields": {},
            }
            continue
        if not current:
            continue
        match = CONTROL_RE.match(line)
        if match:
            current["control_ad_id"] = int(match.group("control_ad_id"))
            continue
        match = FIELD_RE.match(line)
        if match:
            field = match.group("field").strip()
            value = match.group("value").strip()
            if value.startswith("`") and value.endswith("`"):
                value = value[1:-1]
            current["fields"][field] = value
    if current:
        entries.append(current)
    return entries


def load_source_ads(root, campaign_id):
    path = Path(root) / f"source_ads_{campaign_id}.json"
    ads = json.loads(path.read_text(encoding="utf-8"))
    by_id = {}
    by_group = {}
    for ad in ads:
        ad_id = int(ad["Id"])
        by_id[ad_id] = ad
        by_group.setdefault(int(ad["AdGroupId"]), []).append(ad)
    return path, by_id, by_group


def load_ads_perf(root, campaign_id):
    path = Path(root) / f"ads_{campaign_id}.tsv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return {int(row["AdId"]): row for row in reader}


def resolve_href(raw_value, source_ad):
    source_href = ((source_ad or {}).get("TextAd") or {}).get("Href") or ""
    if raw_value.lower().startswith("оставить текущий"):
        return source_href
    return raw_value


def validate_entry(entry, source_root, ads_root):
    campaign_id = entry["campaign_id"]
    adgroup_id = entry["adgroup_id"]
    replace_id = entry["replace_ad_id"]
    control_id = entry.get("control_ad_id")
    fields = entry.get("fields", {})
    errors = []
    warnings = []

    source_path, by_id, by_group = load_source_ads(source_root, campaign_id)
    perf = load_ads_perf(ads_root, campaign_id)
    replace_ad = by_id.get(replace_id)
    control_ad = by_id.get(control_id) if control_id else None

    if not replace_ad:
        errors.append(f"replace ad {replace_id} missing in {source_path.name}")
    if not control_ad:
        errors.append(f"control ad {control_id} missing in {source_path.name}")
    if replace_ad and int(replace_ad.get("AdGroupId", -1)) != adgroup_id:
        errors.append(f"replace ad {replace_id} belongs to group {replace_ad.get('AdGroupId')}, not {adgroup_id}")
    if control_ad and int(control_ad.get("AdGroupId", -1)) != adgroup_id:
        errors.append(f"control ad {control_id} belongs to group {control_ad.get('AdGroupId')}, not {adgroup_id}")
    if control_id == replace_id:
        errors.append("control ad equals replace ad")

    title = fields.get("Title", "")
    title2 = fields.get("Title2", "")
    text = fields.get("Text", "")
    display_path = fields.get("DisplayUrlPath", "")
    href_raw = fields.get("Href", "")
    href = resolve_href(href_raw, replace_ad)

    if not title:
        errors.append("missing Title")
    if len(title) > 56:
        errors.append(f"Title len={len(title)} > 56")
    if title2 and base_len(title2) > 30:
        errors.append(f"Title2 base={base_len(title2)} > 30")
    if text and base_len(text) > 80:
        errors.append(f"Text base={base_len(text)} > 80")
    if not text:
        errors.append("missing Text")
    if display_path and len(display_path) > 20:
        errors.append(f"DisplayUrlPath len={len(display_path)} > 20")
    if not href:
        errors.append("Href is empty after resolve")
    elif not href.startswith("https://"):
        errors.append("Href must start with https:// or inherit from source ad")

    current_group_ads = by_group.get(adgroup_id, [])
    signature = (normalize_text(title), normalize_text(title2), normalize_text(text))
    for ad in current_group_ads:
        if int(ad["Id"]) == replace_id:
            continue
        text_ad = ad.get("TextAd") or {}
        existing_signature = (
            normalize_text(text_ad.get("Title")),
            normalize_text(text_ad.get("Title2")),
            normalize_text(text_ad.get("Text")),
        )
        if signature == existing_signature:
            errors.append(f"new copy duplicates existing ad {ad['Id']} in group {adgroup_id}")
            break

    if replace_ad:
        replace_text_ad = replace_ad.get("TextAd") or {}
        if normalize_text(title) == normalize_text(replace_text_ad.get("Title")):
            warnings.append("Title matches replace ad title; verify copy is materially different")
        if normalize_text(text) == normalize_text(replace_text_ad.get("Text")):
            warnings.append("Text matches replace ad text; verify copy is materially different")

    resolved = {
        "campaign_id": campaign_id,
        "adgroup_id": adgroup_id,
        "section": entry["section"],
        "replace_ad_id": replace_id,
        "control_ad_id": control_id,
        "new_ad": {
            "Title": title,
            "Title2": title2 or None,
            "Text": text,
            "Href": href,
            "DisplayUrlPath": display_path or None,
            "Mobile": ((replace_ad or control_ad or {}).get("TextAd") or {}).get("Mobile"),
            "SitelinkSetId": ((replace_ad or control_ad or {}).get("TextAd") or {}).get("SitelinkSetId"),
            "AdImageHash": ((replace_ad or control_ad or {}).get("TextAd") or {}).get("AdImageHash"),
            "AdExtensions": ((replace_ad or control_ad or {}).get("TextAd") or {}).get("AdExtensions"),
        },
        "replace_perf": perf.get(replace_id),
        "control_perf": perf.get(control_id) if control_id else None,
        "errors": errors,
        "warnings": warnings,
    }
    resolved["status"] = "FAIL" if errors else "OK"
    return resolved


def render_text(results):
    lines = []
    for result in results:
        lines.append(
            f"{result['status']}\tsection={result['section']}\tcampaign={result['campaign_id']}\t"
            f"group={result['adgroup_id']}\treplace={result['replace_ad_id']}\tcontrol={result['control_ad_id']}"
        )
        new_ad = result["new_ad"]
        lines.append(
            "  INFO\t"
            f"title_len={len(new_ad['Title'])}\ttitle2_base={base_len(new_ad['Title2'] or '')}\t"
            f"text_base={base_len(new_ad['Text'])}\tdisplay_len={len(new_ad['DisplayUrlPath'] or '')}"
        )
        for error in result.get("errors", []):
            lines.append(f"  ERROR\t{error}")
        for warning in result.get("warnings", []):
            lines.append(f"  WARN\t{warning}")
    return "\n".join(lines) + ("\n" if lines else "")


def main():
    parser = argparse.ArgumentParser(description="Validate markdown ad replacement pack")
    parser.add_argument("--pack-md", required=True, help="Path to AD_REPLACEMENT_PACK markdown")
    parser.add_argument("--source-ads-root", required=True, help="Directory with source_ads_<cid>.json")
    parser.add_argument("--ads-root", required=True, help="Directory with ads_<cid>.tsv")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    entries = parse_replacement_pack(args.pack_md)
    if not entries:
        sys.stderr.write("No entries parsed from replacement pack\n")
        sys.exit(1)

    results = [validate_entry(entry, args.source_ads_root, args.ads_root) for entry in entries]
    sys.stdout.write(render_text(results))
    if args.output:
        Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(1 if any(result["status"] != "OK" for result in results) else 0)


if __name__ == "__main__":
    main()
