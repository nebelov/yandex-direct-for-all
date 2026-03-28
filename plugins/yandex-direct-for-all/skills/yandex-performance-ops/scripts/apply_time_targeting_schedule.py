#!/usr/bin/env python3
"""Apply a daily time-targeting schedule to campaigns with read-back."""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


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


def api_call(token, login, service, method, params):
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
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {service}.{method}: {detail}") from exc


def ensure_result(resp, label):
    if "error" in resp:
        raise RuntimeError(f"{label}: {json.dumps(resp['error'], ensure_ascii=False)}")
    return resp.get("result", {})


def compact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            item = compact(item)
            if item is None:
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


def schedule_items(start_hour, end_hour):
    items = []
    for day in range(1, 8):
        hourly = []
        for hour in range(24):
            hourly.append("100" if start_hour <= hour < end_hour else "0")
        items.append(",".join([str(day), *hourly]))
    return items


def get_campaigns(token, login, campaign_ids):
    resp = api_call(
        token,
        login,
        "campaigns",
        "get",
        {
            "SelectionCriteria": {"Ids": campaign_ids},
            "FieldNames": ["Id", "Name", "TimeTargeting"],
        },
    )
    return ensure_result(resp, "campaigns.get").get("Campaigns", [])


def render_text(mode, start_hour, end_hour, campaigns, result):
    lines = [f"MODE\t{mode}", f"SCHEDULE\t{start_hour:02d}:00-{end_hour:02d}:00"]
    for campaign in campaigns:
        items = (campaign.get("TimeTargeting") or {}).get("Schedule", {}).get("Items", [])
        lines.append(
            f"CAMPAIGN\t{campaign.get('Id')}\t{campaign.get('Name')}\tschedule_items={len(items)}"
        )
    lines.append(f"RESULT\t{result}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Apply a daily schedule to campaigns")
    ap.add_argument("--token", default="")
    ap.add_argument("--token-file", default="")
    ap.add_argument("--login", required=True)
    ap.add_argument("--campaign-ids", required=True)
    ap.add_argument("--start-hour", type=int, required=True)
    ap.add_argument("--end-hour", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--output-json", default="")
    ap.add_argument("--output-text", default="")
    args = ap.parse_args()

    if not (0 <= args.start_hour <= 23):
        raise SystemExit("start-hour must be 0..23")
    if not (1 <= args.end_hour <= 24):
        raise SystemExit("end-hour must be 1..24")
    if args.start_hour >= args.end_hour:
        raise SystemExit("start-hour must be less than end-hour")

    token = load_token(args)
    campaign_ids = [int(part.strip()) for part in args.campaign_ids.split(",") if part.strip()]
    before = get_campaigns(token, args.login, campaign_ids)
    desired_items = schedule_items(args.start_hour, args.end_hour)

    payload = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "campaign_ids": campaign_ids,
        "start_hour": args.start_hour,
        "end_hour": args.end_hour,
        "before": before,
    }

    if not args.apply:
        text = render_text("DRY_RUN", args.start_hour, args.end_hour, before, "READY")
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.output_text:
            Path(args.output_text).write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        return

    update_rows = []
    for campaign in before:
        tt = campaign.get("TimeTargeting") or {}
        row = {
            "Id": int(campaign["Id"]),
            "TimeTargeting": compact(
                {
                    "Schedule": {"Items": desired_items},
                    "HolidaysSchedule": tt.get("HolidaysSchedule"),
                    "ConsiderWorkingWeekends": tt.get("ConsiderWorkingWeekends"),
                }
            ),
        }
        update_rows.append(row)

    update_resp = api_call(token, args.login, "campaigns", "update", {"Campaigns": update_rows})
    ensure_result(update_resp, "campaigns.update")
    after = get_campaigns(token, args.login, campaign_ids)
    mismatches = []
    for campaign in after:
        got = (campaign.get("TimeTargeting") or {}).get("Schedule", {}).get("Items", [])
        if got != desired_items:
            mismatches.append(int(campaign["Id"]))

    payload["update_response"] = update_resp
    payload["after"] = after
    payload["mismatches"] = mismatches
    payload["result"] = "OK" if not mismatches else "FAIL"
    text = render_text("APPLY", args.start_hour, args.end_hour, after, payload["result"])
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_text:
        Path(args.output_text).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if mismatches:
        sys.exit(1)


if __name__ == "__main__":
    main()
