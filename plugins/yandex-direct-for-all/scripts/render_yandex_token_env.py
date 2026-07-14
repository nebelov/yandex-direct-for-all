#!/usr/bin/env python3
"""Render a protected env file from a protected Yandex OAuth token file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from yandex_auth_common import TOKEN_ENV_NAMES, load_token_payload, write_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=sorted(TOKEN_ENV_NAMES), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    input_path = Path(args.input).expanduser().resolve()
    payload = load_token_payload(input_path)
    output_path = Path(args.output).expanduser().resolve()
    name = TOKEN_ENV_NAMES[args.service]
    write_text(output_path, f"export {name}={json.dumps(str(payload['access_token']))}\n")
    print(f"Защищённый файл создан: {output_path.name}")


if __name__ == "__main__":
    main()
