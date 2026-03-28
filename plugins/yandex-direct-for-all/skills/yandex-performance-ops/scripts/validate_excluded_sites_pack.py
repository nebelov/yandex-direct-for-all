#!/usr/bin/env python3
"""Validate RSYA ExcludedSites after-packs against baseline snapshots."""

import argparse
import csv
import json
import re
import sys
from pathlib import Path


ROOT_DOMAIN_BLOCKLIST = {"yandex.ru", "ya.ru"}
PACKAGE_LIKE_RE = re.compile(r"^(?:com|ru|io|net|org|air)\.[a-z0-9_.-]+$", re.IGNORECASE)
DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$", re.IGNORECASE)
VPN_HINTS = ("vpn", "proxy", "unblock", "secure")
GAME_HINTS = (
    "game", "games", "puzzle", "match", "solitaire", "mahjong", "craft",
    "simulator", "chess", "checkers", "durak", "bubble", "rope", "birdsort",
    "jigsaw", "coloring", "arrowout", "block", "line98", "deeer", "stress",
)
DEFAULT_FORMULA = {
    "vpn_block": {"min_clicks": 3, "min_cost": 20.0, "min_ctr": 10.0},
    "retarget_app_block": {"min_clicks": 5, "min_cost": 20.0, "min_ctr": 10.0},
    "prospecting_app_block": {"min_clicks": 8, "min_cost": 60.0, "min_ctr": 12.0},
    "retarget_site_block": {"min_clicks": 3, "min_cost": 35.0, "min_ctr": 5.0},
    "prospecting_site_block": {"min_clicks": 4, "min_cost": 70.0, "min_ctr": 5.0},
}


