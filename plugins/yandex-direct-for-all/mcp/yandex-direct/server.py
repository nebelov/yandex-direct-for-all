#!/usr/bin/env python3
"""Read-only MCP bridge for Yandex Direct API v5/v501."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from mcp.server.fastmcp import FastMCP


ORDINARY_SERVICES = {
    "campaigns",
    "adgroups",
    "ads",
    "keywords",
    "negativekeywordsharedsets",
    "sitelinks",
    "adextensions",
    "bids",
    "keywordbids",
}
ALLOWED_SERVICES = ORDINARY_SERVICES | {"reports"}
ALLOWED_VERSIONS = {"v5", "v501"}
SANDBOX_BASE = "https://api-sandbox.direct.yandex.com"
PRODUCTION_BASE = "https://api.direct.yandex.com"
RequestFunction = Callable[[str, dict[str, str], bytes], Awaitable[Any]]

mcp = FastMCP("yandex_direct_read_only", host="127.0.0.1", port=int(os.environ.get("YD_MCP_PORT", "8765")))


def validate_route(service: str, method: str, version: str) -> None:
    if method != "get":
        raise ValueError("Разрешён только локальный метод get.")
    if version not in ALLOWED_VERSIONS:
        raise ValueError("Разрешены только версии v5 и v501.")
    if service not in ALLOWED_SERVICES:
        raise ValueError("Сервис не входит в закрытый список чтения.")


def private_json(path: Path) -> dict[str, Any]:
    if path.stat().st_mode & 0o077:
        raise ValueError(f"Файл {path.name} должен иметь права 0600.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Ожидался объект JSON: {path.name}")
    return data


def runtime_from_access_file(raw_path: str) -> tuple[str, str, str]:
    """Читает файл доступа из docs/operator-auth-launchers.md: environment, token_file, client_login."""
    access_path = Path(raw_path).expanduser().resolve()
    access = private_json(access_path)
    token_path = Path(str(access.get("token_file", ""))).expanduser()
    if not token_path.is_absolute():
        token_path = (access_path.parent / token_path).resolve()  # всегда от папки файла доступа
    if not token_path.is_file():
        raise ValueError("Файл токена из файла доступа не найден: путь считается от папки файла доступа.")
    token = str(private_json(token_path).get("access_token", "")).strip()
    environment = str(access.get("environment", "production")).strip().lower()
    return environment, token, str(access.get("client_login", "")).strip()


def resolve_runtime() -> tuple[str, str, str, Path]:
    access_file = os.environ.get("YANDEX_DIRECT_ACCESS_FILE", "").strip()
    if access_file:
        environment, token, login = runtime_from_access_file(access_file)
        if environment not in {"sandbox", "production"}:
            raise ValueError("environment в файле доступа должен быть sandbox или production.")
        if not token:
            raise ValueError("В файле токена из файла доступа нет access_token.")
        if not login:
            raise ValueError("В файле доступа не задан client_login: чтение без явной области клиента запрещено.")
        output = Path(
            os.environ.get("YANDEX_DIRECT_OUTPUT_DIR", str(Path.cwd() / "artifacts" / "yandex-direct"))
        ).expanduser().resolve()
        return environment, token, login, output
    environment = os.environ.get("YANDEX_DIRECT_ENVIRONMENT", "sandbox").strip().lower()
    if environment not in {"sandbox", "production"}:
        raise ValueError("YANDEX_DIRECT_ENVIRONMENT должен быть sandbox или production.")
    token_name = (
        "YANDEX_DIRECT_SANDBOX_TOKEN"
        if environment == "sandbox"
        else "YANDEX_DIRECT_PRODUCTION_READ_TOKEN"
    )
    token = os.environ.get(token_name, "").strip()
    if not token:
        raise ValueError(f"Для среды {environment} не задан отдельный токен чтения.")
    login = os.environ.get("YANDEX_DIRECT_CLIENT_LOGIN", "").strip()
    if not login:
        raise ValueError("Не задан YANDEX_DIRECT_CLIENT_LOGIN: чтение без явной области клиента запрещено.")
    output = Path(
        os.environ.get(
            "YANDEX_DIRECT_OUTPUT_DIR",
            str(Path.cwd() / "artifacts" / "yandex-direct"),
        )
    ).expanduser().resolve()
    return environment, token, login, output


def canonical_body(service: str, params: dict[str, Any]) -> bytes:
    payload = {"params": params} if service == "reports" else {"method": "get", "params": params}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def safe_headers(token: str, login: str, reports: bool) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    headers["Client-Login"] = login
    if reports:
        headers.update({
            "processingMode": "auto",
            "returnMoneyInMicros": "false",
            "skipReportHeader": "true",
            "skipColumnHeader": "false",
            "skipReportSummary": "true",
        })
    return headers


async def http_request(url: str, headers: dict[str, str], body: bytes) -> httpx.Response:
    timeout = httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, headers=headers, content=body)


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def atomic_bytes(path: Path, content: bytes) -> None:
    ensure_private_dir(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_bytes(path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def header(response: Any, name: str, default: str = "") -> str:
    headers = getattr(response, "headers", {})
    return str(headers.get(name, headers.get(name.lower(), default)) or default)


def response_status(response: Any) -> int:
    return int(getattr(response, "status_code"))


def response_content(response: Any) -> bytes:
    value = getattr(response, "content", b"")
    return value if isinstance(value, bytes) else bytes(value)


async def execute_read(
    service: str,
    method: str,
    params: dict[str, Any],
    version: str = "v5",
    *,
    request: RequestFunction | None = None,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    validate_route(service, method, version)
    environment, token, login, output = resolve_runtime()
    base = SANDBOX_BASE if environment == "sandbox" else PRODUCTION_BASE
    url = f"{base}/json/{version}/{service}"
    body = canonical_body(service, params)
    headers = safe_headers(token, login, service == "reports")
    sender = request or http_request

    if service != "reports":
        try:
            response = await sender(url, headers, body)
            status = response_status(response)
            if status != 200:
                return {"status": "error", "http_status": status, "service": service}
            return {
                "status": "ready",
                "service": service,
                "version": version,
                "result": response.json(),
            }
        except Exception as error:
            return {"status": "error", "service": service, "error_type": type(error).__name__}

    request_sha256 = hashlib.sha256(body).hexdigest()
    state_path = output / f"_api_reports_{request_sha256}.state.json"
    while True:
        try:
            response = await sender(url, headers, body)
            status = response_status(response)
        except Exception as error:
            return {
                "status": "error",
                "service": "reports",
                "request_sha256": request_sha256,
                "error_type": type(error).__name__,
            }

        request_id = header(response, "RequestId")
        if status == 200:
            content = response_content(response)
            if not content:
                state = {
                    "status": "error",
                    "request_sha256": request_sha256,
                    "request_id": request_id,
                    "http_status": status,
                    "error": "empty_report",
                }
                atomic_json(state_path, state)
                return state
            artifact = output / f"_api_reports_{request_sha256}.tsv"
            atomic_bytes(artifact, content)
            state = {
                "status": "ready",
                "request_sha256": request_sha256,
                "request_id": request_id,
                "artifact_path": str(artifact),
                "artifact_sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
            atomic_json(state_path, state)
            return state

        if status in {201, 202}:
            retry_in_raw = header(response, "retryIn", "1")
            try:
                retry_in = max(float(retry_in_raw), 0.0)
            except ValueError:
                retry_in = 1.0
            state = {
                "status": "queued" if status == 201 else "pending",
                "request_sha256": request_sha256,
                "request_id": request_id,
                "retry_in": retry_in,
                "reports_in_queue": header(response, "reportsInQueue"),
            }
            atomic_json(state_path, state)
            await sleeper(retry_in)
            continue

        state = {
            "status": "error",
            "request_sha256": request_sha256,
            "request_id": request_id,
            "http_status": status,
        }
        atomic_json(state_path, state)
        return state


def parse_params(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("params должен быть объектом JSON.")
    return parsed


@mcp.tool(
    name="yd_api",
    annotations={
        "title": "Яндекс.Директ: безопасное чтение",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def yd_api(service: str, method: str, params: str, version: str = "v5") -> str:
    """Выполнить разрешённый get без передачи токена в аргументах."""
    try:
        result = await execute_read(service, method, parse_params(params), version)
    except (ValueError, json.JSONDecodeError) as error:
        result = {"status": "rejected", "error": str(error)}
    return json.dumps(result, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transport", nargs="?", choices=["stdio", "sse"], default="stdio")
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
