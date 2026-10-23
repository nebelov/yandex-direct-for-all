#!/usr/bin/env python3
"""Тесты чтения Битрикс24 без сети: подменённый портал с синтетическими данными."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bitrix24_read as b24  # noqa: E402

HOOK = "https://example.bitrix24.ru/rest/1/synthetic-code/"
LEADS = [{"ID": str(i), "DATE_CREATE": "2026-10-01T10:00:00+03:00", "PHONE": [{"VALUE": "+70000000000"}],
          "UTM_SOURCE": "yandex"} for i in range(1, 121)]


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Portal:
    def __init__(self, fail_once_503: bool = False):
        self.calls: list[str] = []
        self.fail = fail_once_503

    def __call__(self, request, timeout=None):
        method = request.full_url.rsplit("/", 1)[1].removesuffix(".json")
        self.calls.append(method)
        params = json.loads(request.data or b"{}")
        if self.fail:
            self.fail = False
            raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, io.BytesIO(b'{"error":"QUERY_LIMIT_EXCEEDED"}'))
        if method == "scope":
            return Response(json.dumps({"result": ["crm", "user"]}).encode())
        if method == "crm.status.entity.types":
            return Response(json.dumps({"result": [{"ID": "STATUS"}]}).encode())
        if method == "crm.lead.list":
            after = int(params["filter"][">ID"])
            page = [dict(x) for x in LEADS if int(x["ID"]) > after][:50]
            return Response(json.dumps({"result": page}).encode())
        raise AssertionError(method)


class Bitrix24ReadTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"BITRIX24_WEBHOOK_URL": HOOK}, clear=False)
        self.env.start()
        self.sleep = mock.patch.object(b24.time, "sleep", lambda *_: None)
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()
        self.env.stop()

    def test_export_walks_all_pages_by_id_without_personal_data(self):
        portal = Portal()
        with tempfile.TemporaryDirectory() as root, mock.patch.object(b24.urllib.request, "urlopen", portal):
            b24.main(["export", "--entity", "lead", "--since", "2026-10-01", "--until", "2026-11-01", "--out", root])
            rows = json.loads(Path(root, "lead.json").read_text())
            manifest = json.loads(Path(root, "lead.manifest.json").read_text())
        self.assertEqual((len(rows), manifest["pages"], manifest["complete"]), (120, 3, True))
        self.assertNotIn("PHONE", rows[0])
        self.assertNotIn("PHONE", manifest["fields"])

    def test_write_methods_and_nested_batch_are_refused(self):
        with self.assertRaises(ValueError):
            b24.call(HOOK, "crm.lead.update", {})
        with self.assertRaises(ValueError):
            b24.call(HOOK, "batch", {"cmd": {"a": "crm.lead.delete?id=1"}})
        with self.assertRaises(ValueError):
            b24.call(HOOK, "batch", {"cmd": {"a": "batch?cmd=1"}})

    def test_probe_retries_limit_and_hides_webhook(self):
        portal = Portal(fail_once_503=True)
        out = io.StringIO()
        with mock.patch.object(b24.urllib.request, "urlopen", portal), mock.patch("sys.stdout", out):
            b24.main(["probe"])
        self.assertEqual(portal.calls[:2], ["scope", "scope"])
        self.assertNotIn("synthetic-code", out.getvalue())
        self.assertIn('"crm"', out.getvalue())

    def test_missing_webhook_is_clear_error(self):
        with mock.patch.dict(os.environ, {"BITRIX24_WEBHOOK_URL": ""}):
            with self.assertRaises(ValueError):
                b24.main(["probe"])


if __name__ == "__main__":
    unittest.main()
