#!/usr/bin/env python3
"""Send ads to moderation and write verification report.

Safe defaults:
- can target explicit ad ids instead of every DRAFT/REJECTED ad in the campaign;
- only suspends campaigns that were OFF before moderation unless explicitly forced.
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List

API_V5 = "https://api.direct.yandex.com/json/v5"


def chunks(items: List[int], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def call_api(token: str, login: str, service: str, method: str, params: dict, retries: int = 4):
    url = f"{API_V5}/{service}"
    body = json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            url,
            data=body,
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
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="ignore")
            if attempt >= retries:
                return {"error": {"http_code": e.code, "raw": raw}}
            time.sleep(attempt)
        except Exception as e:
            if attempt >= retries:
                return {"error": {"http_code": 0, "raw": f"{type(e).__name__}: {e}"}}
            time.sleep(attempt)


def fetch_ads(token: str, login: str, selection: dict) -> List[dict]:
    resp = call_api(
        token,
        login,
        "ads",
        "get",
        {
            "SelectionCriteria": selection,
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "Status", "State"],
        },
    )
    return resp.get("result", {}).get("Ads", [])


def fetch_campaigns(token: str, login: str, campaign_ids: List[int]) -> List[dict]:
    resp = call_api(
        token,
        login,
        "campaigns",
        "get",
        {
            "SelectionCriteria": {"Ids": campaign_ids},
            "FieldNames": ["Id", "Name", "Status", "State"],
        },
        retries=4,
    )
    return resp.get("result", {}).get("Campaigns", [])


def summarize(ads: List[dict]) -> Dict[str, Dict[str, int]]:
    return {
        "status": dict(Counter((a.get("Status") or "UNKNOWN") for a in ads)),
        "state": dict(Counter((a.get("State") or "UNKNOWN") for a in ads)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--login", required=True)
    ap.add_argument("--campaign-ids", default="", help="comma-separated ids")
    ap.add_argument("--ad-ids", default="", help="comma-separated explicit ad ids to moderate")
    ap.add_argument("--output", required=True)
    ap.add_argument("--batch-size", type=int, default=1000)
    ap.add_argument(
        "--allow-auto-start",
        action="store_true",
        help="Do not suspend OFF campaigns after ads.moderate. Unsafe unless launch is explicitly approved.",
    )
    ap.add_argument(
        "--suspend-running-campaigns",
        action="store_true",
        help="Also suspend campaigns that were ON before moderation. Use only if suspension of active traffic is intended.",
    )
    args = ap.parse_args()

    campaign_ids = [int(x.strip()) for x in args.campaign_ids.split(",") if x.strip()]
    ad_ids = [int(x.strip()) for x in args.ad_ids.split(",") if x.strip()]
    if not campaign_ids and not ad_ids:
        raise SystemExit("Provide --campaign-ids and/or --ad-ids")
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "campaign_ids": campaign_ids,
        "requested_ad_ids": ad_ids,
    }

    selection = {"Ids": ad_ids} if ad_ids else {"CampaignIds": campaign_ids}
    before_ads = fetch_ads(args.token, args.login, selection)
    derived_campaign_ids = sorted({int(a.get("CampaignId") or 0) for a in before_ads if int(a.get("CampaignId") or 0) > 0})
    if not campaign_ids:
        campaign_ids = derived_campaign_ids
        report["campaign_ids"] = campaign_ids

    before_campaigns = fetch_campaigns(args.token, args.login, campaign_ids) if campaign_ids else []
    report["before_campaigns"] = before_campaigns

    report["before"] = {"ads_total": len(before_ads), **summarize(before_ads)}

    draft_or_rejected_ids = [
        a["Id"]
        for a in before_ads
        if (a.get("Status") in {"DRAFT", "REJECTED"}) and a.get("State") == "OFF"
    ]
    report["candidate_ads_for_moderation"] = len(draft_or_rejected_ids)

    moderate_responses = []
    for batch in chunks(draft_or_rejected_ids, args.batch_size):
        resp = call_api(
            args.token,
            args.login,
            "ads",
            "moderate",
            {"SelectionCriteria": {"Ids": batch}},
        )
        moderate_responses.append(resp)
    report["moderate_calls"] = {
        "batches": len(moderate_responses),
        "responses": moderate_responses,
    }

    # Moderation status propagation may take a moment.
    time.sleep(2)
    suspend_response = None
    campaigns_to_suspend = []
    if not args.allow_auto_start and campaign_ids:
        if args.suspend_running_campaigns:
            campaigns_to_suspend = campaign_ids
        else:
            campaigns_to_suspend = [
                int(c.get("Id") or 0)
                for c in before_campaigns
                if int(c.get("Id") or 0) > 0 and (c.get("State") or "").upper() == "OFF"
            ]
    report["campaigns_to_suspend"] = campaigns_to_suspend
    if campaigns_to_suspend:
        suspend_response = call_api(
            args.token,
            args.login,
            "campaigns",
            "suspend",
            {"SelectionCriteria": {"Ids": campaigns_to_suspend}},
        )
        report["suspend_after_moderation"] = suspend_response
        time.sleep(2)

    after_campaigns = fetch_campaigns(args.token, args.login, campaign_ids) if campaign_ids else []
    report["after_campaigns"] = after_campaigns
    after_ads = fetch_ads(args.token, args.login, selection)
    report["after"] = {"ads_total": len(after_ads), **summarize(after_ads)}
    report["after_draft_ads"] = [a["Id"] for a in after_ads if a.get("Status") == "DRAFT"]
    report["after_moderation_ads"] = [a["Id"] for a in after_ads if a.get("Status") == "MODERATION"]
    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "status": "ok",
                "report": args.output,
                "before": report["before"],
                "after": report["after"],
                "after_campaigns": [
                    {
                        "Id": c.get("Id"),
                        "Status": c.get("Status"),
                        "State": c.get("State"),
                    }
                    for c in after_campaigns
                ],
                "candidate_ads_for_moderation": len(draft_or_rejected_ids),
                "auto_start_allowed": args.allow_auto_start,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
