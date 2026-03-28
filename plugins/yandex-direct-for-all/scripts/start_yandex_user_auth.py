#!/usr/bin/env python3
"""Operator-facing Yandex OAuth launcher for Direct, Metrika, and Audience."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from yandex_auth_common import (  # noqa: E402
    TOKEN_ENV_NAMES,
    auth_env_path,
    auth_token_path,
    discover_client_overlay,
    overlay_counter_id,
    overlay_direct_login,
    pending_session_path,
    resolve_auth_root,
    resolve_public_profile,
)

AUTH_BASE = "https://oauth.yandex.com"
AUTHORIZE_URL = f"{AUTH_BASE}/authorize"
TOKEN_URL = f"{AUTH_BASE}/token"
DEVICE_CODE_URL = f"{AUTH_BASE}/device/code"
DEFAULT_MANUAL_REDIRECT = "https://oauth.yandex.ru/verification_code"


@dataclass(frozen=True)
class ServiceConfig:
    key: str
    label: str
    env_prefix: str


@dataclass(frozen=True)
class ResolvedConfig:
    service: ServiceConfig
    profile_name: str
    profile_source: str
    mode: str
    auth_root: Path
    pending_path: Path
    client_id: str
    client_id_source: str
    client_secret: str
    client_secret_source: str
    redirect_uri: str
    redirect_uri_source: str
    scope: str
    scope_source: str
    output_path: Path
    output_source: str
    env_output_path: Path
    env_output_source: str
    code_verifier: str
    code_verifier_source: str
    code_challenge: str
    code_challenge_method: str
    state: str
    state_source: str
    expected_client_login: str
    expected_client_login_source: str
    expected_counter_id: str
    expected_counter_id_source: str
    overlay_source: str


SERVICES = {
    "direct": ServiceConfig("direct", "Yandex Direct", "YANDEX_DIRECT"),
    "metrika": ServiceConfig("metrika", "Yandex Metrika", "YANDEX_METRIKA"),
    "audience": ServiceConfig("audience", "Yandex Audience", "YANDEX_AUDIENCE"),
}

MODE_ALIASES = {
    "auto": "auto",
    "local": "local-callback",
    "local-callback": "local-callback",
    "manual": "manual-code",
    "manual-code": "manual-code",
    "screen-code": "manual-code",
    "device": "device-code",
    "device-code": "device-code",
}


class LocalCallbackHandler(http.server.BaseHTTPRequestHandler):
    client_id = ""
    client_secret = ""
    redirect_uri = ""
    code_verifier = ""
    state = ""
    device_id = ""
    device_name = ""
    output_path = Path("oauth_token.json")
    token_result: dict | None = None
    completed = threading.Event()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        expected_path = urllib.parse.urlparse(self.redirect_uri).path

        if parsed.path != expected_path or "code" not in params:
            self.send_response(404)
            self.end_headers()
            return
        if self.state and params.get("state", [""])[0] != self.state:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"OAuth state mismatch.")
            self.__class__.completed.set()
            return

        token = exchange_authorization_code(
            code=params["code"][0],
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            device_id=self.device_id,
            device_name=self.device_name,
            code_verifier=self.code_verifier,
        )
        self.__class__.token_result = token

        status = 200 if "access_token" in token else 400
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if status == 200:
            write_json(self.output_path, token)
            token_preview = token["access_token"][:24]
            html = (
                "<html><body style='font-family:Arial;padding:40px'>"
                "<h1 style='color:#0a7a26'>Token received</h1>"
                f"<p>Saved to: <code>{self.output_path}</code></p>"
                f"<p>Token preview: <code>{token_preview}...</code></p>"
                "</body></html>"
            )
        else:
            html = (
                "<html><body style='font-family:Arial;padding:40px'>"
                "<h1 style='color:#b00020'>OAuth error</h1>"
                f"<pre>{json.dumps(token, ensure_ascii=False, indent=2)}</pre>"
                "</body></html>"
            )

        self.wfile.write(html.encode("utf-8"))
        self.__class__.completed.set()

    def log_message(self, fmt: str, *args: object) -> None:
        return


def first_non_empty(options: Iterable[tuple[str, str]]) -> tuple[str, str]:
    for value, source in options:
        if value:
            return value, source
    return "", ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operator-facing OAuth launcher for Yandex Direct, Yandex Metrika, "
            "and Yandex Audience. This launcher is intentionally not used for "
            "Wordstat or Yandex Search API."
        )
    )
    parser.add_argument("--service", choices=sorted(SERVICES), required=True)
    parser.add_argument(
        "--mode",
        default="auto",
        help=(
            "Auth mode: auto, screen-code/manual-code, local-callback, or device-code. "
            "Compatibility aliases: device, manual, screen-code, local."
        ),
    )
    parser.add_argument("--profile", default="auto", help="OAuth profile: auto, legacy_direct, master_yandex.")
    parser.add_argument("--client-id", default="")
    parser.add_argument("--client-secret", default="")
    parser.add_argument("--redirect-uri", default="")
    parser.add_argument("--scope", default="")
    parser.add_argument("--output", default="", help="Token JSON output path.")
    parser.add_argument("--env-output", default="", help="Shell env file output path.")
    parser.add_argument("--auth-root", default="")
    parser.add_argument("--code", default="", help="Confirmation code for manual exchange.")
    parser.add_argument("--login-hint", default="")
    parser.add_argument("--client-login", default="", help="Expected Direct Client-Login for post-auth preflight.")
    parser.add_argument("--counter-id", default="", help="Expected Metrika counter_id for post-auth preflight.")
    parser.add_argument("--segment-name", default="", help="Expected Audience segment name for post-auth preflight.")
    parser.add_argument("--device-id", default="")
    parser.add_argument("--device-name", default="")
    parser.add_argument("--port", type=int, default=8080, help="Default port for local-callback mode.")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout for local or device flow.")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=0,
        help="Override polling interval for device-code mode.",
    )
    parser.add_argument("--force-confirm", action="store_true")
    parser.add_argument("--print-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Compatibility alias for --print-only.")
    parser.add_argument("--skip-preflight", action="store_true", help="Do not run post-auth read-only preflight.")

    browser_group = parser.add_mutually_exclusive_group()
    browser_group.add_argument("--open-browser", dest="open_browser", action="store_true")
    browser_group.add_argument("--no-browser", dest="open_browser", action="store_false")
    parser.set_defaults(open_browser=None)
    return parser


def normalize_mode(raw_mode: str) -> str:
    mode = MODE_ALIASES.get(raw_mode.strip().lower())
    if not mode:
        allowed = ", ".join(sorted(set(MODE_ALIASES.values())))
        raise SystemExit(f"Unsupported mode: {raw_mode}. Allowed values: {allowed}")
    return mode


def should_open_browser(args: argparse.Namespace) -> bool:
    if args.open_browser is not None:
        return args.open_browser
    return not (args.print_only or args.dry_run)


def auth_root_path(args: argparse.Namespace) -> tuple[Path, str]:
    root, source = resolve_auth_root(args.auth_root)
    if args.auth_root:
        return root, "--auth-root"
    if os.environ.get("YANDEX_AUTH_OUTPUT_DIR", ""):
        return root, "YANDEX_AUTH_OUTPUT_DIR"
    if os.environ.get("YANDEX_OAUTH_AUTH_ROOT", ""):
        return root, "YANDEX_OAUTH_AUTH_ROOT"
    return root, source


def resolve_output_path(args: argparse.Namespace, service: ServiceConfig) -> tuple[Path, str]:
    value, source = first_non_empty(
        [
            (args.output, "--output"),
            (os.environ.get(f"{service.env_prefix}_OAUTH_TOKEN_PATH", ""), f"{service.env_prefix}_OAUTH_TOKEN_PATH"),
            (os.environ.get("YANDEX_OAUTH_TOKEN_PATH", ""), "YANDEX_OAUTH_TOKEN_PATH"),
        ]
    )
    if value:
        return Path(value).expanduser().resolve(), source

    root, root_source = auth_root_path(args)
    return auth_token_path(root, service.key), root_source


def resolve_env_output_path(args: argparse.Namespace, service: ServiceConfig) -> tuple[Path, str]:
    value, source = first_non_empty(
        [
            (args.env_output, "--env-output"),
            (os.environ.get(f"{service.env_prefix}_OAUTH_ENV_PATH", ""), f"{service.env_prefix}_OAUTH_ENV_PATH"),
            (os.environ.get("YANDEX_OAUTH_ENV_PATH", ""), "YANDEX_OAUTH_ENV_PATH"),
        ]
    )
    if value:
        return Path(value).expanduser().resolve(), source

    root, root_source = auth_root_path(args)
    return auth_env_path(root, service.key), root_source


def resolve_redirect_uri(
    args: argparse.Namespace,
    service: ServiceConfig,
    mode: str,
) -> tuple[str, str]:
    if mode == "device-code":
        return "", "not-used-in-device-code"

    default_value = (
        f"http://localhost:{args.port}/callback"
        if mode == "local-callback"
        else DEFAULT_MANUAL_REDIRECT
    )
    return first_non_empty(
        [
            (args.redirect_uri, "--redirect-uri"),
            (os.environ.get(f"{service.env_prefix}_OAUTH_REDIRECT_URI", ""), f"{service.env_prefix}_OAUTH_REDIRECT_URI"),
            (os.environ.get("YANDEX_OAUTH_REDIRECT_URI", ""), "YANDEX_OAUTH_REDIRECT_URI"),
            (default_value, f"default:{default_value}"),
        ]
    )


def resolve_scope(args: argparse.Namespace, service: ServiceConfig) -> tuple[str, str]:
    return first_non_empty(
        [
            (args.scope, "--scope"),
            (os.environ.get(f"{service.env_prefix}_OAUTH_SCOPE", ""), f"{service.env_prefix}_OAUTH_SCOPE"),
            (os.environ.get("YANDEX_OAUTH_SCOPE", ""), "YANDEX_OAUTH_SCOPE"),
        ]
    )


def load_pending_session(path: Path) -> tuple[dict, str]:
    if not path.is_file():
        return {}, ""
    try:
        return json.loads(path.read_text(encoding="utf-8")), str(path)
    except Exception:
        return {}, ""


def clear_pending_session(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        if path.exists():
            path.unlink()


def pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_pkce_verifier() -> str:
    raw = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")
    return raw[:96]


def resolve_expected_client_login(
    args: argparse.Namespace,
    overlay: dict,
) -> tuple[str, str]:
    value, source = first_non_empty(
        [
            (args.client_login, "--client-login"),
            (os.environ.get("YD_CLIENT_LOGIN", ""), "YD_CLIENT_LOGIN"),
            (overlay_direct_login(overlay), "overlay.direct.login"),
        ]
    )
    return value, source


def resolve_expected_counter_id(
    args: argparse.Namespace,
    overlay: dict,
) -> tuple[str, str]:
    value, source = first_non_empty(
        [
            (args.counter_id, "--counter-id"),
            (os.environ.get("YANDEX_METRIKA_COUNTER_ID", ""), "YANDEX_METRIKA_COUNTER_ID"),
            (overlay_counter_id(overlay), "overlay.metrika.counter_id"),
        ]
    )
    return value, source


def resolve_config(args: argparse.Namespace) -> ResolvedConfig:
    service = SERVICES[args.service]
    auth_root, auth_root_source = auth_root_path(args)
    pending_path = pending_session_path(auth_root, service.key)
    pending, pending_source = load_pending_session(pending_path)
    overlay, overlay_source = discover_client_overlay(Path.cwd())

    requested_profile = ""
    profile_source = ""
    if args.profile and args.profile != "auto":
        requested_profile = args.profile
        profile_source = "--profile"
    elif os.environ.get("YANDEX_OAUTH_PROFILE", ""):
        requested_profile = os.environ["YANDEX_OAUTH_PROFILE"]
        profile_source = "YANDEX_OAUTH_PROFILE"

    public_profile, public_profile_name, public_profile_source = resolve_public_profile(
        service.key,
        requested_profile,
    )
    if not profile_source:
        profile_source = public_profile_source

    requested_mode = normalize_mode(args.mode)
    mode = public_profile.get("default_mode", "manual-code") if requested_mode == "auto" else requested_mode
    if pending.get("mode") and args.code and requested_mode == "auto":
        mode = pending["mode"]

    client_id, client_id_source = first_non_empty(
        [
            (args.client_id, "--client-id"),
            (os.environ.get(f"{service.env_prefix}_OAUTH_CLIENT_ID", ""), f"{service.env_prefix}_OAUTH_CLIENT_ID"),
            (os.environ.get("YANDEX_OAUTH_CLIENT_ID", ""), "YANDEX_OAUTH_CLIENT_ID"),
            (str(pending.get("client_id", "")), pending_source or "pending-session"),
            (str(public_profile.get("client_id", "")), profile_source),
        ]
    )
    client_secret, client_secret_source = first_non_empty(
        [
            (args.client_secret, "--client-secret"),
            (os.environ.get(f"{service.env_prefix}_OAUTH_CLIENT_SECRET", ""), f"{service.env_prefix}_OAUTH_CLIENT_SECRET"),
            (os.environ.get("YANDEX_OAUTH_CLIENT_SECRET", ""), "YANDEX_OAUTH_CLIENT_SECRET"),
            (str(pending.get("client_secret", "")), pending_source or "pending-session"),
        ]
    )

    if not client_id:
        raise SystemExit(
            f"Missing OAuth client_id for {service.label}. "
            "No env seed was provided and no public profile was resolved."
        )

    redirect_uri_default = str(public_profile.get("redirect_uri", ""))
    redirect_uri, redirect_uri_source = first_non_empty(
        [
            (args.redirect_uri, "--redirect-uri"),
            (os.environ.get(f"{service.env_prefix}_OAUTH_REDIRECT_URI", ""), f"{service.env_prefix}_OAUTH_REDIRECT_URI"),
            (os.environ.get("YANDEX_OAUTH_REDIRECT_URI", ""), "YANDEX_OAUTH_REDIRECT_URI"),
            (str(pending.get("redirect_uri", "")), pending_source or "pending-session"),
            (redirect_uri_default, profile_source),
        ]
    )
    if mode == "manual-code" and not redirect_uri:
        redirect_uri = DEFAULT_MANUAL_REDIRECT
        redirect_uri_source = f"default:{DEFAULT_MANUAL_REDIRECT}"
    if mode == "local-callback" and not redirect_uri:
        redirect_uri = f"http://localhost:{args.port}/callback"
        redirect_uri_source = f"default:http://localhost:{args.port}/callback"

    scope, scope_source = resolve_scope(args, service)
    if not scope and pending.get("scope"):
        scope = str(pending.get("scope", "")).strip()
        scope_source = pending_source or "pending-session"

    output_path, output_source = resolve_output_path(args, service)
    if not args.output and not os.environ.get(f"{service.env_prefix}_OAUTH_TOKEN_PATH", "") and not os.environ.get("YANDEX_OAUTH_TOKEN_PATH", "") and pending.get("output_path"):
        output_path = Path(str(pending["output_path"])).expanduser().resolve()
        output_source = pending_source or "pending-session"

    env_output_path, env_output_source = resolve_env_output_path(args, service)
    if not args.env_output and not os.environ.get(f"{service.env_prefix}_OAUTH_ENV_PATH", "") and not os.environ.get("YANDEX_OAUTH_ENV_PATH", "") and pending.get("env_output_path"):
        env_output_path = Path(str(pending["env_output_path"])).expanduser().resolve()
        env_output_source = pending_source or "pending-session"
    expected_client_login, expected_client_login_source = resolve_expected_client_login(args, overlay)
    expected_counter_id, expected_counter_id_source = resolve_expected_counter_id(args, overlay)
    code_verifier, code_verifier_source = first_non_empty(
        [
            (str(pending.get("code_verifier", "")), pending_source or "pending-session"),
        ]
    )
    state, state_source = first_non_empty(
        [
            (str(pending.get("state", "")), pending_source or "pending-session"),
        ]
    )
    code_challenge = str(pending.get("code_challenge", "")).strip()
    if not code_verifier:
        code_verifier = generate_pkce_verifier()
        code_verifier_source = "generated:pkce"
        code_challenge = pkce_code_challenge(code_verifier)
    if not state:
        state = secrets.token_urlsafe(18)
        state_source = "generated:oauth-state"

    return ResolvedConfig(
        service=service,
        profile_name=public_profile_name,
        profile_source=profile_source,
        mode=mode,
        auth_root=auth_root,
        pending_path=pending_path,
        client_id=client_id,
        client_id_source=client_id_source,
        client_secret=client_secret,
        client_secret_source=client_secret_source or "pkce:no-secret",
        redirect_uri=redirect_uri,
        redirect_uri_source=redirect_uri_source,
        scope=scope,
        scope_source=scope_source or "app-default-scope",
        output_path=output_path,
        output_source=output_source,
        env_output_path=env_output_path,
        env_output_source=env_output_source,
        code_verifier=code_verifier,
        code_verifier_source=code_verifier_source,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        state=state,
        state_source=state_source,
        expected_client_login=expected_client_login,
        expected_client_login_source=expected_client_login_source,
        expected_counter_id=expected_counter_id,
        expected_counter_id_source=expected_counter_id_source,
        overlay_source=overlay_source or auth_root_source,
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_env_file(service_key: str, input_path: Path, output_path: Path, access_token: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        (
            f"# Generated from {input_path}\n"
            f"# Service: {service_key}\n"
            f"export {TOKEN_ENV_NAMES[service_key]}={json.dumps(access_token, ensure_ascii=False)}\n"
        ),
        encoding="utf-8",
    )


def persist_outputs(config: ResolvedConfig, payload: dict) -> None:
    write_json(config.output_path, payload)
    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise SystemExit(f"No access_token found in token payload for {config.service.label}.")
    write_env_file(config.service.key, config.output_path, config.env_output_path, access_token)


def save_pending_session(config: ResolvedConfig, args: argparse.Namespace) -> None:
    payload = {
        "service": config.service.key,
        "profile_name": config.profile_name,
        "mode": config.mode,
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "scope": config.scope,
        "output_path": str(config.output_path),
        "env_output_path": str(config.env_output_path),
        "code_verifier": config.code_verifier,
        "code_challenge": config.code_challenge,
        "code_challenge_method": config.code_challenge_method,
        "state": config.state,
        "device_id": args.device_id,
        "device_name": args.device_name,
        "client_login": config.expected_client_login,
        "counter_id": config.expected_counter_id,
        "segment_name": args.segment_name,
        "created_at": int(time.time()),
    }
    write_json(config.pending_path, payload)


def run_post_auth_preflight(config: ResolvedConfig, args: argparse.Namespace) -> None:
    if args.skip_preflight or args.print_only or args.dry_run:
        return
    preflight_script = SCRIPT_DIR / "preflight_yandex_user_token.py"
    command = [
        sys.executable,
        str(preflight_script),
        "--service",
        config.service.key,
        "--token-json",
        str(config.output_path),
        "--auth-root",
        str(config.auth_root),
    ]
    if config.expected_client_login:
        command.extend(["--client-login", config.expected_client_login])
    if config.expected_counter_id:
        command.extend(["--counter-id", config.expected_counter_id])
    if args.segment_name:
        command.extend(["--segment-name", args.segment_name])
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise SystemExit(
            f"Token was saved, but post-auth preflight failed for {config.service.label}. "
            f"Inspect the preflight output for {config.service.key}."
        )


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    login_hint: str,
    force_confirm: bool,
    state: str,
    code_challenge: str,
    code_challenge_method: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    if scope:
        params["scope"] = scope
    if login_hint:
        params["login_hint"] = login_hint
    if force_confirm:
        params["force_confirm"] = "yes"
    if state:
        params["state"] = state
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = code_challenge_method
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_authorization_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    device_id: str,
    device_name: str,
    code_verifier: str,
) -> dict:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    if device_id:
        payload["device_id"] = device_id
    if device_name:
        payload["device_name"] = device_name
    if code_verifier:
        payload["code_verifier"] = code_verifier
    response = requests.post(TOKEN_URL, data=payload, timeout=60)
    return response.json()


def request_device_code(
    *,
    client_id: str,
    scope: str,
    device_id: str,
    device_name: str,
) -> dict:
    payload = {"client_id": client_id}
    if scope:
        payload["scope"] = scope
    if device_id:
        payload["device_id"] = device_id
    if device_name:
        payload["device_name"] = device_name
    response = requests.post(DEVICE_CODE_URL, data=payload, timeout=60)
    return response.json()


def poll_device_token(
    *,
    device_code: str,
    client_id: str,
    client_secret: str,
    timeout: int,
    interval: int,
) -> dict:
    deadline = time.monotonic() + timeout
    current_interval = max(1, interval)

    while time.monotonic() < deadline:
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "device_code",
                "code": device_code,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=60,
        )
        payload = response.json()
        if "access_token" in payload:
            return payload

        error = payload.get("error", "")
        if error == "authorization_pending":
            time.sleep(current_interval)
            continue
        if error == "slow_down":
            current_interval += 5
            time.sleep(current_interval)
            continue
        raise SystemExit(f"Device-code flow failed: {json.dumps(payload, ensure_ascii=False)}")

    raise SystemExit("Timed out while waiting for device-code authorization.")


def validate_local_redirect(redirect_uri: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"} or not parsed.port:
        raise SystemExit(
            "local-callback mode requires exact local HTTP redirect, for example "
            "http://localhost:8080/callback. Register that URI in the Yandex OAuth app first."
        )
    return parsed.hostname, parsed.port


def print_config(config: ResolvedConfig) -> None:
    print(f"Service: {config.service.label}")
    print("Auth model: reusable approved app + per-user consent token")
    print(f"OAuth profile: {config.profile_name}")
    print(f"OAuth profile source: {config.profile_source}")
    print(f"Mode: {config.mode}")
    print(f"Client ID source: {config.client_id_source}")
    print(f"Client secret source: {config.client_secret_source}")
    if config.redirect_uri:
        print(f"Redirect URI: {config.redirect_uri}")
        print(f"Redirect source: {config.redirect_uri_source}")
    print(f"PKCE verifier source: {config.code_verifier_source}")
    print(f"PKCE challenge method: {config.code_challenge_method}")
    print(f"Pending session: {config.pending_path}")
    print(f"Scope source: {config.scope_source}")
    if config.scope:
        print(f"Scope value: {config.scope}")
    print(f"Token JSON: {config.output_path}")
    print(f"Token JSON source: {config.output_source}")
    print(f"Token env: {config.env_output_path}")
    print(f"Token env source: {config.env_output_source}")
    if config.expected_client_login:
        print(f"Expected Direct login: {config.expected_client_login}")
        print(f"Expected Direct login source: {config.expected_client_login_source}")
    if config.expected_counter_id:
        print(f"Expected Metrika counter_id: {config.expected_counter_id}")
        print(f"Expected Metrika counter_id source: {config.expected_counter_id_source}")
    if config.overlay_source:
        print(f"Overlay source: {config.overlay_source}")


def run_manual_code(args: argparse.Namespace, config: ResolvedConfig) -> None:
    auth_url = build_authorize_url(
        client_id=config.client_id,
        redirect_uri=config.redirect_uri,
        scope=config.scope,
        login_hint=args.login_hint,
        force_confirm=args.force_confirm,
        state=config.state,
        code_challenge=config.code_challenge,
        code_challenge_method=config.code_challenge_method,
    )
    save_pending_session(config, args)
    print_config(config)
    print(f"Auth URL: {auth_url}")

    if args.print_only or args.dry_run:
        print(f"Pending session saved: {config.pending_path}")
        return

    if args.code:
        token = exchange_authorization_code(
            code=args.code,
            client_id=config.client_id,
            client_secret=config.client_secret,
            redirect_uri=config.redirect_uri,
            device_id=args.device_id,
            device_name=args.device_name,
            code_verifier=config.code_verifier,
        )
        if "access_token" not in token:
            raise SystemExit(f"Code exchange failed: {json.dumps(token, ensure_ascii=False)}")
        persist_outputs(config, token)
        clear_pending_session(config.pending_path)
        print(f"Saved token: {config.output_path}")
        print(f"Saved env: {config.env_output_path}")
        run_post_auth_preflight(config, args)
        return

    if should_open_browser(args):
        webbrowser.open(auth_url)
    if sys.stdin.isatty():
        print("Open the URL, finish consent, then paste the confirmation code below.")
        code = input("Confirmation code: ").strip()
        if code:
            token = exchange_authorization_code(
                code=code,
                client_id=config.client_id,
                client_secret=config.client_secret,
                redirect_uri=config.redirect_uri,
                device_id=args.device_id,
                device_name=args.device_name,
                code_verifier=config.code_verifier,
            )
            if "access_token" not in token:
                raise SystemExit(f"Code exchange failed: {json.dumps(token, ensure_ascii=False)}")
            persist_outputs(config, token)
            clear_pending_session(config.pending_path)
            print(f"Saved token: {config.output_path}")
            print(f"Saved env: {config.env_output_path}")
            run_post_auth_preflight(config, args)
            return
    print(f"Open the URL, finish consent, then rerun this command with --code <confirmation-code>.")


def run_device_code(args: argparse.Namespace, config: ResolvedConfig) -> None:
    print_config(config)
    print(f"Device code endpoint: {DEVICE_CODE_URL}")

    if args.code:
        raise SystemExit("--code is not used with device-code mode.")
    if not config.client_secret:
        raise SystemExit("device-code mode requires client_secret. Use the default PKCE path instead.")
    if args.print_only or args.dry_run:
        print("Print-only mode: device_code was not requested.")
        return

    payload = request_device_code(
        client_id=config.client_id,
        scope=config.scope,
        device_id=args.device_id,
        device_name=args.device_name,
    )
    if "device_code" not in payload or "user_code" not in payload:
        raise SystemExit(f"Device-code start failed: {json.dumps(payload, ensure_ascii=False)}")

    verification_url = payload.get("verification_url_complete") or payload["verification_url"]
    interval = args.poll_interval or int(payload.get("interval", 5))
    timeout = min(args.timeout, int(payload.get("expires_in", args.timeout)))

    print(f"Verification URL: {verification_url}")
    print(f"User code: {payload['user_code']}")
    print(f"Poll interval: {interval}s")
    print(f"Timeout: {timeout}s")

    if should_open_browser(args):
        webbrowser.open(verification_url)

    token = poll_device_token(
        device_code=payload["device_code"],
        client_id=config.client_id,
        client_secret=config.client_secret,
        timeout=timeout,
        interval=interval,
    )
    persist_outputs(config, token)
    clear_pending_session(config.pending_path)
    print(f"Saved token: {config.output_path}")
    print(f"Saved env: {config.env_output_path}")
    run_post_auth_preflight(config, args)


def run_local_callback(args: argparse.Namespace, config: ResolvedConfig) -> None:
    auth_url = build_authorize_url(
        client_id=config.client_id,
        redirect_uri=config.redirect_uri,
        scope=config.scope,
        login_hint=args.login_hint,
        force_confirm=args.force_confirm,
        state=config.state,
        code_challenge=config.code_challenge,
        code_challenge_method=config.code_challenge_method,
    )
    save_pending_session(config, args)
    print_config(config)
    print(f"Auth URL: {auth_url}")

    if args.print_only or args.dry_run:
        print(f"Pending session saved: {config.pending_path}")
        return

    if args.code:
        token = exchange_authorization_code(
            code=args.code,
            client_id=config.client_id,
            client_secret=config.client_secret,
            redirect_uri=config.redirect_uri,
            device_id=args.device_id,
            device_name=args.device_name,
            code_verifier=config.code_verifier,
        )
        if "access_token" not in token:
            raise SystemExit(f"Code exchange failed: {json.dumps(token, ensure_ascii=False)}")
        persist_outputs(config, token)
        clear_pending_session(config.pending_path)
        print(f"Saved token: {config.output_path}")
        print(f"Saved env: {config.env_output_path}")
        run_post_auth_preflight(config, args)
        return

    host, port = validate_local_redirect(config.redirect_uri)

    LocalCallbackHandler.client_id = config.client_id
    LocalCallbackHandler.client_secret = config.client_secret
    LocalCallbackHandler.redirect_uri = config.redirect_uri
    LocalCallbackHandler.code_verifier = config.code_verifier
    LocalCallbackHandler.state = config.state
    LocalCallbackHandler.device_id = args.device_id
    LocalCallbackHandler.device_name = args.device_name
    LocalCallbackHandler.output_path = config.output_path
    LocalCallbackHandler.token_result = None
    LocalCallbackHandler.completed = threading.Event()

    server = http.server.HTTPServer((host, port), LocalCallbackHandler)
    server.timeout = 1
    deadline = time.monotonic() + args.timeout

    if should_open_browser(args):
        webbrowser.open(auth_url)

    try:
        while time.monotonic() < deadline and not LocalCallbackHandler.completed.is_set():
            server.handle_request()
    except KeyboardInterrupt as exc:
        raise SystemExit("Interrupted before callback was completed.") from exc
    finally:
        server.server_close()

    token = LocalCallbackHandler.token_result or {}
    if "access_token" not in token:
        raise SystemExit(
            "local-callback flow did not produce access_token before timeout. "
            "Check that the exact redirect URI is registered in the OAuth app."
        )

    persist_outputs(config, token)
    clear_pending_session(config.pending_path)
    print(f"Saved token: {config.output_path}")
    print(f"Saved env: {config.env_output_path}")
    run_post_auth_preflight(config, args)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.dry_run:
        args.print_only = True

    config = resolve_config(args)
    if config.mode == "device-code":
        run_device_code(args, config)
        return
    if config.mode == "manual-code":
        run_manual_code(args, config)
        return
    run_local_callback(args, config)


if __name__ == "__main__":
    main()
