#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import requests


def load_token(args):
    if args.token:
        return args.token.strip()
    if args.token_file:
        data = json.loads(Path(args.token_file).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("access_token") or data.get("token") or "").strip()
        return str(data).strip()
    raise SystemExit("token required: pass --token or --token-file")


def api_call(token, login, service, method, params, version="v5"):
    url = f"https://api.direct.yandex.com/json/{version}/{service}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Login": login,
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"method": method, "params": params}
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    try:
        body = resp.json()
    except Exception:
        body = {"raw_text": resp.text}
    return {"http_status": resp.status_code, "body": body}


def ensure_ok(resp, label):
    if resp["http_status"] != 200:
        raise RuntimeError(f"{label} http {resp['http_status']}: {json.dumps(resp['body'], ensure_ascii=False)}")
    if "error" in resp["body"]:
        raise RuntimeError(f"{label} api error: {json.dumps(resp['body']['error'], ensure_ascii=False)}")
    return resp["body"].get("result", {})


def ensure_no_item_errors(items, label):
    errors = []
    for idx, item in enumerate(items):
        if item.get("Errors"):
            errors.append({"index": idx, "errors": item["Errors"]})
    if errors:
        raise RuntimeError(f"{label} item errors: {json.dumps(errors, ensure_ascii=False)}")
    return items


def compact_dict(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            value = compact_dict(value)
            if value is None:
                continue
            if value == []:
                continue
            out[key] = value
        return out
    if isinstance(obj, list):
        return [compact_dict(v) for v in obj]
    return obj


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def read_plan(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect_change_targets(plan):
    update_targets = []
    archive_ids = []
    for op in plan.get("operations", []):
        kind = op.get("kind")
        if kind == "ads.update":
            for change in op.get("changes", []):
                update_targets.append(
                    {
                        "campaign_id": op.get("campaign_id"),
                        "campaign_name": op.get("campaign_name"),
                        "adgroup_id": op.get("adgroup_id"),
                        "adgroup_name": op.get("adgroup_name"),
                        "ad_id": change["ad_id"],
                        "field": change["field"],
                        "before": change.get("before"),
                        "after": change.get("after"),
                        "reason": op.get("reason"),
                    }
                )
        elif kind == "ads.archive":
            for change in op.get("changes", []):
                archive_ids.append(change["ad_id"])
    return update_targets, archive_ids


def get_ads(token, login, ids):
    if not ids:
        return []
    resp = api_call(
        token,
        login,
        "ads",
        "get",
        {
            "SelectionCriteria": {"Ids": ids},
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "Status", "State", "StatusClarification", "Type"],
            "TextAdFieldNames": [
                "Title",
                "Title2",
                "Text",
                "Href",
                "DisplayUrlPath",
                "Mobile",
                "SitelinkSetId",
                "SitelinksModeration",
                "AdImageHash",
                "AdImageModeration",
                "AdExtensions",
                "BusinessId",
            ],
        },
        version="v5",
    )
    return ensure_ok(resp, "ads.get").get("Ads", [])


def get_adgroups(token, login, ids):
    if not ids:
        return []
    resp = api_call(
        token,
        login,
        "adgroups",
        "get",
        {
            "SelectionCriteria": {"Ids": ids},
            "FieldNames": ["Id", "CampaignId", "Name", "Status", "ServingStatus", "RegionIds"],
        },
        version="v5",
    )
    return ensure_ok(resp, "adgroups.get").get("AdGroups", [])


def get_sitelinks(token, login, ids):
    if not ids:
        return []
    resp = api_call(
        token,
        login,
        "sitelinks",
        "get",
        {
            "SelectionCriteria": {"Ids": ids},
            "FieldNames": ["Id", "Sitelinks"],
        },
        version="v5",
    )
    return ensure_ok(resp, "sitelinks.get").get("SitelinksSets", [])


def build_update_payloads(current_ads, update_targets):
    by_id = {int(ad["Id"]): ad for ad in current_ads}
    payloads = []
    plans = []
    for target in update_targets:
        ad_id = int(target["ad_id"])
        ad = by_id.get(ad_id)
        if not ad:
            raise RuntimeError(f"ad {ad_id} not found in live get")
        ta = ad.get("TextAd") or {}
        ext_ids = []
        for ext in ta.get("AdExtensions") or []:
            ext_id = ext.get("AdExtensionId") if isinstance(ext, dict) else None
            if ext_id:
                ext_ids.append(ext_id)
        text_ad = compact_dict(
            {
                "SitelinkSetId": target["after"],
            }
        )
        payload = {"Id": ad_id, "TextAd": text_ad}
        payloads.append(payload)
        plans.append(
            {
                "ad_id": ad_id,
                "campaign_id": ad.get("CampaignId"),
                "adgroup_id": ad.get("AdGroupId"),
                "status_before": ad.get("Status"),
                "state_before": ad.get("State"),
                "sitelink_before": ta.get("SitelinkSetId"),
                "sitelink_after": target["after"],
                "reason": target.get("reason"),
                "payload": payload,
            }
        )
    return payloads, plans


def main():
    parser = argparse.ArgumentParser(description="Apply point-fix pack for ad-layer defects")
    parser.add_argument("--token", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--login", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true", help="perform live changes; default is dry-run")
    args = parser.parse_args()

    token = load_token(args)
    plan = read_plan(args.plan_json)
    update_targets, archive_ids = collect_change_targets(plan)
    update_ad_ids = [item["ad_id"] for item in update_targets]
    current_update_ads = get_ads(token, args.login, update_ad_ids)
    update_payloads, update_plans = build_update_payloads(current_update_ads, update_targets)

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "plan_json": args.plan_json,
        "update_plans": update_plans,
        "archive_ids": archive_ids,
    }

    if args.apply:
        update_responses = []
        for batch in chunked(update_payloads, 10):
            resp = api_call(token, args.login, "ads", "update", {"Ads": batch}, version="v501")
            result = ensure_ok(resp, "ads.update")
            ensure_no_item_errors(result.get("UpdateResults", []), "ads.update")
            update_responses.append(resp)
        report["update_responses"] = update_responses

        archive_responses = []
        for batch in chunked(archive_ids, 200):
            resp = api_call(token, args.login, "ads", "archive", {"SelectionCriteria": {"Ids": batch}}, version="v5")
            result = ensure_ok(resp, "ads.archive")
            ensure_no_item_errors(result.get("ArchiveResults", []), "ads.archive")
            archive_responses.append(resp)
        report["archive_responses"] = archive_responses

    affected_ids = update_ad_ids + archive_ids
    post_ads = get_ads(token, args.login, affected_ids)
    affected_group_ids = sorted({ad.get("AdGroupId") for ad in post_ads if ad.get("AdGroupId")})
    post_groups = get_adgroups(token, args.login, affected_group_ids)
    sitelink_ids = sorted(
        {
            (ad.get("TextAd") or {}).get("SitelinkSetId")
            for ad in post_ads
            if (ad.get("TextAd") or {}).get("SitelinkSetId")
        }
    )
    post_sitelinks = get_sitelinks(token, args.login, sitelink_ids)
    report["postcheck"] = {
        "ads": post_ads,
        "adgroups": post_groups,
        "sitelinks": post_sitelinks,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
