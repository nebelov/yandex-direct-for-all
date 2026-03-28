#!/usr/bin/env python3
"""Shared helpers for Yandex OAuth runtime scripts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_AUTH_ROOT = Path.cwd() / ".codex" / "auth"
SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent
PUBLIC_PROFILE_PATH = PLUGIN_DIR / "config" / "yandex_oauth_public_profiles.json"
DEFAULT_SERVICE_PROFILE = {
    "direct": "legacy_direct",
    "metrika": "master_yandex",
    "audience": "master_yandex",
}
TOKEN_ENV_NAMES = {
    "direct": "YD_TOKEN",
    "metrika": "YANDEX_METRIKA_TOKEN",
    "audience": "YANDEX_AUDIENCE_TOKEN",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_auth_root(explicit: str = "") -> tuple[Path, str]:
    value = (
        explicit
        or os.environ.get("YANDEX_AUTH_OUTPUT_DIR", "")
        or os.environ.get("YANDEX_OAUTH_AUTH_ROOT", "")
    )
    if value:
        return Path(value).expanduser().resolve(), "explicit-or-env"
    return DEFAULT_AUTH_ROOT.resolve(), f"default:{DEFAULT_AUTH_ROOT}"


def auth_token_path(auth_root: Path, service: str) -> Path:
    return (auth_root / f"{service}_oauth_token.json").resolve()


def auth_env_path(auth_root: Path, service: str) -> Path:
    return (auth_root / f"{service}_oauth.env").resolve()


def pending_session_path(auth_root: Path, service: str) -> Path:
    return (auth_root / f"{service}_oauth_pending.json").resolve()


def load_public_profiles() -> dict[str, dict[str, Any]]:
    return load_json(PUBLIC_PROFILE_PATH)


def resolve_public_profile(service: str, requested_profile: str = "") -> tuple[dict[str, Any], str, str]:
    profiles = load_public_profiles()
    profile_name = requested_profile or DEFAULT_SERVICE_PROFILE[service]
    if profile_name not in profiles:
        raise SystemExit(
            f"Unknown OAuth profile: {profile_name}. Available: {', '.join(sorted(profiles))}"
        )
    profile = profiles[profile_name]
    supports = set(profile.get("supports") or [])
    if supports and service not in supports:
        raise SystemExit(
            f"OAuth profile {profile_name} is not marked for service {service}. "
            f"Supported services: {', '.join(sorted(supports))}"
        )
    return profile, profile_name, str(PUBLIC_PROFILE_PATH)


def load_token_from_json(path: Path) -> str:
    payload = load_json(path)
    token = str(payload.get("access_token", "")).strip()
    if not token:
        raise SystemExit(f"No access_token found in token file: {path}")
    return token


def iter_overlay_candidates(start_dir: Path | None = None) -> list[Path]:
    start = (start_dir or Path.cwd()).resolve()
    out: list[Path] = []
    for current in [start, *start.parents]:
        candidate = current / ".codex" / "yandex-performance-client.json"
        if candidate.is_file():
            out.append(candidate)
    return out


def discover_client_overlay(start_dir: Path | None = None) -> tuple[dict[str, Any] | None, str]:
    for candidate in iter_overlay_candidates(start_dir):
        try:
            return load_json(candidate), str(candidate)
        except Exception:
            continue
    return None, ""


def overlay_direct_login(overlay: dict[str, Any] | None) -> str:
    if not overlay:
        return ""
    return str((overlay.get("direct") or {}).get("login") or "").strip()


def overlay_counter_id(overlay: dict[str, Any] | None) -> str:
    if not overlay:
        return ""
    return str((overlay.get("metrika") or {}).get("counter_id") or "").strip()


def overlay_owner_login_candidates(overlay: dict[str, Any] | None) -> list[str]:
    values: list[str] = []
    direct_login = overlay_direct_login(overlay)
    if direct_login:
        values.append(direct_login)
    return values

