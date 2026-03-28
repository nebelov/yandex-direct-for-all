#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exchange or refresh amoCRM OAuth tokens.")
    parser.add_argument("--subdomain", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--redirect-uri", required=True)
    parser.add_argument("--code")
    parser.add_argument("--refresh-token")
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if bool(args.code) == bool(args.refresh_token):
        raise SystemExit("Pass exactly one of --code or --refresh-token")

    payload = {
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": args.redirect_uri,
    }
    if args.code:
        payload["grant_type"] = "authorization_code"
        payload["code"] = args.code
    else:
        payload["grant_type"] = "refresh_token"
        payload["refresh_token"] = args.refresh_token

    url = f"https://{args.subdomain}.amocrm.ru/oauth2/access_token"
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    result = {
        "subdomain": args.subdomain,
        "base_url": f"https://{args.subdomain}.amocrm.ru",
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": args.redirect_uri,
        "authorization_code": args.code or "",
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
        "token_type": data.get("token_type", "Bearer"),
        "expires_in": data.get("expires_in", 0),
        "server_time": data.get("server_time"),
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
