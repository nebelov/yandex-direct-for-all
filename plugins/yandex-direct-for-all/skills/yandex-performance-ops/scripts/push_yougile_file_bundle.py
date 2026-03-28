#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_HOST = os.environ.get("YOUGILE_API_HOST_URL", "https://ru.yougile.com/api-v2")
DEFAULT_KEY = os.environ.get("YOUGILE_API_KEY", "")
CHAR_LIMIT = 24000


def guess_lang(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".md": "markdown",
        ".json": "json",
        ".tsv": "tsv",
        ".txt": "text",
        ".py": "python",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, "")


def make_chunks(path: Path) -> list[str]:
    text = path.read_text()
    lang = guess_lang(path)
    header = f"[Материал] {path.name}\n\n"
    if len(header) + len(text) + 10 <= CHAR_LIMIT:
        fence = f"```{lang}\n{text}\n```" if lang else f"```\n{text}\n```"
        return [header + fence]

    chunks: list[str] = []
    lines = text.splitlines()
    buf: list[str] = []
    current = 0
    part = 1
    for line in lines:
        extra = len(line) + 1
        projected = current + extra
        overhead = len(header) + 80
        if projected + overhead > CHAR_LIMIT and buf:
            body = "\n".join(buf)
            title = f"{header}(часть {part})\n"
            fence = f"```{lang}\n{body}\n```" if lang else f"```\n{body}\n```"
            chunks.append(title + fence)
            buf = []
            current = 0
            part += 1
        buf.append(line)
        current += extra
    if buf:
        body = "\n".join(buf)
        title = f"{header}(часть {part})\n" if part > 1 else header
        fence = f"```{lang}\n{body}\n```" if lang else f"```\n{body}\n```"
        chunks.append(title + fence)
    return chunks


def post_message(host: str, api_key: str, chat_id: str, text: str) -> dict:
    url = f"{host.rstrip('/')}/chats/{chat_id}/messages"
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Push local file contents into a YouGile task/group chat.")
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--file", action="append", required=True, dest="files")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--api-key", default=DEFAULT_KEY)
    args = parser.parse_args()

    if not args.api_key:
        print("YOUGILE_API_KEY is required", file=sys.stderr)
        return 2

    results = []
    for raw_path in args.files:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            print(f"skip missing file: {path}", file=sys.stderr)
            continue
        for chunk in make_chunks(path):
            try:
                resp = post_message(args.host, args.api_key, args.chat_id, chunk)
                results.append({"file": str(path), "message": resp})
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="ignore")
                print(f"upload failed for {path}: HTTP {exc.code} {body}", file=sys.stderr)
                return 1
            except Exception as exc:
                print(f"upload failed for {path}: {exc}", file=sys.stderr)
                return 1

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
