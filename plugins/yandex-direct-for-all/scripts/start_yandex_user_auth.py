#!/usr/bin/env python3
"""Shared-app Yandex OAuth launcher using authorization code + PKCE S256."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import portable_http as requests  # noqa: E402

from yandex_auth_common import (  # noqa: E402
    TOKEN_ENV_NAMES,
    auth_env_path,
    auth_token_path,
    discover_client_overlay,
    load_json,
    overlay_counter_id,
    overlay_direct_login,
    pending_session_path,
    require_private_file,
    resolve_auth_root,
    resolve_public_profile,
    write_json,
    write_text,
)


AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
TOKEN_URL = "https://oauth.yandex.ru/token"
SERVICES = {"direct", "metrika", "audience"}


@dataclass(frozen=True)
class AuthConfig:
    service: str
    profile_name: str
    mode: str
    client_id: str
    redirect_uri: str
    scope: str
    auth_root: Path
    token_path: Path
    env_path: Path
    pending_path: Path
    verifier: str
    challenge: str
    state: str
    expected_client_login: str
    expected_counter_id: str
    expected_segment_name: str


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    redirect_uri = ""
    expected_state = ""
    code = ""
    completed = False

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        expected_path = urllib.parse.urlparse(self.redirect_uri).path
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path != expected_path:
            self.send_response(404)
            self.end_headers()
            return
        if query.get("state", [""])[0] != self.expected_state:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Состояние авторизации не совпало.".encode("utf-8"))
            return
        code = query.get("code", [""])[0]
        if not code:
            self.send_response(400)
            self.end_headers()
            return
        self.__class__.code = code
        self.__class__.completed = True
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            (
                "<html><body style='font-family:Arial;padding:40px'>"
                "<h1>Код авторизации получен</h1>"
                "<p>Вернитесь в терминал. Токен и код на этой странице не отображаются.</p>"
                "</body></html>"
            ).encode("utf-8")
        )

    def log_message(self, fmt: str, *args: object) -> None:
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Авторизация Яндекс через общие приложения и PKCE.")
    parser.add_argument("--service", choices=sorted(SERVICES), required=True)
    parser.add_argument("--mode", choices=["auto", "local-callback", "manual-code"], default="auto")
    parser.add_argument("--profile", choices=["auto", "legacy_direct", "master_yandex"], default="auto")
    parser.add_argument("--auth-root", default="")
    parser.add_argument("--login-hint", default="")
    parser.add_argument("--client-login", default="")
    parser.add_argument("--counter-id", default="")
    parser.add_argument("--segment-name", default="")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--print-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    return parser


def generate_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")[:96]


def challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def load_pending(path: Path) -> dict:
    if not path.is_file():
        return {}
    require_private_file(path)
    value = load_json(path)
    return value if value.get("status") == "pending" else {}


def resolve_config(args: argparse.Namespace) -> AuthConfig:
    profile, profile_name, _ = resolve_public_profile(args.service, args.profile)
    auth_root, _ = resolve_auth_root(args.auth_root)
    pending_path = pending_session_path(auth_root, args.service)
    mode = profile.get("default_mode", "manual-code") if args.mode == "auto" else args.mode
    redirect_uri = str(profile["redirect_uri"])
    if mode == "local-callback":
        parsed = urllib.parse.urlparse(redirect_uri)
        if parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Локальный режим требует зарегистрированный localhost redirect_uri.")
        registered_port = parsed.port or 80
        if args.port != registered_port:
            raise ValueError(f"Общее приложение зарегистрировано на порту {registered_port}.")

    overlay, _ = discover_client_overlay(Path.cwd())
    expected_login = (
        args.client_login
        or os.environ.get("YANDEX_DIRECT_CLIENT_LOGIN", "")
        or overlay_direct_login(overlay)
    ).strip()
    if args.service == "direct" and not expected_login:
        raise ValueError(
            "Для Директа обязателен --client-login: укажите логин рекламодателя или клиента агентства."
        )
    expected_counter = (
        args.counter_id
        or os.environ.get("YANDEX_METRIKA_COUNTER_ID", "")
        or overlay_counter_id(overlay)
    )
    pending = load_pending(pending_path)
    can_resume = (
        pending.get("service") == args.service
        and pending.get("client_id") == profile["client_id"]
        and pending.get("redirect_uri") == redirect_uri
        and pending.get("mode") == mode
    )
    verifier = str(pending.get("code_verifier") or "") if can_resume else generate_verifier()
    state = str(pending.get("state") or "") if can_resume else secrets.token_urlsafe(32)
    return AuthConfig(
        service=args.service,
        profile_name=profile_name,
        mode=mode,
        client_id=str(profile["client_id"]),
        redirect_uri=redirect_uri,
        scope=str(profile.get("scope") or ""),
        auth_root=auth_root,
        token_path=auth_token_path(auth_root, args.service),
        env_path=auth_env_path(auth_root, args.service),
        pending_path=pending_path,
        verifier=verifier,
        challenge=challenge_for(verifier),
        state=state,
        expected_client_login=expected_login,
        expected_counter_id=expected_counter,
        expected_segment_name=args.segment_name,
    )


def authorize_url(config: AuthConfig, login_hint: str = "") -> str:
    values = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "code_challenge": config.challenge,
        "code_challenge_method": "S256",
        "state": config.state,
        "force_confirm": "yes",
    }
    if config.scope:
        values["scope"] = config.scope
    if login_hint:
        values["login_hint"] = login_hint
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(values)}"


def save_pending(config: AuthConfig, url: str) -> None:
    write_json(
        config.pending_path,
        {
            "status": "pending",
            "service": config.service,
            "profile": config.profile_name,
            "mode": config.mode,
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "code_verifier": config.verifier,
            "state": config.state,
            "authorize_url": url,
        },
    )


def read_code() -> str:
    if sys.stdin.isatty():
        value = getpass.getpass("Вставьте одноразовый код Яндекса (ввод скрыт): ")
    else:
        value = sys.stdin.readline()
    code = value.strip()
    if not code:
        raise ValueError("Одноразовый код не получен.")
    return code


def exchange_code(config: AuthConfig, code: str) -> dict:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "code_verifier": config.verifier,
    }
    response = requests.post(TOKEN_URL, data=payload, timeout=(30, None))
    try:
        result = response.json()
    except ValueError as error:
        raise RuntimeError("Яндекс OAuth вернул ответ неизвестного формата.") from error
    if response.status_code != 200 or not result.get("access_token"):
        error_name = str(result.get("error") or "oauth_exchange_failed")
        raise RuntimeError(f"Обмен кода не выполнен: {error_name}.")
    return result


def persist_token(config: AuthConfig, token: dict) -> None:
    stored = dict(token)
    stored["oauth_client_id"] = config.client_id
    stored["oauth_profile"] = config.profile_name
    write_json(config.token_path, stored)
    env_name = TOKEN_ENV_NAMES[config.service]
    write_text(config.env_path, f"export {env_name}={json.dumps(str(token['access_token']))}\n")


def run_preflight(config: AuthConfig) -> None:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "preflight_yandex_user_token.py"),
        "--service",
        config.service,
        "--auth-root",
        str(config.auth_root),
    ]
    if config.expected_client_login:
        command.extend(["--client-login", config.expected_client_login])
    if config.expected_counter_id:
        command.extend(["--counter-id", config.expected_counter_id])
    if config.expected_segment_name:
        command.extend(["--segment-name", config.expected_segment_name])
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError("Токен сохранён, но обязательное чтение службы не прошло.")


def finish(config: AuthConfig, token: dict) -> None:
    persist_token(config, token)
    config.pending_path.unlink(missing_ok=True)
    run_preflight(config)
    print(f"Авторизация {config.service} завершена; токен сохранён в защищённом файле.")
    print(f"Проверка чтением: {config.service}_oauth_preflight.json")


def run_manual(args: argparse.Namespace, config: AuthConfig, url: str) -> None:
    save_pending(config, url)
    print("Откройте страницу авторизации Яндекса:")
    print(url)
    if not args.no_browser and not (args.print_only or args.dry_run):
        webbrowser.open(url)
    if args.print_only or args.dry_run:
        print("Незавершённое состояние сохранено для продолжения.")
        return
    finish(config, exchange_code(config, read_code()))


def callback_server(config: AuthConfig) -> http.server.HTTPServer:
    parsed = urllib.parse.urlparse(config.redirect_uri)
    CallbackHandler.redirect_uri = config.redirect_uri
    CallbackHandler.expected_state = config.state
    CallbackHandler.code = ""
    CallbackHandler.completed = False
    return http.server.HTTPServer((parsed.hostname or "localhost", parsed.port or 80), CallbackHandler)


def run_local(args: argparse.Namespace, config: AuthConfig, url: str) -> None:
    save_pending(config, url)
    print("Откройте страницу авторизации Яндекса:")
    print(url)
    if args.print_only or args.dry_run:
        print("Незавершённое состояние сохранено для продолжения.")
        return
    if not args.no_browser:
        webbrowser.open(url)
    server = callback_server(config)
    print("Ожидаю обратный вызов Яндекса. Для отмены нажмите Ctrl-C.")
    try:
        while not CallbackHandler.completed:
            server.handle_request()
    finally:
        server.server_close()
    finish(config, exchange_code(config, CallbackHandler.code))


def main() -> None:
    args = build_parser().parse_args()
    config = resolve_config(args)
    url = authorize_url(config, args.login_hint)
    if config.mode == "local-callback":
        run_local(args, config, url)
    else:
        run_manual(args, config, url)


if __name__ == "__main__":
    main()
