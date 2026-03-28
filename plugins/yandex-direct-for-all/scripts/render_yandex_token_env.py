#!/usr/bin/env python3
"""Render a sourceable env file from a Yandex OAuth token JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ENV_NAMES = {
    "direct": "YD_TOKEN",
    "metrika": "YANDEX_METRIKA_TOKEN",
    "audience": "YANDEX_AUDIENCE_TOKEN",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=sorted(ENV_NAMES), required=True)
    parser.add_argument("--input", required=True, help="Path to OAuth token JSON")
    parser.add_argument("--output", required=True, help="Path to generated .env file")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise SystemExit(f"No access_token found in {input_path}")

    env_name = ENV_NAMES[args.service]
    content = (
        f"# Generated from {input_path}\n"
        f"# Service: {args.service}\n"
        f"export {env_name}={json.dumps(access_token, ensure_ascii=False)}\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
