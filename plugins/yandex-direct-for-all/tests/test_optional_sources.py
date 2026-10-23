#!/usr/bin/env python3
"""Roistat и amoCRM необязательны: общие сценарии работают без них."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
OPS = PLUGIN / "skills" / "yandex-performance-ops"
CLEAN_ENV = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}


class OptionalSourcesTests(unittest.TestCase):
    def test_roistat_query_skips_without_access_only_with_flag(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "out.json"
            skipped = subprocess.run(["bash", str(OPS / "scripts/roistat_query.sh"), str(out), "project/list",
                                      "--if-configured"], env=CLEAN_ENV, capture_output=True, text=True)
            self.assertEqual(skipped.returncode, 0)
            self.assertFalse(out.exists())
            failed = subprocess.run(["bash", str(OPS / "scripts/roistat_query.sh"), str(out), "project/list"],
                                    env=CLEAN_ENV, capture_output=True, text=True)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("необязателен", failed.stderr)

    def context(self, *flags: str) -> dict:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "ctx.json"
            subprocess.run([sys.executable, str(OPS / "scripts/init_client_context.py"), "--output", str(path), *flags],
                           check=True, capture_output=True)
            return json.loads(path.read_text(encoding="utf-8"))

    def test_client_context_defaults_without_sales_source(self):
        default = self.context()
        self.assertNotIn("roistat", default["analytics"]["source_priority"])
        self.assertEqual((default["analytics"]["sales_source"], default["analytics"]["roistat_first"],
                          default["roistat"]["enabled"]), ("none", False, False))
        with_roistat = self.context("--with-roistat")
        self.assertEqual(with_roistat["analytics"]["source_priority"][0], "roistat")
        self.assertTrue(with_roistat["roistat"]["enabled"])
        both = self.context("--with-crm", "--with-roistat")
        self.assertEqual(both["analytics"]["source_priority"][:2], ["crm", "roistat"])

    def test_templates_do_not_make_roistat_unconditional(self):
        pattern = re.compile(r"Roistat (wins|is primary)|Roistat as primary|^- Roistat period comparison", re.M)
        for folder in (OPS / "templates", OPS / "references/task_playbooks"):
            for path in folder.glob("*.md"):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), path.name)


if __name__ == "__main__":
    unittest.main()
