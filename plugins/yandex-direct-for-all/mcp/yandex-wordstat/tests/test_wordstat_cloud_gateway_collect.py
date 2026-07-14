from __future__ import annotations

import importlib.util
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import httpx


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wordstat_cloud_gateway_collect.py"
SPEC = importlib.util.spec_from_file_location("wordstat_cloud_gateway_collect", SCRIPT)
assert SPEC and SPEC.loader
cloud = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cloud)


class FakePacer:
    def __init__(self) -> None:
        self.billed: list[bool] = []
        self.deferred: list[float] = []

    def before_request(self, billed: bool = True) -> None:
        self.billed.append(billed)

    def defer(self, seconds: float) -> None:
        self.deferred.append(seconds)


class CollectorTests(unittest.TestCase):
    def test_wordstat_operators_are_preserved(self) -> None:
        samples = [
            "-бесплатно",
            "+для",
            "!купить",
            '"точная фраза"',
            "[фиксированный порядок]",
            "(вариант|другой)",
        ]
        self.assertEqual([cloud.normalize_mask(item) for item in samples], samples)

    def test_current_response_schemas(self) -> None:
        cloud.validate_top_response(
            {"totalCount": "1", "results": [{"phrase": "пример услуги", "count": "1"}], "associations": []}
        )
        cloud.validate_dynamics_response(
            {"results": [{"date": "2026-06-01T00:00:00Z", "count": "1", "share": 0.1}]}
        )
        cloud.validate_regions_response(
            {"results": [{"region": "225", "count": "1", "share": 0.1, "affinityIndex": 1.0}]}
        )
        cloud.validate_regions_tree_response(
            {"regions": [{"id": "225", "label": "Россия", "children": []}]}
        )

    def test_retry_after_continues_and_records_billed_call(self) -> None:
        responses = [
            httpx.Response(429, headers={"Retry-After": "1"}, json={"message": "quota"}),
            httpx.Response(200, json={"totalCount": "1", "results": [], "associations": []}),
        ]
        pacer = FakePacer()
        with mock.patch.object(cloud.httpx, "post", side_effect=responses):
            result = cloud.request_cloud(
                "not-a-real-key",
                "/v2/wordstat/topRequests",
                {"phrase": "пример"},
                cloud.validate_top_response,
                pacer,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(pacer.billed, [True, True])
        self.assertEqual(pacer.deferred, [1.0])

    def test_regions_tree_has_zero_billed_cost(self) -> None:
        pacer = FakePacer()
        with mock.patch.object(
            cloud.httpx,
            "post",
            return_value=httpx.Response(200, json={"regions": []}),
        ):
            result = cloud.request_cloud(
                "not-a-real-key",
                "/v2/wordstat/getRegionsTree",
                {},
                cloud.validate_regions_tree_response,
                pacer,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(pacer.billed, [False])

    def test_regions_tree_still_consumes_total_hourly_request_quota(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "limits.json"
            pacer = cloud.QuotaPacer(state_path)
            state_path.write_text(
                json.dumps({
                    "version": 2,
                    "requests": [
                        {"at": 900_000.0, "endpoint": "test", "billed": False, "costUnits": 0}
                        for _ in range(100)
                    ],
                    "nextAllowedAt": 0,
                }),
                encoding="utf-8",
            )
            os.chmod(state_path, 0o600)
            with mock.patch.object(cloud.time, "time", side_effect=[1000.0, 4501.0]), mock.patch.object(
                cloud.time, "sleep"
            ) as sleeper:
                pacer.before_request(billed=False)
            sleeper.assert_called_once_with(3500.0)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["requests"]), 1)
            self.assertFalse(saved["requests"][0]["billed"])
            lock_path = state_path.with_suffix(".json.lock")
            self.assertTrue(lock_path.exists())
            self.assertEqual(lock_path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_quota_state_fails_closed_without_replacing_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "limits.json"
            original = b"{not-json\n"
            state_path.write_bytes(original)
            os.chmod(state_path, 0o600)
            pacer = cloud.QuotaPacer(state_path)
            with mock.patch.object(cloud.time, "sleep") as sleeper, self.assertRaisesRegex(
                RuntimeError, "Состояние квоты Wordstat повреждено"
            ):
                pacer.before_request(billed=False)
            sleeper.assert_not_called()
            self.assertEqual(state_path.read_bytes(), original)

    def test_wrong_shape_quota_state_fails_closed_without_replacing_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "limits.json"
            original = b'{"requestTimes": [], "billedTimes": [], "nextAllowedAt": 0}\n'
            state_path.write_bytes(original)
            os.chmod(state_path, 0o600)
            pacer = cloud.QuotaPacer(state_path)
            with self.assertRaisesRegex(RuntimeError, "Состояние квоты Wordstat повреждено"):
                pacer.before_request(billed=False)
            self.assertEqual(state_path.read_bytes(), original)
            self.assertTrue(state_path.with_suffix(".json.lock").exists())

    def test_non_finite_quota_values_fail_closed_without_replacing_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "limits.json"
            payloads = [
                {"version": 2, "requests": [], "nextAllowedAt": float("nan")},
                {"version": 2, "requests": [], "nextAllowedAt": float("inf")},
                {"version": 2, "requests": [{"at": float("nan"), "endpoint": "x", "billed": True, "costUnits": 1}], "nextAllowedAt": 0},
                {"version": 2, "requests": [{"at": 1, "endpoint": "x", "billed": True, "costUnits": float("inf")}], "nextAllowedAt": 0},
            ]
            for payload in payloads:
                original = json.dumps(payload).encode("utf-8")
                state_path.write_bytes(original)
                os.chmod(state_path, 0o600)
                with self.assertRaisesRegex(RuntimeError, "Состояние квоты Wordstat повреждено"):
                    cloud.QuotaPacer(state_path).before_request(billed=False)
                self.assertEqual(state_path.read_bytes(), original)

    def test_node_waits_for_python_advisory_lock_and_then_uses_shared_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "limits.json"
            lock_path = state_path.with_suffix(".json.lock")
            started_path = root / "node-started"
            done_path = root / "node-done"
            convert_uri = (SCRIPT.parents[1] / "src" / "convert.mjs").as_uri()
            code = f"""
                import {{ writeFile }} from 'node:fs/promises';
                import {{ WordstatUsageLedger }} from {json.dumps(convert_uri)};
                await writeFile({json.dumps(str(started_path))}, 'started');
                const ledger = new WordstatUsageLedger({{ statePath: {json.dumps(str(state_path))}, now: () => 500000 }});
                await ledger.reserve({{ endpoint: 'node-cross-runtime', billed: true }});
                await writeFile({json.dumps(str(done_path))}, 'done');
            """
            lock_path.touch(mode=0o600)
            with lock_path.open("r+b") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                process = subprocess.Popen(
                    ["node", "--input-type=module", "--eval", code],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                while not started_path.exists():
                    if process.poll() is not None:
                        stdout, stderr = process.communicate()
                        self.fail(f"Node завершился до попытки блокировки: {stdout} {stderr}")
                    time.sleep(0.01)
                time.sleep(0.1)
                self.assertFalse(done_path.exists())
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            stdout, stderr = process.communicate()
            self.assertEqual(process.returncode, 0, f"{stdout}\n{stderr}")
            self.assertTrue(done_path.exists())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["requests"][0]["endpoint"], "node-cross-runtime")

    def test_full_run_and_resume_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            masks = root / "masks.tsv"
            source_mask = '  "пример  услуги"  '
            masks.write_text(f"mask\tintent\n{source_mask}\tcommercial\n", encoding="utf-8")
            config = root / "credentials.json"
            config.write_text(
                json.dumps(
                    {
                        "api_key": "not-a-real-key",
                        "folder_id": "folder-example",
                        "quota_state_path": str(root / "limits.json"),
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(config, 0o600)
            output = root / "output"
            requests: list[str] = []

            def response_for(url: str, **kwargs):
                requests.append(url.rsplit("/", 1)[-1])
                if url.endswith("/getRegionsTree"):
                    return httpx.Response(200, json={"regions": []})
                if url.endswith("/topRequests"):
                    self.assertEqual(kwargs["json"]["phrase"], source_mask)
                    return httpx.Response(
                        200,
                        json={"totalCount": "1", "results": [{"phrase": "пример услуги", "count": "1"}], "associations": []},
                    )
                if url.endswith("/regions"):
                    return httpx.Response(
                        200,
                        json={"results": [{"region": "225", "count": "1", "share": 0.1, "affinityIndex": 1.0}]},
                    )
                if url.endswith("/dynamics"):
                    return httpx.Response(
                        200,
                        json={"results": [{"date": "2026-06-01T00:00:00Z", "count": "1", "share": 0.1}]},
                    )
                raise AssertionError(url)

            argv = [
                "collector",
                "--masks-file", str(masks),
                "--output-dir", str(output),
                "--config", str(config),
                "--dynamics",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                cloud.httpx, "post", side_effect=response_for
            ):
                self.assertEqual(cloud.main(), 0)
            self.assertEqual(requests, ["getRegionsTree", "topRequests", "regions", "dynamics"])
            manifest = json.loads((output / "raw_bundle/_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest), 4)
            mask_entries = [item for item in manifest if item["artifact"] != "regions_tree"]
            self.assertTrue(all(item["source_mask"] == source_mask for item in mask_entries))
            self.assertTrue(all(item["normalized_label"] == "пример_услуги" for item in mask_entries))

            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                cloud.httpx, "post", side_effect=AssertionError("resume must not request again")
            ):
                self.assertEqual(cloud.main(), 0)
            resumed = json.loads((output / "raw_bundle/_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(resumed), 4)


if __name__ == "__main__":
    unittest.main()
