#!/usr/bin/env python3
"""Deploy generic search campaign scaffolds from cluster map."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from collections import defaultdict


API_V5 = "https://api.direct.yandex.com/json/v5"
API_V501 = "https://api.direct.yandex.com/json/v501"


def api_call(service, method, params, token, login, version="v5", retries=4):
    base = API_V501 if version == "v501" else API_V5
    url = f"{base}/{service}"
    body = json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Language": "ru",
    }
    if login:
        headers["Client-Login"] = login
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            if attempt == retries:
                return {"error": {"http": exc.code, "raw": raw}}
        except Exception as exc:
            if attempt == retries:
                return {"error": {"http": 0, "raw": f"{type(exc).__name__}: {exc}"}}


def read_tsv(path):
    with open(path, "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def clean_kw(text):
    text = re.sub(r"\s+", " ", (text or "").strip().lower())
    return text.replace('"', "").replace("'", "")[:4096]


def display_path(name):
    raw = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ\s-]", "", name or "").strip().lower()
    raw = re.sub(r"[\s-]+", "-", raw)
    raw = raw.strip("-")
    return raw[:20] if raw else "search"


def _squash_spaces(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def _trim(value, limit):
    value = _squash_spaces(value)
    if len(value) <= limit:
        return value
    trimmed = value[:limit].rstrip(" ,.;:-")
    return trimmed or value[:limit]


def sanitize_copy(copy_data):
    return {
        "title": _trim(copy_data.get("title", ""), 56),
        "title2": _trim(copy_data.get("title2", ""), 30),
        "text": _trim(copy_data.get("text", ""), 80),
    }


def parse_csv_ints(value):
    return [int(part.strip()) for part in str(value).split(",") if part.strip()]


def parse_csv_strings(value):
    return [part.strip() for part in str(value).split(",") if part.strip()]


def build_search_strategy(settings):
    strategy_type = settings["search_strategy"]
    if strategy_type == "WB_MAXIMUM_CONVERSION_RATE":
        bid_ceiling = settings.get("search_bid_ceiling_micros")
        if not bid_ceiling:
            raise ValueError("Search WB_MAXIMUM_CONVERSION_RATE requires explicit search_bid_ceiling_micros")
        return {
            "BiddingStrategyType": strategy_type,
            "WbMaximumConversionRate": {
                "WeeklySpendLimit": settings["weekly_spend_limit_micros"],
                "GoalId": settings["search_goal_id"],
                "BidCeiling": bid_ceiling,
            },
            "PlacementTypes": settings["placement_types"],
        }
    return {
        "BiddingStrategyType": strategy_type,
        "PlacementTypes": settings["placement_types"],
    }


def load_copy_map(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit("copy-map must be JSON object")
    return data


def resolve_copy(copy_map, group_name, defaults):
    by_group = copy_map.get("by_adgroup", {}) if isinstance(copy_map, dict) else {}
    by_regex = copy_map.get("by_regex", []) if isinstance(copy_map, dict) else []
    if group_name in by_group and isinstance(by_group[group_name], dict):
        resolved = dict(defaults)
        resolved.update(by_group[group_name])
        return resolved
    lower_name = (group_name or "").lower()
    for rule in by_regex:
        pattern = rule.get("pattern", "")
        if pattern and re.search(pattern, lower_name):
            resolved = dict(defaults)
            resolved.update(rule.get("copy", {}))
            return resolved
    return dict(defaults)


def ensure_campaign(name, token, login, settings, dry_run=False):
    got = api_call(
        "campaigns",
        "get",
        {"SelectionCriteria": {}, "FieldNames": ["Id", "Name", "State", "Status"]},
        token,
        login,
        version="v501",
    )
    if "result" in got:
        for campaign in got["result"].get("Campaigns", []):
            if campaign.get("Name") == name:
                return campaign["Id"], {"existing": True, "campaign": campaign}

    if dry_run:
        return None, {"dry_run_add_campaign": name}

    campaign = {
        "Name": name,
        "StartDate": dt.date.today().isoformat(),
        "NegativeKeywords": {"Items": settings["negative_keywords"]},
        "UnifiedCampaign": {
            "TrackingParams": settings["tracking_params"],
            "CounterIds": {"Items": settings["counter_ids"]},
            "Settings": settings["campaign_settings"],
            "BiddingStrategy": {
                "Search": build_search_strategy(settings),
                "Network": {"BiddingStrategyType": settings["network_strategy"]},
            },
        },
    }
    if settings["search_strategy"] == "HIGHEST_POSITION":
        campaign["DailyBudget"] = {"Amount": settings["daily_budget_micros"], "Mode": "STANDARD"}
    payload = {"Campaigns": [campaign]}
    response = api_call("campaigns", "add", payload, token, login, version="v501")
    if "result" in response and response["result"].get("AddResults"):
        return response["result"]["AddResults"][0].get("Id"), {"added": response}
    return None, {"add_error": response}


def ensure_adgroup(campaign_id, group_name, token, login, settings, dry_run=False):
    got = api_call(
        "adgroups",
        "get",
        {
            "SelectionCriteria": {"CampaignIds": [campaign_id]},
            "FieldNames": ["Id", "Name", "CampaignId"],
            "UnifiedAdGroupFieldNames": ["OfferRetargeting"],
        },
        token,
        login,
        version="v501",
    )
    if "result" in got:
        for group in got["result"].get("AdGroups", []):
            if group.get("Name") == group_name:
                return group["Id"], {"existing": True, "adgroup": group}

    if dry_run:
        return None, {"dry_run_add_adgroup": group_name}

    payload = {
        "AdGroups": [
            {
                "CampaignId": campaign_id,
                "Name": group_name,
                "RegionIds": settings["regions"],
                "TrackingParams": settings["tracking_params"],
                "UnifiedAdGroup": {"OfferRetargeting": settings["offer_retargeting"]},
            }
        ]
    }
    response = api_call("adgroups", "add", payload, token, login, version="v501")
    if "result" in response and response["result"].get("AddResults"):
        return response["result"]["AddResults"][0].get("Id"), {"added": response}
    return None, {"add_error": response}


def ensure_ad(adgroup_id, group_name, href, token, login, copy_data, dry_run=False):
    got = api_call(
        "ads",
        "get",
        {
            "SelectionCriteria": {"AdGroupIds": [adgroup_id]},
            "FieldNames": ["Id", "AdGroupId", "Status", "State", "Type"],
            "TextAdFieldNames": ["Title", "Title2", "Text", "Href", "DisplayUrlPath"],
        },
        token,
        login,
        version="v5",
    )
    if "result" in got and got["result"].get("Ads"):
        return got["result"]["Ads"][0]["Id"], {"existing": True}

    if dry_run:
        return None, {"dry_run_add_ad": adgroup_id}

    safe_copy = sanitize_copy(copy_data)
    payload = {
        "Ads": [
            {
                "AdGroupId": adgroup_id,
                "TextAd": {
                    "Title": safe_copy["title"],
                    "Title2": safe_copy["title2"],
                    "Text": safe_copy["text"],
                    "Href": href,
                    "DisplayUrlPath": display_path(group_name),
                },
            }
        ]
    }
    response = api_call("ads", "add", payload, token, login, version="v5")
    if "result" in response and response["result"].get("AddResults"):
        return response["result"]["AddResults"][0].get("Id"), {"added": response}
    return None, {"add_error": response}


def add_keywords(adgroup_id, phrases, token, login, bid_micros, dry_run=False):
    if dry_run:
        return {"dry_run_keywords": len(phrases)}

    keywords = []
    for phrase in phrases:
        keyword = clean_kw(phrase)
        if not keyword:
            continue
        keywords.append({"AdGroupId": adgroup_id, "Keyword": keyword, "Bid": bid_micros})

    responses = []
    for offset in range(0, len(keywords), 200):
        responses.append(api_call("keywords", "add", {"Keywords": keywords[offset : offset + 200]}, token, login, "v5"))
    return {"batches": len(responses), "responses": responses, "count": len(keywords)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--login", default="")
    parser.add_argument("--cluster-map", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--href", required=True)
    parser.add_argument("--counter-ids", required=True, help="comma-separated counter ids")
    parser.add_argument("--regions", default="225", help="comma-separated region ids")
    parser.add_argument("--tracking-params", default="utm_source=yandex&utm_medium=cpc&utm_campaign={campaign_name}&utm_content={ad_id}&utm_term={keyword}")
    parser.add_argument("--negative-keywords", default="скачать,бесплатно,вакансия,реферат,apk")
    parser.add_argument("--daily-budget-micros", type=int, default=500000000)
    parser.add_argument("--bid-micros", type=int, default=8000000)
    parser.add_argument("--search-bid-ceiling-micros", type=int, default=8000000)
    parser.add_argument("--search-strategy", default="WB_MAXIMUM_CONVERSION_RATE")
    parser.add_argument("--search-goal-id", type=int, default=13)
    parser.add_argument("--network-strategy", default="SERVING_OFF")
    parser.add_argument("--dynamic-places", default="NO")
    parser.add_argument("--product-gallery", default="NO")
    parser.add_argument("--maps", default="NO")
    parser.add_argument("--search-org-list", default="NO")
    parser.add_argument("--offer-retargeting", default="NO")
    parser.add_argument("--default-title", required=True)
    parser.add_argument("--default-title2", required=True)
    parser.add_argument("--default-text", required=True)
    parser.add_argument("--copy-map", default="", help="JSON file with by_adgroup/by_regex copy rules")
    parser.add_argument("--max-per-group", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    cluster_rows = read_tsv(args.cluster_map)
    copy_map = load_copy_map(args.copy_map)
    defaults = {"title": args.default_title, "title2": args.default_title2, "text": args.default_text}

    settings = {
        "daily_budget_micros": args.daily_budget_micros,
        "weekly_spend_limit_micros": args.daily_budget_micros * 7,
        "negative_keywords": parse_csv_strings(args.negative_keywords),
        "tracking_params": args.tracking_params,
        "counter_ids": parse_csv_ints(args.counter_ids),
        "regions": parse_csv_ints(args.regions),
        "offer_retargeting": args.offer_retargeting,
        "search_strategy": args.search_strategy,
        "search_goal_id": args.search_goal_id,
        "search_bid_ceiling_micros": args.search_bid_ceiling_micros,
        "network_strategy": args.network_strategy,
        "placement_types": {
            "SearchResults": "YES",
            "ProductGallery": args.product_gallery,
            "DynamicPlaces": args.dynamic_places,
            "Maps": args.maps,
            "SearchOrganizationList": args.search_org_list,
        },
        "campaign_settings": [
            {"Option": "ADD_METRICA_TAG", "Value": "YES"},
            {"Option": "ENABLE_AREA_OF_INTEREST_TARGETING", "Value": "NO"},
            {"Option": "ALTERNATIVE_TEXTS_ENABLED", "Value": "NO"},
            {"Option": "ENABLE_SITE_MONITORING", "Value": "YES"},
            {"Option": "ENABLE_COMPANY_INFO", "Value": "YES"},
        ],
    }

    plan = defaultdict(lambda: defaultdict(list))
    for row in cluster_rows:
        campaign_name = (row.get("campaign_name") or "").strip()
        adgroup_name = (row.get("adgroup_name") or "").strip()
        phrase = clean_kw(row.get("phrase", ""))
        if not campaign_name or not adgroup_name or not phrase:
            continue
        if phrase not in plan[campaign_name][adgroup_name]:
            plan[campaign_name][adgroup_name].append(phrase)

    log = {"campaigns": {}}
    for campaign_name, groups in plan.items():
        campaign_id, campaign_meta = ensure_campaign(campaign_name, args.token, args.login, settings, args.dry_run)
        log["campaigns"][campaign_name] = {"campaign_id": campaign_id, "campaign_meta": campaign_meta, "groups": {}}
        if campaign_id is None and not args.dry_run:
            continue

        for group_name, phrases in groups.items():
            group_id, group_meta = ensure_adgroup(campaign_id, group_name, args.token, args.login, settings, args.dry_run)
            info = {"adgroup_id": group_id, "adgroup_meta": group_meta}
            log["campaigns"][campaign_name]["groups"][group_name] = info
            if group_id is None and not args.dry_run:
                continue

            ad_copy = resolve_copy(copy_map, group_name, defaults)
            ad_id, ad_meta = ensure_ad(group_id, group_name, args.href, args.token, args.login, ad_copy, args.dry_run)
            info["ad_id"] = ad_id
            info["ad_meta"] = ad_meta

            selected_phrases = phrases if args.max_per_group <= 0 else phrases[: args.max_per_group]
            info["keywords"] = {
                "requested": len(selected_phrases),
                **add_keywords(group_id, selected_phrases, args.token, args.login, args.bid_micros, args.dry_run),
            }

    with open(os.path.join(args.output_dir, "deploy_log.json"), "w", encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=2)

    summary = {"campaigns": 0, "groups": 0, "keywords_requested": 0}
    for campaign in log["campaigns"].values():
        summary["campaigns"] += 1
        for group in campaign["groups"].values():
            summary["groups"] += 1
            summary["keywords_requested"] += int(group.get("keywords", {}).get("requested", 0))

    with open(os.path.join(args.output_dir, "deploy_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
