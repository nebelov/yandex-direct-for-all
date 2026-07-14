#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

import httpx


BASE_URL = "https://searchapi.api.cloud.yandex.net"
DNS_MARKERS = (
    "[errno 8]",
    "enotfound",
    "eai_again",
    "nodename nor servname provided",
    "temporary failure in name resolution",
    "connecterror",
    "getaddrinfo",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect a file-first Wordstat bundle via Yandex Search API v2."
    )
    parser.add_argument("--masks-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--regions", default="225")
    parser.add_argument("--devices", default="all")
    parser.add_argument("--num-phrases", type=int, default=2000)
    parser.add_argument("--dynamics", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def write_json_atomic(path: Path, payload: Any, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if mode is not None:
        os.chmod(temporary, mode)
    temporary.replace(path)


def safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def normalize_mask(mask: str) -> str:
    text = str(mask or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text


def parse_masks(path: Path) -> list[tuple[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("masks file is empty")
    if lines[0].strip().lower() == "mask":
        lines = ["mask\tintent", *lines[1:]]
    if "\t" in lines[0]:
        header = [part.strip().lower() for part in lines[0].split("\t")]
        if "mask" in header:
            idx_mask = header.index("mask")
            idx_intent = header.index("intent") if "intent" in header else None
            rows: list[tuple[str, str]] = []
            for line in lines[1:]:
                cols = line.split("\t")
                mask = cols[idx_mask] if idx_mask < len(cols) else ""
                intent = cols[idx_intent] if idx_intent is not None and idx_intent < len(cols) else ""
                if normalize_mask(mask):
                    rows.append((mask, intent.strip()))
            if rows:
                return rows
    rows = []
    for line in lines:
        if line.startswith("#"):
            continue
        raw_mask, _, intent = line.partition("\t")
        if normalize_mask(raw_mask):
            rows.append((raw_mask, intent.strip()))
    if not rows:
        raise RuntimeError("no valid masks found")
    return rows


def cloud_device(value: str) -> str:
    mapping = {
        "ALL": "DEVICE_ALL",
        "DESKTOP": "DEVICE_DESKTOP",
        "MOBILE": "DEVICE_PHONE",
        "PHONE": "DEVICE_PHONE",
        "SMARTPHONE": "DEVICE_PHONE",
        "TABLET": "DEVICE_TABLET",
    }
    normalized = str(value or "").strip().upper()
    if normalized.startswith("DEVICE_"):
        return normalized
    return mapping.get(normalized, "DEVICE_ALL")


def month_range(months_back: int = 6) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start_year = now.year
    start_month = now.month - months_back
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start = date(start_year, start_month, 1)
    end = date(now.year, now.month, 1) - timedelta(days=1)
    return f"{start.isoformat()}T00:00:00Z", f"{end.isoformat()}T23:59:59Z"


def is_transient_transport_error(summary: str) -> bool:
    blob = str(summary or "").lower()
    return any(marker in blob for marker in DNS_MARKERS)


def is_int_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, str) and bool(re.fullmatch(r"-?\d+", value))


def is_number_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if not isinstance(value, str):
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def require_object(payload: Any, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object")
    return payload


def require_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def validate_phrase_rows(rows: list[Any], field: str) -> None:
    for index, row in enumerate(rows):
        item = require_object(row, f"{field}[{index}]")
        if not isinstance(item.get("phrase"), str) or not is_int_like(item.get("count")):
            raise ValueError(f"{field}[{index}] must contain phrase and count")


def validate_top_response(payload: Any) -> None:
    item = require_object(payload, "topRequests response")
    if not is_int_like(item.get("totalCount")):
        raise ValueError("totalCount must be an integer")
    validate_phrase_rows(require_list(item, "results"), "results")
    validate_phrase_rows(require_list(item, "associations"), "associations")


def validate_dynamics_response(payload: Any) -> None:
    item = require_object(payload, "dynamics response")
    for index, row in enumerate(require_list(item, "results")):
        value = require_object(row, f"results[{index}]")
        if not isinstance(value.get("date"), str):
            raise ValueError(f"results[{index}].date must be a timestamp")
        if not is_int_like(value.get("count")) or not is_number_like(value.get("share")):
            raise ValueError(f"results[{index}] must contain count and share")


def validate_regions_response(payload: Any) -> None:
    item = require_object(payload, "regions response")
    for index, row in enumerate(require_list(item, "results")):
        value = require_object(row, f"results[{index}]")
        if not isinstance(value.get("region"), str) or not is_int_like(value.get("count")):
            raise ValueError(f"results[{index}] must contain region and count")
        if not is_number_like(value.get("share")) or not is_number_like(value.get("affinityIndex")):
            raise ValueError(f"results[{index}] must contain share and affinityIndex")


def validate_regions_tree_response(payload: Any) -> None:
    item = require_object(payload, "regions tree response")

    def validate_nodes(nodes: Any, path: str) -> None:
        if not isinstance(nodes, list):
            raise ValueError(f"{path} must be an array")
        for index, row in enumerate(nodes):
            value = require_object(row, f"{path}[{index}]")
            if not isinstance(value.get("id"), str) or not isinstance(value.get("label"), str):
                raise ValueError(f"{path}[{index}] must contain id and label")
            validate_nodes(value.get("children", []), f"{path}[{index}].children")

    validate_nodes(item.get("regions"), "regions")


class QuotaPacer:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.lock_path = state_path.with_suffix(f"{state_path.suffix}.lock")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state_path.parent, 0o700)

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"requestTimes": [], "billedTimes": [], "nextAllowedAt": 0.0}
        try:
            state = load_json(self.state_path)
        except Exception:
            return {"requestTimes": [], "billedTimes": [], "nextAllowedAt": 0.0}
        return state

    def _save(self, state: dict[str, Any]) -> None:
        write_json_atomic(self.state_path, state, mode=0o600)

    def before_request(self, billed: bool = True) -> None:
        while True:
            with self.lock_path.open("a+", encoding="utf-8") as lock_file:
                os.chmod(self.lock_path, 0o600)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                now = time.time()
                state = self._load()
                request_times = sorted(
                    float(value)
                    for value in state.get("requestTimes", [])
                    if isinstance(value, (int, float)) and float(value) > now - 3600
                )
                billed_times = sorted(
                    float(value)
                    for value in state.get("billedTimes", state.get("requestTimes", []))
                    if isinstance(value, (int, float)) and float(value) > now - 3600
                )
                next_allowed = float(state.get("nextAllowedAt") or 0.0)
                wait_seconds = max(0.0, next_allowed - now)
                recent_second = [value for value in request_times if value > now - 1]
                if len(recent_second) >= 10:
                    wait_seconds = max(wait_seconds, recent_second[0] + 1 - now)
                if len(request_times) >= 100:
                    wait_seconds = max(wait_seconds, request_times[0] + 3600 - now)
                if wait_seconds <= 0:
                    request_times.append(now)
                    if billed:
                        billed_times.append(now)
                    self._save({
                        "requestTimes": request_times,
                        "billedTimes": billed_times,
                        "nextAllowedAt": next_allowed,
                    })
                    return
            time.sleep(wait_seconds)

    def defer(self, seconds: float) -> None:
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            state = self._load()
            state["nextAllowedAt"] = max(
                float(state.get("nextAllowedAt") or 0.0), time.time() + max(seconds, 1.0)
            )
            self._save(state)


def retry_after_seconds(response: httpx.Response) -> float:
    raw = str(response.headers.get("Retry-After") or "").strip()
    if not raw:
        return 60.0
    try:
        return max(float(raw), 1.0)
    except ValueError:
        try:
            target = parsedate_to_datetime(raw)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max((target - datetime.now(timezone.utc)).total_seconds(), 1.0)
        except (TypeError, ValueError, OverflowError):
            return 60.0


def request_cloud(
    api_key: str,
    endpoint: str,
    body: dict[str, Any],
    validator: Callable[[Any], None],
    pacer: QuotaPacer,
) -> dict[str, Any]:
    attempt = 0
    transient_failures = 0
    while True:
        attempt += 1
        pacer.before_request(billed=endpoint != "/v2/wordstat/getRegionsTree")
        try:
            response = httpx.post(
                f"{BASE_URL}{endpoint}",
                headers={
                    "Authorization": f"Api-Key {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=60,
            )
            payload = safe_json(response)
            if response.status_code == 429:
                wait_seconds = retry_after_seconds(response)
                pacer.defer(wait_seconds)
                continue
            result = {
                "endpoint": endpoint,
                "http_status": response.status_code,
                "ok": response.is_success,
                "payload": payload,
                "attempt": attempt,
                "summary": (
                    f"{endpoint} ok"
                    if response.is_success
                    else (payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)[:500])
                ),
            }
            if response.is_success:
                try:
                    validator(payload)
                except ValueError as exc:
                    result["ok"] = False
                    result["summary"] = f"schema_error: {exc}"
                return result
            if response.status_code >= 500 and transient_failures < 2:
                transient_failures += 1
                time.sleep(min(2 * transient_failures, 6))
                continue
            return result
        except Exception as exc:
            summary = f"{type(exc).__name__}: {exc}"
            if is_transient_transport_error(summary) and transient_failures < 2:
                transient_failures += 1
                time.sleep(min(2 * transient_failures, 6))
                continue
            return {
                "endpoint": endpoint,
                "http_status": None,
                "ok": False,
                "payload": None,
                "attempt": attempt,
                "summary": summary,
            }


def artifact_kind(entry: dict[str, Any]) -> str:
    return str(entry.get("artifact") or entry.get("type") or "").removesuffix("_error")


def upsert_manifest(manifest: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    key = (str(entry.get("source_mask", entry.get("mask")) or ""), artifact_kind(entry))
    manifest[:] = [
        item
        for item in manifest
        if (str(item.get("source_mask", item.get("mask")) or ""), artifact_kind(item)) != key
    ]
    manifest.append(entry)


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def completed_artifact(
    manifest: list[dict[str, Any]],
    source_mask: str,
    artifact: str,
    validator: Callable[[Any], None],
) -> dict[str, Any] | None:
    for entry in manifest:
        if str(entry.get("source_mask", entry.get("mask")) or "") != source_mask or artifact_kind(entry) != artifact:
            continue
        if entry.get("status") != "success":
            continue
        raw_path = Path(str(entry.get("file") or ""))
        if not raw_path.is_file():
            continue
        try:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            validator(payload)
        except Exception:
            continue
        return {"ok": True, "payload": payload, "resumed": True, "summary": "resumed"}
    return None


def collect_artifact(
    *,
    api_key: str,
    endpoint: str,
    body: dict[str, Any],
    validator: Callable[[Any], None],
    pacer: QuotaPacer,
    manifest: list[dict[str, Any]],
    manifest_path: Path,
    raw_bundle_dir: Path,
    source_mask: str,
    normalized_label: str,
    intent: str,
    artifact: str,
    filename: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completed = completed_artifact(manifest, source_mask, artifact, validator)
    if completed:
        return completed

    result = request_cloud(api_key, endpoint, body, validator, pacer)
    raw_path = raw_bundle_dir / filename
    if result["ok"]:
        write_json_atomic(raw_path, result["payload"])
        entry = {
            "mask": source_mask,
            "source_mask": source_mask,
            "normalized_label": normalized_label,
            "intent": intent,
            "artifact": artifact,
            "type": artifact,
            "status": "success",
            "file": str(raw_path),
            **(metadata or {}),
        }
    else:
        error_path = raw_bundle_dir / f"error_{filename.removesuffix('.json')}.txt"
        error_path.write_text(str(result["summary"]), encoding="utf-8")
        entry = {
            "mask": source_mask,
            "source_mask": source_mask,
            "normalized_label": normalized_label,
            "intent": intent,
            "artifact": artifact,
            "type": f"{artifact}_error",
            "status": "error",
            "file": str(error_path),
            "error": str(result["summary"]),
        }
    upsert_manifest(manifest, entry)
    write_json_atomic(manifest_path, manifest)
    return result


def main() -> int:
    args = parse_args()
    if not 1 <= args.num_phrases <= 2000:
        raise RuntimeError("num-phrases must be between 1 and 2000")

    masks_path = Path(args.masks_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    raw_bundle_dir = output_dir / "raw_bundle"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_bundle_dir.mkdir(parents=True, exist_ok=True)

    config_path = Path(args.config).resolve()
    if config_path.stat().st_mode & 0o077:
        raise RuntimeError("config must be readable only by its owner (mode 600)")
    config = load_json(config_path)
    api_key = str(config.get("api_key") or "").strip()
    folder_id = str(config.get("folder_id") or "").strip()
    if not api_key or not folder_id:
        raise RuntimeError("config must contain api_key and folder_id")

    default_state_root = Path(
        os.environ.get(
            "YDFALL_STATE_ROOT",
            str(Path.home() / ".local" / "state" / "yandex-direct-for-all"),
        )
    ).expanduser()
    quota_state_path = Path(
        str(config.get("quota_state_path") or default_state_root / "wordstat" / "limits.json")
    ).expanduser()
    pacer = QuotaPacer(quota_state_path)
    masks_rows = parse_masks(masks_path)
    regions = list(dict.fromkeys(part.strip() for part in str(args.regions).split(",") if part.strip()))
    devices = list(dict.fromkeys(cloud_device(part) for part in str(args.devices).split(",") if part.strip()))
    if len(regions) > 100:
        raise RuntimeError("no more than 100 regions are allowed")
    if not devices or len(devices) > 3:
        raise RuntimeError("between 1 and 3 device values are required")

    date_from, date_to = month_range(6)
    manifest_path = raw_bundle_dir / "_manifest.json"
    manifest = load_manifest(manifest_path)
    diagnostics: dict[str, Any] = {}

    tree = collect_artifact(
        api_key=api_key,
        endpoint="/v2/wordstat/getRegionsTree",
        body={"folderId": folder_id},
        validator=validate_regions_tree_response,
        pacer=pacer,
        manifest=manifest,
        manifest_path=manifest_path,
        raw_bundle_dir=raw_bundle_dir,
        source_mask="",
        normalized_label="regions_tree",
        intent="",
        artifact="regions_tree",
        filename="regions_tree.json",
    )
    diagnostics["regions_tree"] = {
        key: value for key, value in tree.items() if key not in {"payload"}
    }

    counters = {
        "top": {"ok": 0, "fail": 0},
        "regions": {"ok": 0, "fail": 0},
        "dynamics": {"ok": 0, "fail": 0},
    }
    truncated_masks = 0
    for source_mask, intent in masks_rows:
        digest = hashlib.sha256(source_mask.encode("utf-8")).hexdigest()[:10]
        readable = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_-]+", "_", source_mask).lower()[:55].strip("_") or "mask"
        stub = f"{readable}_{digest}"

        top = collect_artifact(
            api_key=api_key,
            endpoint="/v2/wordstat/topRequests",
            body={
                "phrase": source_mask,
                "numPhrases": args.num_phrases,
                "regions": regions,
                "devices": devices,
                "folderId": folder_id,
            },
            validator=validate_top_response,
            pacer=pacer,
            manifest=manifest,
            manifest_path=manifest_path,
            raw_bundle_dir=raw_bundle_dir,
            source_mask=source_mask,
            normalized_label=readable,
            intent=intent,
            artifact="top_requests",
            filename=f"top_requests_{stub}.json",
        )
        counters["top"]["ok" if top["ok"] else "fail"] += 1
        if top["ok"]:
            total_count = int(top["payload"].get("totalCount") or 0)
            if total_count > args.num_phrases:
                truncated_masks += 1
            for entry in manifest:
                if entry.get("source_mask", entry.get("mask")) == source_mask and artifact_kind(entry) == "top_requests":
                    entry["totalCount"] = total_count
                    entry["truncated"] = total_count > args.num_phrases
            write_json_atomic(manifest_path, manifest)

        regional = collect_artifact(
            api_key=api_key,
            endpoint="/v2/wordstat/regions",
            body={
                "phrase": source_mask,
                "region": "REGION_ALL",
                "devices": devices,
                "folderId": folder_id,
            },
            validator=validate_regions_response,
            pacer=pacer,
            manifest=manifest,
            manifest_path=manifest_path,
            raw_bundle_dir=raw_bundle_dir,
            source_mask=source_mask,
            normalized_label=readable,
            intent=intent,
            artifact="regions",
            filename=f"regions_{stub}.json",
        )
        counters["regions"]["ok" if regional["ok"] else "fail"] += 1

        if args.dynamics:
            dynamics = collect_artifact(
                api_key=api_key,
                endpoint="/v2/wordstat/dynamics",
                body={
                    "phrase": source_mask,
                    "period": "PERIOD_MONTHLY",
                    "fromDate": date_from,
                    "toDate": date_to,
                    "regions": regions,
                    "devices": devices,
                    "folderId": folder_id,
                },
                validator=validate_dynamics_response,
                pacer=pacer,
                manifest=manifest,
                manifest_path=manifest_path,
                raw_bundle_dir=raw_bundle_dir,
                source_mask=source_mask,
                normalized_label=readable,
                intent=intent,
                artifact="dynamics",
                filename=f"dynamics_{stub}.json",
                metadata={"fromDate": date_from, "toDate": date_to},
            )
            counters["dynamics"]["ok" if dynamics["ok"] else "fail"] += 1

    write_json_atomic(output_dir / "wordstat_diagnostics.json", diagnostics)
    access_info = {
        "accessPath": "yandex_search_api_v2",
        "folderId": folder_id,
        "configPath": str(config_path),
        "userInfoAvailable": False,
        "quotaControl": "local pacing plus HTTP 429 Retry-After",
    }
    write_json_atomic(raw_bundle_dir / "_access_context.json", access_info)
    write_json_atomic(manifest_path, manifest)

    tree_ok = bool(tree["ok"])
    all_top_ok = counters["top"]["ok"] == len(masks_rows)
    all_regions_ok = counters["regions"]["ok"] == len(masks_rows)
    all_dynamics_ok = not args.dynamics or counters["dynamics"]["ok"] == len(masks_rows)
    ready = tree_ok and all_top_ok and all_regions_ok and all_dynamics_ok
    summary = {
        "masks": len(masks_rows),
        "config": {
            "numPhrases": args.num_phrases,
            "regions": regions,
            "devices": devices,
            "doDynamics": args.dynamics,
        },
        **counters,
        "regionsTree": {"ok": tree_ok},
        "truncatedMasks": truncated_masks,
        "accessPath": "yandex_search_api_v2",
        "quotaStatePath": str(quota_state_path),
    }
    write_json_atomic(raw_bundle_dir / "_summary.json", summary)

    run_summary = {
        "status": "ready" if ready else "failed",
        "raw_bundle_dir": str(raw_bundle_dir),
        "mask_count": len(masks_rows),
        "diagnostics_path": str(output_dir / "wordstat_diagnostics.json"),
        "summary_path": str(raw_bundle_dir / "_summary.json"),
        "manifest_path": str(manifest_path),
    }
    write_json_atomic(output_dir / "gateway_wordstat_run_summary.json", run_summary)
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
