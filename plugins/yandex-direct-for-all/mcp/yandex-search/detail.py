"""Безопасный клиент платного Yandex Cloud Search API."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.exceptions import RequestException


GEN_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/gen/search"
WEB_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"
ROUTES = {"web", "generative"}
REGIONS = {"ru", "tr", "en"}
SECRET_INPUT_KEYS = {"api_key", "folder_id", "token", "credentials"}
CONTROL_INPUT_KEYS = {"paid_search_approval", "approval_ref", "approved", "max_calls"}


class SearchPolicyError(RuntimeError):
    """Запрос не прошёл ворота платного поиска."""


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SearchPolicyError("Время разрешения должно иметь формат ISO 8601") from exc
    if parsed.tzinfo is None:
        raise SearchPolicyError("Время разрешения должно содержать часовой пояс")
    return parsed.astimezone(timezone.utc)


def private_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SearchPolicyError("Закрытый файл должен существовать и иметь права 0600")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SearchPolicyError("Закрытый файл не является JSON") from exc
    if not isinstance(value, dict):
        raise SearchPolicyError("Закрытый файл должен содержать объект JSON")
    return value


def get_search_api_credentials() -> tuple[str, str]:
    api_key = os.environ.get("YANDEX_SEARCH_API_KEY", "").strip()
    folder_id = os.environ.get("YANDEX_SEARCH_FOLDER_ID", "").strip()
    if not api_key or any(character.isspace() for character in api_key):
        raise SearchPolicyError("Не задана безопасная переменная YANDEX_SEARCH_API_KEY")
    if not folder_id or any(character.isspace() for character in folder_id):
        raise SearchPolicyError("Не задана безопасная переменная YANDEX_SEARCH_FOLDER_ID")
    return api_key, folder_id


def validate_input_data(data: Dict[str, Any], required_keys: set[str]) -> Optional[str]:
    if not isinstance(data, dict):
        return "Тело запроса должно быть объектом"
    if SECRET_INPUT_KEYS.intersection(data):
        return "Доступы нельзя передавать в теле вызова"
    if CONTROL_INPUT_KEYS.intersection(data):
        return "Разрешение платного вызова нельзя передавать в теле запроса"
    if missing_keys := required_keys - set(data):
        return f"Не хватает полей: {', '.join(sorted(missing_keys))}"
    query = data.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        return "Поисковый запрос должен быть непустой строкой длиной до 500 символов"
    if data.get("search_region") not in REGIONS:
        return "Область поиска должна быть ru, tr или en"
    return None


def request_sha256(route: str, data: dict[str, Any]) -> str:
    payload = {
        "route": route,
        "query": str(data.get("query") or ""),
        "search_region": str(data.get("search_region") or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_folder_and_expiry(approval: dict[str, Any], current: datetime) -> None:
    if parse_time(str(approval.get("expires_at") or "")) <= current:
        raise SearchPolicyError("Срок разрешения на платный поиск истёк")
    _, folder_id = get_search_api_credentials()
    folder_sha256 = hashlib.sha256(folder_id.encode("utf-8")).hexdigest()
    if approval.get("folder_sha256") != folder_sha256:
        raise SearchPolicyError("Разрешение относится к другой папке Yandex Cloud")


def reserve_approved_call(approval: dict[str, Any], route: str, ledger_path: Path, now: datetime) -> str:
    approval_ref = str(approval.get("approval_ref") or "").strip()
    max_calls = approval.get("max_calls")
    if not approval_ref or not isinstance(max_calls, int) or isinstance(max_calls, bool) or max_calls <= 0:
        raise SearchPolicyError("Разрешение не содержит корректные approval_ref и max_calls")
    ledger_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ledger_path.parent, 0o700)
    if ledger_path.exists() and stat.S_IMODE(ledger_path.stat().st_mode) & 0o077:
        raise SearchPolicyError("Журнал платного поиска должен иметь права 0600")
    descriptor = os.open(ledger_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            raw = handle.read().strip()
            try:
                ledger = json.loads(raw) if raw else {"version": 1, "calls": []}
            except json.JSONDecodeError as exc:
                raise SearchPolicyError("Журнал платного поиска повреждён") from exc
            calls = ledger.get("calls")
            if not isinstance(calls, list):
                raise SearchPolicyError("Журнал платного поиска имеет неверную схему")
            used = sum(1 for call in calls if isinstance(call, dict) and call.get("approval_ref") == approval_ref)
            if used >= max_calls:
                raise SearchPolicyError("Лимит платных вызовов по разрешению исчерпан")
            calls.append({"approval_ref": approval_ref, "route": route, "reserved_at": now.isoformat()})
            handle.seek(0)
            json.dump(ledger, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        # fdopen закрывает дескриптор после входа в контекст.
        raise
    return approval_ref


def authorize_paid_call(route: str, data: dict[str, Any], now: datetime | None = None) -> str:
    if route not in ROUTES:
        raise SearchPolicyError("Неизвестный маршрут платного поиска")
    mode = os.environ.get("YANDEX_SEARCH_ROUTE", "disabled").strip().lower() or "disabled"
    if mode == "disabled":
        raise SearchPolicyError("Платный Search API выключен; выберите ручной или заранее разрешённый режим")
    if mode == "manual":
        if CONTROL_INPUT_KEYS.intersection(data):
            raise SearchPolicyError("Тело вызова не может подтверждать собственный платный запрос")
        approval_name = os.environ.get("YANDEX_SEARCH_APPROVAL_FILE", "").strip()
        ledger_name = os.environ.get("YANDEX_SEARCH_USAGE_LEDGER", "").strip()
        if not approval_name or not ledger_name:
            raise SearchPolicyError("Ручной режим требует закрытые файлы разрешения и журнала")
        approval = private_json(Path(approval_name).expanduser().resolve())
        if approval.get("approved") is not True:
            raise SearchPolicyError("Владелец не разрешил ручной платный вызов")
        if approval.get("routes") != [route] or approval.get("max_calls") != 1:
            raise SearchPolicyError("Ручное разрешение должно относиться к точному маршруту и одному вызову")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        validate_folder_and_expiry(approval, current)
        if approval.get("request_sha256") != request_sha256(route, data):
            raise SearchPolicyError("Ручное разрешение относится к другому запросу")
        return reserve_approved_call(approval, route, Path(ledger_name).expanduser().resolve(), current)
    if mode != "approved":
        raise SearchPolicyError("YANDEX_SEARCH_ROUTE должен быть disabled, manual или approved")

    approval_name = os.environ.get("YANDEX_SEARCH_APPROVAL_FILE", "").strip()
    ledger_name = os.environ.get("YANDEX_SEARCH_USAGE_LEDGER", "").strip()
    if not approval_name or not ledger_name:
        raise SearchPolicyError("Разрешённый режим требует явные файлы разрешения и журнала")
    approval = private_json(Path(approval_name).expanduser().resolve())
    if approval.get("approved") is not True or route not in approval.get("routes", []):
        raise SearchPolicyError("Маршрут не входит в разрешённую область")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    validate_folder_and_expiry(approval, current)
    return reserve_approved_call(approval, route, Path(ledger_name).expanduser().resolve(), current)


def make_http_request(url: str, *, headers: Dict[str, str], json_body: Dict[str, Any], decode_base64: bool = False) -> str:
    try:
        with requests.post(url, headers=headers, json=json_body) as response:
            response.raise_for_status()
            if not decode_base64:
                return response.text
            value = response.json()
            raw_data = value.get("rawData") if isinstance(value, dict) else None
            if not isinstance(raw_data, str):
                raise RuntimeError("Ответ веб-поиска не содержит rawData")
            return base64.b64decode(raw_data, validate=True).decode("utf-8")
    except RequestException as exc:
        raise RuntimeError(f"Search API вернул сетевую ошибку: {exc.__class__.__name__}") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("Ответ Search API не удалось разобрать") from exc


def call_ai_search_with_yazeka(data: Dict[str, Any]) -> str:
    api_key, folder_id = get_search_api_credentials()
    authorize_paid_call("generative", data)
    region = data["search_region"]
    body = {
        "messages": [{"content": data["query"], "role": "ROLE_USER"}],
        "searchFilters": [{"lang": "tr" if region == "tr" else "en"}],
        "folderId": folder_id,
        "fixMisspell": True,
        "enableNrfmDocs": True,
        "search_type": "SEARCH_TYPE_TR" if region == "tr" else "SEARCH_TYPE_COM",
    }
    return make_http_request(
        GEN_SEARCH_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Api-Key {api_key}"},
        json_body=body,
    )


def call_web_search(data: Dict[str, Any]) -> str:
    api_key, folder_id = get_search_api_credentials()
    authorize_paid_call("web", data)
    region = data["search_region"]
    search_type, localization = {
        "ru": ("SEARCH_TYPE_RU", "LOCALIZATION_RU"),
        "tr": ("SEARCH_TYPE_TR", "LOCALIZATION_TR"),
        "en": ("SEARCH_TYPE_COM", "LOCALIZATION_EN"),
    }[region]
    body = {
        "query": {
            "searchType": search_type,
            "queryText": data["query"],
            "familyMode": "FAMILY_MODE_NONE",
            "fixTypoMode": "FIX_TYPO_MODE_OFF",
        },
        "folderId": folder_id,
        "groupSpec": {"groupsOnPage": 10},
        "l10n": localization,
        "region": region,
        "responseFormat": "FORMAT_XML",
    }
    return make_http_request(
        WEB_SEARCH_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Api-Key {api_key}"},
        json_body=body,
        decode_base64=True,
    )
