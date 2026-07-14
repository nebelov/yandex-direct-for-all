#!/usr/bin/env python3
"""Private-file helpers and public profile resolution for Yandex OAuth."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent
PUBLIC_PROFILE_PATH = PLUGIN_DIR / "config" / "yandex_oauth_public_profiles.json"
DEFAULT_SERVICE_PROFILE = {
    "direct": "legacy_direct",
    "metrika": "master_yandex",
    "audience": "master_yandex",
}
TOKEN_ENV_NAMES = {
    "direct": "YANDEX_DIRECT_PRODUCTION_READ_TOKEN",
    "metrika": "YANDEX_METRIKA_TOKEN",
    "audience": "YANDEX_AUDIENCE_TOKEN",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Ожидался объект JSON: {path.name}")
    return value


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def atomic_write(path: Path, content: bytes) -> None:
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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write(path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def write_text(path: Path, value: str) -> None:
    atomic_write(path, value.encode("utf-8"))


def require_private_file(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError(f"Файл {path.name} должен иметь права 600.")


def resolve_auth_root(explicit: str = "") -> tuple[Path, str]:
    value = explicit or os.environ.get("YANDEX_AUTH_OUTPUT_DIR", "")
    if value:
        path = Path(value).expanduser().resolve()
        source = "explicit-or-env"
    else:
        path = (Path.cwd() / ".codex" / "auth").resolve()
        source = "project-default"
    ensure_private_dir(path)
    return path, source


def auth_token_path(auth_root: Path, service: str) -> Path:
    return (auth_root / f"{service}_oauth_token.json").resolve()


def auth_env_path(auth_root: Path, service: str) -> Path:
    return (auth_root / f"{service}_oauth.env").resolve()


def pending_session_path(auth_root: Path, service: str) -> Path:
    return (auth_root / f"{service}_oauth_pending.json").resolve()


def preflight_path(auth_root: Path, service: str) -> Path:
    return (auth_root / f"{service}_oauth_preflight.json").resolve()


def load_public_profiles() -> dict[str, dict[str, Any]]:
    return load_json(PUBLIC_PROFILE_PATH)


def load_custom_config() -> tuple[dict[str, Any], str]:
    raw = os.environ.get("YANDEX_OAUTH_CONFIG_FILE", "").strip()
    if not raw:
        return {}, ""
    path = Path(raw).expanduser().resolve()
    require_private_file(path)
    return load_json(path), str(path)


def resolve_public_profile(service: str, requested_profile: str = "") -> tuple[dict[str, Any], str, str]:
    profiles = load_public_profiles()
    profile_name = requested_profile if requested_profile not in {"", "auto"} else DEFAULT_SERVICE_PROFILE[service]
    if profile_name not in profiles:
        raise ValueError(f"Неизвестный профиль авторизации: {profile_name}")
    profile = dict(profiles[profile_name])
    supports = set(profile.get("supports") or [])
    if service not in supports:
        raise ValueError(f"Профиль {profile_name} не предназначен для службы {service}.")

    custom, custom_source = load_custom_config()
    service_custom = custom.get(service, custom) if custom else {}
    prefix = f"YANDEX_{service.upper()}_OAUTH"
    client_id = (
        os.environ.get(f"{prefix}_CLIENT_ID", "").strip()
        or str(service_custom.get("client_id") or "").strip()
    )
    redirect_uri = (
        os.environ.get(f"{prefix}_REDIRECT_URI", "").strip()
        or str(service_custom.get("redirect_uri") or "").strip()
    )
    scope = (
        os.environ.get(f"{prefix}_SCOPE", "").strip()
        or str(service_custom.get("scope") or "").strip()
    )
    if client_id:
        profile["client_id"] = client_id
        profile_name = "custom"
    if redirect_uri:
        profile["redirect_uri"] = redirect_uri
    if scope:
        profile["scope"] = scope
    if not profile.get("client_id") or not profile.get("redirect_uri"):
        raise ValueError("У профиля должны быть client_id и redirect_uri.")
    if "client_secret" in profile or service_custom.get("client_secret"):
        raise ValueError("Эта поставка использует PKCE и не принимает секрет приложения.")
    return profile, profile_name, custom_source or str(PUBLIC_PROFILE_PATH)


def load_token_payload(path: Path) -> dict[str, Any]:
    require_private_file(path)
    payload = load_json(path)
    if not str(payload.get("access_token") or "").strip():
        raise ValueError(f"В файле {path.name} нет access_token.")
    return payload


def load_token_from_json(path: Path) -> str:
    return str(load_token_payload(path).get("access_token") or "").strip()


def discover_client_overlay(start_dir: Path | None = None) -> tuple[dict[str, Any] | None, str]:
    start = (start_dir or Path.cwd()).resolve()
    for current in [start, *start.parents]:
        candidate = current / ".codex" / "yandex-performance-client.json"
        if not candidate.is_file():
            continue
        try:
            require_private_file(candidate)
            return load_json(candidate), str(candidate)
        except Exception:
            continue
    return None, ""


def overlay_direct_login(overlay: dict[str, Any] | None) -> str:
    return str(((overlay or {}).get("direct") or {}).get("login") or "").strip()


def overlay_counter_id(overlay: dict[str, Any] | None) -> str:
    return str(((overlay or {}).get("metrika") or {}).get("counter_id") or "").strip()
