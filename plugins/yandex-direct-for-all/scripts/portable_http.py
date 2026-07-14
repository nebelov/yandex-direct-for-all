#!/usr/bin/env python3
"""Небольшой переносимый HTTP-слой на стандартной библиотеке Python."""

from __future__ import annotations

import json as json_module
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class HTTPStatusError(RuntimeError):
    pass


@dataclass
class Response:
    status_code: int
    content: bytes
    headers: dict[str, str]
    url: str

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    @property
    def text(self) -> str:
        charset = "utf-8"
        content_type = self.headers.get("Content-Type", "")
        for part in content_type.split(";")[1:]:
            key, separator, value = part.strip().partition("=")
            if separator and key.lower() == "charset" and value:
                charset = value.strip('"')
        return self.content.decode(charset, errors="replace")

    def json(self) -> Any:
        return json_module.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPStatusError(f"HTTP {self.status_code}: {self.text[:800]}")

    def __enter__(self) -> Response:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        return None


def _timeout(value: Any) -> float | None:
    if isinstance(value, tuple):
        value = next((item for item in value if item is not None), None)
    return float(value) if value is not None else None


def request(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    json: Any = None,
    data: Any = None,
    timeout: Any = None,
    allow_redirects: bool = True,
) -> Response:
    if not allow_redirects:
        raise ValueError("Переносимый HTTP-слой поддерживает только переходы по перенаправлениям")
    if params:
        encoded = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}{'&' if '?' in url else '?'}{encoded}"
    request_headers = dict(headers or {})
    body: bytes | None = None
    if json is not None:
        body = json_module.dumps(json, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json; charset=utf-8")
    elif data is not None:
        if isinstance(data, bytes):
            body = data
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    prepared = urllib.request.Request(url, data=body, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(prepared, timeout=_timeout(timeout)) as source:
            return Response(int(source.status), source.read(), dict(source.headers.items()), source.geturl())
    except urllib.error.HTTPError as error:
        try:
            return Response(int(error.code), error.read(), dict(error.headers.items()), error.geturl())
        finally:
            error.close()


def get(url: str, **kwargs: Any) -> Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> Response:
    return request("POST", url, **kwargs)


class Session:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    def get(self, url: str, **kwargs: Any) -> Response:
        headers = {**self.headers, **dict(kwargs.pop("headers", {}) or {})}
        return get(url, headers=headers, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        headers = {**self.headers, **dict(kwargs.pop("headers", {}) or {})}
        return post(url, headers=headers, **kwargs)