def load_campaigns(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        campaigns = data.get("result", {}).get("Campaigns", [])
    elif isinstance(data, list):
        campaigns = data
    else:
        campaigns = []
    result = {}
    for campaign in campaigns:
        if not isinstance(campaign, dict):
            continue
        cid = campaign.get("Id")
        if cid is None:
            continue
        raw = campaign.get("ExcludedSites")
        if isinstance(raw, dict):
            items = raw.get("Items") or []
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        result[int(cid)] = {
            "name": campaign.get("Name", ""),
            "excluded_sites": [str(x).strip() for x in items if str(x).strip()],
        }
    return result


def load_placements(placements_root, campaign_id):
    if not placements_root:
        return {}
    root = Path(placements_root)
    candidates = [root / f"placements_{campaign_id}.tsv", root / "all_placements.tsv"]
    rows = {}
    for path in candidates:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                if str(row.get("CampaignId", "")).strip() != str(campaign_id):
                    continue
                placement = str(row.get("Placement", "")).strip()
                if not placement:
                    continue
                rows[placement] = row
        if rows:
            break
    return rows


def load_rules(path):
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_float(value):
    raw = str(value or "").strip()
    if raw in {"", "--"}:
        return None
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def extract_prefixed_metric(row, prefix, zero_for_dash=False):
    for key, value in row.items():
        if str(key).startswith(prefix):
            raw = str(value or "").strip()
            if zero_for_dash and raw in {"", "--"}:
                return 0.0
            return parse_float(value)
    return None


def classify_app_like(site):
    site_l = site.lower()
    if "vpn" in site_l:
        return True
    if site_l.endswith(".app"):
        return True
    if site_l.startswith(("com.", "ru.", "app.", "org.")) and ".android" in site_l:
        return True
    if ".browser" in site_l or "browser" in site_l:
        return True
    if site_l.count(".") >= 2 and site_l.startswith(("com.", "ru.", "app.")) and "/" not in site_l:
        return True
    return False


def normalize(value):
    return str(value or "").strip().casefold()


def is_retarget_campaign(campaign_name):
    text = normalize(campaign_name)
    return "ретаргет" in text or "retarget" in text


def classify_placement(site, rules):
    placement_norm = normalize(site)
    labels = set()
    if placement_norm in {normalize(item) for item in rules.get("safe_exact_placements", [])}:
        labels.add("exact_safe_block")
    if placement_norm in {normalize(item) for item in rules.get("yandex_root_blocklist", [])}:
        labels.add("yandex_root")
    if any(hint in placement_norm for hint in map(normalize, rules.get("protected_platform_hints", []))):
        labels.add("protected")
    if any(hint in placement_norm for hint in map(normalize, rules.get("yandex_hints", []))):
        labels.add("yandex")
    if PACKAGE_LIKE_RE.match(placement_norm):
        labels.add("app_like")
    elif DOMAIN_RE.match(placement_norm):
        labels.add("site")
    if any(hint in placement_norm for hint in VPN_HINTS):
        labels.add("vpn")
    if any(hint in placement_norm for hint in GAME_HINTS):
        labels.add("game")
    if any(hint in placement_norm for hint in map(normalize, rules.get("content_hints", []))):
        labels.add("content")
    return labels


def formula_allows(site, row, campaign_name, rules):
    formula = dict(DEFAULT_FORMULA)
    formula.update((rules.get("tail_formula_v3") or {}))
    clicks = parse_float(row.get("Clicks")) or 0.0
    ctr = parse_float(row.get("Ctr")) or 0.0
    cost = parse_float(row.get("Cost")) or 0.0
    conversions = extract_prefixed_metric(row, "Conversions", zero_for_dash=True) or 0.0
    labels = classify_placement(site, rules)
    if conversions > 0:
        return False, f"{site}: conversions={conversions:g} > 0, blocking forbidden"
    if labels & {"protected", "yandex", "yandex_root"}:
        return False, f"{site}: protected/yandex inventory cannot be auto-blocked by formula gate"
    if "exact_safe_block" in labels:
        return True, ""
    if "vpn" in labels:
        cfg = formula["vpn_block"]
        ok = clicks >= cfg["min_clicks"] or cost >= cfg["min_cost"] or (clicks >= 2 and ctr >= cfg["min_ctr"])
        if not ok:
            return False, f"{site}: does not pass vpn_block formula"
        return True, ""
    retarget = is_retarget_campaign(campaign_name)
    if "app_like" in labels:
        cfg = formula["retarget_app_block" if retarget else "prospecting_app_block"]
        ok = clicks >= cfg["min_clicks"] or cost >= cfg["min_cost"] or (clicks >= 3 and ctr >= cfg["min_ctr"])
        if not ok:
            return False, f"{site}: does not pass {'retarget' if retarget else 'prospecting'} app formula"
        return True, ""
    if labels & {"site", "content", "game"}:
        cfg = formula["retarget_site_block" if retarget else "prospecting_site_block"]
        ok = (clicks >= cfg["min_clicks"] and cost >= cfg["min_cost"]) or (clicks >= max(cfg["min_clicks"], 3) and ctr >= cfg["min_ctr"])
        if not ok:
            return False, f"{site}: does not pass {'retarget' if retarget else 'prospecting'} site formula"
        return True, ""
    return False, f"{site}: placement not classified into a formula risk lane"


def validate_pack(pack_path, campaigns, placements_root, rules):
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    cid = int(pack["campaign_id"])
    baseline = campaigns.get(cid)
    errors = []
    warnings = []
    info = []

    if not baseline:
        errors.append(f"campaign {cid} missing in baseline campaigns_meta")
        return {
            "pack": str(pack_path),
            "campaign_id": cid,
            "status": "FAIL",
            "errors": errors,
            "warnings": warnings,
            "info": info,
        }

    current_items = baseline["excluded_sites"]
    current_set = set(current_items)
    add_sites = [str(x).strip() for x in (pack.get("add_sites") or []) if str(x).strip()]
    after_items = [str(x).strip() for x in (pack.get("after_items") or []) if str(x).strip()]
    after_set = set(after_items)
    add_set = set(add_sites)
    expected_after = current_set | add_set
    placements = load_placements(placements_root, cid)

    if pack.get("current_count") != len(current_items):
        errors.append(f"current_count mismatch: pack={pack.get('current_count')} baseline={len(current_items)}")
    if pack.get("after_count") != len(after_items):
        errors.append(f"after_count mismatch: pack={pack.get('after_count')} actual={len(after_items)}")
    if len(after_items) != len(after_set):
        errors.append("after_items contains duplicates")
    if len(add_sites) != len(add_set):
        errors.append("add_sites contains duplicates")
    if missing := sorted(add_set - after_set):
        errors.append(f"add_sites missing in after_items: {', '.join(missing)}")
    if already := sorted(add_set & current_set):
        errors.append(f"add_sites already present in baseline: {', '.join(already)}")
    if after_set != expected_after:
        missing = sorted(expected_after - after_set)
        extra = sorted(after_set - expected_after)
        if missing:
            errors.append(f"after_items missing baseline/add items: {', '.join(missing[:10])}")
        if extra:
            errors.append(f"after_items contains unexpected items: {', '.join(extra[:10])}")
    if len(after_set) > 1000:
        errors.append(f"after_count exceeds limit: {len(after_set)}/1000")
    if root_blocked := sorted(site for site in add_set if site.lower() in ROOT_DOMAIN_BLOCKLIST):
        errors.append(f"root Yandex domains cannot be blocked: {', '.join(root_blocked)}")

    for site in add_sites:
        row = placements.get(site)
        if not row:
            warnings.append(f"{site}: missing placements evidence in review window")
            continue
        clicks = parse_float(row.get("Clicks"))
        ctr = parse_float(row.get("Ctr"))
        cost = parse_float(row.get("Cost"))
        conversions = extract_prefixed_metric(row, "Conversions", zero_for_dash=True)
        app_like = classify_app_like(site)
        if rules:
            ok, message = formula_allows(site, row, baseline["name"], rules)
            if not ok:
                errors.append(message)
        else:
            if clicks is None:
                warnings.append(f"{site}: clicks missing in placements row")
            elif clicks <= 5:
                errors.append(f"{site}: clicks={clicks:g} does not pass >5 rule")
            if ctr is None:
                warnings.append(f"{site}: ctr missing in placements row")
            elif ctr <= 1.0 and not app_like:
                errors.append(f"{site}: ctr={ctr:g}% does not pass >1% rule for non-app candidate")
            if conversions is None:
                warnings.append(f"{site}: conversions metric missing in placements row")
            elif conversions > 0:
                errors.append(f"{site}: conversions={conversions:g} > 0, blocking forbidden")
        info.append(
            {
                "site": site,
                "clicks": clicks,
                "ctr": ctr,
                "cost": cost,
                "conversions": conversions,
                "app_like": app_like,
            }
        )

    return {
        "pack": str(pack_path),
        "campaign_id": cid,
        "campaign_name": baseline["name"],
        "status": "FAIL" if errors else "OK",
        "current_count": len(current_items),
        "add_count": len(add_sites),
        "after_count": len(after_items),
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }


def render_text(results):
    lines = []
    for result in results:
        lines.append(
            f"{result['status']}\tcampaign={result['campaign_id']}\tcurrent={result.get('current_count','?')}\t"
            f"add={result.get('add_count','?')}\tafter={result.get('after_count','?')}\tpack={result['pack']}"
        )
        for error in result.get("errors", []):
            lines.append(f"  ERROR\t{error}")
        for warning in result.get("warnings", []):
            lines.append(f"  WARN\t{warning}")
        for item in result.get("info", []):
            lines.append(
                "  INFO\t"
                f"{item['site']}\tclicks={item['clicks']}\tctr={item['ctr']}\tcost={item['cost']}\t"
                f"conv={item['conversions']}\tapp_like={item['app_like']}"
            )
    return "\n".join(lines) + ("\n" if lines else "")


def main():
    parser = argparse.ArgumentParser(description="Validate ExcludedSites after-packs")
    parser.add_argument("--campaigns-meta", required=True, help="Path to campaigns_meta.json baseline")
    parser.add_argument("--placements-root", default="", help="Path to placements directory")
    parser.add_argument("--rules", default="", help="Optional path to rsya-placement-rules.json for formula-based validation")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("packs", nargs="+", help="One or more excluded-sites after JSON packs")
    args = parser.parse_args()

    campaigns = load_campaigns(args.campaigns_meta)
    rules = load_rules(args.rules)
    results = [validate_pack(pack, campaigns, args.placements_root, rules) for pack in args.packs]
    text = render_text(results)
    sys.stdout.write(text)
    if args.output:
        Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(1 if any(result["status"] != "OK" for result in results) else 0)


if __name__ == "__main__":
    main()
