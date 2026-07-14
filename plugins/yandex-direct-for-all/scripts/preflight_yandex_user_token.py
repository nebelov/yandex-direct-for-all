#!/usr/bin/env python3
"""Mandatory app ownership and read-only service check after Yandex OAuth."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import portable_http as requests  # noqa: E402

from yandex_auth_common import (  # noqa: E402
    DEFAULT_SERVICE_PROFILE,
    TOKEN_ENV_NAMES,
    auth_token_path,
    load_public_profiles,
    load_token_payload,
    preflight_path,
    resolve_auth_root,
    write_json,
)


ID_INFO_URL = "https://login.yandex.ru/info"
DIRECT_URL = "https://api.direct.yandex.com/json/v501/campaigns"
METRIKA_URL = "https://api-metrika.yandex.net/management/v1/counters"
AUDIENCE_URL = "https://api-audience.yandex.com/v1/management/segments"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Проверка приложения и чтения Яндекс-службы.")
    parser.add_argument("--service", choices=["direct", "metrika", "audience"], required=True)
    parser.add_argument("--token-json", default="")
    parser.add_argument("--auth-root", default="")
    parser.add_argument("--client-login", default="")
    parser.add_argument("--counter-id", default="")
    parser.add_argument("--segment-name", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--max-items", type=int, default=5)
    return parser


def resolve_token(args: argparse.Namespace, auth_root: Path) -> tuple[str, str, str]:
    path = (
        Path(args.token_json).expanduser().resolve()
        if args.token_json
        else auth_token_path(auth_root, args.service)
    )
    if path.is_file():
        payload = load_token_payload(path)
        token = str(payload["access_token"])
        expected_client_id = str(payload.get("oauth_client_id") or "")
        source = path.name
    else:
        env_name = TOKEN_ENV_NAMES[args.service]
        token = os.environ.get(env_name, "").strip()
        if not token:
            raise ValueError(f"Нет защищённого файла токена для службы {args.service}.")
        expected_client_id = ""
        source = env_name
    if not expected_client_id:
        profiles = load_public_profiles()
        expected_client_id = str(profiles[DEFAULT_SERVICE_PROFILE[args.service]]["client_id"])
    return token, expected_client_id, source


def yandex_id_client_id(token: str) -> str:
    response = requests.get(
        ID_INFO_URL,
        params={"format": "json"},
        headers={"Authorization": f"OAuth {token}"},
        timeout=(30, None),
    )
    if response.status_code != 200:
        raise RuntimeError(f"Яндекс ID вернул HTTP {response.status_code}.")
    payload = response.json()
    client_id = str(payload.get("client_id") or "").strip()
    if not client_id:
        raise RuntimeError("Яндекс ID не вернул client_id токена.")
    return client_id


def direct_read(token: str, client_login: str, max_items: int) -> dict[str, Any]:
    if not client_login.strip():
        raise ValueError("Для проверки Директа обязателен логин рекламодателя или клиента агентства.")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
        "Client-Login": client_login.strip(),
    }
    response = requests.post(
        DIRECT_URL,
        headers=headers,
        json={
            "method": "get",
            "params": {
                "SelectionCriteria": {},
                "FieldNames": ["Id", "Name", "State", "Status"],
            },
        },
        timeout=(30, None),
    )
    payload = response.json()
    campaigns = payload.get("result", {}).get("Campaigns", []) if isinstance(payload, dict) else []
    return {
        "http_status": response.status_code,
        "ok": response.status_code == 200 and not payload.get("error"),
        "visible_campaign_count": len(campaigns),
        "api_error_code": ((payload.get("error") or {}).get("error_code") if isinstance(payload, dict) else None),
    }


def metrika_read(token: str, counter_id: str, max_items: int) -> dict[str, Any]:
    response = requests.get(
        METRIKA_URL,
        headers={"Authorization": f"OAuth {token}"},
        timeout=(30, None),
    )
    payload = response.json()
    counters = payload.get("counters", []) if isinstance(payload, dict) else []
    matched = any(str(item.get("id") or "") == counter_id for item in counters) if counter_id else None
    return {
        "http_status": response.status_code,
        "ok": response.status_code == 200 and isinstance(payload, dict) and "counters" in payload,
        "visible_counter_count": len(counters),
        "expected_counter_visible": matched,
    }


def audience_read(token: str, segment_name: str, max_items: int) -> dict[str, Any]:
    response = requests.get(
        AUDIENCE_URL,
        headers={"Authorization": f"OAuth {token}"},
        timeout=(30, None),
    )
    payload = response.json()
    segments = payload.get("segments", []) if isinstance(payload, dict) else []
    matched = (
        any(str(item.get("name") or "").casefold() == segment_name.casefold() for item in segments)
        if segment_name
        else None
    )
    return {
        "http_status": response.status_code,
        "ok": response.status_code == 200 and isinstance(payload, dict) and "segments" in payload,
        "visible_segment_count": len(segments),
        "expected_segment_visible": matched,
    }


def run_check(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    if args.service == "direct" and not args.client_login.strip():
        raise ValueError("Для проверки Директа обязателен --client-login.")
    auth_root, _ = resolve_auth_root(args.auth_root)
    token, expected_client_id, token_source = resolve_token(args, auth_root)
    actual_client_id = yandex_id_client_id(token)
    app_matches = actual_client_id == expected_client_id
    if args.service == "direct":
        read = direct_read(token, args.client_login, args.max_items) if app_matches else {"ok": False}
    elif args.service == "metrika":
        read = metrika_read(token, args.counter_id, args.max_items) if app_matches else {"ok": False}
    else:
        read = audience_read(token, args.segment_name, args.max_items) if app_matches else {"ok": False}
    result = {
        "service": args.service,
        "verdict": "ready" if app_matches and read.get("ok") else "error",
        "token_source": token_source,
        "oauth_client_id_matches": app_matches,
        "read": read,
    }
    if args.service == "direct":
        result["direct_scope"] = "explicit_client"
    output = Path(args.output).expanduser().resolve() if args.output else preflight_path(auth_root, args.service)
    write_json(output, result)
    return result, output


def main() -> None:
    args = build_parser().parse_args()
    result, output = run_check(args)
    print(f"Служба: {result['service']}")
    print(f"Приложение совпало: {'да' if result['oauth_client_id_matches'] else 'нет'}")
    print(f"Чтение службы: {'успешно' if result['read'].get('ok') else 'ошибка'}")
    print(f"Результат сохранён: {output.name}")
    if result["verdict"] != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
