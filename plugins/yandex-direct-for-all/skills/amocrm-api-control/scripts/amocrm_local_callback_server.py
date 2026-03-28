#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import urllib.parse
from pathlib import Path


HTML_OK = """<!doctype html>
<html lang="ru"><meta charset="utf-8"><title>amoCRM OAuth</title>
<body style="font-family: sans-serif; padding: 24px">
<h1>Код amoCRM получен</h1>
<p>Можно закрыть это окно и вернуться в терминал.</p>
</body></html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local callback receiver for amoCRM OAuth.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8031)
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            payload = {
                "path": parsed.path,
                "query": {k: v[0] if len(v) == 1 else v for k, v in params.items()},
                "full_url": f"http://{args.host}:{args.port}{self.path}",
            }
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_OK.encode("utf-8"))
            raise KeyboardInterrupt

        def log_message(self, fmt, *args_):  # noqa: A003
            return

    with socketserver.TCPServer((args.host, args.port), Handler) as httpd:
        print(json.dumps({"listening": f"http://{args.host}:{args.port}/callback", "output": str(output)}, ensure_ascii=False))
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
