#!/usr/bin/env python3
"""Convert Yandex Direct autotargeting keywords to EXACT-only mode with read-back.

Supports:
- campaign-scoped discovery of `---autotargeting` keywords
- dry-run planning
- live apply via keywords.update
- post-apply validation that dangerous categories are disabled
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_V5 = "https://api.direct.yandex.com/json/v5"


def api_call(token, login, service, method, params):
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
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {service}.{method}: {detail}") from exc


def fetch_autotarget_keywords(token, login, campaign_ids):
    resp = api_call(
        token,
        login,
        "keywords",
        "get",
        {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "Keyword", "State", "Status", "AutotargetingCategories"],
        },
    )
    items = resp.get("result", {}).get("Keywords", [])
    out = []
    for item in items:
        if item.get("Keyword") != "---autotargeting":
            continue
        out.append(item)
    return out


def cats_map(keyword):
    mapping = {}
    for item in (keyword.get("AutotargetingCategories") or {}).get("Items", []):
        mapping[item.get("Category")] = item.get("Value")
    return mapping


def dangerous_yes(categories):
    dangerous = []
    for name in ("COMPETITOR", "BROADER", "ACCESSORY"):
        if categories.get(name) == "YES":
            dangerous.append(name)
    return dangerous


def update_exact_only(token, login, keyword_ids):
    payload = {
        "Keywords": [
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
            for keyword_id in keyword_ids
        ]
    }
    return api_call(token, login, "keywords", "update", payload)


def render_text(mode, before_items, after_items=None, result=None):
    lines = [f"MODE\t{mode}", f"AUTOTARGET_KEYWORDS\t{len(before_items)}"]
    for item in before_items:
        current = cats_map(item)
        lines.append(
            "BEFORE\t"
            f"campaign={item.get('CampaignId')}\tadgroup={item.get('AdGroupId')}\tkeyword_id={item.get('Id')}\t"
            f"state={item.get('State')}\tstatus={item.get('Status')}\tdangerous={','.join(dangerous_yes(current)) or '-'}\t"
            f"cats={json.dumps(current, ensure_ascii=False, sort_keys=True)}"
        )
    if after_items is not None:
        for item in after_items:
            current = cats_map(item)
            lines.append(
                "AFTER\t"
                f"campaign={item.get('CampaignId')}\tadgroup={item.get('AdGroupId')}\tkeyword_id={item.get('Id')}\t"
                f"state={item.get('State')}\tstatus={item.get('Status')}\tdangerous={','.join(dangerous_yes(current)) or '-'}\t"
                f"cats={json.dumps(current, ensure_ascii=False, sort_keys=True)}"
            )
    if result is not None:
        lines.append(f"RESULT\t{result}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Fix dangerous autotargeting categories to EXACT-only")
    ap.add_argument("--token", required=True)
    ap.add_argument("--login", required=True)
    ap.add_argument("--campaign-ids", required=True, help="Campaign IDs comma-separated")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--output-json", default="")
    ap.add_argument("--output-text", default="")
    args = ap.parse_args()

    campaign_ids = [int(part.strip()) for part in args.campaign_ids.split(",") if part.strip()]
    before_items = fetch_autotarget_keywords(args.token, args.login, campaign_ids)
    keyword_ids = [item["Id"] for item in before_items]
    before_violations = [
        {
            "campaign_id": item.get("CampaignId"),
            "adgroup_id": item.get("AdGroupId"),
            "keyword_id": item.get("Id"),
            "dangerous": dangerous_yes(cats_map(item)),
            "categories": cats_map(item),
        }
        for item in before_items
    ]
    payload = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "campaign_ids": campaign_ids,
        "before_count": len(before_items),
        "keyword_ids": keyword_ids,
        "before": before_violations,
    }

    if not args.apply:
        text = render_text("DRY_RUN", before_items, result="READY" if keyword_ids else "NO_AUTOTARGET")
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.output_text:
            Path(args.output_text).write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        return

    update_resp = update_exact_only(args.token, args.login, keyword_ids)
    after_items = fetch_autotarget_keywords(args.token, args.login, campaign_ids)
    after_violations = [
        {
            "campaign_id": item.get("CampaignId"),
            "adgroup_id": item.get("AdGroupId"),
            "keyword_id": item.get("Id"),
            "dangerous": dangerous_yes(cats_map(item)),
            "categories": cats_map(item),
        }
        for item in after_items
    ]
    failures = [item for item in after_violations if item["dangerous"]]
    payload["update_response"] = update_resp
    payload["after_count"] = len(after_items)
    payload["after"] = after_violations
    payload["result"] = "OK" if not failures else "FAIL"
    payload["failures"] = failures

    text = render_text("APPLY", before_items, after_items=after_items, result=payload["result"])
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_text:
        Path(args.output_text).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
