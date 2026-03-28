#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def load_template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def render(text: str, client_key: str, client_name: str) -> str:
    return (
        text.replace("__CLIENT_KEY__", client_key)
        .replace("__CLIENT_NAME__", client_name)
    )


def write_file(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return f"skip  {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"write {path}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold a reusable local client lifecycle pack for Yandex Direct work."
    )
    parser.add_argument("--output-dir", required=True, help="Target project directory")
    parser.add_argument("--client-key", required=True, help="Short client key")
    parser.add_argument("--client-name", required=True, help="Human-readable client name")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {
        output_dir / "client-kb.md": render(
            load_template("client-kb-template.md"), args.client_key, args.client_name
        ),
        output_dir / "source-register.tsv": load_template("source-register-template.tsv"),
        output_dir / "competitor-raw-register.tsv": load_template(
            "competitor-raw-register-template.tsv"
        ),
        output_dir / "human-review.tsv": load_template("human-review-template.tsv"),
        output_dir / "proposal-pack.md": render(
            load_template("proposal-pack-template.md"), args.client_key, args.client_name
        ),
        output_dir / "product-map.md": load_template("product-map-template.md"),
        output_dir / "routing-map.tsv": load_template("routing-map-template.tsv"),
        output_dir / "research" / "analysis" / "company-footprint.md": render(
            load_template("company-footprint-template.md"), args.client_key, args.client_name
        ),
        output_dir / "research" / "analysis" / "landing-inventory.md": load_template(
            "landing-inventory-template.md"
        ),
        output_dir / "research" / "analysis" / "research-backlog.md": load_template(
            "research-backlog-template.md"
        ),
        output_dir / "research" / "analysis" / "единая-карта-конкурентов.md": load_template(
            "unified-competitor-map-template.md"
        ).replace("__DATE__", "YYYY-MM-DD"),
        output_dir / "research" / "analysis" / "пакет-структуры-будущего-кабинета.md": load_template(
            "future-cabinet-structure-template.md"
        ).replace("__DATE__", "YYYY-MM-DD"),
        output_dir / "research" / "analysis" / "пакет-текстов-и-офферов.md": load_template(
            "offers-pack-template.md"
        ).replace("__DATE__", "YYYY-MM-DD"),
        output_dir / "research" / "analysis" / "готовые-тексты-для-директа.tsv": load_template(
            "direct-copy-pack-template.tsv"
        ),
        output_dir / "research" / "semantics" / args.client_key / "00-product-map.md": load_template(
            "semantics-product-map-template.md"
        ),
        output_dir / "research" / "semantics" / args.client_key / "01-masks-wave1.tsv": load_template(
            "wordstat-masks-wave1-template.tsv"
        ),
        output_dir / "research" / "jobs" / "organic-serp-jobs.tsv": load_template(
            "serp-job-template.tsv"
        ),
        output_dir / "research" / "jobs" / "ad-serp-jobs.tsv": load_template(
            "ad-serp-job-template.tsv"
        ),
        output_dir / "research" / "jobs" / "page-capture-jobs.tsv": load_template(
            "page-capture-job-template.tsv"
        ),
        output_dir / "research" / "jobs" / "sitemap-jobs.tsv": load_template(
            "sitemap-job-template.tsv"
        ),
        output_dir / "research" / "jobs" / "search-api.env.example": load_template(
            "search-api-env-template.env"
        ),
        output_dir / ".codex" / "yandex-performance-client.json": render(
            load_template("yandex-performance-client-template.json"),
            args.client_key,
            args.client_name,
        ),
    }

    for relative_dir in [
        output_dir / "research" / "raw",
        output_dir / "research" / "analysis",
        output_dir / "research" / "semantics" / args.client_key,
        output_dir / "research" / "jobs",
        output_dir / "proposal",
        output_dir / "handoff",
    ]:
        relative_dir.mkdir(parents=True, exist_ok=True)

    results = [write_file(path, content, args.force) for path, content in files.items()]
    print("\n".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
