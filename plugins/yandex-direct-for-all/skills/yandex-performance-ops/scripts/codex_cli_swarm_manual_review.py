#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
SEARCH_TEMPLATE_PATH = SKILL_ROOT / "templates/codex_swarm_search_worker_prompt.md"
RSYA_TEMPLATE_PATH = SKILL_ROOT / "templates/codex_swarm_rsya_worker_prompt.md"
SEARCH_SCHEMA_PATH = SKILL_ROOT / "schemas/codex_swarm_search_chunk_response.schema.json"
RSYA_SCHEMA_PATH = SKILL_ROOT / "schemas/codex_swarm_rsya_chunk_response.schema.json"
GLOBAL_SKILL_PATH = SKILL_ROOT / "SKILL.md"


@dataclass(frozen=True)
class ChunkSpec:
    chunk_id: str
    index: int
    chunk_path: Path
    focus_context_path: Path
    context_path: Path
    knowledge_pack_path: Path
    codex_home: Path
    prompt_path: Path
    response_path: Path
    stdout_path: Path
    stderr_path: Path
    row_count: int
    candidate_ids: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch multiple local Codex CLI workers for strict manual review chunks."
    )
    parser.add_argument("--kind", required=True, choices=("search", "rsya"))
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=25)
    parser.add_argument("--limit-chunks", type=int, default=0)
    parser.add_argument("--model", default="gpt-5.1-codex-mini")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--sandbox", choices=("read-only", "workspace-write", "danger-full-access"), default="danger-full-access")
    parser.add_argument("--approval-policy", choices=("untrusted", "on-failure", "on-request", "never"), default="never")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--merge-into", type=Path)
    parser.add_argument("--allow-unresolved", action="store_true")
    parser.add_argument("--include-resolved", action="store_true")
    parser.add_argument("--disable-mcp", action="store_true", default=True)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--global-skill", type=Path, default=GLOBAL_SKILL_PATH)
    parser.add_argument("--local-skill", type=Path)
    parser.add_argument("--product-catalog", type=Path)
    parser.add_argument("--search-rules", type=Path)
    parser.add_argument("--rsya-rules", type=Path)
    parser.add_argument("--lessons", type=Path)
    parser.add_argument("--manual-decisions", type=Path, action="append", default=[])
    parser.add_argument("--extra-context", type=Path, action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def resolved(row: dict[str, str]) -> bool:
    return bool(str(row.get("assistant_status", "")).strip())


def default_output_dir(queue: Path, kind: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    review_dir = queue.resolve().parent.parent if queue.resolve().parent.name == "manual" else queue.resolve().parent
    return review_dir / "swarm" / f"{kind}_{stamp}"


def normalize_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for path in paths:
        resolved_path = path.expanduser().resolve()
        if resolved_path.exists():
            out.append(resolved_path)
    return out


def render_prompt(template_path: Path, replacements: dict[str, str]) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(f"__{key}__", value)
    return text


def read_text_or_empty(path: Path | None) -> str:
    if path is None:
        return ""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def append_pack_section(lines: list[str], title: str, path: Path | None, body: str) -> None:
    if path is None or not body.strip():
        return
    lines.append(f"## {title}")
    lines.append(f"Source: {path}")
    lines.append("")
    lines.append(body.rstrip())
    lines.append("")


def quick_reference_lines(kind: str) -> list[str]:
    base = [
        "- Roistat = truth layer for sales/leads. Direct conversions are support-only.",
        "- Verdicts are manual-only. Scripts may inspect files but must not invent decisions.",
        "- Prefer route-fix / phrase minus / growth handling over blind broad negatives.",
    ]
    if kind == "search":
        return base + [
            "- `натяжной` = hard minus.",
            "- `скрытый карниз` = target demand, route to type 7 if trapped elsewhere.",
            "- `потолочный плинтус с подсветкой` / `с подсветкой` = target LED demand, not trash.",
            "- `откос` / оконно-дверные откосы can be target demand (type 8), not blind-minus.",
            "- `двери скрытого монтажа` = complementary demand, not auto-trash.",
            "- `микроплинтус` = growth demand, not blind-minus.",
            "- `для пола` is usually a route-fix outside plinth/floor groups.",
        ]
    return base + [
        "- RSYA placement verdicts are based on Direct reports, not Roistat placement guesses.",
        "- Do not blind-block Yandex-owned inventory, protected platforms, or anomaly rows.",
        "- `game/app/vpn/exact junk` can be blocked only when the row itself has enough evidence.",
        "- If evidence is weak, keep/monitor explicitly instead of force-blocking.",
    ]


def tokenize_focus_terms(text: str) -> list[str]:
    return re.findall(r"[a-zA-Zа-яА-Я0-9]+", str(text).lower())


def search_focus_terms(chunk_rows: list[dict[str, str]]) -> list[str]:
    stopwords = {
        "теневой", "профиль", "плинтус", "скрытый", "скрытого", "монтажа",
        "купить", "цена", "москва", "спб", "пола", "пола", "потолка",
        "потолок", "тип", "типы", "мм", "см", "для", "с", "на", "из",
        "группа", "autotargeting", "поиск",
    }
    soft_stopwords = {
        "купить", "цена", "москва", "спб", "для", "с", "на", "из",
        "группа", "autotargeting", "поиск",
    }
    terms: list[str] = []
    seen: set[str] = set()
    fallback_terms: list[str] = []
    for row in chunk_rows:
        for field in (row.get("ad_group_name", ""), row.get("query", "")):
            for token in tokenize_focus_terms(field):
                if len(token) < 4:
                    continue
                if token not in soft_stopwords and token not in seen:
                    fallback_terms.append(token)
                if token in stopwords:
                    continue
                if token in seen:
                    continue
                seen.add(token)
                terms.append(token)
    if terms:
        return terms[:20]
    dedup_fallback: list[str] = []
    seen_fallback: set[str] = set()
    for token in fallback_terms:
        if token in seen_fallback:
            continue
        seen_fallback.add(token)
        dedup_fallback.append(token)
    return sorted(dedup_fallback, key=len, reverse=True)[:6]


def rsya_focus_terms(chunk_rows: list[dict[str, str]]) -> list[str]:
    stopwords = {
        "com", "www", "http", "https", "android", "ios", "app", "apps",
        "game", "games", "yandex", "ru", "net", "org", "play",
    }
    terms: list[str] = []
    seen: set[str] = set()
    for row in chunk_rows:
        for field in (row.get("placement", ""), row.get("campaign_name", "")):
            for token in tokenize_focus_terms(field):
                if len(token) < 4:
                    continue
                if token in stopwords:
                    continue
                if token in seen:
                    continue
                seen.add(token)
                terms.append(token)
    return terms[:20]


def extract_focus_windows(text: str, terms: list[str], *, window: int = 2, max_windows: int = 24) -> list[tuple[int, int, list[str]]]:
    if not text.strip() or not terms:
        return []
    lines = text.splitlines()
    raw_windows: list[tuple[int, int, list[str]]] = []
    lowered_terms = [term.lower() for term in terms]
    for idx, line in enumerate(lines):
        lowered_line = line.lower()
        matched = [term for term in lowered_terms if term in lowered_line]
        if not matched:
            continue
        start = max(0, idx - window)
        end = min(len(lines), idx + window + 1)
        raw_windows.append((start, end, matched))
        if len(raw_windows) >= max_windows:
            break
    if not raw_windows:
        return []
    merged: list[tuple[int, int, list[str]]] = []
    cur_start, cur_end, cur_terms = raw_windows[0]
    for start, end, matched in raw_windows[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
            cur_terms = sorted(set(cur_terms + matched))
            continue
        merged.append((cur_start, cur_end, cur_terms))
        cur_start, cur_end, cur_terms = start, end, matched
    merged.append((cur_start, cur_end, cur_terms))
    return merged[:max_windows]


def build_focus_context(
    args: argparse.Namespace,
    chunk_rows: list[dict[str, str]],
    knowledge_pack_path: Path,
    focus_context_path: Path,
) -> None:
    knowledge_text = knowledge_pack_path.read_text(encoding="utf-8")
    terms = search_focus_terms(chunk_rows) if args.kind == "search" else rsya_focus_terms(chunk_rows)
    windows = extract_focus_windows(knowledge_text, terms)
    lines = [
        f"# {args.kind.upper()} chunk focus context",
        "",
        "Deterministic snippet extract from the full worker knowledge pack.",
        "Use this first for fast orientation; use the full knowledge pack only if a contradiction remains.",
        "",
        f"Knowledge pack source: {knowledge_pack_path}",
        f"Focus terms: {', '.join(terms) if terms else '(none)'}",
        "",
    ]
    if not windows:
        lines.append("No snippet windows matched the focus terms. Fall back to the full knowledge pack.")
        lines.append("")
        focus_context_path.write_text("\n".join(lines), encoding="utf-8")
        return
    source_lines = knowledge_text.splitlines()
    for start, end, matched in windows:
        lines.append(f"## Snippet lines {start + 1}-{end}")
        lines.append(f"Matched terms: {', '.join(sorted(set(matched)))}")
        lines.append("")
        for idx in range(start, end):
            lines.append(f"{idx + 1}: {source_lines[idx]}")
        lines.append("")
    focus_context_path.write_text("\n".join(lines), encoding="utf-8")


def build_worker_knowledge_pack(args: argparse.Namespace, output_dir: Path) -> Path:
    knowledge_pack_path = output_dir / "context" / f"{args.kind}_worker_knowledge_pack.md"
    lines = [
        f"# {args.kind.upper()} worker knowledge pack",
        "",
        f"Generated at: {datetime.now().isoformat()}",
        f"Project root: {args.project_root.resolve()}",
        "",
        "This file is the canonical full business/product/rules context for Codex swarm workers.",
        "Workers should read this pack instead of reopening raw overlay/catalog/rules files.",
        "",
        "## Quick reference",
        "",
        *quick_reference_lines(args.kind),
        "",
    ]
    if args.kind == "search":
        append_pack_section(lines, "Product catalog", args.product_catalog, read_text_or_empty(args.product_catalog))
        append_pack_section(lines, "Search stop-word rules", args.search_rules, read_text_or_empty(args.search_rules))
    else:
        append_pack_section(lines, "RSYA placement rules", args.rsya_rules, read_text_or_empty(args.rsya_rules))
    append_pack_section(lines, "Lessons learned", args.lessons, read_text_or_empty(args.lessons))
    append_pack_section(lines, "Client overlay", args.overlay, read_text_or_empty(args.overlay))
    if args.extra_context:
        for idx, path in enumerate(args.extra_context, start=1):
            append_pack_section(lines, f"Extra context {idx}", path, read_text_or_empty(path))
    knowledge_pack_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return knowledge_pack_path


def seed_codex_home(worker_home: Path, *, copy_config: bool) -> None:
    base_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()
    worker_home.mkdir(parents=True, exist_ok=True)
    filenames = ["auth.json", "models_cache.json", "version.json"]
    if copy_config:
        filenames.append("config.toml")
    for filename in filenames:
        source = base_home / filename
        target = worker_home / filename
        if source.exists() and not target.exists():
            shutil.copy2(source, target)
    (worker_home / "skills").mkdir(exist_ok=True)
    (worker_home / "tmp").mkdir(exist_ok=True)
    (worker_home / "sessions").mkdir(exist_ok=True)


def split_candidate_id(candidate_id: str) -> tuple[str, str, str]:
    parts = str(candidate_id).split("||", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0], parts[1], parts[2]


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def parse_search_manual_context(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for row in rows:
        campaign_id, ad_group_name, query = split_candidate_id(row.get("candidate_id", ""))
        if not row.get("candidate_id"):
            continue
        parsed.append(
            {
                "candidate_id": row.get("candidate_id", ""),
                "campaign_id": campaign_id,
                "ad_group_name": ad_group_name,
                "query": query,
                "assistant_status": row.get("assistant_status", ""),
                "assistant_action": row.get("assistant_action", ""),
                "assistant_reason": row.get("assistant_reason", ""),
            }
        )
    return parsed


def parse_rsya_manual_context(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for row in rows:
        campaign_id, placement, _tail = split_candidate_id(row.get("candidate_id", ""))
        if not row.get("candidate_id"):
            continue
        parsed.append(
            {
                "candidate_id": row.get("candidate_id", ""),
                "campaign_id": campaign_id,
                "placement": placement,
                "assistant_status": row.get("assistant_status", ""),
                "assistant_action": row.get("assistant_action", ""),
                "assistant_reason": row.get("assistant_reason", ""),
            }
        )
    return parsed


def select_relevant_search_context(
    chunk_rows: list[dict[str, str]],
    manual_rows: list[dict[str, str]],
    *,
    limit: int = 80,
) -> list[dict[str, str]]:
    parsed_manual = parse_search_manual_context(manual_rows)
    ad_groups = {normalize_text(row.get("ad_group_name", "")) for row in chunk_rows if row.get("ad_group_name")}
    queries = {normalize_text(row.get("query", "")) for row in chunk_rows if row.get("query")}
    campaign_ids = {str(row.get("campaign_id", "")).strip() for row in chunk_rows if row.get("campaign_id")}
    selected: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for row in parsed_manual:
        row_id = row["candidate_id"]
        if row_id in seen_ids:
            continue
        row_ad_group = normalize_text(row.get("ad_group_name", ""))
        row_query = normalize_text(row.get("query", ""))
        if row_ad_group in ad_groups or row_query in queries:
            seen_ids.add(row_id)
            selected.append(row)
        if len(selected) >= limit:
            return selected[:limit]
    if len(selected) < min(20, limit):
        for row in parsed_manual:
            if len(selected) >= limit:
                break
            row_id = row["candidate_id"]
            if row_id in seen_ids:
                continue
            if str(row.get("campaign_id", "")).strip() in campaign_ids:
                seen_ids.add(row_id)
                selected.append(row)
    return selected[:limit]


def select_relevant_rsya_context(
    chunk_rows: list[dict[str, str]],
    manual_rows: list[dict[str, str]],
    *,
    limit: int = 80,
) -> list[dict[str, str]]:
    parsed_manual = parse_rsya_manual_context(manual_rows)
    campaigns = {str(row.get("campaign_id", "")).strip() for row in chunk_rows if row.get("campaign_id")}
    placements = {normalize_text(row.get("placement", "")) for row in chunk_rows if row.get("placement")}
    selected: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for row in parsed_manual:
        row_id = row["candidate_id"]
        if row_id in seen_ids:
            continue
        if normalize_text(row.get("placement", "")) in placements:
            seen_ids.add(row_id)
            selected.append(row)
        if len(selected) >= limit:
            return selected[:limit]
    if len(selected) < min(20, limit):
        for row in parsed_manual:
            if len(selected) >= limit:
                break
            row_id = row["candidate_id"]
            if row_id in seen_ids:
                continue
            if str(row.get("campaign_id", "")).strip() in campaigns:
                seen_ids.add(row_id)
                selected.append(row)
    return selected[:limit]


def build_required_reads(args: argparse.Namespace, chunk: ChunkSpec) -> list[str]:
    reads: list[Path] = []
    for path in [
        chunk.focus_context_path,
        chunk.context_path,
        chunk.chunk_path,
    ]:
        if path is None:
            continue
        resolved_path = path.expanduser().resolve()
        if resolved_path.exists():
            reads.append(resolved_path)
    lines: list[str] = []
    for idx, path in enumerate(reads, start=1):
        lines.append(f"{idx}. {path}")
    return lines


def prepare_chunks(args: argparse.Namespace) -> tuple[list[ChunkSpec], list[str]]:
    queue_rows = load_tsv(args.queue)
    if not queue_rows:
        raise SystemExit("Queue TSV is empty.")

    queue_fieldnames = list(queue_rows[0].keys())
    unresolved_rows = [
        row for row in queue_rows
        if str(row.get("candidate_id", "")).strip()
        and (args.include_resolved or not resolved(row))
    ]
    if not unresolved_rows:
        raise SystemExit("No unresolved rows found in queue.")

    output_dir = args.output_dir or default_output_dir(args.queue, args.kind)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "chunks").mkdir(exist_ok=True)
    (output_dir / "context").mkdir(exist_ok=True)
    (output_dir / "codex_homes").mkdir(exist_ok=True)
    (output_dir / "prompts").mkdir(exist_ok=True)
    (output_dir / "results").mkdir(exist_ok=True)
    (output_dir / "logs").mkdir(exist_ok=True)
    (output_dir / "decisions").mkdir(exist_ok=True)

    knowledge_pack_path = build_worker_knowledge_pack(args, output_dir)

    manual_rows: list[dict[str, str]] = []
    for path in args.manual_decisions:
        if path.exists():
            manual_rows.extend(load_tsv(path))

    chunks: list[ChunkSpec] = []
    for start in range(0, len(unresolved_rows), args.chunk_size):
        chunk_rows = unresolved_rows[start:start + args.chunk_size]
        chunk_index = len(chunks) + 1
        chunk_id = f"{args.kind}_chunk_{chunk_index:04d}"
        chunk_path = output_dir / "chunks" / f"{chunk_id}.tsv"
        focus_context_path = output_dir / "context" / f"{chunk_id}_focus_context.md"
        context_path = output_dir / "context" / f"{chunk_id}_prior_manual_context.tsv"
        codex_home = output_dir / "codex_homes" / chunk_id
        prompt_path = output_dir / "prompts" / f"{chunk_id}.md"
        response_path = output_dir / "results" / f"{chunk_id}.json"
        stdout_path = output_dir / "logs" / f"{chunk_id}.stdout.log"
        stderr_path = output_dir / "logs" / f"{chunk_id}.stderr.log"
        write_tsv(chunk_path, chunk_rows, queue_fieldnames)
        if args.kind == "search":
            context_rows = select_relevant_search_context(chunk_rows, manual_rows)
            context_fields = ["candidate_id", "campaign_id", "ad_group_name", "query", "assistant_status", "assistant_action", "assistant_reason"]
        else:
            context_rows = select_relevant_rsya_context(chunk_rows, manual_rows)
            context_fields = ["candidate_id", "campaign_id", "placement", "assistant_status", "assistant_action", "assistant_reason"]
        write_tsv(context_path, context_rows, context_fields)
        build_focus_context(args, chunk_rows, knowledge_pack_path, focus_context_path)
        seed_codex_home(codex_home, copy_config=not args.disable_mcp)
        chunk = ChunkSpec(
            chunk_id=chunk_id,
            index=chunk_index,
            chunk_path=chunk_path,
            focus_context_path=focus_context_path,
            context_path=context_path,
            knowledge_pack_path=knowledge_pack_path,
            codex_home=codex_home,
            prompt_path=prompt_path,
            response_path=response_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            row_count=len(chunk_rows),
            candidate_ids=tuple(row["candidate_id"] for row in chunk_rows),
        )
        chunks.append(chunk)
        if args.limit_chunks and len(chunks) >= args.limit_chunks:
            break

    template_path = SEARCH_TEMPLATE_PATH if args.kind == "search" else RSYA_TEMPLATE_PATH
    for chunk in chunks:
        replacements = {
            "KIND": args.kind,
            "CHUNK_ID": chunk.chunk_id,
            "CHUNK_PATH": str(chunk.chunk_path),
            "CHUNK_ROW_COUNT": str(chunk.row_count),
            "PROJECT_ROOT": str(args.project_root.resolve()),
            "FOCUS_CONTEXT": str(chunk.focus_context_path),
            "KNOWLEDGE_PACK": str(knowledge_pack_path),
            "CHUNK_PRIOR_CONTEXT": str(chunk.context_path),
            "REQUIRED_READS": "\n".join(build_required_reads(args, chunk)),
        }
        prompt = render_prompt(template_path, replacements)
        chunk.prompt_path.write_text(prompt, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "kind": args.kind,
        "queue": str(args.queue.resolve()),
        "project_root": str(args.project_root.resolve()),
        "output_dir": str(output_dir.resolve()),
        "workers": args.workers,
        "chunk_size": args.chunk_size,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "sandbox": args.sandbox,
        "approval_policy": args.approval_policy,
        "knowledge_pack_path": str(knowledge_pack_path),
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "row_count": chunk.row_count,
                "chunk_path": str(chunk.chunk_path),
                "focus_context_path": str(chunk.focus_context_path),
                "context_path": str(chunk.context_path),
                "knowledge_pack_path": str(chunk.knowledge_pack_path),
                "codex_home": str(chunk.codex_home),
                "prompt_path": str(chunk.prompt_path),
                "response_path": str(chunk.response_path),
                "stdout_path": str(chunk.stdout_path),
                "stderr_path": str(chunk.stderr_path),
            }
            for chunk in chunks
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return chunks, queue_fieldnames


def codex_command(args: argparse.Namespace, schema_path: Path, response_path: Path) -> list[str]:
    command = [
        "codex",
        "exec",
        "-C",
        str(args.project_root.resolve()),
        "--skip-git-repo-check",
        "--color",
        "never",
        "-m",
        args.model,
        "-c",
        f'model_reasoning_effort="{args.reasoning_effort}"',
        "-c",
        f'approval_policy="{args.approval_policy}"',
        "-s",
        args.sandbox,
        "--json",
        "--output-schema",
        str(schema_path),
        "-o",
        str(response_path),
        "-",
    ]
    if args.disable_mcp:
        command.extend(["-c", "mcp_servers={}"])
    return command


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_chunk_response(
    payload: dict[str, Any],
    chunk: ChunkSpec,
    *,
    allow_unresolved: bool,
) -> list[dict[str, str]]:
    decisions = payload.get("decisions")
    unresolved = payload.get("unresolved_candidate_ids")
    if not isinstance(decisions, list):
        raise ValueError("Response missing decisions array.")
    if not isinstance(unresolved, list):
        raise ValueError("Response missing unresolved_candidate_ids array.")
    decision_ids: list[str] = []
    decision_rows: list[dict[str, str]] = []
    for item in decisions:
        if not isinstance(item, dict):
            raise ValueError("Decision item is not an object.")
        candidate_id = str(item.get("candidate_id", "")).strip()
        assistant_status = str(item.get("assistant_status", "")).strip()
        assistant_action = str(item.get("assistant_action", "")).strip()
        assistant_reason = str(item.get("assistant_reason", "")).strip()
        if not candidate_id or not assistant_status or not assistant_action or not assistant_reason:
            raise ValueError(f"Incomplete decision item for {candidate_id or 'unknown candidate'}.")
        decision_ids.append(candidate_id)
        decision_rows.append(
            {
                "candidate_id": candidate_id,
                "assistant_status": assistant_status,
                "assistant_action": assistant_action,
                "assistant_reason": assistant_reason,
            }
        )

    unresolved_ids = [str(item).strip() for item in unresolved if str(item).strip()]
    expected_ids = set(chunk.candidate_ids)
    seen_ids = set(decision_ids)
    unresolved_set = set(unresolved_ids)
    if len(decision_ids) != len(seen_ids):
        raise ValueError("Duplicate candidate_id inside decisions array.")
    if seen_ids - expected_ids:
        raise ValueError("Decisions contain candidate_id values outside the chunk.")
    if unresolved_set - expected_ids:
        raise ValueError("unresolved_candidate_ids contain values outside the chunk.")
    if seen_ids & unresolved_set:
        raise ValueError("candidate_id present in both decisions and unresolved_candidate_ids.")
    missing = expected_ids - seen_ids - unresolved_set
    if missing:
        raise ValueError(f"Response omitted candidate_id values: {sorted(missing)[:5]}")
    if unresolved_ids and not allow_unresolved:
        raise ValueError(f"Chunk has unresolved ids but allow_unresolved=false: {unresolved_ids[:5]}")
    return decision_rows


def run_chunk(args: argparse.Namespace, chunk: ChunkSpec) -> tuple[ChunkSpec, list[dict[str, str]]]:
    schema_path = SEARCH_SCHEMA_PATH if args.kind == "search" else RSYA_SCHEMA_PATH
    prompt_text = chunk.prompt_path.read_text(encoding="utf-8")
    retry_suffix = (
        "\n\nRETRY INSTRUCTION:\n"
        "- The previous attempt failed schema/coverage validation.\n"
        "- Re-read the whole chunk and return one decision for every candidate_id.\n"
        "- Do not omit rows. Do not return extra ids. unresolved_candidate_ids must stay empty unless truly impossible.\n"
    )
    last_error = "unknown"
    for attempt in range(1, args.max_attempts + 1):
        chunk.response_path.unlink(missing_ok=True)
        command = codex_command(args, schema_path, chunk.response_path)
        prompt_for_attempt = prompt_text if attempt == 1 else prompt_text + retry_suffix
        with chunk.stdout_path.open("a", encoding="utf-8") as stdout_fh, chunk.stderr_path.open("a", encoding="utf-8") as stderr_fh:
            stdout_fh.write(f"\n=== attempt {attempt} started {datetime.now().isoformat()} ===\n")
            stderr_fh.write(f"\n=== attempt {attempt} started {datetime.now().isoformat()} ===\n")
            try:
                child_env = dict(os.environ)
                child_env["CODEX_HOME"] = str(chunk.codex_home)
                completed = subprocess.run(
                    command,
                    input=prompt_for_attempt,
                    text=True,
                    cwd=str(args.project_root.resolve()),
                    env=child_env,
                    stdout=stdout_fh,
                    stderr=stderr_fh,
                    timeout=args.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                last_error = f"timeout after {args.timeout_seconds}s"
                stderr_fh.write(last_error + "\n")
                continue
        if completed.returncode != 0:
            last_error = f"codex exit code {completed.returncode}"
            continue
        if not chunk.response_path.exists():
            last_error = "missing response file"
            continue
        try:
            payload = load_json(chunk.response_path)
            decisions = validate_chunk_response(payload, chunk, allow_unresolved=args.allow_unresolved)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue
        return chunk, decisions
    raise RuntimeError(f"{chunk.chunk_id} failed after {args.max_attempts} attempts: {last_error}")


def merge_decisions(existing_path: Path, new_rows: list[dict[str, str]]) -> None:
    fieldnames = ["candidate_id", "assistant_status", "assistant_action", "assistant_reason"]
    existing_rows: list[dict[str, str]] = []
    if existing_path.exists():
        existing_rows = load_tsv(existing_path)
    by_id: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in existing_rows:
        candidate_id = str(row.get("candidate_id", "")).strip()
        if not candidate_id:
            continue
        if candidate_id not in by_id:
            order.append(candidate_id)
        by_id[candidate_id] = {
            "candidate_id": candidate_id,
            "assistant_status": str(row.get("assistant_status", "")).strip(),
            "assistant_action": str(row.get("assistant_action", "")).strip(),
            "assistant_reason": str(row.get("assistant_reason", "")).strip(),
        }
    for row in new_rows:
        candidate_id = row["candidate_id"]
        if candidate_id not in by_id:
            order.append(candidate_id)
        by_id[candidate_id] = row
    merged_rows = [by_id[candidate_id] for candidate_id in order]
    write_tsv(existing_path, merged_rows, fieldnames)


def main() -> int:
    args = parse_args()
    args.project_root = args.project_root.expanduser().resolve()
    args.queue = args.queue.expanduser().resolve()
    args.manual_decisions = normalize_paths(args.manual_decisions)
    args.extra_context = normalize_paths(args.extra_context)
    for attr in ("output_dir", "merge_into", "overlay", "global_skill", "local_skill", "product_catalog", "search_rules", "rsya_rules", "lessons"):
        value = getattr(args, attr, None)
        if value is not None:
            setattr(args, attr, value.expanduser().resolve())

    chunks, _queue_fieldnames = prepare_chunks(args)
    output_dir = (args.output_dir or default_output_dir(args.queue, args.kind)).expanduser().resolve()
    if args.dry_run:
        print(json.dumps({"ok": True, "prepared_chunks": len(chunks), "output_dir": str(output_dir)}, ensure_ascii=False))
        return 0

    all_decisions: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        future_map = {pool.submit(run_chunk, args, chunk): chunk for chunk in chunks}
        ordered_results: dict[str, list[dict[str, str]]] = {}
        for future in as_completed(future_map):
            chunk = future_map[future]
            try:
                finished_chunk, decisions = future.result()
                ordered_results[finished_chunk.chunk_id] = decisions
                decision_path = output_dir / "decisions" / f"{finished_chunk.chunk_id}.tsv"
                write_tsv(decision_path, decisions, ["candidate_id", "assistant_status", "assistant_action", "assistant_reason"])
            except Exception as exc:  # noqa: BLE001
                failures.append({"chunk_id": chunk.chunk_id, "error": str(exc)})

    if failures:
        (output_dir / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "output_dir": str(output_dir), "failures": failures}, ensure_ascii=False))
        return 1

    for chunk in chunks:
        all_decisions.extend(ordered_results.get(chunk.chunk_id, []))

    aggregate_path = output_dir / "aggregated_manual_decisions.tsv"
    write_tsv(aggregate_path, all_decisions, ["candidate_id", "assistant_status", "assistant_action", "assistant_reason"])
    if args.merge_into is not None:
        merge_decisions(args.merge_into, all_decisions)

    summary = {
        "ok": True,
        "kind": args.kind,
        "prepared_chunks": len(chunks),
        "decision_rows": len(all_decisions),
        "output_dir": str(output_dir),
        "aggregate_path": str(aggregate_path),
        "merged_into": str(args.merge_into) if args.merge_into else None,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "sandbox": args.sandbox,
        "approval_policy": args.approval_policy,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
