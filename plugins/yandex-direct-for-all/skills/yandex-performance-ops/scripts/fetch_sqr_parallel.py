#!/usr/bin/env python3
"""Безопасный сбор отчёта поисковых запросов Яндекс.Директа."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from check_access_paths import DirectAccess, atomic_write_json, load_direct_access, sanitize_error


def _campaign_ids(raw: str, source: str) -> list[int]:
    values: list[int] = []
    if source:
        path = Path(source)
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        if lines and "\t" in lines[0]:
            for row in csv.DictReader(lines, delimiter="\t"):
                value = row.get("Id") or row.get("id") or row.get("CampaignId") or row.get("campaign_id")
                if value and str(value).strip().isdigit():
                    values.append(int(str(value).strip()))
        else:
            raw = ",".join(lines)
    for part in raw.replace("\n", ",").split(","):
        part = part.strip()
        if part:
            if not part.isdigit():
                raise ValueError("Номера кампаний должны быть целыми числами")
            values.append(int(part))
    return list(dict.fromkeys(values))


def _definition(campaign_id: int, date_from: str, date_to: str) -> dict[str, Any]:
    return {
        "SelectionCriteria": {"DateFrom": date_from, "DateTo": date_to, "Filter": [{"Field": "CampaignId", "Operator": "EQUALS", "Values": [str(campaign_id)]}]},
        "FieldNames": ["Date", "CampaignId", "CampaignName", "AdGroupId", "AdGroupName", "Query", "Keyword", "Impressions", "Clicks", "Cost", "Conversions", "ConversionRate"],
        "ReportName": f"public-sqr-{campaign_id}-{date_from}-{date_to}",
        "ReportType": "SEARCH_QUERY_PERFORMANCE_REPORT",
        "DateRangeType": "CUSTOM_DATE",
        "Format": "TSV",
        "IncludeVAT": "YES",
        "IncludeDiscount": "NO",
    }


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def collect_one(access: DirectAccess, campaign_id: int, date_from: str, date_to: str, output_dir: Path) -> dict[str, Any]:
    body = _canonical({"params": _definition(campaign_id, date_from, date_to)})
    request_sha = hashlib.sha256(body).hexdigest()
    host = "api-sandbox.direct.yandex.com" if access.environment == "sandbox" else "api.direct.yandex.com"
    headers = {
        "Authorization": f"Bearer {access.token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
        "processingMode": "auto",
    }
    if access.client_login:
        headers["Client-Login"] = access.client_login
    while True:
        request = urllib.request.Request(f"https://{host}/json/v5/reports", data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request) as response:
                payload = response.read()
                status = response.status
                response_headers = response.headers
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            status = exc.code
            response_headers = exc.headers
        if status == 200:
            path = output_dir / f"sqr_{campaign_id}.tsv"
            _atomic_bytes(path, payload)
            return {"campaign_id": campaign_id, "status": "ready", "request_sha256": request_sha, "artifact": path.name, "artifact_sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        if status in {201, 202}:
            retry = int(response_headers.get("retryIn") or 5)
            state = "queued" if status == 201 else "pending"
            atomic_write_json(output_dir / f"sqr_{campaign_id}.state.json", {"campaign_id": campaign_id, "status": state, "request_sha256": request_sha, "retry_in": retry, "reports_in_queue": response_headers.get("reportsInQueue", "")})
            time.sleep(max(1, retry))
            continue
        detail = payload.decode("utf-8", errors="replace")
        return {"campaign_id": campaign_id, "status": "error", "request_sha256": request_sha, "error": sanitize_error(f"HTTP {status}: {detail}", (access.token,))}


def merge_ready(output_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ready = [output_dir / row["artifact"] for row in rows if row.get("status") == "ready"]
    merged = bytearray()
    for index, path in enumerate(ready):
        lines = path.read_bytes().splitlines(keepends=True)
        merged.extend(b"".join(lines if index == 0 else lines[1:]))
    target = output_dir / "all_sqr.tsv"
    _atomic_bytes(target, bytes(merged))
    return {"artifact": target.name, "sha256": hashlib.sha256(merged).hexdigest(), "bytes": len(merged), "parts": len(ready)}


def collect(access_file: str | None, campaign_ids: list[int], date_from: str, date_to: str, output_dir: Path, workers: int) -> dict[str, Any]:
    access = load_direct_access(access_file)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        futures = {pool.submit(collect_one, access, cid, date_from, date_to, output_dir): cid for cid in campaign_ids}
        for future in as_completed(futures):
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append({"campaign_id": futures[future], "status": "error", "error": sanitize_error(exc, (access.token,))})
    rows.sort(key=lambda row: int(row["campaign_id"]))
    merged = merge_ready(output_dir, rows)
    manifest = {"complete": len(rows) == len(campaign_ids) and all(row["status"] == "ready" for row in rows), "campaigns": len(campaign_ids), "ready": sum(row["status"] == "ready" for row in rows), "failed": sum(row["status"] != "ready" for row in rows), "parts": rows, "merged": merged}
    atomic_write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Собрать отчёт поисковых запросов")
    parser.add_argument("--access-file", help="Защищённый файл доступа")
    parser.add_argument("--campaigns", default="")
    parser.add_argument("--campaigns-file", default="")
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--to", dest="date_to", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if any(item in {"--token", "--direct-token"} for item in sys.argv[1:]):
        parser.error("сырой токен в командной строке запрещён")
    try:
        ids = _campaign_ids(args.campaigns, args.campaigns_file)
        if not ids:
            raise ValueError("Не выбраны кампании")
        manifest = collect(args.access_file, ids, args.date_from, args.date_to, Path(args.output_dir), args.workers)
    except Exception as exc:
        print(f"Сбор не выполнен: {sanitize_error(exc)}", file=sys.stderr)
        return 1
    print("Отчёт собран полностью" if manifest["complete"] else "Отчёт собран частично")
    return 0 if manifest["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
