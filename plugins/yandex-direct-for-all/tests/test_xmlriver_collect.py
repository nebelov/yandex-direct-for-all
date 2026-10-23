#!/usr/bin/env python3
"""Тесты сборщика XMLRiver без сети: синтетические ответы, транспорт подменён."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "xmlriver-serp-research" / "scripts" / "xmlriver_collect.py"
SPEC = importlib.util.spec_from_file_location("xmlriver_collect", SCRIPT)
xc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xc)

SECRET = "not-a-real-key"
JOBS = ("job_id\tsearch_query\tregion_id\tpage\n"
        "j1\tкупить стол\t213\t0\n"
        "j2\tкупить стул\t225\t0\n")
INFO = {"cost": {"yandex": 25, "google": 25, "wordstat": 25}, "balance": 100,
        "threads": {"yandex": 10, "google": 10, "wordstat": 10}, "engine": {"yandex": 1, "google": 1, "wordstat": 1}}


def serp_xml(query: str, urls: list[str], ads: int = 0, echo_key: bool = False) -> bytes:
    docs = "".join(f"<group><doc><url>https://{u}/</url><title>{u}</title><passages><passage>t</passage>"
                   f"</passages></doc></group>" for u in urls)
    adv = "".join(f"<query><url>ad{i}.example</url><title>%3Cb%3EСтол%3C/b%3E</title><snippet>s</snippet></query>"
                  for i in range(ads))
    extra = f"<debug>{SECRET}</debug>" if echo_key else ""
    return (f"<yandexsearch><request><query>{query}</query></request><response date='x'>"
            f"<results><grouping>{docs}</grouping></results><topads>{adv}</topads>{extra}</response>"
            f"</yandexsearch>").encode()


def error_xml(code: str) -> bytes:
    return f"<yandexsearch><response><error code='{code}'>err</error></response></yandexsearch>".encode()


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Transport:
    """Подменяет urlopen: get_info отдаёт INFO, сбор — заранее заданные ответы по запросу."""

    def __init__(self, answers: dict[str, list]):
        self.answers = answers
        self.calls: list[str] = []

    def __call__(self, url, timeout=None):
        if "get_info" in url:
            return FakeResponse(json.dumps(INFO).encode())
        self.calls.append(url)
        query = xc.urllib.parse.parse_qs(xc.urllib.parse.urlparse(url).query)["query"][0]
        answer = self.answers[query].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)


class XmlriverCollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "jobs.tsv").write_text(JOBS, encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"XMLRIVER_USER": "1", "XMLRIVER_KEY": SECRET}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cmd(self, *args: str) -> tuple[int, dict | str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = xc.main(list(args))
        text = out.getvalue()
        last = text[text.rfind("\n{") + 1:] if "\n{" in text else text
        try:
            return code, json.loads(last)
        except ValueError:
            return code, text

    def serp_args(self, *extra: str) -> list[str]:
        return ["--kind", "serp", "--jobs-file", str(self.root / "jobs.tsv"), "--output-dir", str(self.root / "run"),
                "--workers", "1", *extra]

    def plan(self, *extra: str) -> str:
        return self.run_cmd("plan", *self.serp_args(*extra))[1]["plan_sha256"]

    def test_help_runs_isolated_without_network(self):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("collect", result.stdout)

    def test_plan_is_stable_and_changes_with_parameters(self):
        self.assertEqual(self.plan(), self.plan())
        self.assertNotEqual(self.plan(), self.plan("--ads", "on"))
        self.assertNotEqual(self.plan(), self.plan("--device", "mobile"))

    def test_params_explicit_ai_zero_and_google_page_plus_one(self):
        args = xc.build_parser().parse_args(["plan", *self.serp_args("--engine", "both")])
        jobs = xc.serp_jobs(args)
        google = [j for j in jobs if j["engine"] == "google"][0]["params"]
        yandex = [j for j in jobs if j["engine"] == "yandex"][0]["params"]
        self.assertEqual(google["page"], 1)
        self.assertEqual((yandex["page"], yandex["groupby"], yandex["domain"], yandex["ai"]), (0, 10, "ru", 0))
        self.assertNotIn(SECRET, json.dumps([j["params"] for j in jobs]))

    def test_decimal_cap_blocks_before_any_request(self):
        transport = Transport({})
        with mock.patch.object(xc, "urlopen", transport):
            with self.assertRaises(ValueError):
                self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(), "--max-cost-rub", "0.049"))
        self.assertEqual(transport.calls, [])

    def test_collect_resume_and_redaction(self):
        transport = Transport({"купить стол": [serp_xml("купить стол", ["a.ru", "b.ru"], ads=1, echo_key=True)],
                               "купить стул": [serp_xml("купить стул", ["c.ru"])]})
        with mock.patch.object(xc, "urlopen", transport):
            code, result = self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(),
                                                                   "--max-cost-rub", "0.05"))
            self.assertEqual((code, result["success"]), (0, 2))
            code, again = self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(),
                                                                  "--max-cost-rub", "0.05"))
        self.assertEqual((again["new_requests"], len(transport.calls)), (0, 2))
        raw = b"".join(p.read_bytes() for p in (self.root / "run" / "raw").glob("*.xml"))
        self.assertNotIn(SECRET.encode(), raw)
        self.assertIn(b"[REDACTED]", raw)
        code, exported = self.run_cmd("export", *self.serp_args())
        self.assertEqual((exported["organic_rows"], exported["ad_rows"]), (3, 1))
        header = (self.root / "run" / "serp_results.tsv").read_text(encoding="utf-8").splitlines()[0].split("\t")
        self.assertEqual(header[:len(xc.RESULT_HEADER)], xc.RESULT_HEADER)
        ad = (self.root / "run" / "ad_rows.tsv").read_text(encoding="utf-8")
        self.assertIn("%3Cb%3EСтол%3C/b%3E", ad)
        self.assertIn("landing-unresolved", ad)

    def test_transport_error_stays_inflight_and_is_not_resent(self):
        transport = Transport({"купить стол": [OSError("boom")], "купить стул": [serp_xml("купить стул", ["c.ru"])]})
        with mock.patch.object(xc, "urlopen", transport):
            code, result = self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(),
                                                                   "--max-cost-rub", "1"))
            self.assertEqual((code, result["inflight"]), (2, 1))
            self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(), "--max-cost-rub", "1"))
        self.assertEqual(len(transport.calls), 2)
        with self.assertRaises(ValueError):
            key = self.run_cmd("inflight", *self.serp_args())[1]["inflight"][0]["job_key"]
            self.run_cmd("inflight", *self.serp_args("--job-key", key))

    def test_500_retry_and_stop_codes(self):
        transport = Transport({"купить стол": [error_xml("500"), serp_xml("купить стол", ["a.ru"])],
                               "купить стул": [error_xml("15")]})
        with mock.patch.object(xc, "urlopen", transport):
            code, result = self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(),
                                                                   "--max-cost-rub", "1"))
            self.assertEqual((result["error"], result["empty"]), (1, 1))
            code, retry = self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(),
                                                                  "--max-cost-rub", "1", "--retry-errors"))
        self.assertEqual((retry["new_requests"], retry["success"]), (1, 1))
        stop = Transport({"купить стол": [error_xml("115")], "купить стул": [serp_xml("купить стул", ["c.ru"])]})
        with mock.patch.object(xc, "urlopen", stop):
            code, result = self.run_cmd("collect", "--output-dir", str(self.root / "run2"), "--kind", "serp",
                                        "--jobs-file", str(self.root / "jobs.tsv"), "--workers", "1",
                                        "--approve-plan-sha256", self.plan(), "--max-cost-rub", "1")
        self.assertEqual(code, 3)
        self.assertEqual(len(stop.calls), 1)

    def test_rank_chain_needs_previous_page_without_overlap(self):
        pages = {("yandex", "q", 0): ([f"u{i}" for i in range(10)], "", 0),
                 ("yandex", "q", 1): (["u9", "v1"], "", 0)}
        self.assertEqual(xc.rank_state(pages, {"page": 1, "engine": "yandex"}), "url_overlap_between_pages")
        pages[("yandex", "q", 1)] = (["v1"], "", 0)
        self.assertEqual(xc.rank_state(pages, {"page": 1, "engine": "yandex"}), "verified")
        del pages[("yandex", "q", 0)]
        self.assertEqual(xc.rank_state(pages, {"page": 1, "engine": "yandex"}), "previous_page_missing_or_not_successful")

    def test_wordstat_normalization_without_history_has_no_total(self):
        (self.root / "masks.txt").write_text("купить стол\n", encoding="utf-8")
        words = json.dumps({"popular": [{"text": "+купить +стол", "value": "1 234"}], "associations": []}).encode()
        transport = Transport({"купить стол": [words]})
        args = ["--kind", "wordstat", "--masks-file", str(self.root / "masks.txt"), "--output-dir",
                str(self.root / "runw"), "--pagetypes", "words", "--workers", "1"]
        sha = self.run_cmd("plan", *args)[1]["plan_sha256"]
        with mock.patch.object(xc, "urlopen", transport):
            self.run_cmd("collect", *args, "--approve-plan-sha256", sha, "--max-cost-rub", "1")
        self.run_cmd("export", *args)
        files = list((self.root / "runw" / "raw_bundle").glob("top_requests_*.json"))
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertNotIn("totalCount", payload)
        self.assertEqual(payload["results"][0], {"phrase": "купить стол", "count": 1234, "phrase_raw": "+купить +стол"})

    def test_history_range_rejects_short_or_today(self):
        args = xc.build_parser().parse_args(["plan", "--kind", "wordstat", "--period", "month",
                                             "--start", "01.01.2026", "--end", "28.02.2026"])
        with self.assertRaises(ValueError):
            xc.history_range(args)

    def test_demo_key_has_hard_cap(self):
        with mock.patch.dict(os.environ, {"XMLRIVER_USER": "", "XMLRIVER_KEY": "", "XMLRIVER_USER_ID": ""}):
            with self.assertRaises(ValueError):
                self.run_cmd("collect", *self.serp_args("--use-demo-key", "--approve-plan-sha256", self.plan(),
                                                        "--max-cost-rub", "5"))


if __name__ == "__main__":
    unittest.main()
