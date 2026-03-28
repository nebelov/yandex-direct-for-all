#!/usr/bin/env python3
import argparse
import json
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from zoneinfo import ZoneInfo


MSK = ZoneInfo("Europe/Moscow")
UTC = timezone.utc

MANUAL_SPECS = [
    ("lead_prior_any", "API база truth | лид: был лид раньше"),
    ("lead_prior_paid", "API база truth | лид: была покупка раньше"),
    ("lead_prior_paid_ge_2000", "API база truth | лид: была покупка >= 2000 раньше"),
    ("sale_prior_any", "API база truth | продажа: был лид раньше"),
    ("sale_prior_paid", "API база truth | продажа: была покупка раньше"),
    ("sale_prior_paid_ge_2000", "API база truth | продажа: была покупка >= 2000 раньше"),
    ("sale_old_visit_30", "API база truth | продажа из визита > 30 дней"),
    ("sale_old_visit_90", "API база truth | продажа из визита > 90 дней"),
    ("sale_old_visit_180", "API база truth | продажа из визита > 180 дней"),
]

FORMULA_SPECS = [
    ("sys_cost", "Система Roistat | Расход", "money", "{marketing_cost}"),
    ("sys_visits", "Система Roistat | Визиты", "integer", "{visits}"),
    ("sys_unique_visits", "Система Roistat | Уникальные посетители", "integer", "{unique_visits}"),
    ("sys_leads", "Система Roistat | Все заявки", "integer", "{leads}"),
    ("sys_sales", "Система Roistat | Все продажи", "integer", "{sales}"),
    ("sys_revenue", "Система Roistat | Вся выручка", "money", "{revenue}"),
    ("sys_first_leads", "Система Roistat | Новые заявки по внутренней логике", "integer", "{first_leads}"),
    ("sys_repeat_leads", "Система Roistat | Повторные заявки по внутренней логике", "integer", "{repeated_leads}"),
    ("sys_new_sales", "Система Roistat | Новые продажи по внутренней логике", "integer", "{new_sales}"),
    ("sys_repeat_sales", "Система Roistat | Повторные продажи по внутренней логике", "integer", "{repeated_sales}"),
    ("sys_first_sales_revenue", "Система Roistat | Выручка новых продаж по внутренней логике", "money", "{first_sales_revenue}"),
    ("sys_repeat_sales_revenue", "Система Roistat | Выручка повторных продаж по внутренней логике", "money", "{repeated_sales_revenue}"),
    ("fact_real_first_lead", "Факт по истории Roistat | Реально первый лид", "integer", "{leads} - {manual:lead_prior_any}"),
    ("fact_real_repeat_lead", "Факт по истории Roistat | Реально повторный лид", "integer", "{manual:lead_prior_any}"),
    ("fact_lead_had_paid_before", "Факт по истории Roistat | К этому лиду уже была покупка раньше", "integer", "{manual:lead_prior_paid}"),
    ("fact_lead_had_paid_ge_2000_before", "Факт по истории Roistat | К этому лиду уже была покупка раньше >= 2000 ₽", "integer", "{manual:lead_prior_paid_ge_2000}"),
    ("fact_old_lead_without_purchase", "Факт по истории Roistat | Лид старого клиента, у которого еще не было покупки", "integer", "{manual:lead_prior_any} - {manual:lead_prior_paid}"),
    ("fact_real_first_sale", "Факт по истории Roistat | Реально первая покупка", "integer", "{sales} - {manual:sale_prior_paid}"),
    ("fact_first_sale_after_old_lead", "Факт по истории Roistat | Первая покупка после более ранней заявки", "integer", "{manual:sale_prior_any} - {manual:sale_prior_paid}"),
    ("fact_real_repeat_sale", "Факт по истории Roistat | Реально повторная покупка", "integer", "{manual:sale_prior_paid}"),
    ("fact_repeat_sale_after_ge_2000", "Факт по истории Roistat | Повторная покупка после прошлой покупки >= 2000 ₽", "integer", "{manual:sale_prior_paid_ge_2000}"),
    ("attr_sale_old_visit_30", "Атрибуция по датам | Продажа из визита старше 30 дней", "integer", "{manual:sale_old_visit_30}"),
    ("attr_sale_old_visit_90", "Атрибуция по датам | Продажа из визита старше 90 дней", "integer", "{manual:sale_old_visit_90}"),
    ("attr_sale_old_visit_180", "Атрибуция по датам | Продажа из визита старше 180 дней", "integer", "{manual:sale_old_visit_180}"),
    ("diff_new_leads", "Расхождение системы и факта | Новые заявки Roistat минус реально первые лиды", "integer", "{first_leads} - ({leads} - {manual:lead_prior_any})"),
    ("diff_new_sales", "Расхождение системы и факта | Новые продажи Roistat минус реально первые покупки", "integer", "{new_sales} - ({sales} - {manual:sale_prior_paid})"),
    ("diff_repeat_sales", "Расхождение системы и факта | Повторные продажи Roistat минус реально повторные покупки", "integer", "{repeated_sales} - {manual:sale_prior_paid}"),
]

