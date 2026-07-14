from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PortableScriptTests(unittest.TestCase):
    def test_ad_html_parser_extracts_only_advertising_rows(self) -> None:
        module = load_module(
            "portable_ad_parser",
            PLUGIN / "skills/yandex-direct-client-lifecycle/scripts/yandex_search_ads_batch.py",
        )
        vnl = json.dumps({
            "reportFeedback": {
                "feature": "Реклама",
                "customMetaFields": [
                    {"name": "snippetUrl", "value": "https://example.ru/offer"},
                    {"name": "countUrl", "value": "https://counter.example/1"},
                ],
            }
        }).replace('"', "&quot;")
        source = f"""
        <main>
          <article class="serp-item organic"><a class="OrganicTitle-Link" href="https://organic.example">Обычный результат</a></article>
          <article class="serp-item premium">
            <div data-vnl="{vnl}"></div>
            <a class="OrganicTitle-Link extra" href="https://example.ru/offer">Рекламный заголовок</a>
            <span class="OrganicTextContentSpan">Описание предложения</span>
          </article>
          <article class="serp-item RsyaGuarantee"><a class="OrganicTitle-Link">Исключено</a></article>
        </main>
        """
        job = module.Job(2, "job", "ad_serp", "test", "запрос", "rf", "225", 0, "")
        rows = module.extract_search_ad_rows(
            source, job, "2026-07-14T00:00:00+00:00", Path("raw.json"), Path("raw.html")
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["result_title"], "Рекламный заголовок")
        self.assertEqual(rows[0]["result_headline"], "Описание предложения")
        self.assertEqual(rows[0]["result_domain"], "example.ru")
        self.assertEqual(rows[0]["count_url"], "https://counter.example/1")


if __name__ == "__main__":
    unittest.main()
