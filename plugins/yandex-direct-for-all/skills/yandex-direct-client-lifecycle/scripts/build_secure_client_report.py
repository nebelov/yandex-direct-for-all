#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path


GATE_STYLE = """
<style>
  html.report-locked,
  html.report-locked body {
    overflow: hidden;
  }

  .report-shell {
    display: none;
  }

  html.report-unlocked .report-shell {
    display: block;
  }

  .report-gate {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: grid;
    place-items: center;
    padding: 24px;
    background:
      linear-gradient(135deg, #ffd84d 0 42%, #f3ede2 42% 100%);
  }

  html.report-unlocked .report-gate {
    display: none;
  }

  .report-gate-card {
    width: min(100%, 540px);
    border: 4px solid #101010;
    box-shadow: 10px 10px 0 #101010;
    background: #fffdf7;
    padding: 24px;
    color: #101010;
    font-family: "IBM Plex Mono", "Cascadia Mono", Menlo, Monaco, "SFMono-Regular", "Courier New", monospace;
  }

  .report-gate-kicker {
    display: inline-block;
    padding: 6px 10px;
    border: 2px solid #101010;
    background: #ffffff;
    font-size: 12px;
    text-transform: uppercase;
  }

  .report-gate-card h1 {
    margin: 18px 0 14px;
    font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
    font-size: clamp(32px, 6vw, 58px);
    line-height: 0.92;
    text-transform: uppercase;
  }

  .report-gate-card p {
    margin: 0 0 16px;
    line-height: 1.6;
  }

  .report-gate-form {
    display: grid;
    gap: 12px;
  }

  .report-gate-form input {
    width: 100%;
    border: 4px solid #101010;
    background: #ffffff;
    padding: 14px 16px;
    color: #101010;
    font: inherit;
  }

  .report-gate-form button {
    border: 4px solid #101010;
    background: #101010;
    color: #ffffff;
    padding: 14px 16px;
    font: inherit;
    text-transform: uppercase;
    cursor: pointer;
  }

  .report-gate-error {
    min-height: 22px;
    color: #c63817;
    font-size: 13px;
  }
</style>
"""


GATE_SCRIPT_TEMPLATE = """
<script>
  (function() {
    var STORAGE_KEY = "__nevgroup_client_report_unlock__";
    var PASSWORD_HASH = "__PASSWORD_HASH__";

    function hex(buffer) {
      return Array.from(new Uint8Array(buffer)).map(function(value) {
        return value.toString(16).padStart(2, "0");
      }).join("");
    }

    function unlock() {
      document.documentElement.classList.remove("report-locked");
      document.documentElement.classList.add("report-unlocked");
      try {
        sessionStorage.setItem(STORAGE_KEY, "1");
      } catch (error) {
      }
    }

    function lock() {
      document.documentElement.classList.remove("report-unlocked");
      document.documentElement.classList.add("report-locked");
    }

    try {
      if (sessionStorage.getItem(STORAGE_KEY) === "1") {
        unlock();
        return;
      }
    } catch (error) {
    }

    lock();

    window.__nevgroupReportGate = {
      submit: async function(password) {
        var digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(password));
        if (hex(digest) === PASSWORD_HASH) {
          unlock();
          return true;
        }
        return false;
      }
    };
  })();
</script>
"""


GATE_MARKUP = """
<div class="report-gate" id="report-gate">
  <div class="report-gate-card">
    <div class="report-gate-kicker">NEV Group · Закрытый отчет</div>
    <h1>Отчет защищен паролем</h1>
    <p>Введите пароль, чтобы открыть исследование, карту конкурентов, структуру кабинета и примеры объявлений.</p>
    <form class="report-gate-form" id="report-gate-form">
      <input type="text" name="username" autocomplete="username" value="nevgroup" tabindex="-1" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0;">
      <input id="report-password" type="password" autocomplete="current-password" placeholder="Пароль">
      <button type="submit">Открыть отчет</button>
      <div class="report-gate-error" id="report-gate-error"></div>
    </form>
  </div>
</div>
"""


GATE_BOOTSTRAP = """
<script>
  (function() {
    var form = document.getElementById("report-gate-form");
    var input = document.getElementById("report-password");
    var error = document.getElementById("report-gate-error");

    if (!form || !input || !window.__nevgroupReportGate) {
      return;
    }

    form.addEventListener("submit", async function(event) {
      event.preventDefault();
      error.textContent = "";
      var ok = await window.__nevgroupReportGate.submit(input.value);
      if (!ok) {
        error.textContent = "Пароль не подошел.";
        input.focus();
        input.select();
      }
    });

    input.focus();
  })();
</script>
"""


