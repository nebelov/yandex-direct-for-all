#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch core amoCRM schema read-only.")
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def load_credentials(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(base_url: str, token: str, endpoint: str) -> dict:
    resp = requests.get(
        f"{base_url}{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    args = build_parser().parse_args()
    creds = load_credentials(Path(args.credentials).expanduser().resolve())
    base_url = creds["base_url"]
    token = creds["access_token"]
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = {
        "account.json": "/api/v4/account",
        "pipelines.json": "/api/v4/leads/pipelines",
        "lead_fields.json": "/api/v4/leads/custom_fields",
        "contact_fields.json": "/api/v4/contacts/custom_fields",
    }

    written = []
    for filename, endpoint in targets.items():
        data = fetch_json(base_url, token, endpoint)
        path = output_dir / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(str(path))

    print(json.dumps({"ok": True, "written": written}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
