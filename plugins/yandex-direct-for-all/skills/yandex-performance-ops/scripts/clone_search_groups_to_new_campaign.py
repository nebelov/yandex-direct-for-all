#!/usr/bin/env python3
"""Clone selected search ad groups into a separate unified search campaign.

Default mode is dry-run. Use --apply for live changes.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_V5 = "https://api.direct.yandex.com/json/v5"
API_V501 = "https://api.direct.yandex.com/json/v501"
ALLOWED_UNIFIED_SETTINGS_FOR_ADD = {
    "ADD_METRICA_TAG",
    "ADD_TO_FAVORITES",
    "ENABLE_AREA_OF_INTEREST_TARGETING",
    "ENABLE_CURRENT_AREA_TARGETING",
    "ENABLE_REGULAR_AREA_TARGETING",
    "ENABLE_SITE_MONITORING",
    "REQUIRE_SERVICING",
    "ENABLE_COMPANY_INFO",
    "CAMPAIGN_EXACT_PHRASE_MATCHING_ENABLED",
    "ALTERNATIVE_TEXTS_ENABLED",
}


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
    last_error = None
    for _ in range(retries):
        req = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            last_error = {"http": exc.code, "raw": raw}
        except Exception as exc:  # pragma: no cover - network path
            last_error = {"http": 0, "raw": f"{type(exc).__name__}: {exc}"}
    return {"error": last_error or {"http": 0, "raw": "unknown error"}}


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_token(args) -> str:
    if args.token:
        return args.token
    if args.token_file:
        data = json.loads(Path(args.token_file).read_text(encoding="utf-8"))
        token = data.get("access_token")
        if token:
            return token
    raise SystemExit("No token provided. Use --token or --token-file.")


def load_copy_map(path):
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def csv_ints(value: str) -> list[int]:
    return [int(part.strip()) for part in str(value).split(",") if part.strip()]


def maybe_items(value):
    if value is None:
        return None
    if isinstance(value, dict) and not value.get("Items"):
        return None
    if isinstance(value, list) and not value:
        return None
    return value


def compact_dict(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            compacted = compact_dict(item)
            if compacted is None:
                continue
            cleaned[key] = compacted
        return cleaned or None
    if isinstance(value, list):
        cleaned = [compact_dict(item) for item in value]
        cleaned = [item for item in cleaned if item is not None]
        return cleaned or None
    return value


def fatal_if_error(resp, label):
    if "error" in resp:
        raise SystemExit(f"{label} failed: {json.dumps(resp['error'], ensure_ascii=False)}")


def get_campaign(token, login, campaign_id):
    resp = api_call(
        "campaigns",
        "get",
        {
            "SelectionCriteria": {"Ids": [campaign_id]},
            "FieldNames": [
                "Id",
                "Name",
                "StartDate",
                "Status",
                "State",
                "DailyBudget",
                "NegativeKeywords",
                "TimeTargeting",
            ],
            "UnifiedCampaignFieldNames": [
                "BiddingStrategy",
                "Settings",
                "TrackingParams",
                "PriorityGoals",
                "CounterIds",
                "NegativeKeywordSharedSetIds",
            ],
        },
        token,
        login,
        version="v501",
    )
    fatal_if_error(resp, "campaigns.get")
    campaigns = resp.get("result", {}).get("Campaigns", [])
    if not campaigns:
        raise SystemExit(f"Source campaign {campaign_id} not found")
    return campaigns[0]


def list_campaigns_by_name(token, login, name):
    resp = api_call(
        "campaigns",
        "get",
        {"SelectionCriteria": {}, "FieldNames": ["Id", "Name", "Status", "State"]},
        token,
        login,
        version="v501",
    )
    fatal_if_error(resp, "campaigns.get(list)")
    return [item for item in resp.get("result", {}).get("Campaigns", []) if item.get("Name") == name]


def get_adgroups(token, login, campaign_id):
    resp = api_call(
        "adgroups",
        "get",
        {
            "SelectionCriteria": {"CampaignIds": [campaign_id]},
            "FieldNames": [
                "Id",
                "Name",
                "CampaignId",
                "Status",
                "ServingStatus",
                "RegionIds",
                "NegativeKeywords",
                "NegativeKeywordSharedSetIds",
                "TrackingParams",
            ],
            "UnifiedAdGroupFieldNames": ["OfferRetargeting"],
        },
        token,
        login,
        version="v501",
    )
    fatal_if_error(resp, "adgroups.get")
    return resp.get("result", {}).get("AdGroups", [])


def get_ads(token, login, adgroup_ids):
    rich_fields = [
        "Title",
        "Title2",
        "Text",
        "Href",
        "Mobile",
        "DisplayUrlPath",
        "AdImageHash",
        "SitelinkSetId",
        "AdExtensions",
    ]
    params = {
        "SelectionCriteria": {"AdGroupIds": adgroup_ids},
        "FieldNames": ["Id", "CampaignId", "AdGroupId", "Status", "State", "Type"],
        "TextAdFieldNames": rich_fields,
    }
    resp = api_call("ads", "get", params, token, login, version="v5")
    if "error" in resp:
        params["TextAdFieldNames"] = ["Title", "Title2", "Text", "Href", "Mobile", "DisplayUrlPath"]
        resp = api_call("ads", "get", params, token, login, version="v5")
    fatal_if_error(resp, "ads.get")
    return resp.get("result", {}).get("Ads", [])


def get_keywords(token, login, campaign_id):
    resp = api_call(
        "keywords",
        "get",
        {
            "SelectionCriteria": {"CampaignIds": [campaign_id]},
            "FieldNames": ["Id", "Keyword", "AdGroupId", "CampaignId", "State", "Status", "ServingStatus"],
        },
        token,
        login,
        version="v5",
    )
    fatal_if_error(resp, "keywords.get")
    return resp.get("result", {}).get("Keywords", [])


def get_keyword_bids(token, login, keyword_ids):
    if not keyword_ids:
        return {}

    result = {}
    for offset in range(0, len(keyword_ids), 1000):
        chunk = keyword_ids[offset : offset + 1000]
        resp = api_call(
            "keywordbids",
            "get",
            {
                "SelectionCriteria": {"KeywordIds": chunk},
                "FieldNames": ["KeywordId", "AdGroupId", "CampaignId", "ServingStatus"],
                "SearchFieldNames": ["Bid"],
            },
            token,
            login,
            version="v5",
        )
        if "error" in resp:
            fallback = api_call(
                "bids",
                "get",
                {
                    "SelectionCriteria": {"KeywordIds": chunk},
                    "FieldNames": ["KeywordId", "AdGroupId", "CampaignId", "Bid", "ContextBid", "ServingStatus"],
                },
                token,
                login,
                version="v5",
            )
            fatal_if_error(fallback, "bids.get fallback")
            for item in fallback.get("result", {}).get("Bids", []):
                result[item["KeywordId"]] = {
                    "SearchBid": item.get("Bid"),
                    "ContextBid": item.get("ContextBid"),
                    "Raw": item,
                }
            continue
        for item in resp.get("result", {}).get("KeywordBids", []):
            search = item.get("Search") or {}
            result[item["KeywordId"]] = {
                "SearchBid": search.get("Bid") or item.get("Bid") or item.get("SearchBid"),
                "ContextBid": (item.get("Network") or {}).get("Bid") or item.get("ContextBid"),
                "Raw": item,
            }
    return result


def sanitize_campaign_for_add(source, name, override_budget_micros=0):
    unified = source.get("UnifiedCampaign") or {}
    safe_settings = []
    for item in unified.get("Settings") or []:
        option = item.get("Option")
        if option not in ALLOWED_UNIFIED_SETTINGS_FOR_ADD:
            continue
        safe_settings.append({"Option": option, "Value": item.get("Value")})
    payload = {
        "Name": name,
        "StartDate": dt.datetime.utcnow().date().isoformat(),
        "DailyBudget": copy.deepcopy(source.get("DailyBudget")),
        "NegativeKeywords": copy.deepcopy(maybe_items(source.get("NegativeKeywords"))),
        "TimeTargeting": copy.deepcopy(source.get("TimeTargeting")),
        "UnifiedCampaign": {
            "BiddingStrategy": copy.deepcopy(unified.get("BiddingStrategy")),
            "Settings": safe_settings,
            "TrackingParams": unified.get("TrackingParams"),
            "PriorityGoals": copy.deepcopy(unified.get("PriorityGoals")),
            "CounterIds": copy.deepcopy(unified.get("CounterIds")),
            "NegativeKeywordSharedSetIds": copy.deepcopy(maybe_items(unified.get("NegativeKeywordSharedSetIds"))),
        },
    }
    if override_budget_micros:
        payload["DailyBudget"] = {"Amount": override_budget_micros, "Mode": "DISTRIBUTED"}
    return compact_dict(payload)


def sanitize_adgroup_for_add(source, campaign_id):
    payload = {
        "CampaignId": campaign_id,
        "Name": source.get("Name"),
        "RegionIds": copy.deepcopy(source.get("RegionIds")),
        "TrackingParams": source.get("TrackingParams"),
        "NegativeKeywords": copy.deepcopy(maybe_items(source.get("NegativeKeywords"))),
        "NegativeKeywordSharedSetIds": copy.deepcopy(maybe_items(source.get("NegativeKeywordSharedSetIds"))),
        "UnifiedAdGroup": copy.deepcopy(source.get("UnifiedAdGroup")),
    }
    return compact_dict(payload)


def sanitize_text_ad(source, target_adgroup_id):
    text_ad = source.get("TextAd") or {}
    ad_extension_ids = []
    for ext in text_ad.get("AdExtensions") or []:
        ext_id = ext.get("AdExtensionId") if isinstance(ext, dict) else None
        if ext_id:
            ad_extension_ids.append(ext_id)
    payload = {
        "AdGroupId": target_adgroup_id,
        "TextAd": {
            "Title": text_ad.get("Title"),
            "Title2": text_ad.get("Title2"),
            "Text": text_ad.get("Text"),
            "Href": text_ad.get("Href"),
            "Mobile": text_ad.get("Mobile"),
            "DisplayUrlPath": text_ad.get("DisplayUrlPath"),
            "AdImageHash": text_ad.get("AdImageHash"),
            "SitelinkSetId": text_ad.get("SitelinkSetId"),
            "AdExtensionIds": ad_extension_ids,
        },
    }
    return compact_dict(payload)


def resolve_override_ads(copy_map, source_group, source_ads):
    if not copy_map:
        return source_ads
    by_name = copy_map.get("by_adgroup_name") or {}
    by_id = copy_map.get("by_adgroup_id") or {}
    templates = by_id.get(str(source_group["Id"])) or by_name.get(source_group["Name"])
    if not templates:
        return source_ads
    if not source_ads:
        return []
    base_text_ad = copy.deepcopy((source_ads[0].get("TextAd") or {}))
    resolved = []
    for idx, item in enumerate(templates, start=1):
        merged = copy.deepcopy(base_text_ad)
        for key, value in item.items():
            merged[key] = value
        resolved.append({"Id": f"override-{source_group['Id']}-{idx}", "AdGroupId": source_group["Id"], "TextAd": merged})
    return resolved


def validate_text_ad_payload(payload, max_text_len):
    text_ad = payload.get("TextAd") or {}
    text = text_ad.get("Text") or ""
    if max_text_len and len(text) > max_text_len:
        return False, f"Text length {len(text)} > {max_text_len}"
    return True, ""


def ad_signature(ad_obj):
    text_ad = ad_obj.get("TextAd") or {}
    ext_ids = []
    for ext in text_ad.get("AdExtensions") or []:
        ext_ids.append(f"{ext.get('Type')}:{ext.get('AdExtensionId')}")
    for ext_id in text_ad.get("AdExtensionIds") or []:
        ext_ids.append(f"CALLOUT:{ext_id}")
    return "|".join(
        [
            text_ad.get("Title") or "",
            text_ad.get("Title2") or "",
            text_ad.get("Text") or "",
            text_ad.get("Href") or "",
            text_ad.get("DisplayUrlPath") or "",
            text_ad.get("AdImageHash") or "",
            str(text_ad.get("SitelinkSetId") or ""),
            text_ad.get("Mobile") or "",
            ",".join(sorted(ext_ids)),
        ]
    )


def keyword_signature(keyword_obj):
    return keyword_obj.get("Keyword") or ""


def ensure_campaign(token, login, source_campaign, new_name, override_budget_micros, reuse_existing, apply):
    existing = list_campaigns_by_name(token, login, new_name)
    payload = sanitize_campaign_for_add(source_campaign, new_name, override_budget_micros)
    if existing:
        if not reuse_existing:
            raise SystemExit(f"Campaign named '{new_name}' already exists. Use --reuse-existing-campaign.")
        return existing[0]["Id"], {"mode": "reuse", "campaign": existing[0], "payload": payload}
    if not apply:
        return None, {"mode": "dry-run-add", "payload": payload}
    resp = api_call("campaigns", "add", {"Campaigns": [payload]}, token, login, version="v501")
    fatal_if_error(resp, "campaigns.add")
    add_results = resp.get("result", {}).get("AddResults", [])
    if not add_results or "Id" not in add_results[0]:
        raise SystemExit(f"campaigns.add returned no Id: {json.dumps(resp, ensure_ascii=False)}")
    return add_results[0]["Id"], {"mode": "added", "response": resp, "payload": payload}


def ensure_adgroup(token, login, target_campaign_id, source_group, target_campaign_groups, apply):
    name = source_group["Name"]
    existing = next((item for item in target_campaign_groups if item.get("Name") == name), None)
    payload = sanitize_adgroup_for_add(source_group, target_campaign_id)
    if existing:
        return existing["Id"], {"mode": "reuse", "payload": payload, "adgroup": existing}
    if not apply:
        return None, {"mode": "dry-run-add", "payload": payload}
    resp = api_call("adgroups", "add", {"AdGroups": [payload]}, token, login, version="v501")
    fatal_if_error(resp, "adgroups.add")
    add_results = resp.get("result", {}).get("AddResults", [])
    if not add_results or "Id" not in add_results[0]:
        raise SystemExit(f"adgroups.add returned no Id: {json.dumps(resp, ensure_ascii=False)}")
    return add_results[0]["Id"], {"mode": "added", "response": resp, "payload": payload}


def add_ads(token, login, dest_group_id, source_ads, dest_ads, max_ads_per_group, max_text_len, apply):
    existing_signatures = {ad_signature(item) for item in dest_ads}
    payloads = []
    skipped = []
    for ad in source_ads:
        payload = sanitize_text_ad(ad, dest_group_id)
        is_valid, reason = validate_text_ad_payload(payload, max_text_len)
        if not is_valid:
            skipped.append({"source_ad_id": ad.get("Id"), "reason": reason})
            continue
        if ad_signature(payload) in existing_signatures:
            continue
        payloads.append(payload)
        if max_ads_per_group and len(payloads) >= max_ads_per_group:
            break
    if not apply:
        return {
            "planned_add_count": len(payloads),
            "payload_preview": payloads[:3],
            "skipped_count": len(skipped),
            "skipped_preview": skipped[:10],
        }
    responses = []
    for offset in range(0, len(payloads), 10):
        chunk = payloads[offset : offset + 10]
        if not chunk:
            continue
        resp = api_call("ads", "add", {"Ads": chunk}, token, login, version="v5")
        fatal_if_error(resp, "ads.add")
        responses.append(resp)
    return {
        "added_count": len(payloads),
        "responses": responses,
        "skipped_count": len(skipped),
        "skipped_preview": skipped[:10],
    }


def add_keywords(token, login, dest_group_id, source_keywords, dest_keywords, bids_map, fallback_bid_micros, apply):
    existing_signatures = {keyword_signature(item) for item in dest_keywords}
    payloads = []
    for kw in source_keywords:
        phrase = kw.get("Keyword") or ""
        if not phrase or phrase in existing_signatures:
            continue
        bid_meta = bids_map.get(kw["Id"], {})
        bid = bid_meta.get("SearchBid") or fallback_bid_micros
        item = {"AdGroupId": dest_group_id, "Keyword": phrase, "Bid": bid}
        context_bid = bid_meta.get("ContextBid")
        if context_bid:
            item["ContextBid"] = context_bid
        payloads.append(item)
    if not apply:
        return {"planned_add_count": len(payloads), "payload_preview": payloads[:5]}
    responses = []
    for offset in range(0, len(payloads), 1000):
        chunk = payloads[offset : offset + 1000]
        if not chunk:
            continue
        resp = api_call("keywords", "add", {"Keywords": chunk}, token, login, version="v5")
        fatal_if_error(resp, "keywords.add")
        responses.append(resp)
    return {"added_count": len(payloads), "responses": responses}


def suspend_source_groups(token, login, source_group_ids):
    resp = api_call(
        "adgroups",
        "suspend",
        {"SelectionCriteria": {"Ids": source_group_ids}},
        token,
        login,
        version="v501",
    )
    fatal_if_error(resp, "adgroups.suspend")
    return resp


def set_autotargeting_exact_only(token, login, keyword_ids):
    if not keyword_ids:
        return {"updated_count": 0, "keyword_ids": []}
    keywords = []
    for keyword_id in keyword_ids:
        keywords.append(
            {
                "Id": keyword_id,
                "AutotargetingSettings": {
                    "Categories": {
                        "Exact": "YES",
                        "Narrow": "NO",
                        "Alternative": "NO",
                        "Accessory": "NO",
                        "Broader": "NO",
                    },
                    "BrandOptions": {
                        "WithoutBrands": "YES",
                        "WithAdvertiserBrand": "YES",
                        "WithCompetitorsBrand": "NO",
                    },
                },
            }
        )
    resp = api_call(
        "keywords",
        "update",
        {"Keywords": keywords},
        token,
        login,
        version="v5",
    )
    fatal_if_error(resp, "keywords.update autotargeting")
    update_results = resp.get("result", {}).get("UpdateResults", [])
    errors = [item.get("Errors") for item in update_results if item.get("Errors")]
    if errors:
        raise SystemExit(f"keywords.update autotargeting item errors: {json.dumps(errors, ensure_ascii=False)}")
    return {"updated_count": len(keyword_ids), "keyword_ids": keyword_ids, "response": resp}


def build_summary(source_campaign, selected_groups, source_ads, source_keywords, bids_map, skip_autotargeting):
    ads_by_group = {}
    for ad in source_ads:
        ads_by_group.setdefault(ad["AdGroupId"], []).append(ad)
    kws_by_group = {}
    for kw in source_keywords:
        phrase = kw.get("Keyword") or ""
        if skip_autotargeting and phrase == "---autotargeting":
            continue
        kws_by_group.setdefault(kw["AdGroupId"], []).append(kw)

    groups = []
    for group in selected_groups:
        kw_items = kws_by_group.get(group["Id"], [])
        bids = [bids_map.get(item["Id"], {}).get("SearchBid") for item in kw_items]
        bids = [bid for bid in bids if bid]
        groups.append(
            {
                "source_adgroup_id": group["Id"],
                "name": group["Name"],
                "regions": group.get("RegionIds") or [],
                "source_ads": len(ads_by_group.get(group["Id"], [])),
                "source_keywords_manual": len(kw_items),
                "bid_min_micros": min(bids) if bids else None,
                "bid_max_micros": max(bids) if bids else None,
                "offer_retargeting": (group.get("UnifiedAdGroup") or {}).get("OfferRetargeting"),
            }
        )

    return {
        "source_campaign_id": source_campaign["Id"],
        "source_campaign_name": source_campaign["Name"],
        "selected_groups": groups,
        "manual_keyword_total": sum(item["source_keywords_manual"] for item in groups),
        "ad_total": sum(item["source_ads"] for item in groups),
        "skip_autotargeting": skip_autotargeting,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--login", required=True)
    parser.add_argument("--source-campaign-id", type=int, required=True)
    parser.add_argument("--new-campaign-name", required=True)
    parser.add_argument("--adgroup-ids", required=True, help="comma-separated source ad group ids")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--daily-budget-micros", type=int, default=0)
    parser.add_argument("--fallback-bid-micros", type=int, default=15000000)
    parser.add_argument("--max-ads-per-group", type=int, default=0)
    parser.add_argument("--max-text-len", type=int, default=80)
    parser.add_argument("--copy-map", default="")
    parser.add_argument("--reuse-existing-campaign", action="store_true")
    parser.add_argument("--suspend-source-groups", action="store_true")
    parser.add_argument("--include-autotargeting", action="store_true")
    parser.add_argument("--apply", action="store_true", help="live changes; default is dry-run")
    args = parser.parse_args()

    token = load_token(args)
    copy_map = load_copy_map(args.copy_map)
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    source_campaign = get_campaign(token, args.login, args.source_campaign_id)
    source_groups_all = get_adgroups(token, args.login, args.source_campaign_id)
    wanted_group_ids = set(csv_ints(args.adgroup_ids))
    selected_groups = [group for group in source_groups_all if group["Id"] in wanted_group_ids]
    missing_group_ids = sorted(wanted_group_ids - {group["Id"] for group in selected_groups})
    if missing_group_ids:
        raise SystemExit(f"Missing source ad groups: {missing_group_ids}")

    source_ads_all = get_ads(token, args.login, sorted(wanted_group_ids))
    source_keywords_all = get_keywords(token, args.login, args.source_campaign_id)
    source_keywords = [kw for kw in source_keywords_all if kw["AdGroupId"] in wanted_group_ids]
    if not args.include_autotargeting:
        source_keywords = [kw for kw in source_keywords if kw.get("Keyword") != "---autotargeting"]
    source_bids = get_keyword_bids(token, args.login, [kw["Id"] for kw in source_keywords])

    summary = build_summary(
        source_campaign,
        selected_groups,
        source_ads_all,
        source_keywords,
        source_bids,
        skip_autotargeting=not args.include_autotargeting,
    )

    dump_json(output_dir / "source_campaign.json", source_campaign)
    dump_json(output_dir / "source_adgroups.json", selected_groups)
    dump_json(output_dir / "source_ads.json", source_ads_all)
    dump_json(output_dir / "source_keywords.json", source_keywords)
    dump_json(output_dir / "source_bids.json", source_bids)
    dump_json(output_dir / "clone_summary.json", summary)

    target_campaign_id, campaign_log = ensure_campaign(
        token,
        args.login,
        source_campaign,
        args.new_campaign_name,
        args.daily_budget_micros,
        args.reuse_existing_campaign,
        args.apply,
    )

    target_groups_all = get_adgroups(token, args.login, target_campaign_id) if target_campaign_id else []
    apply_log = {
        "mode": "apply" if args.apply else "dry-run",
        "created_at": dt.datetime.now().isoformat(),
        "new_campaign_name": args.new_campaign_name,
        "campaign": campaign_log,
        "groups": [],
        "suspend_source_groups": False,
    }

    for source_group in selected_groups:
        dest_group_id, group_log = ensure_adgroup(
            token,
            args.login,
            target_campaign_id,
            source_group,
            target_groups_all,
            args.apply,
        )
        source_ads = [ad for ad in source_ads_all if ad["AdGroupId"] == source_group["Id"]]
        source_ads = resolve_override_ads(copy_map, source_group, source_ads)
        source_keywords_group = [kw for kw in source_keywords if kw["AdGroupId"] == source_group["Id"]]
        dest_ads = get_ads(token, args.login, [dest_group_id]) if dest_group_id else []
        dest_keywords = []
        if target_campaign_id:
            target_keywords_all = get_keywords(token, args.login, target_campaign_id)
            dest_keywords = [kw for kw in target_keywords_all if kw["AdGroupId"] == dest_group_id]
        autotarget_keyword_ids = [
            kw["Id"]
            for kw in dest_keywords
            if kw.get("Keyword") == "---autotargeting" and kw.get("State") != "SUSPENDED"
        ]
        autotarget_log = None
        if not args.include_autotargeting:
            if args.apply:
                autotarget_log = set_autotargeting_exact_only(token, args.login, autotarget_keyword_ids)
            else:
                autotarget_log = {
                    "planned_exact_only_count": len(autotarget_keyword_ids),
                    "keyword_ids": autotarget_keyword_ids,
                }
        ads_log = add_ads(
            token,
            args.login,
            dest_group_id,
            source_ads,
            dest_ads,
            args.max_ads_per_group,
            args.max_text_len,
            args.apply,
        )
        keywords_log = add_keywords(
            token,
            args.login,
            dest_group_id,
            source_keywords_group,
            dest_keywords,
            source_bids,
            args.fallback_bid_micros,
            args.apply,
        )
        apply_log["groups"].append(
            {
                "source_group_id": source_group["Id"],
                "source_group_name": source_group["Name"],
                "target_group_id": dest_group_id,
                "adgroup": group_log,
                "autotargeting": autotarget_log,
                "ads": ads_log,
                "keywords": keywords_log,
            }
        )
        if args.apply and dest_group_id and all(item.get("Id") != dest_group_id for item in target_groups_all):
            target_groups_all.append({"Id": dest_group_id, "Name": source_group["Name"]})

    if args.apply and args.suspend_source_groups:
        apply_log["suspend_source_groups"] = suspend_source_groups(token, args.login, sorted(wanted_group_ids))

    dump_json(output_dir / "clone_plan.json", apply_log)
    print(json.dumps({"ok": True, "output_dir": str(output_dir), "mode": apply_log["mode"]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
