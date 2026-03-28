#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


DEFAULT_DIMENSIONS = ["marker_level_1", "marker_level_2", "marker_level_3"]

DEFAULT_METRICS = [
    "marketing_cost",
    "visits",
    "unique_visits",
    "leads",
    "first_leads",
    "repeated_leads",
    "sales",
    "new_sales",
    "repeated_sales",
    "revenue",
    "first_sales_revenue",
    "repeated_sales_revenue",
    "clients",
    "paid_clients",
    "cpl",
    "cpo",
    "cac",
    "ltv",
    "conversion_visits_to_leads",
    "conversion_leads_to_sales",
]

DEFAULT_ATTR_MODELS = ["default", "first_click", "last_click", "last_paid_click"]
DEFAULT_ATTR_METRICS = ["leads", "sales", "revenue", "clients", "paid_clients"]
DEFAULT_CUSTOM_METRIC_IDS = [1, 2, 7, 8, 9, 10, 23, 30, 31, 34, 35]


def parse_args():
    p = argparse.ArgumentParser(
        description="Build a standalone Roistat report pack via API only."
    )
    p.add_argument("--project", required=True, help="Roistat project id")
    p.add_argument("--api-key", default="", help="Roistat API key")
    p.add_argument(
        "--api-key-env", default="ROISTAT_API_KEY", help="Env var for API key"
    )
    p.add_argument(
        "--base-url",
        default=os.environ.get("ROISTAT_BASE_URL", "https://cloud.roistat.com/api/v1"),
        help="Base URL for Roistat API",
    )
    p.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD or ISO")
    p.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD or ISO")
    p.add_argument("--report-name", required=True, help="Local name for the new report")
    p.add_argument("--output-dir", required=True, help="Directory to save artifacts")
    p.add_argument(
        "--dimension",
        action="append",
        dest="dimensions",
        default=[],
        help="Repeatable dimension. Defaults to marker hierarchy.",
    )
    p.add_argument(
        "--metric",
        action="append",
        dest="metrics",
        default=[],
        help="Repeatable base metric. Defaults to the built-in report bundle.",
    )
    p.add_argument(
        "--attribution-model",
        action="append",
        dest="attr_models",
        default=[],
        help="Repeatable attribution model. Defaults to default/first/last/last_paid_click.",
    )
    p.add_argument(
        "--attribution-metric",
        action="append",
        dest="attr_metrics",
        default=[],
        help="Repeatable metric to duplicate across attribution models.",
    )
    p.add_argument(
        "--custom-metric-id",
        action="append",
        dest="custom_metric_ids",
        type=int,
        default=[],
        help="Repeatable custom metric id. Defaults to common new/repeat report ids.",
    )
    p.add_argument(
        "--marker-level-1",
        action="append",
        default=[],
        help="Repeatable filter for marker_level_1",
    )
    p.add_argument(
        "--marker-level-2",
        action="append",
        default=[],
        help="Repeatable filter for marker_level_2",
    )
    p.add_argument(
        "--order-limit", type=int, default=500, help="Page size for order audit"
    )
    p.add_argument(
        "--order-max-pages",
        type=int,
        default=20,
        help="Safety cap for order audit pagination",
    )
    p.add_argument(
        "--skip-orders", action="store_true", help="Skip integration/order/list audit"
    )
    p.add_argument(
        "--skip-excel", action="store_true", help="Skip export/excel step"
    )
    return p.parse_args()


def ensure_api_key(args):
    key = args.api_key or os.environ.get(args.api_key_env, "")
    if not key:
        raise SystemExit(
            f"Missing API key. Use --api-key or set {args.api_key_env}."
        )
    return key


def normalize_period(value, is_end):
    if "T" in value:
        return value if any(tz in value for tz in ["+03:00", "+0300", "Z"]) else f"{value}+0300"
    suffix = "23:59:59+0300" if is_end else "00:00:00+0300"
    return f"{value}T{suffix}"


def parse_dt(value):
    if not value:
        return None
    fixed = value.replace("Z", "+00:00")
    if fixed.endswith("+0300"):
        fixed = fixed[:-5] + "+03:00"
    return datetime.fromisoformat(fixed)


