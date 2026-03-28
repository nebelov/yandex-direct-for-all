#!/usr/bin/env python3
"""Generic OAuth helper for Yandex APIs."""

from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests


AUTHORIZE_URL = "https://oauth.yandex.com/authorize"
TOKEN_URL = "https://oauth.yandex.com/token"
SCREEN_CODE_REDIRECT_URI = "https://oauth.yandex.com/verification_code"
LOCAL_HOSTS = {"localhost", "127.0.0.1"}

auth_code = None
token_result = None


def write_token_output(token: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(token, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def exchange_code_for_token(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    device_id: str = "",
    device_name: str = "",
    code_verifier: str = "",
) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        data["client_secret"] = client_secret
    if device_id:
        data["device_id"] = device_id
    if device_name:
        data["device_name"] = device_name
    if code_verifier:
        data["code_verifier"] = code_verifier

    resp = requests.post(TOKEN_URL, data=data, timeout=60)
    try:
        return resp.json()
    except ValueError:
        return {
            "status_code": resp.status_code,
            "text": resp.text,
        }


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    client_id = ""
    client_secret = ""
    redirect_uri = ""
    redirect_path = "/callback"
    device_id = ""
    device_name = ""
    code_verifier = ""
    output_path = Path("oauth_token.json")

    def do_GET(self):
        global auth_code, token_result
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path != self.redirect_path or "code" not in params:
            self.send_response(404)
            self.end_headers()
            return

        auth_code = params["code"][0]
        token_result = exchange_code_for_token(
            code=auth_code,
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            device_id=self.device_id,
            device_name=self.device_name,
            code_verifier=self.code_verifier,
        )

        status = 200 if "access_token" in token_result else 400
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if status == 200:
            write_token_output(token_result, self.output_path)
            token = token_result["access_token"]
            body = (
                "<html><body style='font-family:Arial;text-align:center;padding:50px'>"
                "<h1 style='color:green'>Токен получен</h1>"
                f"<p><code>{token[:30]}...</code></p>"
                f"<p>Сохранено в: {self.output_path}</p>"
                "</body></html>"
            )
        else:
            body = (
                "<html><body style='font-family:Arial;text-align:center;padding:50px'>"
                "<h1 style='color:red'>Ошибка OAuth</h1>"
                f"<pre>{json.dumps(token_result, ensure_ascii=False, indent=2)}</pre>"
                "</body></html>"
            )

        self.wfile.write(body.encode("utf-8"))
        threading.Timer(1.0, lambda: sys.exit(0)).start()

    def log_message(self, format, *args):
        pass


def build_auth_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str = "",
    device_id: str = "",
    device_name: str = "",
    login_hint: str = "",
    force_confirm: bool = False,
    state: str = "",
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    if scope:
        params["scope"] = scope
    if device_id:
        params["device_id"] = device_id
    if device_name:
        params["device_name"] = device_name
    if login_hint:
        params["login_hint"] = login_hint
    if force_confirm:
        params["force_confirm"] = "yes"
    if state:
        params["state"] = state
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def require_exchange_credentials(client_id: str, client_secret: str, code_verifier: str) -> None:
    if client_id and (client_secret or code_verifier):
        return
    raise SystemExit(
        "Token exchange requires --client-id and either --client-secret or --code-verifier."
    )


def run_manual_flow(
    *,
    auth_url: str,
    open_browser: bool,
    prompt_for_code: bool,
    output_path: Path,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    device_id: str,
    device_name: str,
    code_verifier: str,
) -> None:
    print(f"Redirect URI: {redirect_uri}")
    print(f"Output: {output_path}")
    print(f"Auth URL: {auth_url}")

    if open_browser:
        webbrowser.open(auth_url)

    if not prompt_for_code:
        return
    if not sys.stdin.isatty():
        raise SystemExit(
            "Manual code entry requires an interactive terminal. Re-run with --print-auth-url or pass --code."
        )

    require_exchange_credentials(client_id, client_secret, code_verifier)
    code = input("Enter confirmation code: ").strip()
    if not code:
        raise SystemExit("Confirmation code is empty.")

    token = exchange_code_for_token(
        code=code,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        device_id=device_id,
        device_name=device_name,
        code_verifier=code_verifier,
    )
    write_token_output(token, output_path)
    if "access_token" in token:
        print(output_path)
        return
    raise SystemExit("Code exchange did not produce access_token.")


def run_local_callback_flow(
    *,
    auth_url: str,
    open_browser: bool,
    output_path: Path,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    device_id: str,
    device_name: str,
    code_verifier: str,
) -> None:
    global auth_code, token_result
    auth_code = None
    token_result = None

    require_exchange_credentials(client_id, client_secret, code_verifier)
    parsed = urllib.parse.urlparse(redirect_uri)

    OAuthHandler.client_id = client_id
    OAuthHandler.client_secret = client_secret
    OAuthHandler.redirect_uri = redirect_uri
    OAuthHandler.redirect_path = parsed.path or "/"
    OAuthHandler.device_id = device_id
    OAuthHandler.device_name = device_name
    OAuthHandler.code_verifier = code_verifier
    OAuthHandler.output_path = output_path

    server = http.server.HTTPServer((parsed.hostname, parsed.port), OAuthHandler)

    print(f"Redirect URI: {redirect_uri}")
    print(f"Output: {output_path}")
    print(f"Auth URL: {auth_url}")

    if open_browser:
        webbrowser.open(auth_url)

    server.timeout = 300
    try:
        while auth_code is None:
            server.handle_request()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        server.server_close()

    if token_result and "access_token" in token_result:
        print(output_path)
        return
    raise SystemExit("OAuth flow did not produce access_token.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", default="", help="OAuth application client_id")
    parser.add_argument("--client-secret", default="", help="OAuth application client_secret")
    parser.add_argument("--redirect-uri", default="http://localhost:8080/callback")
    parser.add_argument("--scope", default="")
    parser.add_argument("--code", default="", help="Already obtained confirmation code for token exchange")
    parser.add_argument("--code-verifier", default="", help="PKCE code_verifier, if used")
    parser.add_argument("--device-id", default="", help="Optional device_id for screen-code flow")
    parser.add_argument("--device-name", default="", help="Optional device_name for screen-code flow")
    parser.add_argument("--login-hint", default="")
    parser.add_argument("--state", default="")
    parser.add_argument("--output", default="oauth_token.json")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--print-auth-url", action="store_true")
    parser.add_argument("--prompt-for-code", action="store_true")
    parser.add_argument("--force-confirm", action="store_true")
    args = parser.parse_args()

    client_id = args.client_id or os.environ.get("YANDEX_OAUTH_CLIENT_ID", "")
    client_secret = args.client_secret or os.environ.get("YANDEX_OAUTH_CLIENT_SECRET", "")
    redirect_uri = args.redirect_uri
    output_path = Path(args.output).expanduser().resolve()

    if not client_id:
        raise SystemExit(
            "Missing OAuth client_id. Pass --client-id or set YANDEX_OAUTH_CLIENT_ID."
        )

    auth_url = build_auth_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=args.scope,
        device_id=args.device_id,
        device_name=args.device_name,
        login_hint=args.login_hint,
        force_confirm=args.force_confirm,
        state=args.state,
    )

    if args.print_auth_url:
        print(f"Redirect URI: {redirect_uri}")
        print(f"Output: {output_path}")
        print(f"Auth URL: {auth_url}")
        if args.open_browser:
            webbrowser.open(auth_url)
        return

    if args.code:
        require_exchange_credentials(client_id, client_secret, args.code_verifier)
        token = exchange_code_for_token(
            code=args.code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            device_id=args.device_id,
            device_name=args.device_name,
            code_verifier=args.code_verifier,
        )
        write_token_output(token, output_path)
        if "access_token" in token:
            print(output_path)
            return
        raise SystemExit("Code exchange did not produce access_token.")

    parsed = urllib.parse.urlparse(redirect_uri)
    is_local_callback = parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS and bool(parsed.port)
    is_screen_code = redirect_uri == SCREEN_CODE_REDIRECT_URI

    if is_local_callback and not args.prompt_for_code:
        run_local_callback_flow(
            auth_url=auth_url,
            open_browser=args.open_browser,
            output_path=output_path,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            device_id=args.device_id,
            device_name=args.device_name,
            code_verifier=args.code_verifier,
        )
        return

    if is_screen_code or args.prompt_for_code:
        run_manual_flow(
            auth_url=auth_url,
            open_browser=args.open_browser,
            prompt_for_code=args.prompt_for_code,
            output_path=output_path,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            device_id=args.device_id,
            device_name=args.device_name,
            code_verifier=args.code_verifier,
        )
        return

    raise SystemExit(
        "Without --code, use either a localhost redirect (for callback flow), "
        f"the screen-code redirect {SCREEN_CODE_REDIRECT_URI}, or pass --prompt-for-code."
    )


if __name__ == "__main__":
    main()
