#!/usr/bin/env python3
"""Set callouts on all ads in campaigns and verify removals."""

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime
from typing import List

API_V5 = "https://api.direct.yandex.com/json/v5"


def chunks(items: List[int], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def call_api(token: str, login: str, service: str, method: str, params: dict) -> dict:
    req = urllib.request.Request(
        f"{API_V5}/{service}",
        data=json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": "ru",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_ads(token: str, login: str, campaign_ids: List[int]) -> List[dict]:
    resp = call_api(
        token,
        login,
        "ads",
        "get",
        {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "Status", "State"],
            "TextAdFieldNames": ["AdExtensions"],
        },
    )
    return resp.get("result", {}).get("Ads", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--login", required=True)
    ap.add_argument("--campaign-ids", required=True, help="comma-separated")
    ap.add_argument("--keep-callout-ids", required=True, help="comma-separated")
    ap.add_argument("--remove-callout-ids", default="", help="comma-separated; optional verification")
    ap.add_argument("--output", required=True)
    ap.add_argument("--batch-size", type=int, default=10)
    args = ap.parse_args()

    campaign_ids = [int(x.strip()) for x in args.campaign_ids.split(",") if x.strip()]
    keep_ids = [int(x.strip()) for x in args.keep_callout_ids.split(",") if x.strip()]
    remove_ids = [int(x.strip()) for x in args.remove_callout_ids.split(",") if x.strip()]

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    report = {
        "started_at": datetime.utcnow().isoformat() + "Z",
        "campaign_ids": campaign_ids,
        "keep_callout_ids": keep_ids,
        "remove_callout_ids": remove_ids,
    }

    before_ads = fetch_ads(args.token, args.login, campaign_ids)
    report["before_ads_total"] = len(before_ads)

    updates = []
    for a in before_ads:
        updates.append(
            {
                "Id": a["Id"],
                "TextAd": {
                    "CalloutSetting": {
                        "AdExtensions": [{"AdExtensionId": cid, "Operation": "SET"} for cid in keep_ids]
                    }
                },
            }
        )

    responses = []
    for batch in chunks(updates, args.batch_size):
        responses.append(call_api(args.token, args.login, "ads", "update", {"Ads": batch}))
    report["update_batches"] = len(responses)
    report["update_errors"] = [r["error"] for r in responses if "error" in r]

    time.sleep(1)
    after_ads = fetch_ads(args.token, args.login, campaign_ids)
    report["after_ads_total"] = len(after_ads)

    violations_removed = []
    violations_keep_missing = []
    for a in after_ads:
        ex = (a.get("TextAd") or {}).get("AdExtensions") or []
        attached = [x.get("AdExtensionId") for x in ex if isinstance(x, dict)]
        if any(rid in attached for rid in remove_ids):
            violations_removed.append({"ad_id": a["Id"], "attached_ids": attached})
        if not all(kid in attached for kid in keep_ids):
            violations_keep_missing.append({"ad_id": a["Id"], "attached_ids": attached})

    report["violations_removed_ids_present"] = len(violations_removed)
    report["violations_keep_missing"] = len(violations_keep_missing)
    report["violations_removed_samples"] = violations_removed[:20]
    report["violations_keep_missing_samples"] = violations_keep_missing[:20]
    report["finished_at"] = datetime.utcnow().isoformat() + "Z"

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "status": "ok",
                "report": args.output,
                "after_ads_total": len(after_ads),
                "violations_removed_ids_present": len(violations_removed),
                "violations_keep_missing": len(violations_keep_missing),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

