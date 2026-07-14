from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import preflight_yandex_user_token as preflight  # noqa: E402
import start_yandex_user_auth as auth  # noqa: E402
import yandex_auth_common as common  # noqa: E402


class Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class YandexUserAuthTests(unittest.TestCase):
    def parse(self, *values):
        return auth.build_parser().parse_args(list(values))

    def test_public_profiles_remain_shared_and_secretless(self) -> None:
        profiles = common.load_public_profiles()
        self.assertEqual(set(profiles), {"legacy_direct", "master_yandex"})
        self.assertIn("direct", profiles["legacy_direct"]["supports"])
        self.assertIn("metrika", profiles["master_yandex"]["supports"])
        self.assertTrue(all("client_secret" not in profile for profile in profiles.values()))

    def test_sensitive_command_line_options_and_device_mode_are_absent(self) -> None:
        options = {
            option
            for action in auth.build_parser()._actions
            for option in action.option_strings
        }
        for forbidden in {
            "--client-id", "--client-secret", "--code", "--timeout",
            "--poll-interval", "--token", "--direct-token", "--skip-preflight",
        }:
            self.assertNotIn(forbidden, options)
        mode = next(action for action in auth.build_parser()._actions if "--mode" in action.option_strings)
        self.assertNotIn("device-code", mode.choices)

    def test_direct_and_metrika_defaults_use_pkce_without_secret(self) -> None:
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {}, clear=True):
            direct = auth.resolve_config(self.parse(
                "--service", "direct", "--auth-root", root, "--client-login", "example-advertiser"
            ))
            metrika = auth.resolve_config(self.parse("--service", "metrika", "--auth-root", root))
        self.assertEqual(direct.profile_name, "legacy_direct")
        self.assertEqual(direct.mode, "local-callback")
        self.assertEqual(metrika.profile_name, "master_yandex")
        self.assertEqual(metrika.mode, "manual-code")
        for config in (direct, metrika):
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(auth.authorize_url(config)).query)
            self.assertEqual(parsed["response_type"], ["code"])
            self.assertEqual(parsed["code_challenge_method"], ["S256"])
            self.assertEqual(parsed["code_challenge"], [auth.challenge_for(config.verifier)])
            self.assertNotIn("client_secret", parsed)

    def test_custom_app_is_read_only_from_protected_config(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config_path = Path(root) / "oauth.json"
            config_path.write_text(
                json.dumps({"direct": {"client_id": "custom-public-id", "redirect_uri": "http://localhost:8080/callback"}}),
                encoding="utf-8",
            )
            os.chmod(config_path, 0o600)
            with mock.patch.dict(os.environ, {"YANDEX_OAUTH_CONFIG_FILE": str(config_path)}, clear=True):
                config = auth.resolve_config(self.parse(
                    "--service", "direct", "--auth-root", root, "--client-login", "example-advertiser"
                ))
            self.assertEqual(config.profile_name, "custom")
            self.assertEqual(config.client_id, "custom-public-id")

    def test_direct_authorization_requires_explicit_client_login(self) -> None:
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "client-login"):
                auth.resolve_config(self.parse("--service", "direct", "--auth-root", root))

    def test_code_input_is_hidden_and_not_printed(self) -> None:
        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = True
        with mock.patch.object(auth.sys, "stdin", fake_stdin), mock.patch.object(
            auth.getpass, "getpass", return_value="one-time-code"
        ) as hidden, contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(auth.read_code(), "one-time-code")
        hidden.assert_called_once()
        self.assertNotIn("one-time-code", stdout.getvalue())

    def test_pending_token_env_and_preflight_files_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {}, clear=True):
            config = auth.resolve_config(self.parse("--service", "metrika", "--auth-root", root))
            auth.save_pending(config, auth.authorize_url(config))
            auth.persist_token(config, {"access_token": "synthetic-token", "token_type": "bearer"})
            common.write_json(common.preflight_path(config.auth_root, "metrika"), {"verdict": "ready"})
            self.assertEqual(config.auth_root.stat().st_mode & 0o777, 0o700)
            for path in [config.pending_path, config.token_path, config.env_path, common.preflight_path(config.auth_root, "metrika")]:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_pending_session_is_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {}, clear=True):
            first = auth.resolve_config(self.parse("--service", "metrika", "--auth-root", root))
            auth.save_pending(first, auth.authorize_url(first))
            second = auth.resolve_config(self.parse("--service", "metrika", "--auth-root", root))
        self.assertEqual(first.verifier, second.verifier)
        self.assertEqual(first.state, second.state)

    def test_finish_always_calls_preflight_and_never_prints_token(self) -> None:
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {}, clear=True):
            config = auth.resolve_config(self.parse("--service", "metrika", "--auth-root", root))
            auth.save_pending(config, auth.authorize_url(config))
            with mock.patch.object(auth, "run_preflight") as check, contextlib.redirect_stdout(io.StringIO()) as output:
                auth.finish(config, {"access_token": "synthetic-token-value"})
            check.assert_called_once_with(config)
            self.assertNotIn("synthetic-token-value", output.getvalue())

    def test_callback_page_contains_no_token_or_code_preview(self) -> None:
        source = inspect.getsource(auth.CallbackHandler.do_GET)
        self.assertNotIn("access_token", source)
        self.assertNotIn("token_preview", source)
        self.assertNotIn("Token preview", source)
        local_source = inspect.getsource(auth.run_local)
        self.assertNotIn("deadline", local_source)
        self.assertNotIn("timeout", local_source)

    def test_preflight_verifies_client_id_then_reads_metrika(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            auth_root = Path(root)
            common.ensure_private_dir(auth_root)
            profiles = common.load_public_profiles()
            expected = profiles["master_yandex"]["client_id"]
            common.write_json(
                common.auth_token_path(auth_root, "metrika"),
                {"access_token": "synthetic-token", "oauth_client_id": expected},
            )
            args = preflight.build_parser().parse_args(["--service", "metrika", "--auth-root", root])
            with mock.patch.object(
                preflight.requests,
                "get",
                side_effect=[
                    Response(200, {"client_id": expected, "login": "must-not-be-saved"}),
                    Response(200, {"counters": [{"id": 1, "name": "Пример"}]}),
                ],
            ):
                result, output = preflight.run_check(args)
            self.assertEqual(result["verdict"], "ready")
            self.assertTrue(result["oauth_client_id_matches"])
            saved = output.read_text(encoding="utf-8")
            self.assertNotIn("must-not-be-saved", saved)
            self.assertNotIn("Пример", saved)
            self.assertNotIn("synthetic-token", saved)
            self.assertNotIn(expected, saved)

    def test_direct_preflight_rejects_missing_client_login_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            auth_root = Path(root)
            common.ensure_private_dir(auth_root)
            common.write_json(
                common.auth_token_path(auth_root, "direct"),
                {"access_token": "synthetic-token", "oauth_client_id": "expected-app"},
            )
            args = preflight.build_parser().parse_args(["--service", "direct", "--auth-root", root])
            with mock.patch.object(preflight.requests, "get") as identity_call, mock.patch.object(
                preflight.requests, "post"
            ) as service_call:
                with self.assertRaisesRegex(ValueError, "client-login"):
                    preflight.run_check(args)
            identity_call.assert_not_called()
            service_call.assert_not_called()

    def test_direct_agency_preflight_sends_client_login(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            auth_root = Path(root)
            common.ensure_private_dir(auth_root)
            common.write_json(
                common.auth_token_path(auth_root, "direct"),
                {"access_token": "synthetic-token", "oauth_client_id": "expected-app"},
            )
            args = preflight.build_parser().parse_args([
                "--service", "direct", "--auth-root", root, "--client-login", "example-client"
            ])
            with mock.patch.object(
                preflight.requests, "get", return_value=Response(200, {"client_id": "expected-app"})
            ), mock.patch.object(
                preflight.requests,
                "post",
                return_value=Response(200, {"result": {"Campaigns": []}}),
            ) as service_call:
                result, _ = preflight.run_check(args)
            self.assertEqual(result["direct_scope"], "explicit_client")
            self.assertEqual(service_call.call_args.kwargs["headers"]["Client-Login"], "example-client")

    def test_client_id_mismatch_blocks_service_read(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            auth_root = Path(root)
            common.ensure_private_dir(auth_root)
            common.write_json(
                common.auth_token_path(auth_root, "direct"),
                {"access_token": "synthetic-token", "oauth_client_id": "expected-app"},
            )
            args = preflight.build_parser().parse_args([
                "--service", "direct", "--auth-root", root, "--client-login", "example-client"
            ])
            with mock.patch.object(preflight.requests, "get", return_value=Response(200, {"client_id": "other-app"})), mock.patch.object(
                preflight.requests, "post"
            ) as service_call:
                result, _ = preflight.run_check(args)
            self.assertEqual(result["verdict"], "error")
            service_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
