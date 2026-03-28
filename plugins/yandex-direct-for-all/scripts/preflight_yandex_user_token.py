#!/usr/bin/env python3
"""Read-only token preflight for Yandex Direct, Metrika, and Audience."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from yandex_auth_common import (  # noqa: E402
    TOKEN_ENV_NAMES,
    auth_token_path,
    discover_client_overlay,
    load_json,
    load_token_from_json,
    overlay_counter_id,
    overlay_direct_login,
    resolve_auth_root,
    write_json,
)

DIRECT_URL = "https://api.direct.yandex.com/json/v501/campaigns"
DIRECT_LIVE4_URL = "https://api.direct.yandex.ru/live/v4/json/"
METRIKA_COUNTERS_URL = "https://api-metrika.yandex.net/management/v1/counters"
AUDIENCE_SEGMENTS_URL = "https://api-audience.yandex.com/v1/management/segments"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only preflight for Yandex user OAuth tokens."
    )
    parser.add_argument("--service", choices=["direct", "metrika", "audience"], required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--token-json", default="")
    parser.add_argument("--auth-root", default="")
    parser.add_argument("--client-login", default="", help="Expected Direct Client-Login.")
    parser.add_argument("--counter-id", default="", help="Expected Metrika counter_id.")
    parser.add_argument("--segment-name", default="", help="Expected Audience segment name.")
    parser.add_argument("--direct-token", default="", help="Optional Direct token for Audience -> Direct cross-check.")
    parser.add_argument("--output", default="", help="Output JSON path.")
    parser.add_argument("--max-items", type=int, default=5)
    return parser


def first_non_empty(options: list[tuple[str, str]]) -> tuple[str, str]:
    for value, source in options:
        if value:
            return value, source
    return "", ""


def resolve_output_path(args: argparse.Namespace, auth_root: Path) -> tuple[Path, str]:
    if args.output:
        return Path(args.output).expanduser().resolve(), "--output"
    return (auth_root / f"{args.service}_oauth_preflight.json").resolve(), "auth-root-default"


def resolve_token(args: argparse.Namespace, auth_root: Path) -> tuple[str, str]:
    specific_env = TOKEN_ENV_NAMES[args.service]
    candidates: list[tuple[str, str]] = [
        (args.token, "--token"),
        (os.environ.get(specific_env, ""), specific_env),
    ]
    if args.token_json:
        token = load_token_from_json(Path(args.token_json).expanduser().resolve())
        candidates.insert(1, (token, "--token-json"))
    default_token_json = auth_token_path(auth_root, args.service)
    if default_token_json.is_file():
        candidates.append((load_token_from_json(default_token_json), str(default_token_json)))
    token, source = first_non_empty(candidates)
    if not token:
        raise SystemExit(
            f"Missing token for service {args.service}. Pass --token/--token-json or save "
            f"{default_token_json} first."
        )
    return token, source


def resolve_overlay_expectations(args: argparse.Namespace) -> tuple[str, str, str]:
    overlay, overlay_source = discover_client_overlay(Path.cwd())
    direct_login, _ = first_non_empty(
        [
            (args.client_login, "--client-login"),
            (os.environ.get("YD_CLIENT_LOGIN", ""), "YD_CLIENT_LOGIN"),
            (overlay_direct_login(overlay), "overlay.direct.login"),
        ]
    )
    counter_id, _ = first_non_empty(
        [
            (args.counter_id, "--counter-id"),
            (os.environ.get("YANDEX_METRIKA_COUNTER_ID", ""), "YANDEX_METRIKA_COUNTER_ID"),
            (overlay_counter_id(overlay), "overlay.metrika.counter_id"),
        ]
    )
    return direct_login, counter_id, overlay_source


def direct_call(token: str, login: str = "") -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json",
    }
    if login:
        headers["Client-Login"] = login
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "State", "Status"],
        },
    }
    response = requests.post(DIRECT_URL, headers=headers, json=body, timeout=60)
    return response.json()


def preflight_direct(token: str, expected_login: str, max_items: int) -> dict[str, Any]:
    candidates = []
    if expected_login:
        candidates.append(expected_login)
    candidates.append("")
    seen = set()
    probes = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        payload = direct_call(token, candidate)
        campaigns = payload.get("result", {}).get("Campaigns", []) if isinstance(payload, dict) else []
        probes.append(
            {
                "login": candidate or "(token-default)",
                "campaign_count": len(campaigns),
                "campaign_names": [str(item.get("Name", "")) for item in campaigns[:max_items]],
                "error": payload.get("error"),
            }
        )
    successful = [probe for probe in probes if not probe["error"]]
    best = max(successful, key=lambda item: item["campaign_count"], default=None)
    if best and best["campaign_count"] > 0:
        verdict = "ready"
    elif best and best["campaign_count"] == 0:
        verdict = "empty-or-unbound"
    else:
        verdict = "error"
    return {
        "service": "direct",
        "verdict": verdict,
        "expected_login": expected_login or "",
        "selected_login": best["login"] if best else "",
        "selected_campaign_count": best["campaign_count"] if best else 0,
        "selected_campaign_names": best["campaign_names"] if best else [],
        "probes": probes,
    }


def metrika_get(path: str, token: str) -> dict[str, Any]:
    response = requests.get(
        f"https://api-metrika.yandex.net{path}",
        headers={"Authorization": f"OAuth {token}"},
        timeout=60,
    )
    return response.json()


def preflight_metrika(token: str, expected_counter_id: str, max_items: int) -> dict[str, Any]:
    counters_payload = metrika_get("/management/v1/counters", token)
    counters = counters_payload.get("counters", []) if isinstance(counters_payload, dict) else []
    sample = [
        {
            "name": item.get("name", ""),
            "id": str(item.get("id", "")),
            "site": item.get("site", ""),
            "owner_login": item.get("owner_login", ""),
        }
        for item in counters[:max_items]
    ]
    matched = None
    if expected_counter_id:
        matched = next((item for item in counters if str(item.get("id", "")) == expected_counter_id), None)
    if matched:
        counter_info = metrika_get(f"/management/v1/counter/{expected_counter_id}", token)
        goals_info = metrika_get(f"/management/v1/counter/{expected_counter_id}/goals", token)
        verdict = "ready"
    elif counters:
        counter_info = {}
        goals_info = {}
        verdict = "live-but-unbound" if expected_counter_id else "live"
    else:
        counter_info = {}
        goals_info = {}
        verdict = "empty"
    return {
        "service": "metrika",
        "verdict": verdict,
        "expected_counter_id": expected_counter_id or "",
        "visible_counter_count": len(counters),
        "visible_counters": sample,
        "matched_counter": {
            "name": matched.get("name", ""),
            "id": str(matched.get("id", "")),
            "owner_login": matched.get("owner_login", ""),
        } if matched else {},
        "goal_count": len(goals_info.get("goals", [])) if goals_info else 0,
        "owner_login_hint": (
            str((matched or {}).get("owner_login", "")).strip()
            or str((counter_info.get("counter") or {}).get("owner_login", "")).strip()
        ),
    }


def audience_get_segments(token: str) -> dict[str, Any]:
    response = requests.get(
        AUDIENCE_SEGMENTS_URL,
        headers={"Authorization": f"OAuth {token}"},
        timeout=60,
    )
    return response.json()


def resolve_direct_crosscheck_token(args: argparse.Namespace, auth_root: Path) -> str:
    if args.direct_token:
        return args.direct_token
    if os.environ.get("YD_TOKEN", ""):
        return os.environ["YD_TOKEN"]
    direct_json = auth_token_path(auth_root, "direct")
    if direct_json.is_file():
        return load_token_from_json(direct_json)
    return ""


def direct_live4_audience_goals(token: str, login: str) -> dict[str, Any]:
    response = requests.post(
        DIRECT_LIVE4_URL,
        json={"method": "GetRetargetingGoals", "token": token, "param": {}, "login": login},
        timeout=60,
    )
    return response.json()


def preflight_audience(
    token: str,
    expected_segment_name: str,
    max_items: int,
    auth_root: Path,
    direct_login: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = audience_get_segments(token)
    segments = payload.get("segments", []) if isinstance(payload, dict) else []
    sample = [
        {
            "name": item.get("name", ""),
            "status": item.get("status", ""),
            "owner": item.get("owner", ""),
            "type": item.get("type", ""),
        }
        for item in segments[:max_items]
    ]
    matched = None
    if expected_segment_name:
        expected_lower = expected_segment_name.casefold()
        matched = next(
            (
                item
                for item in segments
                if str(item.get("name", "")).casefold() == expected_lower
            ),
            None,
        )
    if matched:
        verdict = "ready"
    elif segments:
        verdict = "live-but-unbound" if expected_segment_name else "live"
    else:
        verdict = "empty"

    crosscheck = {}
    direct_token = resolve_direct_crosscheck_token(args, auth_root)
    owner_login = direct_login or str((segments[0] if segments else {}).get("owner", "")).strip()
    if direct_token and owner_login:
        live4_payload = direct_live4_audience_goals(direct_token, owner_login)
        audience_goals = [
            item for item in live4_payload.get("data", []) if item.get("Type") == "audience_segment"
        ]
        crosscheck = {
            "direct_login": owner_login,
            "direct_visible_audience_goal_count": len(audience_goals),
            "direct_visible_audience_goal_names": [str(item.get("Name", "")) for item in audience_goals[:max_items]],
            "error": live4_payload.get("error_str") or live4_payload.get("error"),
        }

    return {
        "service": "audience",
        "verdict": verdict,
        "expected_segment_name": expected_segment_name or "",
        "visible_segment_count": len(segments),
        "visible_segments": sample,
        "matched_segment": {
            "name": matched.get("name", ""),
            "status": matched.get("status", ""),
            "owner": matched.get("owner", ""),
            "type": matched.get("type", ""),
        } if matched else {},
        "direct_crosscheck": crosscheck,
    }


def print_summary(result: dict[str, Any], output_path: Path, token_source: str, overlay_source: str) -> None:
    print(f"Service: {result['service']}")
    print(f"Verdict: {result['verdict']}")
    print(f"Token source: {token_source}")
    if overlay_source:
        print(f"Overlay source: {overlay_source}")
    if result["service"] == "direct":
        print(f"Selected login: {result.get('selected_login', '')}")
        print(f"Visible campaigns: {result.get('selected_campaign_count', 0)}")
        names = result.get("selected_campaign_names", [])
        if names:
            print("Campaign names:")
            for name in names:
                print(f"- {name}")
    elif result["service"] == "metrika":
        print(f"Visible counters: {result.get('visible_counter_count', 0)}")
        matched = result.get("matched_counter", {})
        if matched:
            print(f"Matched counter: {matched.get('name', '')}")
        else:
            for counter in result.get("visible_counters", []):
                print(f"- {counter.get('name', '')}")
    elif result["service"] == "audience":
        print(f"Visible segments: {result.get('visible_segment_count', 0)}")
        matched = result.get("matched_segment", {})
        if matched:
            print(f"Matched segment: {matched.get('name', '')}")
        else:
            for segment in result.get("visible_segments", []):
                print(f"- {segment.get('name', '')}")
        crosscheck = result.get("direct_crosscheck", {})
        if crosscheck:
            print(
                "Direct Live4 audience goals: "
                f"{crosscheck.get('direct_visible_audience_goal_count', 0)}"
            )
    print(f"Saved preflight JSON: {output_path}")


def main() -> None:
    args = build_parser().parse_args()
    auth_root, _ = resolve_auth_root(args.auth_root)
    token, token_source = resolve_token(args, auth_root)
    direct_login, counter_id, overlay_source = resolve_overlay_expectations(args)
    output_path, _ = resolve_output_path(args, auth_root)

    if args.service == "direct":
        result = preflight_direct(token, direct_login, args.max_items)
    elif args.service == "metrika":
        result = preflight_metrika(token, counter_id, args.max_items)
    else:
        result = preflight_audience(
            token,
            args.segment_name,
            args.max_items,
            auth_root,
            direct_login,
            args,
        )

    result["token_source"] = token_source
    result["overlay_source"] = overlay_source
    write_json(output_path, result)
    print_summary(result, output_path, token_source, overlay_source)
    if result.get("verdict") == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
