#!/usr/bin/env python3
"""Create or reconcile a client YouGile workspace from a JSON spec.

API-only helper for future sessions:
- finds or creates a project by exact title;
- finds or creates boards/columns by exact title;
- optionally seeds starter tasks into target columns;
- writes a deterministic JSON result with created/found IDs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_HOST = os.environ.get("YOUGILE_API_HOST_URL", "https://ru.yougile.com/api-v2")
DEFAULT_KEY = os.environ.get("YOUGILE_API_KEY", "")
RATE_LIMIT_DELAY = 0.45


def api_request(host: str, api_key: str, method: str, path: str, data: dict | None = None) -> dict:
    url = f"{host.rstrip('/')}/{path.lstrip('/')}"
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"YouGile API {method} {url} failed: HTTP {exc.code} {body}") from exc


def paged_list(host: str, api_key: str, path: str, query: dict[str, str] | None = None) -> list[dict]:
    items: list[dict] = []
    offset = 0
    limit = 100
    query = dict(query or {})
    while True:
        qp = dict(query)
        qp["limit"] = str(limit)
        qp["offset"] = str(offset)
        encoded = urllib.parse.urlencode(qp)
        resp = api_request(host, api_key, "GET", f"{path}?{encoded}")
        page_items = resp.get("content") or []
        items.extend(page_items)
        paging = resp.get("paging") or {}
        next_offset = paging.get("nextOffset")
        if not page_items or next_offset is None:
            break
        offset = int(next_offset)
    return items


def exact_match(items: list[dict], title: str) -> dict | None:
    for item in items:
        if item.get("title") == title:
            return item
    return None


def list_tasks_for_column(host: str, api_key: str, column_id: str) -> list[dict]:
    return paged_list(host, api_key, "task-list", {"columnId": column_id})


def find_or_create_project(host: str, api_key: str, title: str) -> tuple[dict, bool]:
    projects = paged_list(host, api_key, "projects", {"title": title})
    found = exact_match(projects, title)
    if found:
        return found, False
    created = api_request(host, api_key, "POST", "projects", {"title": title})
    time.sleep(RATE_LIMIT_DELAY)
    project = api_request(host, api_key, "GET", f"projects/{created['id']}")
    return project, True


def find_or_create_board(host: str, api_key: str, project_id: str, title: str) -> tuple[dict, bool]:
    boards = paged_list(host, api_key, "boards", {"projectId": project_id, "title": title})
    found = exact_match(boards, title)
    if found:
        return found, False
    created = api_request(host, api_key, "POST", "boards", {"title": title, "projectId": project_id})
    time.sleep(RATE_LIMIT_DELAY)
    board = api_request(host, api_key, "GET", f"boards/{created['id']}")
    return board, True


def find_or_create_column(host: str, api_key: str, board_id: str, title: str, color: int | None) -> tuple[dict, bool]:
    columns = paged_list(host, api_key, "columns", {"boardId": board_id, "title": title})
    found = exact_match(columns, title)
    if found:
        return found, False
    payload = {"title": title, "boardId": board_id}
    if color is not None:
        payload["color"] = color
    created = api_request(host, api_key, "POST", "columns", payload)
    time.sleep(RATE_LIMIT_DELAY)
    column = api_request(host, api_key, "GET", f"columns/{created['id']}")
    return column, True


def find_or_create_task(
    host: str,
    api_key: str,
    column_id: str,
    title: str,
    description: str,
    color: str | None,
) -> tuple[dict, bool]:
    tasks = list_tasks_for_column(host, api_key, column_id)
    for task in tasks:
        if task.get("title") == title:
            return task, False
    payload = {
        "title": title,
        "columnId": column_id,
        "description": description,
    }
    if color:
        payload["color"] = color
    created = api_request(host, api_key, "POST", "tasks", payload)
    time.sleep(RATE_LIMIT_DELAY)
    task = api_request(host, api_key, "GET", f"tasks/{created['id']}")
    return task, True


def load_spec(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a YouGile workspace from a JSON spec.")
    parser.add_argument("--spec", required=True, help="Path to workspace JSON spec")
    parser.add_argument("--output", required=True, help="Where to write bootstrap result JSON")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--api-key", default=DEFAULT_KEY)
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("YOUGILE_API_KEY / --api-key is required")

    spec_path = Path(args.spec).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    spec = load_spec(spec_path)
    project_title = (spec.get("project") or {}).get("title")
    if not project_title:
        raise SystemExit("Spec must contain project.title")

    project, project_created = find_or_create_project(args.host, args.api_key, project_title)
    result: dict = {
        "project": {
            "id": project["id"],
            "title": project["title"],
            "created": project_created,
        },
        "boards": [],
    }

    for board_spec in spec.get("boards") or []:
        board, board_created = find_or_create_board(args.host, args.api_key, project["id"], board_spec["title"])
        board_result = {
            "alias": board_spec["alias"],
            "title": board["title"],
            "purpose": board_spec.get("purpose", ""),
            "id": board["id"],
            "created": board_created,
            "columns": [],
            "tasks": [],
        }

        column_ids: dict[str, str] = {}
        for column_spec in board_spec.get("columns") or []:
            column, column_created = find_or_create_column(
                args.host,
                args.api_key,
                board["id"],
                column_spec["title"],
                column_spec.get("color"),
            )
            column_ids[column_spec["alias"]] = column["id"]
            board_result["columns"].append(
                {
                    "alias": column_spec["alias"],
                    "title": column["title"],
                    "id": column["id"],
                    "color": column.get("color"),
                    "created": column_created,
                }
            )

        for task_spec in board_spec.get("tasks") or []:
            column_id = column_ids[task_spec["column_alias"]]
            task, task_created = find_or_create_task(
                args.host,
                args.api_key,
                column_id,
                task_spec["title"],
                task_spec.get("description", ""),
                task_spec.get("color"),
            )
            board_result["tasks"].append(
                {
                    "title": task["title"],
                    "id": task["id"],
                    "column_alias": task_spec["column_alias"],
                    "column_id": column_id,
                    "created": task_created,
                }
            )

        result["boards"].append(board_result)

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
