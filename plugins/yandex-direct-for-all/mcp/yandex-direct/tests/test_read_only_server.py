from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("yandex_direct_read_only", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)

OPS_SCRIPTS = SERVER_PATH.parents[2] / "skills" / "yandex-performance-ops" / "scripts"
sys.path.insert(0, str(OPS_SCRIPTS))
import check_access_paths as access_layer  # noqa: E402
import client_context  # noqa: E402
import init_client_context  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, *, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._payload


class ReadOnlyServerTests(unittest.TestCase):
    def runtime(self, root: str, environment: str = "sandbox") -> dict[str, str]:
        values = {
            "YANDEX_DIRECT_ENVIRONMENT": environment,
            "YANDEX_DIRECT_CLIENT_LOGIN": "example-client",
            "YANDEX_DIRECT_OUTPUT_DIR": root,
            "YANDEX_DIRECT_SANDBOX_TOKEN": "synthetic-sandbox-token",
            "YANDEX_DIRECT_PRODUCTION_READ_TOKEN": "synthetic-production-token",
        }
        return values

    def test_rejects_unknown_routes_before_network(self) -> None:
        calls = []

        async def request(*args):
            calls.append(args)
            raise AssertionError("network must not be called")

        async def run():
            with tempfile.TemporaryDirectory() as root, mock.patch.dict(
                os.environ, self.runtime(root), clear=True
            ):
                for route in [
                    ("campaigns", "add", "v5"),
                    ("campaigns", "get", "v4"),
                    ("clients", "get", "v5"),
                    ("reports", "update", "v5"),
                ]:
                    with self.assertRaises(ValueError):
                        await server.execute_read(*route[:2], {}, route[2], request=request)

        asyncio.run(run())
        self.assertEqual(calls, [])
        self.assertNotIn("token", inspect.signature(server.yd_api).parameters)

    def test_nine_ordinary_services_use_exact_get_contract(self) -> None:
        seen = []

        async def request(url, headers, body):
            seen.append((url, headers, body))
            return FakeResponse(200, payload={"result": {"ok": True}})

        async def run():
            with tempfile.TemporaryDirectory() as root, mock.patch.dict(
                os.environ, self.runtime(root), clear=True
            ):
                for service in sorted(server.ORDINARY_SERVICES):
                    result = await server.execute_read(
                        service, "get", {"SelectionCriteria": {}}, "v501", request=request
                    )
                    self.assertEqual(result["status"], "ready")

        asyncio.run(run())
        self.assertEqual(len(seen), 9)
        for url, headers, body in seen:
            self.assertTrue(url.startswith("https://api-sandbox.direct.yandex.com/json/v501/"))
            self.assertEqual(json.loads(body), {"method": "get", "params": {"SelectionCriteria": {}}})
            self.assertEqual(headers["Client-Login"], "example-client")
            self.assertNotIn("synthetic-sandbox-token", json.dumps(json.loads(body)))

    def test_reports_preserve_body_across_queue_and_ready(self) -> None:
        bodies = []
        sleeps = []
        states = []
        responses = [
            FakeResponse(201, headers={"RequestId": "request-a", "retryIn": "0", "reportsInQueue": "2"}),
            FakeResponse(202, headers={"RequestId": "request-a", "retryIn": "0", "reportsInQueue": "1"}),
            FakeResponse(200, content=b"Name\tClicks\nExample\t1\n", headers={"RequestId": "request-a"}),
        ]

        async def request(url, headers, body):
            self.assertTrue(url.endswith("/json/v5/reports"))
            self.assertEqual(headers["processingMode"], "auto")
            self.assertEqual(headers["Accept-Language"], "ru")
            self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
            self.assertEqual(headers["Client-Login"], "example-client")
            self.assertEqual(headers["returnMoneyInMicros"], "false")
            self.assertEqual(headers["skipReportHeader"], "true")
            self.assertEqual(headers["skipColumnHeader"], "false")
            self.assertEqual(headers["skipReportSummary"], "true")
            bodies.append(body)
            return responses.pop(0)

        async def sleeper(seconds):
            sleeps.append(seconds)
            state_files = list(Path(os.environ["YANDEX_DIRECT_OUTPUT_DIR"]).glob("*.state.json"))
            states.append(json.loads(state_files[0].read_text(encoding="utf-8")))

        async def run():
            with tempfile.TemporaryDirectory() as root, mock.patch.dict(
                os.environ, self.runtime(root), clear=True
            ):
                result = await server.execute_read(
                    "reports",
                    "get",
                    {"FieldNames": ["CampaignName", "Clicks"]},
                    request=request,
                    sleeper=sleeper,
                )
                self.assertEqual(result["status"], "ready")
                artifact = Path(result["artifact_path"])
                self.assertEqual(artifact.read_bytes(), b"Name\tClicks\nExample\t1\n")
                self.assertEqual(result["bytes"], artifact.stat().st_size)
                self.assertEqual(result["artifact_sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
                self.assertEqual(oct(artifact.stat().st_mode & 0o777), "0o600")
                self.assertEqual(oct(artifact.parent.stat().st_mode & 0o777), "0o700")

        asyncio.run(run())
        self.assertEqual([item["status"] for item in states], ["queued", "pending"])
        self.assertEqual([item["request_id"] for item in states], ["request-a", "request-a"])
        self.assertEqual([item["reports_in_queue"] for item in states], ["2", "1"])
        self.assertEqual(states[0]["request_sha256"], states[1]["request_sha256"])
        self.assertEqual(sleeps, [0.0, 0.0])
        self.assertEqual(bodies[0], bodies[1])
        self.assertEqual(bodies[1], bodies[2])
        self.assertEqual(json.loads(bodies[0]), {"params": {"FieldNames": ["CampaignName", "Clicks"]}})

    def test_reports_reject_empty_success_without_retrying(self) -> None:
        calls = []

        async def request(_url, _headers, _body):
            calls.append(True)
            return FakeResponse(200, content=b"", headers={"RequestId": "request-empty"})

        async def run():
            with tempfile.TemporaryDirectory() as root, mock.patch.dict(
                os.environ, self.runtime(root), clear=True
            ):
                result = await server.execute_read(
                    "reports", "get", {"ReportName": "empty"}, request=request
                )
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error"], "empty_report")
                saved = json.loads(next(Path(root).glob("*.state.json")).read_text(encoding="utf-8"))
                self.assertEqual(saved["status"], "error")

        asyncio.run(run())
        self.assertEqual(len(calls), 1)

        with tempfile.TemporaryDirectory() as root:
            helper_calls = []

            def requester(_url, _headers, _body):
                helper_calls.append(True)
                return 200, b"", {"RequestId": "helper-empty"}

            helper_result = access_layer.fetch_direct_report(
                access_layer.DirectAccess("token", "example-client", "sandbox"),
                {"ReportName": "empty"},
                Path(root),
                requester=requester,
                sleeper=lambda _seconds: self.fail("empty HTTP 200 must not be retried"),
            )
            self.assertEqual(helper_result["status"], "error")
            self.assertEqual(helper_result["error"], "empty_report")
            self.assertEqual(len(helper_calls), 1)

    def test_environment_tokens_are_not_interchangeable(self) -> None:
        async def request(url, headers, body):
            return FakeResponse(200, payload={"result": {}})

        async def run():
            with tempfile.TemporaryDirectory() as root:
                sandbox_only = self.runtime(root)
                sandbox_only.pop("YANDEX_DIRECT_SANDBOX_TOKEN")
                with mock.patch.dict(os.environ, sandbox_only, clear=True):
                    with self.assertRaises(ValueError):
                        await server.execute_read("campaigns", "get", {}, request=request)

                production_only = self.runtime(root, "production")
                production_only.pop("YANDEX_DIRECT_PRODUCTION_READ_TOKEN")
                with mock.patch.dict(os.environ, production_only, clear=True):
                    with self.assertRaises(ValueError):
                        await server.execute_read("campaigns", "get", {}, request=request)

                missing_scope = self.runtime(root)
                missing_scope.pop("YANDEX_DIRECT_CLIENT_LOGIN")
                calls = []

                async def owner_request(*args):
                    calls.append(args)
                    raise AssertionError("network must not be called without client scope")

                with mock.patch.dict(os.environ, missing_scope, clear=True), self.assertRaisesRegex(
                    ValueError, "явной области клиента"
                ):
                    await server.execute_read("campaigns", "get", {}, request=owner_request)
                self.assertEqual(calls, [])

                with self.assertRaisesRegex(access_layer.AccessError, "явной области клиента"):
                    access_layer.direct_api_get(
                        access_layer.DirectAccess("token", "", "sandbox"), "campaigns", {}
                    )

        asyncio.run(run())

    def test_errors_do_not_echo_tokens_or_home_paths(self) -> None:
        async def request(url, headers, body):
            raise RuntimeError(f"failed with {headers['Authorization']} at /Users/example/private")

        async def run():
            with tempfile.TemporaryDirectory() as root, mock.patch.dict(
                os.environ, self.runtime(root), clear=True
            ):
                result = await server.execute_read("campaigns", "get", {}, request=request)
                rendered = json.dumps(result)
                self.assertNotIn("synthetic-sandbox-token", rendered)
                self.assertNotIn("/Users/", rendered)
                self.assertEqual(result["error_type"], "RuntimeError")

        asyncio.run(run())

    def test_pagination_empty_repeat_partial_and_complete(self) -> None:
        access = access_layer.DirectAccess("secret-token", "example-client", "sandbox")

        empty = access_layer.fetch_direct_pages(
            access,
            "campaigns",
            {},
            "Campaigns",
            requester=lambda *_: {"result": {"Campaigns": []}},
        )
        self.assertTrue(empty.manifest.complete)
        self.assertEqual((empty.manifest.pages, empty.manifest.objects), (1, 0))

        repeated_responses = iter([
            {"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 1}},
            {"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 2}},
        ])
        repeated = access_layer.fetch_direct_pages(
            access, "campaigns", {}, "Campaigns", requester=lambda *_: next(repeated_responses)
        )
        self.assertFalse(repeated.manifest.complete)
        self.assertEqual((repeated.manifest.pages, repeated.manifest.objects), (1, 1))
        self.assertIn("повтор", repeated.manifest.error)

        partial_calls = 0

        def partial_request(*_):
            nonlocal partial_calls
            partial_calls += 1
            if partial_calls == 1:
                return {"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 1}}
            raise RuntimeError("secret-token /Users/example/private")

        partial = access_layer.fetch_direct_pages(
            access, "campaigns", {}, "Campaigns", requester=partial_request
        )
        self.assertFalse(partial.manifest.complete)
        self.assertEqual((partial.manifest.pages, partial.manifest.objects), (1, 1))
        self.assertNotIn("secret-token", partial.manifest.error)
        self.assertNotIn("/Users/", partial.manifest.error)

        complete_responses = iter([
            {"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 1}},
            {"result": {"Campaigns": [{"Id": 2}]}},
        ])
        complete = access_layer.fetch_direct_pages(
            access, "campaigns", {}, "Campaigns", requester=lambda *_: next(complete_responses)
        )
        self.assertTrue(complete.manifest.complete)
        self.assertEqual((complete.manifest.pages, complete.manifest.objects), (2, 2))
        self.assertEqual(len(complete.manifest.checksum), 64)

    def test_client_context_priority_and_private_initializer(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            default = root_path / ".codex" / "yandex-performance-client.json"
            environment = root_path / "environment.json"
            explicit = root_path / "explicit.json"
            default.parent.mkdir()
            default.write_text('{"client_key":"default"}', encoding="utf-8")
            environment.write_text('{"client_key":"environment"}', encoding="utf-8")
            explicit.write_text('{"client_key":"explicit"}', encoding="utf-8")
            with mock.patch.object(client_context.Path, "cwd", return_value=root_path), mock.patch.dict(
                os.environ, {"YANDEX_PERFORMANCE_CLIENT_CONTEXT": str(environment)}, clear=True
            ):
                loaded = client_context.load_client_context(str(explicit), required=True)
            self.assertEqual(loaded["client_key"], "explicit")
            self.assertEqual(loaded["_context_source"], "local-protected-file")
            self.assertNotIn(str(root_path), json.dumps(loaded))

            output = root_path / "private" / "context.json"
            with mock.patch.object(sys, "argv", ["init_client_context.py", "--output", str(output)]), mock.patch(
                "builtins.print"
            ) as printed:
                init_client_context.main()
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(output.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn(str(root_path), " ".join(str(arg) for call in printed.call_args_list for arg in call.args))


if __name__ == "__main__":
    unittest.main()
