#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(
        description="Create or update a saved Roistat report in the cabinet via API."
    )
    p.add_argument("--project", required=True, help="Roistat project id")
    p.add_argument("--report-spec", required=True, help="Path to new_report_spec.json")
    p.add_argument("--api-key", default="", help="Roistat API key")
    p.add_argument(
        "--api-key-env", default="ROISTAT_API_KEY", help="Env var for API key"
    )
    p.add_argument(
        "--base-url",
        default=os.environ.get("ROISTAT_BASE_URL", "https://cloud.roistat.com/api/v1"),
        help="Base URL for Roistat API",
    )
    p.add_argument(
        "--report-id",
        default="",
        help="Existing saved report id for update. Omit for create.",
    )
    p.add_argument("--title", default="", help="Optional title override")
    p.add_argument(
        "--result-json",
        default="",
        help="Optional path to save the created/updated saved report JSON",
    )
    return p.parse_args()


def ensure_api_key(args):
    key = args.api_key or os.environ.get(args.api_key_env, "")
    if not key:
        raise SystemExit(
            f"Missing API key. Use --api-key or set {args.api_key_env}."
        )
    return key


def api_call(base_url, project, api_key, endpoint, body=None):
    url = f"{base_url.rstrip('/')}/{endpoint}?project={urllib.parse.quote(str(project))}"
    data = None
    headers = {"Api-key": api_key}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{endpoint} -> HTTP {e.code}: {detail[:500]}")
    return json.loads(payload.decode("utf-8", errors="replace"))


def load_report_spec(path):
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if "title" not in report or "settings" not in report:
        raise SystemExit("report-spec must contain top-level title and settings")
    report.setdefault("folderId", None)
    report.setdefault("isSystem", 0)
    report.setdefault("isCreatedByEmployee", 0)
    return report


def fetch_source_titles(base_url, project, api_key):
    try:
        payload = api_call(base_url, project, api_key, "project/analytics/source/list", {})
    except Exception:
        return {}
    titles = {}
    for item in payload.get("data", []):
        source = item.get("source")
        title = item.get("title")
        if source and title:
            titles[source] = title
    return titles


def normalize_saved_filter_value(field, value, source_titles):
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        normalized = []
        for item in value:
            label = source_titles.get(item, item)
            normalized.append({"value": item, "label": label})
        return normalized
    return value


def normalize_saved_report(report, source_titles):
    settings = report.setdefault("settings", {})
    if "date_filter_type" in settings and "dateFilterType" not in settings:
        settings["dateFilterType"] = settings["date_filter_type"]
    settings.setdefault("is_list_deals_available", False)
    settings.setdefault("is_list_deal_cards_available", False)
    settings.setdefault("is_list_calls_available", False)
    settings.setdefault("is_call_record_available", False)
    settings.setdefault("is_users_filter_available", False)
    settings.setdefault("available_user_emails", [])
    settings.setdefault("allowed_period", [])
    settings.setdefault("calendar_events", {"is_need_show": True, "filters": None})
    for level in settings.get("levels", []):
        filters = level.get("filters") or []
        for item in filters:
            item["value"] = normalize_saved_filter_value(
                item.get("field", ""),
                item.get("value"),
                source_titles,
            )
    return report


def reports_index(reports):
    return {str(report.get("id")): report for report in reports}


def main():
    args = parse_args()
    api_key = ensure_api_key(args)

    report = load_report_spec(args.report_spec)
    if args.title:
        report["title"] = args.title
    if args.report_id:
        report["id"] = str(args.report_id)

    source_titles = fetch_source_titles(args.base_url, args.project, api_key)
    report = normalize_saved_report(report, source_titles)

    before = api_call(args.base_url, args.project, api_key, "project/analytics/reports", {})
    before_reports = before["reports"]
    before_index = reports_index(before_reports)
    before_titles = {item.get("title") for item in before_reports}

    if not args.report_id and report["title"] in before_titles:
        raise SystemExit(
            f"Saved report with title {report['title']!r} already exists. "
            "Use --report-id to update it or --title to choose another title."
        )

    api_call(
        args.base_url,
        args.project,
        api_key,
        "project/analytics/report",
        {"report": report},
    )

    after = api_call(args.base_url, args.project, api_key, "project/analytics/reports", {})
    after_reports = after["reports"]
    after_index = reports_index(after_reports)

    target = None
    action = "updated" if args.report_id else "created"

    if args.report_id:
        target = after_index.get(str(args.report_id))
        if target is None:
            raise SystemExit(f"Report id={args.report_id} not found after update")
    else:
        new_ids = [rid for rid in after_index.keys() if rid not in before_index]
        if len(new_ids) == 1:
            target = after_index[new_ids[0]]
        else:
            matches = [
                item for item in after_reports if item.get("title") == report["title"]
            ]
            if len(matches) == 1:
                target = matches[0]
            else:
                raise SystemExit(
                    "Could not uniquely identify the created report after save"
                )

    if args.result_json:
        Path(args.result_json).write_text(
            json.dumps(target, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "action": action,
                "report_id": str(target.get("id")),
                "title": target.get("title"),
                "count_before": len(before_reports),
                "count_after": len(after_reports),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
