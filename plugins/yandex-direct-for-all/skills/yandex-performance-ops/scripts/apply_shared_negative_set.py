#!/usr/bin/env python3
"""Create a shared negative set and attach it to unified campaigns with read-back."""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_V5 = "https://api.direct.yandex.com/json/v5"
API_V501 = "https://api.direct.yandex.com/json/v501"


def load_token(args):
    if args.token:
        return args.token.strip()
    if args.token_file:
        data = json.loads(Path(args.token_file).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("access_token") or data.get("token") or "").strip()
        return str(data).strip()
    raise SystemExit("token required: use --token or --token-file")


def api_call(token, login, service, method, params, version="v5"):
    base = API_V501 if version == "v501" else API_V5
    req = urllib.request.Request(
        f"{base}/{service}",
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
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {service}.{method}: {detail}") from exc


def ensure_result(resp, label):
    if "error" in resp:
        raise RuntimeError(f"{label}: {json.dumps(resp['error'], ensure_ascii=False)}")
    return resp.get("result", {})


def read_items(path):
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("items file must be a JSON array")
    cleaned = []
    seen = set()
    for raw in items:
        text = str(raw).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def get_campaigns(token, login, campaign_ids):
    resp = api_call(
        token,
        login,
        "campaigns",
        "get",
        {
            "SelectionCriteria": {"Ids": campaign_ids},
            "FieldNames": ["Id", "Name"],
            "UnifiedCampaignFieldNames": ["NegativeKeywordSharedSetIds"],
        },
        version="v501",
    )
    return ensure_result(resp, "campaigns.get").get("Campaigns", [])


def create_shared_set(token, login, name, items):
    resp = api_call(
        token,
        login,
        "negativekeywordsharedsets",
        "add",
        {"NegativeKeywordSharedSets": [{"Name": name, "NegativeKeywords": items}]},
        version="v5",
    )
    result = ensure_result(resp, "negativekeywordsharedsets.add")
    rows = result.get("AddResults", [])
    if not rows or rows[0].get("Errors"):
        raise RuntimeError(f"negativekeywordsharedsets.add item errors: {json.dumps(rows, ensure_ascii=False)}")
    return int(rows[0]["Id"]), resp


def attach_shared_set(token, login, campaigns, shared_set_id):
    payload = []
    plans = []
    for campaign in campaigns:
        current = list((campaign.get("UnifiedCampaign", {}).get("NegativeKeywordSharedSetIds") or {}).get("Items", []))
        merged = []
        seen = set()
        for item in current + [shared_set_id]:
            item = int(item)
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
        plans.append(
            {
                "campaign_id": int(campaign["Id"]),
                "campaign_name": campaign.get("Name", ""),
                "before_ids": current,
                "after_ids": merged,
                "changed": current != merged,
            }
        )
        if current != merged:
            payload.append(
                {
                    "Id": int(campaign["Id"]),
                    "UnifiedCampaign": {"NegativeKeywordSharedSetIds": {"Items": merged}},
                }
            )
    if not payload:
        return plans, None
    resp = api_call(token, login, "campaigns", "update", {"Campaigns": payload}, version="v501")
    ensure_result(resp, "campaigns.update")
    return plans, resp


def render_text(mode, shared_set_name, shared_set_id, items, plans, result):
    lines = [f"MODE\t{mode}", f"SHARED_SET_NAME\t{shared_set_name}"]
    if shared_set_id is not None:
        lines.append(f"SHARED_SET_ID\t{shared_set_id}")
    lines.append(f"ITEMS_COUNT\t{len(items)}")
    lines.append(f"ITEMS\t{', '.join(items)}")
    for plan in plans:
        lines.append(
            "CAMPAIGN\t"
            f"{plan['campaign_id']}\t{plan['campaign_name']}\tchanged={plan['changed']}\t"
            f"before={plan['before_ids']}\tafter={plan['after_ids']}"
        )
    lines.append(f"RESULT\t{result}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Create and attach a shared negative set")
    ap.add_argument("--token", default="")
    ap.add_argument("--token-file", default="")
    ap.add_argument("--login", required=True)
    ap.add_argument("--campaign-ids", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--items-json", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--output-json", default="")
    ap.add_argument("--output-text", default="")
    args = ap.parse_args()

    token = load_token(args)
    campaign_ids = [int(part.strip()) for part in args.campaign_ids.split(",") if part.strip()]
    items = read_items(args.items_json)
    campaigns_before = get_campaigns(token, args.login, campaign_ids)

    shared_set_id = None
    plans = []
    payload = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "campaign_ids": campaign_ids,
        "shared_set_name": args.name,
        "items": items,
    }

    if not args.apply:
        plans = [
            {
                "campaign_id": int(campaign["Id"]),
                "campaign_name": campaign.get("Name", ""),
                "before_ids": list((campaign.get("UnifiedCampaign", {}).get("NegativeKeywordSharedSetIds") or {}).get("Items", [])),
                "after_ids": list((campaign.get("UnifiedCampaign", {}).get("NegativeKeywordSharedSetIds") or {}).get("Items", [])) + ["<new_set_id>"],
                "changed": True,
            }
            for campaign in campaigns_before
        ]
        text = render_text("DRY_RUN", args.name, None, items, plans, "READY")
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.output_text:
            Path(args.output_text).write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        return

    shared_set_id, add_resp = create_shared_set(token, args.login, args.name, items)
    plans, update_resp = attach_shared_set(token, args.login, campaigns_before, shared_set_id)
    campaigns_after = get_campaigns(token, args.login, campaign_ids)
    missing = []
    for campaign in campaigns_after:
        ids = list((campaign.get("UnifiedCampaign", {}).get("NegativeKeywordSharedSetIds") or {}).get("Items", [])
)
        if shared_set_id not in [int(x) for x in ids]:
            missing.append(int(campaign["Id"]))
    payload["shared_set_id"] = shared_set_id
    payload["shared_set_add_response"] = add_resp
    payload["campaign_plans"] = plans
    payload["campaign_update_response"] = update_resp
    payload["campaigns_after"] = campaigns_after
    payload["missing_campaign_ids"] = missing
    payload["result"] = "OK" if not missing else "FAIL"
    text = render_text("APPLY", args.name, shared_set_id, items, plans, payload["result"])
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_text:
        Path(args.output_text).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
