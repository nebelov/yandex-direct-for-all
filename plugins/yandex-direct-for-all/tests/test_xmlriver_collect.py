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
        row = {"page": 1, "engine": "yandex", "_series": "q"}
        pages = {("yandex", "q", 0): ([f"u{i}" for i in range(10)], "", 0),
                 ("yandex", "q", 1): (["u9", "v1"], "", 0)}
        self.assertEqual(xc.rank_state(pages, row), "url_overlap_between_pages")
        pages[("yandex", "q", 1)] = (["v1"], "", 0)
        self.assertEqual(xc.rank_state(pages, row), "verified")
        del pages[("yandex", "q", 0)]
        self.assertEqual(xc.rank_state(pages, row), "previous_page_missing_or_not_successful")

    def test_rank_state_does_not_borrow_other_query_pages(self):
        pages = {("yandex", "A", 0): ([f"u{i}" for i in range(10)], "", 0), ("yandex", "A", 1): (["x"], "", 0),
                 ("yandex", "B", 1): (["y"], "", 0)}
        self.assertEqual(xc.rank_state(pages, {"page": 1, "engine": "yandex", "_series": "B"}),
                         "previous_page_missing_or_not_successful")

    def test_claim_is_atomic_and_parallel_collect_is_locked(self):
        run = self.root / "run"
        db = xc.open_db(run, create=True)
        job = {"job_key": "k1", "kind": "serp", "engine": "yandex", "params": {}}
        db.execute("INSERT INTO jobs(job_key,kind,engine,spec_json,status) VALUES('k1','serp','yandex','{}','pending')")
        db.commit()
        self.assertIsNotNone(xc.start_attempt(db, run, job))
        self.assertIsNone(xc.start_attempt(db, run, job))
        held = open(run / ".collect.lock", "w")
        xc.fcntl.flock(held, xc.fcntl.LOCK_EX | xc.fcntl.LOCK_NB)
        transport = Transport({})
        try:
            with mock.patch.object(xc, "urlopen", transport), self.assertRaises(ValueError):
                self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(), "--max-cost-rub", "1"))
        finally:
            held.close()
        self.assertEqual(transport.calls, [])

    def test_ai_needs_price_and_counts_in_cap(self):
        transport = Transport({})
        with mock.patch.object(xc, "urlopen", transport):
            with self.assertRaises(ValueError):
                self.run_cmd("collect", *self.serp_args("--ai", "--approve-plan-sha256", self.plan("--ai"),
                                                        "--max-cost-rub", "1"))
            with self.assertRaises(ValueError):  # 2 x (0.025 + 0.5) > 1
                self.run_cmd("collect", *self.serp_args("--ai", "--ai-price-per-1000", "500", "--approve-plan-sha256",
                                                        self.plan("--ai"), "--max-cost-rub", "1"))
        self.assertEqual(transport.calls, [])

    def test_negative_ai_price_is_refused(self):
        transport = Transport({})
        with mock.patch.object(xc, "urlopen", transport), self.assertRaises(ValueError):
            self.run_cmd("collect", *self.serp_args("--ai", "--ai-price-per-1000", "-500", "--approve-plan-sha256",
                                                    self.plan("--ai"), "--max-cost-rub", "1"))
        self.assertEqual(transport.calls, [])

    def test_export_with_unfinished_jobs_is_incomplete(self):
        transport = Transport({"купить стол": [serp_xml("купить стол", ["a.ru"])]})
        with mock.patch.object(xc, "urlopen", transport):
            self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(), "--max-cost-rub", "1",
                                                    "--max-new", "1"))
        code, result = self.run_cmd("export", *self.serp_args())
        self.assertEqual((code, result["complete"], result["unfinished_jobs"]), (2, False, 1))

    def test_new_requests_counts_only_started(self):
        stop = Transport({"купить стол": [error_xml("115")], "купить стул": [serp_xml("купить стул", ["c.ru"])]})
        with mock.patch.object(xc, "urlopen", stop):
            code, result = self.run_cmd("collect", *self.serp_args("--approve-plan-sha256", self.plan(),
                                                                   "--max-cost-rub", "1"))
        self.assertEqual((code, result["new_requests"], result["queued"]), (3, 1, 2))

    def test_export_geography_and_engine_split(self):
        (self.root / "jobs.tsv").write_text("job_id\tsearch_query\nj1\tкупить стол\n", encoding="utf-8")
        transport = Transport({"купить стол": [serp_xml("купить стол", ["a.ru"]), serp_xml("купить стол", ["g.com"])]})
        with mock.patch.object(xc, "urlopen", transport):
            self.run_cmd("collect", *self.serp_args("--engine", "both", "--approve-plan-sha256",
                                                    self.plan("--engine", "both"), "--max-cost-rub", "1"))
        code, exported = self.run_cmd("export", *self.serp_args("--engine", "both"))
        self.assertEqual(sorted(exported["files"])[:2], ["ad_rows_google.tsv", "ad_rows_yandex.tsv"])
        self.assertFalse((self.root / "run" / "serp_results.tsv").exists())
        yandex = (self.root / "run" / "serp_results_yandex.tsv").read_text(encoding="utf-8").splitlines()
        header, first = yandex[0].split("\t"), yandex[1].split("\t")
        self.assertEqual((first[header.index("region_id")], first[header.index("search_region")]), ("225", "225"))
        self.assertNotIn("g.com", "\n".join(yandex))

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

    def wordstat_run(self, answers: list[bytes], pagetypes: str = "words") -> tuple[list[str], Transport]:
        (self.root / "masks.txt").write_text("купить стол\n", encoding="utf-8")
        transport = Transport({"купить стол": answers})
        args = ["--kind", "wordstat", "--masks-file", str(self.root / "masks.txt"), "--output-dir",
                str(self.root / "runw"), "--pagetypes", pagetypes, "--workers", "1",
                "--start", "01.01.2024", "--end", "31.05.2024"]
        sha = self.run_cmd("plan", *args)[1]["plan_sha256"]
        with mock.patch.object(xc, "urlopen", transport):
            self.run_cmd("collect", *args, "--approve-plan-sha256", sha, "--max-cost-rub", "1")
        return args, transport

    def test_wordstat_bad_schema_is_error_not_success(self):
        args, _ = self.wordstat_run([b"{}"])
        state = self.run_cmd("plan", *args)[1]["status"]
        self.assertEqual((state["success"], state["error"]), (0, 1))

    def test_words_job_needs_popular_not_graph(self):
        args, _ = self.wordstat_run([b'{"graph": {}}'])
        state = self.run_cmd("plan", *args)[1]["status"]
        self.assertEqual((state["success"], state["error"]), (0, 1))

    def test_bad_dynamics_point_marks_partial(self):
        history = json.dumps({"graph": {"tableData": [{"absoluteValue": "1"}, {"startTimestamp": 1715547600000,
                                                                                "absoluteValue": "x"}]}}).encode()
        args, _ = self.wordstat_run([history], pagetypes="history")
        code, result = self.run_cmd("export", *args)
        self.assertEqual((code, result["row_errors"], result["complete"]), (2, 2, False))

    def test_non_finite_share_is_row_error(self):
        history = json.dumps({"graph": {"tableData": [{"startTimestamp": 1715547600000, "absoluteValue": "1",
                                                       "value": "NaN"}]}}).encode()
        args, _ = self.wordstat_run([history], pagetypes="history")
        code, result = self.run_cmd("export", *args)
        self.assertEqual((code, result["row_errors"]), (2, 1))

    def test_wordstat_row_error_marks_partial_and_fails_export(self):
        words = json.dumps({"popular": [{"text": "стол", "value": "abc"}, {"text": "стул", "value": "5"}]}).encode()
        args, _ = self.wordstat_run([words])
        stale = self.root / "runw" / "raw_bundle" / "top_requests_old.json"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("{}", encoding="utf-8")
        code, result = self.run_cmd("export", *args)
        manifest = json.loads((self.root / "runw" / "raw_bundle" / "_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((code, result["complete"], manifest[0]["status"]), (2, False, "partial"))
        self.assertFalse(stale.exists())

    def test_dynamics_dates_are_moscow_and_renderer_uses_manifest(self):
        history = json.dumps({"graph": {"tableData": [{"startTimestamp": 1715547600000, "absoluteValue": "10",
                                                       "value": "0,1"}]}}).encode()
        args, _ = self.wordstat_run([history], pagetypes="history")
        self.run_cmd("export", *args)
        bundle = self.root / "runw" / "raw_bundle"
        render = Path(__file__).resolve().parents[1] / "skills" / "yandex-performance-ops" / "scripts" / "render_wordstat_seasonality.py"
        spec = importlib.util.spec_from_file_location("render_seasonality", render)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        found = module.resolve_raw_path(self.root, str(bundle), "купить стол")
        payload = json.loads(found.read_text(encoding="utf-8"))
        self.assertEqual(payload["dynamics"][0]["date"], "2024-05-13")

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