REPORT_TITLE = "Все каналы | Факт и атрибуция | 30 дней"


def parse_args():
    p = argparse.ArgumentParser(description="Sync factual Roistat truth-layer into manual metrics and a saved report.")
    p.add_argument("--project", required=True)
    p.add_argument("--api-key", default="")
    p.add_argument("--api-key-env", default="ROISTAT_API_KEY")
    p.add_argument("--base-url", default=os.environ.get("ROISTAT_BASE_URL", "https://cloud.roistat.com/api/v1"))
    p.add_argument("--rolling-days", type=int, default=30)
    p.add_argument("--end-date", default="")
    p.add_argument("--history-fallback", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--report-title", default=REPORT_TITLE)
    p.add_argument("--input-truth-rows", default="", help="Use an existing truth_rows json artifact instead of live recomputation.")
    p.add_argument("--write-mode", choices=["aggregate_period", "daily"], default="aggregate_period")
    p.add_argument("--source-mode", choices=["full", "l3"], default="full")
    p.add_argument("--filter-ml1", action="append", default=[])
    p.add_argument("--max-level", type=int, default=6)
    p.add_argument("--metric-title-suffix", default="")
    p.add_argument("--skip-clear", action="store_true")
    return p.parse_args()


def now_msk_date() -> date:
    return datetime.now(MSK).date()


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def start_end_dates(args) -> Tuple[date, date]:
    end_date = parse_date(args.end_date) if args.end_date else now_msk_date()
    start_date = end_date - timedelta(days=args.rolling_days - 1)
    return start_date, end_date


def local_bounds(day_from: date, day_to: date) -> Tuple[datetime, datetime]:
    start_local = datetime.combine(day_from, dtime(0, 0, 0), tzinfo=MSK)
    end_local = datetime.combine(day_to, dtime(23, 59, 59), tzinfo=MSK)
    return start_local, end_local


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def to_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def day_period(day_str: str) -> Dict[str, str]:
    day = parse_date(day_str)
    start_local = datetime.combine(day, dtime(0, 0, 0), tzinfo=MSK)
    end_local = datetime.combine(day, dtime(23, 59, 59), tzinfo=MSK)
    return {"from": to_iso(start_local), "to": to_iso(end_local)}


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


@dataclass
class RoistatAPI:
    base_url: str
    project: str
    api_key: str

    def request(self, method: str, endpoint: str, body=None, timeout=180):
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        params = {"project": self.project}
        headers = {"Api-key": self.api_key}
        attempt = 0
        while True:
            resp = requests.request(method, url, params=params, json=body, headers=headers, timeout=timeout)
            resp.raise_for_status()
            obj = resp.json()
            if obj.get("error") == "request_limit_error":
                attempt += 1
                if attempt > 8:
                    raise RuntimeError(f"{endpoint} -> request_limit_error after retries")
                time.sleep(min(60, 5 * attempt))
                continue
            return obj


def fetch_orders_window(api: RoistatAPI, start_local: datetime, end_local: datetime) -> List[dict]:
    rows: List[dict] = []
    offset = 0
    limit = 500
    start_utc = start_local.astimezone(UTC)
    while True:
        body = {"extend": ["visit"], "limit": limit, "offset": offset}
        obj = api.request("POST", "project/integration/order/list", body)
        data = obj.get("data") or []
        if not data:
            break
        rows.extend(data)
        oldest_dt = min(parse_dt(r.get("creation_date")) for r in data if r.get("creation_date"))
        if oldest_dt and oldest_dt < start_utc:
            break
        offset += limit
        total = obj.get("total")
        if total is not None and offset >= int(total):
            break
    kept = []
    for row in rows:
        created = parse_dt(row.get("creation_date"))
        if created is None:
            continue
        created_local = created.astimezone(MSK)
        if start_local <= created_local <= end_local:
            kept.append(row)
    return kept


def extract_source(row: dict) -> Tuple[str, List[str]]:
    visit = row.get("visit") or {}
    source = visit.get("source") or {}
    system_name = source.get("system_name") or ""
    levels = source.get("system_name_by_level") or []
    roistat_value = row.get("roistat") or ""
    if system_name:
        return system_name, levels
    if levels:
        return "_".join(levels), levels
    return roistat_value, []


def load_fallback_history(path: Path, window_start_local: datetime) -> Dict[str, dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    data = obj["data"]
    ym_uid = defaultdict(lambda: {"any": False, "paid": False, "paid_ge_2000": False})
    phone = defaultdict(lambda: {"any": False, "paid": False, "paid_ge_2000": False})
    visit_chain = defaultdict(lambda: {"any": False, "paid": False, "paid_ge_2000": False})
    for row in data:
        created = parse_dt(row.get("creation_date"))
        if created is None or created.astimezone(MSK) >= window_start_local:
            continue
        paid = (row.get("status") or {}).get("type") == "paid"
        revenue = float(row.get("revenue") or 0)
        visit = row.get("visit") or {}
        source = visit.get("source") or {}
        chain_keys = set()
        if row.get("visit_id"):
            chain_keys.add(str(row.get("visit_id")))
        if row.get("roistat"):
            chain_keys.add(str(row.get("roistat")))
        uid = visit.get("ym_uid") or ""
        if uid:
            slot = ym_uid[uid]
            slot["any"] = True
            slot["paid"] = slot["paid"] or paid
            slot["paid_ge_2000"] = slot["paid_ge_2000"] or (paid and revenue >= 2000)
        receiver_phone = normalize_phone((row.get("custom_fields") or {}).get("Телефон получателя", ""))
        if receiver_phone:
            slot = phone[receiver_phone]
            slot["any"] = True
            slot["paid"] = slot["paid"] or paid
            slot["paid_ge_2000"] = slot["paid_ge_2000"] or (paid and revenue >= 2000)
        for key in chain_keys:
            slot = visit_chain[key]
            slot["any"] = True
            slot["paid"] = slot["paid"] or paid
            slot["paid_ge_2000"] = slot["paid_ge_2000"] or (paid and revenue >= 2000)
    return {"ym_uid": ym_uid, "phone": phone, "visit_chain": visit_chain}


def fetch_prior_by_client(api: RoistatAPI, client_ids: Iterable[str], window_start_local: datetime) -> Dict[str, dict]:
    client_ids = [str(c) for c in client_ids if c]
    out = defaultdict(lambda: {"any": False, "paid": False, "paid_ge_2000": False})
    if not client_ids:
        return out
    cutoff = to_iso(window_start_local.astimezone(UTC))
    batch_size = 50
    for idx in range(0, len(client_ids), batch_size):
        batch = client_ids[idx:idx + batch_size]
        body = {
            "limit": 500,
            "offset": 0,
            "filters": [
                ["client_id", "in", batch],
                ["creation_date", "<", cutoff],
            ],
        }
        while True:
            obj = api.request("POST", "project/integration/order/list", body)
            data = obj.get("data") or []
            for row in data:
                cid = str(row.get("client_id") or "")
                if not cid:
                    continue
                paid = (row.get("status") or {}).get("type") == "paid"
                revenue = float(row.get("revenue") or 0)
                slot = out[cid]
                slot["any"] = True
                slot["paid"] = slot["paid"] or paid
                slot["paid_ge_2000"] = slot["paid_ge_2000"] or (paid and revenue >= 2000)
            if not data or len(data) < body["limit"]:
                break
            body["offset"] += body["limit"]
        print(json.dumps({"client_batch": idx // batch_size + 1, "of": (len(client_ids) + batch_size - 1) // batch_size, "rows": sum(v["any"] for v in out.values())}, ensure_ascii=False))
    return out


def row_truth(row: dict, prior_by_client: Dict[str, dict], fallback: Dict[str, dict]) -> dict:
    created = parse_dt(row.get("creation_date")).astimezone(MSK)
    visit = row.get("visit") or {}
    visit_date = parse_dt(visit.get("date"))
    visit_local = visit_date.astimezone(MSK) if visit_date else None
    source_key, levels = extract_source(row)
    status = row.get("status") or {}
    revenue = float(row.get("revenue") or 0)
    is_sale = status.get("type") == "paid"
    client_id = str(row.get("client_id") or "")
    by_client = prior_by_client.get(client_id, {"any": False, "paid": False, "paid_ge_2000": False})
    ym_uid = (visit.get("ym_uid") or "").strip()
    receiver_phone = normalize_phone((row.get("custom_fields") or {}).get("Телефон получателя", ""))
    chain_hit = {"any": False, "paid": False, "paid_ge_2000": False}
    for key in [str(row.get("visit_id") or ""), str(row.get("roistat") or "")]:
        if key and key in fallback["visit_chain"]:
            other = fallback["visit_chain"][key]
            chain_hit["any"] = chain_hit["any"] or other["any"]
            chain_hit["paid"] = chain_hit["paid"] or other["paid"]
            chain_hit["paid_ge_2000"] = chain_hit["paid_ge_2000"] or other["paid_ge_2000"]
    by_uid = fallback["ym_uid"].get(ym_uid, {"any": False, "paid": False, "paid_ge_2000": False})
    by_phone = fallback["phone"].get(receiver_phone, {"any": False, "paid": False, "paid_ge_2000": False})
    prior_any = any([by_client["any"], by_uid["any"], by_phone["any"], chain_hit["any"]])
    prior_paid = any([by_client["paid"], by_uid["paid"], by_phone["paid"], chain_hit["paid"]])
    prior_paid_ge_2000 = any([by_client["paid_ge_2000"], by_uid["paid_ge_2000"], by_phone["paid_ge_2000"], chain_hit["paid_ge_2000"]])
    age_days = None
    if visit_local:
        age_days = (created.date() - visit_local.date()).days
    return {
        "id": str(row.get("id")),
        "source_key": source_key,
        "levels": levels,
        "source_title": ((visit.get("source") or {}).get("display_name") or row.get("roistat") or ""),
        "day": created.date().isoformat(),
        "creation_dt_msk": to_iso(created),
        "visit_dt_msk": to_iso(visit_local) if visit_local else None,
        "client_id": client_id,
        "ym_uid": ym_uid,
        "receiver_phone": receiver_phone,
        "roistat": row.get("roistat") or "",
        "status_type": status.get("type") or "",
        "status_name": status.get("name") or "",
        "revenue": revenue,
        "is_sale": is_sale,
        "prior_any_fact": prior_any,
        "prior_paid_fact": prior_paid,
        "prior_paid_ge_2000_fact": prior_paid_ge_2000,
        "prior_any_by_client_id": by_client["any"],
        "prior_paid_by_client_id": by_client["paid"],
        "prior_paid_ge_2000_by_client_id": by_client["paid_ge_2000"],
        "prior_any_by_ym_uid": by_uid["any"],
        "prior_paid_by_ym_uid": by_uid["paid"],
        "prior_any_by_phone": by_phone["any"],
        "prior_paid_by_phone": by_phone["paid"],
        "prior_any_by_visit_chain": chain_hit["any"],
        "age_days": age_days,
        "is_old_visit_30": bool(age_days is not None and age_days > 30),
        "is_old_visit_90": bool(age_days is not None and age_days > 90),
        "is_old_visit_180": bool(age_days is not None and age_days > 180),
    }


def aggregate_daily(rows: List[dict]) -> Dict[Tuple[str, str], Dict[str, int]]:
    agg = defaultdict(lambda: defaultdict(int))
    for row in rows:
        key = (row["day"], row["source_key"])
        agg[key]["lead_prior_any"] += int(row["prior_any_fact"])
        agg[key]["lead_prior_paid"] += int(row["prior_paid_fact"])
        agg[key]["lead_prior_paid_ge_2000"] += int(row["prior_paid_ge_2000_fact"])
        agg[key]["sale_prior_any"] += int(row["is_sale"] and row["prior_any_fact"])
        agg[key]["sale_prior_paid"] += int(row["is_sale"] and row["prior_paid_fact"])
        agg[key]["sale_prior_paid_ge_2000"] += int(row["is_sale"] and row["prior_paid_ge_2000_fact"])
        agg[key]["lead_old_visit_30"] += int(row["is_old_visit_30"])
        agg[key]["lead_old_visit_90"] += int(row["is_old_visit_90"])
        agg[key]["lead_old_visit_180"] += int(row["is_old_visit_180"])
        agg[key]["sale_old_visit_30"] += int(row["is_sale"] and row["is_old_visit_30"])
        agg[key]["sale_old_visit_90"] += int(row["is_sale"] and row["is_old_visit_90"])
        agg[key]["sale_old_visit_180"] += int(row["is_sale"] and row["is_old_visit_180"])
    return agg


def aggregate_period(rows: List[dict]) -> Dict[str, Dict[str, int]]:
    agg = defaultdict(lambda: defaultdict(int))
    for row in rows:
        key = row["source_key"]
        agg[key]["lead_prior_any"] += int(row["prior_any_fact"])
        agg[key]["lead_prior_paid"] += int(row["prior_paid_fact"])
        agg[key]["lead_prior_paid_ge_2000"] += int(row["prior_paid_ge_2000_fact"])
        agg[key]["sale_prior_any"] += int(row["is_sale"] and row["prior_any_fact"])
        agg[key]["sale_prior_paid"] += int(row["is_sale"] and row["prior_paid_fact"])
        agg[key]["sale_prior_paid_ge_2000"] += int(row["is_sale"] and row["prior_paid_ge_2000_fact"])
        agg[key]["lead_old_visit_30"] += int(row["is_old_visit_30"])
        agg[key]["lead_old_visit_90"] += int(row["is_old_visit_90"])
        agg[key]["lead_old_visit_180"] += int(row["is_old_visit_180"])
        agg[key]["sale_old_visit_30"] += int(row["is_sale"] and row["is_old_visit_30"])
        agg[key]["sale_old_visit_90"] += int(row["is_sale"] and row["is_old_visit_90"])
        agg[key]["sale_old_visit_180"] += int(row["is_sale"] and row["is_old_visit_180"])
    return agg


def list_formula_metrics(api: RoistatAPI) -> List[dict]:
    return api.request("GET", "project/analytics/metrics/custom/list").get("data") or []


def list_manual_metrics(api: RoistatAPI) -> List[dict]:
    return api.request("POST", "project/analytics/metrics/custom/manual/list", {}).get("data") or []


def ensure_manual_metric(api: RoistatAPI, title: str) -> int:
    existing = {m["title"]: m for m in list_manual_metrics(api)}
    if title in existing:
        metric_id = int(existing[title]["id"])
        api.request("POST", "project/analytics/metrics/custom/manual/update", {"id": metric_id, "title": title, "type": "integer"})
        return metric_id
    api.request("POST", "project/analytics/metrics/custom/manual/create", {"title": title, "type": "integer"})
    refreshed = {m["title"]: m for m in list_manual_metrics(api)}
    return int(refreshed[title]["id"])


def ensure_formula_metric(api: RoistatAPI, title: str, formula: str, metric_type: str) -> int:
    existing = {m["title"]: m for m in list_formula_metrics(api)}
    body = {"title": title, "type": metric_type, "formula": formula}
    if title in existing:
        body["id"] = int(existing[title]["id"])
        api.request("POST", "project/analytics/metrics/custom/update", body)
        return int(existing[title]["id"])
    api.request("POST", "project/analytics/metrics/custom/create", body)
    refreshed = {m["title"]: m for m in list_formula_metrics(api)}
    return int(refreshed[title]["id"])


def list_manual_values(api: RoistatAPI, metric_id: int) -> List[dict]:
    return api.request("POST", "project/analytics/metrics/custom/manual/value/list", {"manual_custom_metric_id": metric_id}).get("data") or []


def clear_manual_values(api: RoistatAPI, metric_id: int, start_local: datetime, end_local: datetime):
    start_date = start_local.date().isoformat()
    end_date = end_local.date().isoformat()
    for item in list_manual_values(api, metric_id):
        df = item.get("date_from", "")[:10]
        if start_date <= df <= end_date:
            api.request("POST", "project/analytics/metrics/custom/manual/value/delete", {"id": int(item["id"])}, timeout=300)


def add_manual_value(api: RoistatAPI, metric_id: int, source: str, day: str, value: int):
    api.request(
        "POST",
        "project/analytics/metrics/custom/manual/value/add",
        {
            "manual_custom_metric_id": metric_id,
            "source": source,
            "period": day_period(day),
            "value": value,
        },
        timeout=300,
    )


def add_manual_value_for_period(api: RoistatAPI, metric_id: int, source: str, start_local: datetime, end_local: datetime, value: int):
    api.request(
        "POST",
        "project/analytics/metrics/custom/manual/value/add",
        {
            "manual_custom_metric_id": metric_id,
            "source": source,
            "period": {"from": to_iso(start_local), "to": to_iso(end_local)},
            "value": value,
        },
        timeout=300,
    )


def cleanup_tmp(api: RoistatAPI):
    manual = list_manual_metrics(api)
    for metric in manual:
        if metric["title"].startswith("API TMP"):
            for item in list_manual_values(api, int(metric["id"])):
                api.request("POST", "project/analytics/metrics/custom/manual/value/delete", {"id": int(item["id"])}, timeout=300)
            api.request("POST", "project/analytics/metrics/custom/manual/delete", {"id": int(metric["id"])}, timeout=300)
    for metric in list_formula_metrics(api):
        if metric["title"].startswith("API TMP"):
            api.request("POST", "project/analytics/metrics/custom/delete", {"id": int(metric["id"])}, timeout=300)


def build_formula(formula: str, manual_ids: Dict[str, int]) -> str:
    out = formula
    for slug, metric_id in manual_ids.items():
        out = out.replace(f"{{manual:{slug}}}", f"{{manual_custom_{metric_id}}}")
    return out


def build_report(metric_ids: List[int], title: str, max_level: int, filter_ml1: List[str]) -> dict:
    shown = [{"id": f"custom_{mid}", "attributionModel": "default", "isAvailable": True} for mid in metric_ids]
    levels = []
    ml1_set = list(dict.fromkeys(filter_ml1))
    for level in range(1, max_level + 1):
        filters = []
        if level == 1 and ml1_set:
            filters = [{
                "field": "marker_level_1",
                "operator": "in",
                "value": [{"value": v, "label": v} for v in ml1_set],
            }]
        levels.append({"dimension": f"marker_level_{level}", "isVisible": True, "level": level, "filters": filters})
    return {
        "title": title,
        "settings": {
            "backgroundColor": "#F8F9F9",
            "date_filter_type": "lead",
            "is_use_all_multichannel_visits": False,
            "_isWithNewMetrics": True,
            "levels": levels,
            "shownMetrics": shown,
        },
        "isSystem": 0,
        "isCreatedByEmployee": 0,
        "folderId": None,
        "isChanged": False,
    }


def save_report(api: RoistatAPI, report_spec: dict) -> dict:
    reports = api.request("POST", "project/analytics/reports", {}).get("reports") or []
    existing = next((r for r in reports if r.get("title") == report_spec["title"]), None)
    if existing:
        report_spec["id"] = existing["id"]
    api.request("POST", "project/analytics/report", {"report": report_spec}, timeout=300)
    refreshed = api.request("POST", "project/analytics/reports", {}).get("reports") or []
    return next(r for r in refreshed if r.get("title") == report_spec["title"])


def compute_expected_totals(rows: List[dict]) -> Dict[str, int]:
    totals = Counter()
    for row in rows:
        totals["real_first_lead"] += int(not row["prior_any_fact"])
        totals["real_repeat_lead"] += int(row["prior_any_fact"])
        totals["lead_had_paid_before"] += int(row["prior_paid_fact"])
        totals["lead_had_paid_ge_2000_before"] += int(row["prior_paid_ge_2000_fact"])
        totals["old_lead_without_purchase"] += int(row["prior_any_fact"] and not row["prior_paid_fact"])
        totals["real_first_sale"] += int(row["is_sale"] and not row["prior_paid_fact"])
        totals["first_sale_after_old_lead"] += int(row["is_sale"] and row["prior_any_fact"] and not row["prior_paid_fact"])
        totals["real_repeat_sale"] += int(row["is_sale"] and row["prior_paid_fact"])
        totals["repeat_sale_after_ge_2000"] += int(row["is_sale"] and row["prior_paid_ge_2000_fact"])
        totals["lead_old_visit_30"] += int(row["is_old_visit_30"])
        totals["lead_old_visit_90"] += int(row["is_old_visit_90"])
        totals["lead_old_visit_180"] += int(row["is_old_visit_180"])
        totals["sale_old_visit_30"] += int(row["is_sale"] and row["is_old_visit_30"])
        totals["sale_old_visit_90"] += int(row["is_sale"] and row["is_old_visit_90"])
        totals["sale_old_visit_180"] += int(row["is_sale"] and row["is_old_visit_180"])
    return dict(totals)


def load_prebuilt_truth_rows(path: Path, source_mode: str, filter_ml1: List[str]) -> List[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    rows = obj["rows"]
    fixed = []
    ml1_set = set(filter_ml1)
    for row in rows:
        if ml1_set and (row.get("ml1") or "") not in ml1_set:
            continue
        if source_mode == "l3":
            source_key = row.get("manual_source_key") or (row.get("roistat") or "")
        else:
            source_key = "_".join(row.get("levels") or []) or (row.get("roistat") or "")
        row["source_key"] = source_key
        row["day"] = (row.get("creation_dt_msk") or "")[:10]
        fixed.append(row)
    return fixed


def validate(api: RoistatAPI, start_local: datetime, end_local: datetime, expected: Dict[str, int], formula_ids: Dict[str, int], filter_ml1: List[str]) -> dict:
    metric_map = {
        f"custom_{formula_ids['fact_real_first_lead']}": "real_first_lead",
        f"custom_{formula_ids['fact_real_repeat_lead']}": "real_repeat_lead",
        f"custom_{formula_ids['fact_lead_had_paid_before']}": "lead_had_paid_before",
        f"custom_{formula_ids['fact_lead_had_paid_ge_2000_before']}": "lead_had_paid_ge_2000_before",
        f"custom_{formula_ids['fact_old_lead_without_purchase']}": "old_lead_without_purchase",
        f"custom_{formula_ids['fact_real_first_sale']}": "real_first_sale",
        f"custom_{formula_ids['fact_first_sale_after_old_lead']}": "first_sale_after_old_lead",
        f"custom_{formula_ids['fact_real_repeat_sale']}": "real_repeat_sale",
        f"custom_{formula_ids['fact_repeat_sale_after_ge_2000']}": "repeat_sale_after_ge_2000",
        f"custom_{formula_ids['attr_sale_old_visit_30']}": "sale_old_visit_30",
        f"custom_{formula_ids['attr_sale_old_visit_90']}": "sale_old_visit_90",
        f"custom_{formula_ids['attr_sale_old_visit_180']}": "sale_old_visit_180",
    }
    body = {
        "dimensions": ["marker_level_1"],
        "metrics": list(metric_map.keys()),
        "period": {"from": to_iso(start_local), "to": to_iso(end_local)},
    }
    if filter_ml1:
        body["filters"] = [{
            "field": "marker_level_1",
            "operator": "in",
            "value": filter_ml1,
        }]
    obj = api.request("POST", "project/analytics/data", body, timeout=300)
    mean = ((obj.get("data") or [{}])[0].get("mean") or {}).get("metrics") or []
    actual = {}
    for metric in mean:
        key = metric_map.get(metric["metric_name"])
        if key:
            actual[key] = int(metric["value"] or 0)
    return {
        "expected": expected,
        "actual_from_analytics_mean": actual,
        "diff": {k: actual.get(k, 0) - expected.get(k, 0) for k in expected},
    }


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    args = parse_args()
    api_key = args.api_key or os.environ.get(args.api_key_env, "")
    if not api_key:
        raise SystemExit(f"Missing API key. Use --api-key or set {args.api_key_env}.")
    api = RoistatAPI(args.base_url, args.project, api_key)
    start_date, end_date = start_end_dates(args)
    start_local, end_local = local_bounds(start_date, end_date)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cleanup_tmp(api)
    if args.input_truth_rows:
        truth_rows = load_prebuilt_truth_rows(Path(args.input_truth_rows), args.source_mode, args.filter_ml1)
        window_orders = truth_rows
        client_ids = sorted({str(r.get("client_id") or "") for r in truth_rows if r.get("client_id")})
    else:
        window_orders = fetch_orders_window(api, start_local, end_local)
        fallback = load_fallback_history(Path(args.history_fallback), start_local)
        client_ids = sorted({str(r.get("client_id") or "") for r in window_orders if r.get("client_id")})
        prior_by_client = fetch_prior_by_client(api, client_ids, start_local)
        truth_rows = [row_truth(row, prior_by_client, fallback) for row in window_orders]
    bucket_values = aggregate_period(truth_rows) if args.write_mode == "aggregate_period" else aggregate_daily(truth_rows)

    manual_ids = {}
    for slug, title in MANUAL_SPECS:
        final_title = f"{title}{args.metric_title_suffix}"
        manual_ids[slug] = ensure_manual_metric(api, final_title)
    if not args.skip_clear:
        for slug, metric_id in manual_ids.items():
            clear_manual_values(api, metric_id, start_local, end_local)

    ops = 0
    if args.write_mode == "aggregate_period":
        for source, metrics in sorted(bucket_values.items()):
            for slug, _title in MANUAL_SPECS:
                value = int(metrics.get(slug, 0))
                if value:
                    add_manual_value_for_period(api, manual_ids[slug], source, start_local, end_local, value)
                    ops += 1
    else:
        for (day, source), metrics in sorted(bucket_values.items()):
            for slug, _title in MANUAL_SPECS:
                value = int(metrics.get(slug, 0))
                if value:
                    add_manual_value(api, manual_ids[slug], source, day, value)
                    ops += 1

    formula_ids = {}
    for slug, title, metric_type, formula in FORMULA_SPECS:
        final_title = f"{title}{args.metric_title_suffix}"
        formula_ids[slug] = ensure_formula_metric(api, final_title, build_formula(formula, manual_ids), metric_type)

    shown_metric_ids = [formula_ids[slug] for slug, _title, _type, _formula in FORMULA_SPECS]
    report = save_report(api, build_report(shown_metric_ids, args.report_title, args.max_level, args.filter_ml1))

    expected = compute_expected_totals(truth_rows)
    validation = validate(api, start_local, end_local, expected, formula_ids, args.filter_ml1)

    write_json(output_dir / "truth_rows_live_30d.json", {"rows": truth_rows})
    write_json(output_dir / "daily_truth_aggregate.json", {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "write_mode": args.write_mode,
        "rows": (
            [
                {"day": day, "source": source, **dict(metrics)}
                for (day, source), metrics in sorted(bucket_values.items())
            ]
            if args.write_mode == "daily"
            else [
                {"source": source, **dict(metrics)}
                for source, metrics in sorted(bucket_values.items())
            ]
        ),
    })
    write_json(output_dir / "metric_mapping.json", {"manual_ids": manual_ids, "formula_ids": formula_ids})
    write_json(output_dir / "saved_report.json", report)
    write_json(output_dir / "validation.json", validation)
    summary = {
        "status": "success",
        "report_id": report["id"],
        "report_title": report["title"],
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "window_rows": len(window_orders),
        "truth_rows": len(truth_rows),
        "unique_sources": len({row["source_key"] for row in truth_rows if row["source_key"]}),
        "write_mode": args.write_mode,
        "source_buckets": len(bucket_values),
        "manual_value_writes": ops,
        "client_ids_window": len(client_ids),
        "expected_totals": expected,
        "validation_diff": validation["diff"],
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
