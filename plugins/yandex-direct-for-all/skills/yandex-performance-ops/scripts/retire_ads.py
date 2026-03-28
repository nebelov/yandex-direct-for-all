#!/usr/bin/env python3
"""Suspend and archive Yandex Direct ads with read-back validation."""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_V5 = "https://api.direct.yandex.com/json/v5"


def load_token(args):
    if args.token:
        return args.token.strip()
    if args.token_file:
        data = json.loads(Path(args.token_file).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (data.get("access_token") or data.get("token") or "").strip()
        return str(data).strip()
    raise SystemExit("token required: use --token or --token-file")


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


def ensure_result(resp, label):
    if "error" in resp:
        raise RuntimeError(f"{label}: {json.dumps(resp['error'], ensure_ascii=False)}")
    return resp.get("result", {})


def ensure_no_errors(items, label):
    bad = []
    for idx, item in enumerate(items):
        if item.get("Errors"):
            bad.append({"index": idx, "errors": item["Errors"]})
    if bad:
        raise RuntimeError(f"{label}: {json.dumps(bad, ensure_ascii=False)}")


def get_ads(token, login, ad_ids):
    resp = api_call(
        token,
        login,
        "ads",
        "get",
        {
            "SelectionCriteria": {"Ids": ad_ids},
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "Status", "State", "StatusClarification"],
        },
    )
    return ensure_result(resp, "ads.get").get("Ads", [])


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def render_text(mode, before, after_suspend=None, after_archive=None, result="READY"):
    lines = [f"MODE\t{mode}", f"ADS\t{len(before)}"]
    for item in before:
        lines.append(
            f"BEFORE\tad_id={item.get('Id')}\tcampaign={item.get('CampaignId')}\tadgroup={item.get('AdGroupId')}\t"
            f"status={item.get('Status')}\tstate={item.get('State')}\tclar={item.get('StatusClarification') or '-'}"
        )
    if after_suspend is not None:
        for item in after_suspend:
            lines.append(
                f"AFTER_SUSPEND\tad_id={item.get('Id')}\tstatus={item.get('Status')}\tstate={item.get('State')}\t"
                f"clar={item.get('StatusClarification') or '-'}"
            )
    if after_archive is not None:
        for item in after_archive:
            lines.append(
                f"AFTER_ARCHIVE\tad_id={item.get('Id')}\tstatus={item.get('Status')}\tstate={item.get('State')}\t"
                f"clar={item.get('StatusClarification') or '-'}"
            )
    lines.append(f"RESULT\t{result}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Suspend and archive ads")
    ap.add_argument("--token", default="")
    ap.add_argument("--token-file", default="")
    ap.add_argument("--login", required=True)
    ap.add_argument("--ad-ids", required=True, help="Comma-separated ad IDs")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--output-json", default="")
    ap.add_argument("--output-text", default="")
    args = ap.parse_args()

    token = load_token(args)
    ad_ids = [int(part.strip()) for part in args.ad_ids.split(",") if part.strip()]
    before = get_ads(token, args.login, ad_ids)
    payload = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "ad_ids": ad_ids,
        "before": before,
    }

    if not args.apply:
        text = render_text("DRY_RUN", before, result="READY")
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.output_text:
            Path(args.output_text).write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        return

    suspend_responses = []
    for batch in chunked(ad_ids, 200):
        resp = api_call(token, args.login, "ads", "suspend", {"SelectionCriteria": {"Ids": batch}})
        result = ensure_result(resp, "ads.suspend")
        ensure_no_errors(result.get("SuspendResults", []), "ads.suspend")
        suspend_responses.append(resp)
    after_suspend = get_ads(token, args.login, ad_ids)

    archive_responses = []
    for batch in chunked(ad_ids, 200):
        resp = api_call(token, args.login, "ads", "archive", {"SelectionCriteria": {"Ids": batch}})
        result = ensure_result(resp, "ads.archive")
        ensure_no_errors(result.get("ArchiveResults", []), "ads.archive")
        archive_responses.append(resp)
    after_archive = get_ads(token, args.login, ad_ids)

    still_on = [item["Id"] for item in after_archive if item.get("State") == "ON"]
    payload["suspend_responses"] = suspend_responses
    payload["archive_responses"] = archive_responses
    payload["after_suspend"] = after_suspend
    payload["after_archive"] = after_archive
    payload["result"] = "OK" if not still_on else "FAIL"
    payload["still_on"] = still_on

    text = render_text("APPLY", before, after_suspend=after_suspend, after_archive=after_archive, result=payload["result"])
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_text:
        Path(args.output_text).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if still_on:
        sys.exit(1)


if __name__ == "__main__":
    main()