def api_call(base_url, project, api_key, endpoint, body=None, method="POST", binary=False):
    url = f"{base_url.rstrip('/')}/{endpoint}?project={urllib.parse.quote(str(project))}"
    data = None
    headers = {"Api-key": api_key}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{endpoint} -> HTTP {e.code}: {detail[:500]}")
    if binary:
        return payload
    text = payload.decode("utf-8", errors="replace")
    return json.loads(text)


def build_filters(args):
    filters = []
    if args.marker_level_1:
        if len(args.marker_level_1) == 1:
            filters.append(
                {"field": "marker_level_1", "operator": "=", "value": args.marker_level_1[0]}
            )
        else:
            filters.append(
                {
                    "field": "marker_level_1",
                    "operator": "in",
                    "value": list(args.marker_level_1),
                }
            )
    if args.marker_level_2:
        if len(args.marker_level_2) == 1:
            filters.append(
                {"field": "marker_level_2", "operator": "=", "value": args.marker_level_2[0]}
            )
        else:
            filters.append(
                {
                    "field": "marker_level_2",
                    "operator": "in",
                    "value": list(args.marker_level_2),
                }
            )
    return filters


def build_metrics(args, available_custom_ids):
    metrics = list(dict.fromkeys(args.metrics or DEFAULT_METRICS))
    attr_models = list(dict.fromkeys(args.attr_models or DEFAULT_ATTR_MODELS))
    attr_metrics = list(dict.fromkeys(args.attr_metrics or DEFAULT_ATTR_METRICS))
    custom_ids = list(dict.fromkeys(args.custom_metric_ids or DEFAULT_CUSTOM_METRIC_IDS))

    request_metrics = list(metrics)
    shown_metrics = [{"id": metric, "attributionModel": "default", "isAvailable": True} for metric in metrics]

    for custom_id in custom_ids:
        if custom_id not in available_custom_ids:
            continue
        metric_id = f"custom_{custom_id}"
        request_metrics.append(metric_id)
        shown_metrics.append({"id": metric_id, "attributionModel": "default", "isAvailable": True})

    for metric in attr_metrics:
        for model in attr_models:
            if model == "default":
                if metric not in request_metrics:
                    request_metrics.append(metric)
                continue
            request_metrics.append({"metric": metric, "attribution": model})
            shown_metrics.append({"id": metric, "attributionModel": model, "isAvailable": True})

    unique_request = []
    seen = set()
    for metric in request_metrics:
        key = json.dumps(metric, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            unique_request.append(metric)
    return unique_request, shown_metrics


def build_report_spec(args, dimensions, shown_metrics, filters):
    return {
        "title": args.report_name,
        "settings": {
            "backgroundColor": "#F8F9F9",
            "date_filter_type": "lead",
            "is_use_all_multichannel_visits": False,
            "_isWithNewMetrics": True,
            "levels": [
                {
                    "dimension": dimension,
                    "isVisible": True,
                    "level": idx + 1,
                    "filters": filters if idx == 0 else [],
                }
                for idx, dimension in enumerate(dimensions)
            ],
            "shownMetrics": shown_metrics,
        },
        "isSystem": 0,
        "isCreatedByEmployee": 0,
        "folderId": None,
        "isChanged": False,
    }


def flatten_metric_name(metric):
    name = metric.get("metric_name") or metric.get("id") or "metric"
    attr = metric.get("attribution_model_id", "default")
    return f"{name}__{attr}"


def flatten_dimensions(dimensions, row):
    if isinstance(dimensions, dict):
        for key, meta in dimensions.items():
            if isinstance(meta, dict):
                row[f"{key}__value"] = meta.get("value")
                row[f"{key}__title"] = meta.get("title")
            else:
                row[f"{key}__value"] = meta
    elif isinstance(dimensions, list):
        for idx, meta in enumerate(dimensions):
            key = f"dimension_{idx+1}"
            if isinstance(meta, dict):
                row[f"{key}__value"] = meta.get("value")
                row[f"{key}__title"] = meta.get("title")
            else:
                row[f"{key}__value"] = meta
    return row


def flatten_analytics_items(response):
    rows = []
    data = response.get("data") or []
    if not data:
        return rows
    items = data[0].get("items") or []
    for item in items:
        row = {}
        row = flatten_dimensions(item.get("dimensions"), row)
        for metric in item.get("metrics", []):
            row[flatten_metric_name(metric)] = metric.get("value")
        row["isHasChild"] = item.get("isHasChild")
        rows.append(row)
    return rows


def write_tsv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fetch_orders(base_url, project, api_key, date_from, date_to, page_size, max_pages):
    all_rows = []
    offset = 0
    start_dt = parse_dt(date_from)
    end_dt = parse_dt(date_to)
    for _ in range(max_pages):
        body = {"extend": ["visit"], "limit": page_size, "offset": offset}
        response = api_call(
            base_url, project, api_key, "project/integration/order/list", body=body
        )
        if response.get("status") == "error":
            raise RuntimeError(
                f"project/integration/order/list -> {response.get('error')}: {response.get('description')}"
            )
        data = response.get("data") or []
        all_rows.extend(data)
        total = response.get("total")
        oldest_dt = None
        for row in data:
            row_dt = parse_dt(row.get("creation_date"))
            if row_dt is not None and (oldest_dt is None or row_dt < oldest_dt):
                oldest_dt = row_dt
        if oldest_dt is not None and start_dt is not None and oldest_dt < start_dt:
            break
        if not data or total is None:
            if len(data) < page_size:
                break
        offset += page_size
        if total is not None and offset >= total:
            break
    return all_rows


def flatten_orders(rows, date_from=None, date_to=None, marker_level_1=None, marker_level_2=None):
    flat = []
    start_dt = parse_dt(date_from) if date_from else None
    end_dt = parse_dt(date_to) if date_to else None
    marker_level_1 = set(marker_level_1 or [])
    marker_level_2 = set(marker_level_2 or [])
    for row in rows:
        created = parse_dt(row.get("creation_date"))
        visit = row.get("visit") or {}
        source = visit.get("source") or {}
        status = row.get("status") or {}
        source_levels = source.get("system_name_by_level") or []
        source_ml1 = source.get("marker_level_1") or (source_levels[0] if len(source_levels) > 0 else None)
        source_ml2 = source.get("marker_level_2") or (source_levels[1] if len(source_levels) > 1 else None)
        source_ml3 = source.get("marker_level_3") or (source_levels[2] if len(source_levels) > 2 else None)
        if created is None:
            continue
        if start_dt and created < start_dt:
            continue
        if end_dt and created > end_dt:
            continue
        if marker_level_1 and source_ml1 not in marker_level_1:
            continue
        if marker_level_2 and source_ml2 not in marker_level_2:
            continue
        flat.append(
            {
                "id": row.get("id"),
                "creation_date": row.get("creation_date"),
                "source_type": row.get("source_type"),
                "revenue": row.get("revenue"),
                "status_id": status.get("id"),
                "status_name": status.get("name"),
                "roistat": row.get("roistat"),
                "visit_id": visit.get("id"),
                "visit_date": visit.get("date"),
                "visit_marker_level_1": source_ml1,
                "visit_marker_level_2": source_ml2,
                "visit_marker_level_3": source_ml3,
                "visit_landing_page": visit.get("landing_page"),
                "visit_referrer_host": visit.get("referrer_host"),
                "url": row.get("url"),
            }
        )
    return flat


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_summary(
    output_dir,
    report_spec,
    dimensions,
    request_metrics,
    analytics_rows,
    custom_metrics,
    saved_reports,
    order_rows,
):
    lines = [
        f"# {report_spec['title']}",
        "",
        "Это новый standalone report-pack, собранный через API.",
        "Существующие сохраненные отчеты в кабинете не изменялись.",
        "",
        "## Состав",
        "",
        f"- Сохраненных отчетов в проекте: {len(saved_reports)}",
        f"- Кастомных метрик в проекте: {len(custom_metrics)}",
        f"- Измерений в новом отчете: {len(dimensions)}",
        f"- Метрик в API-запросе: {len(request_metrics)}",
        f"- Строк в analytics/data: {len(analytics_rows)}",
        f"- Сделок в order-audit: {len(order_rows)}",
        "",
        "## Артефакты",
        "",
        "- `saved_reports_snapshot.json`",
        "- `custom_metrics_snapshot.json`",
        "- `new_report_spec.json`",
        "- `analytics_request.json`",
        "- `analytics_response.json`",
        "- `analytics_rows.tsv`",
        "- `analytics_export.xlsx`",
        "- `orders_raw.json`",
        "- `orders_rows.tsv`",
        "",
        "## Важное",
        "",
        "- Новый отчет собран с нуля как JSON-спека.",
        "- Discovery старых отчетов использован только для понимания, какие метрики уже живут в проекте.",
        "- Если нужен persisted report внутри кабинета, нужен отдельно подтвержденный write-endpoint.",
        "",
    ]
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    args = parse_args()
    api_key = ensure_api_key(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_from = normalize_period(args.date_from, is_end=False)
    date_to = normalize_period(args.date_to, is_end=True)
    dimensions = args.dimensions or DEFAULT_DIMENSIONS
    filters = build_filters(args)

    saved_reports = api_call(
        args.base_url, args.project, api_key, "project/analytics/reports", body={}
    ).get("reports", [])
    custom_metrics_resp = api_call(
        args.base_url,
        args.project,
        api_key,
        "project/analytics/metrics/custom/list",
        method="GET",
    )
    custom_metrics = custom_metrics_resp.get("data", [])
    available_custom_ids = {int(item["id"]) for item in custom_metrics if "id" in item}

    request_metrics, shown_metrics = build_metrics(args, available_custom_ids)
    report_spec = build_report_spec(args, dimensions, shown_metrics, filters)
    analytics_request = {
        "dimensions": dimensions,
        "metrics": request_metrics,
        "period": {"from": date_from, "to": date_to},
        "filters": filters,
    }

    analytics_response = api_call(
        args.base_url,
        args.project,
        api_key,
        "project/analytics/data",
        body=analytics_request,
    )
    analytics_rows = flatten_analytics_items(analytics_response)

    write_json(output_dir / "saved_reports_snapshot.json", {"reports": saved_reports})
    write_json(
        output_dir / "custom_metrics_snapshot.json", {"data": custom_metrics}
    )
    write_json(output_dir / "new_report_spec.json", report_spec)
    write_json(output_dir / "analytics_request.json", analytics_request)
    write_json(output_dir / "analytics_response.json", analytics_response)
    write_tsv(output_dir / "analytics_rows.tsv", analytics_rows)

    if not args.skip_excel:
        xlsx = api_call(
            args.base_url,
            args.project,
            api_key,
            "project/analytics/data/export/excel",
            body=analytics_request,
            binary=True,
        )
        (output_dir / "analytics_export.xlsx").write_bytes(xlsx)

    order_rows = []
    if not args.skip_orders:
        orders_raw = fetch_orders(
            args.base_url,
            args.project,
            api_key,
            date_from,
            date_to,
            args.order_limit,
            args.order_max_pages,
        )
        order_rows = flatten_orders(
            orders_raw,
            date_from=date_from,
            date_to=date_to,
            marker_level_1=args.marker_level_1,
            marker_level_2=args.marker_level_2,
        )
        write_json(output_dir / "orders_raw.json", {"data": orders_raw})
        write_tsv(output_dir / "orders_rows.tsv", order_rows)

    build_summary(
        output_dir,
        report_spec,
        dimensions,
        request_metrics,
        analytics_rows,
        custom_metrics,
        saved_reports,
        order_rows,
    )

    print(f"Saved report pack to {output_dir}")
    print(f"analytics rows: {len(analytics_rows)}")
    print(f"orders rows: {len(order_rows)}")


if __name__ == "__main__":
    main()
