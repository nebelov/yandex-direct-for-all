#!/usr/bin/env python3
"""Audit ad-level delivery failures for current Direct campaigns.

Focus:
- groups in active campaigns that have zero live ads;
- non-live ads in active campaigns;
- rejected moderation of image/sitelinks/callouts.

This is a parsing tool. Analysis should be done manually on the output files.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

API_V501 = "https://api.direct.yandex.com/json/v501"


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def call_api(token: str, login: str, service: str, method: str, params: dict) -> dict:
    req = urllib.request.Request(
        f"{API_V501}/{service}",
        data=json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": "ru",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="ignore")
        try:
            return {"error": json.loads(payload)}
        except Exception:
            return {"error": payload}


def fatal_if_error(resp: dict, label: str) -> dict:
    if "error" in resp:
        raise RuntimeError(f"{label}: {json.dumps(resp['error'], ensure_ascii=False)}")
    return resp


def is_live_ad(ad: dict) -> bool:
    return ad.get("Status") == "ACCEPTED" and ad.get("State") == "ON"


def group_failure_kind(group: dict, ads: list[dict]) -> str:
    if group.get("Status") != "ACCEPTED":
        return "group_not_accepted"
    if not ads:
        return "empty_group"
    live_ads = [a for a in ads if is_live_ad(a)]
    if live_ads:
        return "has_live_ads"
    statuses = Counter((a.get("Status"), a.get("State")) for a in ads)
    if len(statuses) == 1:
        (status, state), _ = statuses.most_common(1)[0]
        if status == "REJECTED":
            return "rejected_only"
        if status == "MODERATION":
            return "moderation_only"
        if status == "DRAFT":
            return "draft_only"
        if status == "ACCEPTED" and state == "OFF":
            return "accepted_off_only"
    return "mixed_non_live"


def serialize_status_breakdown(ads: list[dict]) -> dict:
    counter = Counter((a.get("Status"), a.get("State")) for a in ads)
    return {f"{status}/{state}": count for (status, state), count in counter.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--login", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--states", default="ON,SUSPENDED,OFF", help="campaign states, comma-separated")
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    states = [s.strip() for s in args.states.split(",") if s.strip()]
    camps_resp = fatal_if_error(
        call_api(
            args.token,
            args.login,
            "campaigns",
            "get",
            {
                "SelectionCriteria": {"States": states},
                "FieldNames": ["Id", "Name", "State", "Status", "StatusClarification"],
            },
        ),
        "campaigns.get",
    )
    campaigns = camps_resp["result"]["Campaigns"]
    campaign_ids = [c["Id"] for c in campaigns]

    adgroups = []
    for batch in chunks(campaign_ids, 10):
        resp = fatal_if_error(
            call_api(
                args.token,
                args.login,
                "adgroups",
                "get",
                {
                    "SelectionCriteria": {"CampaignIds": batch},
                    "FieldNames": ["Id", "CampaignId", "Name", "Status", "ServingStatus", "RegionIds"],
                },
            ),
            "adgroups.get",
        )
        adgroups.extend(resp["result"]["AdGroups"])

    ads = []
    for batch in chunks(campaign_ids, 5):
        resp = fatal_if_error(
            call_api(
                args.token,
                args.login,
                "ads",
                "get",
                {
                    "SelectionCriteria": {"CampaignIds": batch},
                    "FieldNames": ["Id", "CampaignId", "AdGroupId", "Status", "State", "StatusClarification", "Type"],
                    "TextAdFieldNames": [
                        "Title",
                        "Title2",
                        "Text",
                        "Href",
                        "DisplayUrlPath",
                        "AdImageHash",
                        "SitelinkSetId",
                        "SitelinksModeration",
                        "AdImageModeration",
                        "AdExtensions",
                    ],
                    "TextImageAdFieldNames": ["Title", "Title2", "Text", "Href", "AdImageHash"],
                    "ShoppingAdFieldNames": ["FeedId", "DefaultTexts"],
                },
            ),
            "ads.get",
        )
        ads.extend(resp["result"]["Ads"])

    campaign_map = {c["Id"]: c for c in campaigns}
    groups_by_campaign = defaultdict(list)
    for g in adgroups:
        groups_by_campaign[g["CampaignId"]].append(g)
    ads_by_group = defaultdict(list)
    for ad in ads:
        ads_by_group[ad["AdGroupId"]].append(ad)

    raw = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "campaigns": campaigns,
        "adgroups": adgroups,
        "ads": ads,
    }
    (outdir / "raw_state.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2))

    non_live_ads = []
    component_rejections = []
    groups_no_live_ads = []
    groups_with_only_non_live_rejected = []

    for ad in ads:
        camp = campaign_map.get(ad["CampaignId"], {})
        if camp.get("State") == "ON" and not is_live_ad(ad):
            ta = ad.get("TextAd") or {}
            non_live_ads.append(
                {
                    "campaign_id": ad["CampaignId"],
                    "campaign_name": camp.get("Name"),
                    "adgroup_id": ad["AdGroupId"],
                    "ad_id": ad["Id"],
                    "type": ad.get("Type"),
                    "status": ad.get("Status"),
                    "state": ad.get("State"),
                    "status_clarification": ad.get("StatusClarification"),
                    "title": ta.get("Title"),
                    "title2": ta.get("Title2"),
                }
            )

        ta = ad.get("TextAd") or {}
        problems = []
        slm = ta.get("SitelinksModeration") or {}
        if slm.get("Status") == "REJECTED":
            problems.append("sitelinks_rejected")
        aim = ta.get("AdImageModeration") or {}
        if aim.get("Status") == "REJECTED":
            problems.append("image_rejected")
        for ext in ta.get("AdExtensions") or []:
            if ext.get("Status") == "REJECTED":
                problems.append(f"extension_rejected:{ext.get('AdExtensionId')}")
        if problems:
            component_rejections.append(
                {
                    "campaign_id": ad["CampaignId"],
                    "campaign_name": campaign_map.get(ad["CampaignId"], {}).get("Name"),
                    "adgroup_id": ad["AdGroupId"],
                    "ad_id": ad["Id"],
                    "status": ad.get("Status"),
                    "state": ad.get("State"),
                    "title": ta.get("Title"),
                    "problems": problems,
                }
            )

    for group in adgroups:
        camp = campaign_map.get(group["CampaignId"], {})
        if camp.get("State") != "ON":
            continue
        kind = group_failure_kind(group, ads_by_group.get(group["Id"], []))
        if kind != "has_live_ads":
            entry = {
                "campaign_id": group["CampaignId"],
                "campaign_name": camp.get("Name"),
                "adgroup_id": group["Id"],
                "adgroup_name": group["Name"],
                "group_status": group.get("Status"),
                "serving_status": group.get("ServingStatus"),
                "failure_kind": kind,
                "ads_total": len(ads_by_group.get(group["Id"], [])),
                "ads_status_breakdown": serialize_status_breakdown(ads_by_group.get(group["Id"], [])),
                "ad_ids": [a["Id"] for a in ads_by_group.get(group["Id"], [])],
            }
            groups_no_live_ads.append(entry)
            if kind in {"rejected_only", "mixed_non_live"}:
                groups_with_only_non_live_rejected.append(entry)

    summary = {
        "generated_at": raw["generated_at"],
        "counts": {
            "campaigns_total": len(campaigns),
            "campaigns_on": sum(1 for c in campaigns if c.get("State") == "ON"),
            "adgroups_total": len(adgroups),
            "ads_total": len(ads),
            "non_live_ads_in_on_campaigns": len(non_live_ads),
            "component_rejections": len(component_rejections),
            "groups_no_live_ads_in_on_campaigns": len(groups_no_live_ads),
        },
        "campaign_summary": [],
        "groups_no_live_ads": groups_no_live_ads,
        "non_live_ads": non_live_ads,
        "component_rejections": component_rejections,
    }

    for camp in campaigns:
        cid = camp["Id"]
        camp_ads = [a for a in ads if a["CampaignId"] == cid]
        camp_groups = [g for g in adgroups if g["CampaignId"] == cid]
        summary["campaign_summary"].append(
            {
                "campaign_id": cid,
                "campaign_name": camp.get("Name"),
                "campaign_state": camp.get("State"),
                "campaign_status": camp.get("Status"),
                "adgroups_total": len(camp_groups),
                "ads_total": len(camp_ads),
                "live_ads": sum(1 for a in camp_ads if is_live_ad(a)),
                "non_live_ads": sum(1 for a in camp_ads if not is_live_ad(a)),
                "groups_no_live_ads": sum(1 for g in groups_no_live_ads if g["campaign_id"] == cid),
                "component_rejections": sum(1 for x in component_rejections if x["campaign_id"] == cid),
            }
        )

    (outdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