def replace_once(text: str, pattern: str, replacement: str) -> str:
    result, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Не удалось заменить паттерн: {pattern}")
    return result


def build_index(
    source_html: Path,
    source_css: Path,
    source_js: Path,
    ads_tsv: Path,
    demand_exact_tsv: Path,
    demand_roots_tsv: Path,
    seasonality_tsv: Path,
    geo_priority_tsv: Path,
    password: str,
) -> str:
    html_text = source_html.read_text(encoding="utf-8")
    css_text = source_css.read_text(encoding="utf-8")
    js_text = source_js.read_text(encoding="utf-8")
    ads_tsv_text = ads_tsv.read_text(encoding="utf-8")
    demand_exact_tsv_text = demand_exact_tsv.read_text(encoding="utf-8")
    demand_roots_tsv_text = demand_roots_tsv.read_text(encoding="utf-8")
    seasonality_tsv_text = seasonality_tsv.read_text(encoding="utf-8")
    geo_priority_tsv_text = geo_priority_tsv.read_text(encoding="utf-8")

    js_text = js_text.replace(
        'const ADS_TSV_PATH = "research/analysis/готовые-тексты-для-директа.tsv";',
        'const ADS_TSV_PATH = "research/analysis/готовые-тексты-для-директа.tsv";',
    )

    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

    html_text = replace_once(
        html_text,
        r'<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '    <meta name="robots" content="noindex,nofollow,noarchive">',
    )
    html_text = replace_once(
        html_text,
        r'<link rel="stylesheet" href="client-report-brutalism.css">',
        f"<style>\n{css_text}\n</style>\n{GATE_STYLE}\n"
        f"{GATE_SCRIPT_TEMPLATE.replace('__PASSWORD_HASH__', password_hash)}",
    )

    body_match = re.search(r"<body>(.*)</body>", html_text, flags=re.S)
    if not body_match:
        raise RuntimeError("Не найден body в исходном HTML")
    body_inner = body_match.group(1).strip()

    wrapped_body = (
        "<body>\n"
        f"{GATE_MARKUP}\n"
        '<div class="report-shell">\n'
        f"{body_inner}\n"
        "</div>\n"
        f'<script>window.__ADS_TSV__ = {json.dumps(ads_tsv_text, ensure_ascii=False)};</script>\n'
        f'<script>window.__WORDSTAT_DEMAND_EXACT_TSV__ = {json.dumps(demand_exact_tsv_text, ensure_ascii=False)};</script>\n'
        f'<script>window.__WORDSTAT_DEMAND_ROOTS_TSV__ = {json.dumps(demand_roots_tsv_text, ensure_ascii=False)};</script>\n'
        f'<script>window.__WORDSTAT_SEASONALITY_MATRIX_TSV__ = {json.dumps(seasonality_tsv_text, ensure_ascii=False)};</script>\n'
        f'<script>window.__WORDSTAT_GEO_PRIORITY_TSV__ = {json.dumps(geo_priority_tsv_text, ensure_ascii=False)};</script>\n'
        f"<script>\n{js_text}\n</script>\n"
        f"{GATE_BOOTSTRAP}\n"
        "</body>"
    )
    html_text = replace_once(html_text, r"<body>.*</body>", wrapped_body)
    html_text = re.sub(r'\s*<script src="client-report-brutalism.js"></script>\s*', "\n", html_text)
    return html_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-html", required=True)
    parser.add_argument("--source-css", required=True)
    parser.add_argument("--source-js", required=True)
    parser.add_argument("--ads-tsv", required=True)
    parser.add_argument("--demand-exact-tsv", required=True)
    parser.add_argument("--demand-roots-tsv", required=True)
    parser.add_argument("--seasonality-tsv", required=True)
    parser.add_argument("--geo-priority-tsv", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    index_html = build_index(
        Path(args.source_html),
        Path(args.source_css),
        Path(args.source_js),
        Path(args.ads_tsv),
        Path(args.demand_exact_tsv),
        Path(args.demand_roots_tsv),
        Path(args.seasonality_tsv),
        Path(args.geo_priority_tsv),
        args.password,
    )

    (out_dir / "index.html").write_text(index_html, encoding="utf-8")
    (out_dir / "vercel.json").write_text(
        json.dumps(
            {
                "headers": [
                    {
                        "source": "/(.*)",
                        "headers": [
                            {"key": "X-Robots-Tag", "value": "noindex, nofollow, noarchive"},
                            {"key": "Cache-Control", "value": "no-store, max-age=0"},
                        ],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "outDir": str(out_dir),
                "indexHtml": str(out_dir / "index.html"),
                "passwordHash": hashlib.sha256(args.password.encode("utf-8")).hexdigest(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
