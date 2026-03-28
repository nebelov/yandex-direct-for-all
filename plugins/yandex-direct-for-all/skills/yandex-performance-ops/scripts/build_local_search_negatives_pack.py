#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


STOP_WORD_RE = re.compile(r"(?:стоп|минус)-?слово `([^`]+)`", re.IGNORECASE)
PHRASE_MINUS_RE = re.compile(r"фразовый минус `([^`]+)`", re.IGNORECASE)
API_V501 = "https://api.direct.yandex.com/json/v501"

_SOFT_SUFFIXES = (
    "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "ую", "юю",
    "ой", "ей", "ий", "ый", "ая", "яя", "ое", "ее", "ом", "ем", "ах", "ях",
    "ам", "ям", "ы", "и", "а", "я", "е", "у", "ю", "о",
)
_ADJECTIVE_SUFFIXES = (
    "ованный", "еванный", "ированный", "ированный", "ённый", "енный",
    "ованные", "еванные", "ированные", "ённые", "енные",
    "ованная", "еванная", "ированная", "ённая", "енная",
    "ованное", "еванное", "ированное", "ённое", "енное",
    "енный", "ённый", "анный", "янный", "овой", "евый", "овый", "евой",
    "ический", "ичный", "тивный", "альный", "ельный", "ильный", "ичный",
    "чатый", "истый", "овой", "овый", "ский", "ческий", "шный",
    "ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие",
)
_REASON_BRAND_MARKERS = (
    "бренд", "конкурент", "чуж", "sku", "витрин", "магазин", "продав", "каталог",
)
_REASON_B2B_MARKERS = (
    "поставщик", "поставщики", "производител", "b2b",
)
_ALT_CLASS_MARKERS = (
    "электрокарниз", "электрическ", "душ", "ванн", "огражден", "ступен",
    "вагонк", "вентиляц", "сантехничес", "столешниц", "зеркал", "кабель",
    "провод", "лючк", "калошниц", "книжк", "протектор", "рейк", "порог",
    "короб", "приточ", "фанер", "шум", "крепеж", "креплен",
)
_LOW_CONFIDENCE_REASON_MARKERS = (
    "мусорн", "искаж", "обрезан", "кроссворд", "информацион",
)
_GENERIC_NAVIGATION_REJECT = {"центр", "магазин", "каталог"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local Search negatives apply-pack from manual decisions.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--manual-decisions", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=("stop_word_only", "with_phrase_minus"),
        default="stop_word_only",
        help="Use strict stop-word-only mode by default; phrase-minus route fixes can be enabled explicitly.",
    )
    parser.add_argument(
        "--allow-zero-signal",
        action="store_true",
        help="Include rows with 0 clicks and 0 cost. Disabled by default for strict pre-apply packs.",
    )
    return parser.parse_args()


def load_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def soft_token(value: str) -> str:
    token = re.sub(r"^[!+]+", "", value.strip()).casefold().replace("ё", "е")
    token = re.sub(r"[^0-9a-zа-я_-]+", "", token)
    if len(token) <= 4:
        return token
    for suffix in _SOFT_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def soft_phrase_key(value: Any) -> str:
    tokens: list[str] = []
    for raw in re.split(r"\s+", str(value or "").strip()):
        token = soft_token(raw)
        if token:
            tokens.append(token)
    return " ".join(sorted(tokens))


def word_count(value: Any) -> int:
    return len([part for part in re.split(r"\s+", str(value or "").strip()) if part])


def parse_candidate_id(candidate_id: str) -> tuple[str, str, str]:
    parts = str(candidate_id or "").split("||", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


def current_criterion_conflict(negative_keyword: str, criterion: str) -> bool:
    neg_soft = soft_phrase_key(negative_keyword)
    if not neg_soft:
        return False
    criterion_soft = {soft_token(raw) for raw in re.split(r"\s+", normalize_text(criterion)) if soft_token(raw)}
    neg_tokens = [soft_token(raw) for raw in re.split(r"\s+", normalize_text(negative_keyword)) if soft_token(raw)]
    if not neg_tokens:
        return False
    return any(token in criterion_soft for token in neg_tokens)


def has_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = normalize_text(text).casefold().replace("ё", "е")
    return any(marker in lowered for marker in markers)


def has_vowel(token: str) -> bool:
    return bool(re.search(r"[aeiouyаеиоуыэюя]", token.casefold()))


def is_adjective_like(token: str) -> bool:
    lowered = normalize_text(token).casefold().replace("ё", "е")
    return any(lowered.endswith(suffix) for suffix in _ADJECTIVE_SUFFIXES)


def high_confidence_stop_word(item: dict[str, Any], keyword_frequency: dict[str, int]) -> tuple[bool, str]:
    keyword = normalize_text(item.get("negative_keyword")).casefold().replace("ё", "е")
    query = normalize_text(item.get("query")).casefold().replace("ё", "е")
    reason = normalize_text(item.get("assistant_reason")).casefold().replace("ё", "е")
    soft = soft_token(keyword)
    if not soft:
        return False, "empty_soft_keyword"
    if re.fullmatch(r"\d+", keyword):
        return False, "numeric_code_keyword"
    if len(soft) < 4:
        return False, "keyword_too_short"
    if soft in _GENERIC_NAVIGATION_REJECT:
        return False, "generic_navigation_keyword"
    if not has_vowel(soft) and not re.fullmatch(r"[a-z0-9._-]+", soft):
        return False, "no_vowels_non_brand"
    if query == keyword and has_any_marker(reason, _LOW_CONFIDENCE_REASON_MARKERS):
        return False, "query_equals_low_confidence_garbage"

    brand_or_vendor = has_any_marker(reason, _REASON_BRAND_MARKERS) or has_any_marker(query, _REASON_BRAND_MARKERS)
    b2b_intent = has_any_marker(reason, _REASON_B2B_MARKERS) or has_any_marker(query, _REASON_B2B_MARKERS)
    alt_class = has_any_marker(reason, _ALT_CLASS_MARKERS) or has_any_marker(query, _ALT_CLASS_MARKERS)
    low_confidence = has_any_marker(reason, _LOW_CONFIDENCE_REASON_MARKERS)
    latin_only = bool(re.fullmatch(r"[a-z0-9._-]+", keyword))
    repeated = keyword_frequency.get(keyword, 0) >= 2

    if is_adjective_like(keyword):
        return False, "adjective_like_single_word"
    if brand_or_vendor or b2b_intent:
        return True, "stable_brand_or_b2b"
    if low_confidence:
        return False, "low_confidence_reason"
    if latin_only:
        return True, "latin_brand_like"
    if alt_class:
        return True, "explicit_alt_class_marker"
    if repeated:
        return True, "repeated_keyword"
    return False, "single_low_confidence_keyword"


def load_runtime(project_root: Path) -> tuple[str, str]:
    package_root = project_root / "direct-orchestrator" / "src"
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from direct_orchestrator.services.audience_apply_runtime import load_direct_runtime  # type: ignore

    config_path = project_root / ".codex" / "yandex-performance-client.json"
    _runtime, login, token = load_direct_runtime(project_root, config_path)
    return login, token


def direct_call(token: str, login: str, service: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        f"{API_V501}/{service}",
        data=json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": "ru",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {service}.{method}: {detail}") from exc


def fetch_campaign_adgroups(token: str, login: str, campaign_ids: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for start in range(0, len(campaign_ids), 10):
        batch = campaign_ids[start : start + 10]
        payload = direct_call(
            token,
            login,
            "adgroups",
            "get",
            {
                "SelectionCriteria": {"CampaignIds": batch},
                "FieldNames": ["Id", "CampaignId", "Name", "NegativeKeywords"],
            },
        )
        rows.extend(payload.get("result", {}).get("AdGroups", payload.get("AdGroups", [])) or [])
    return rows


def get_negative_keywords(row: dict[str, Any]) -> list[str]:
    raw = row.get("NegativeKeywords") or {}
    items = raw.get("Items") or [] if isinstance(raw, dict) else []
    cleaned: list[str] = []
    for item in items:
        phrase = normalize_text(item)
        if phrase and phrase not in cleaned:
            cleaned.append(phrase)
    return cleaned


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    queue_rows, _ = load_tsv(args.queue.expanduser().resolve())
    decision_rows, _ = load_tsv(args.manual_decisions.expanduser().resolve())
    decisions_by_id = {normalize_text(row.get("candidate_id")): row for row in decision_rows if normalize_text(row.get("candidate_id"))}

    merged_rows: list[dict[str, str]] = []
    for row in queue_rows:
        candidate_id = normalize_text(row.get("candidate_id"))
        merged = dict(row)
        if candidate_id in decisions_by_id:
            for field in ("assistant_status", "assistant_action", "assistant_reason"):
                value = normalize_text(decisions_by_id[candidate_id].get(field))
                if value:
                    merged[field] = value
        merged_rows.append(merged)

    candidate_items: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    affected_campaign_ids: set[int] = set()
    for row in merged_rows:
        action = normalize_text(row.get("assistant_action"))
        if not action:
            continue
        candidate_id = normalize_text(row.get("candidate_id"))
        campaign_id_str, ad_group_name, query = parse_candidate_id(candidate_id)
        if not campaign_id_str or not ad_group_name:
            continue
        campaign_id = int(campaign_id_str)
        campaign_name = normalize_text(row.get("campaign_name"))
        criterion = normalize_text(row.get("criterion"))
        extracted: list[tuple[str, str]] = []
        for value in STOP_WORD_RE.findall(action):
            keyword = normalize_text(value)
            if keyword:
                extracted.append(("stop_word", keyword))
        if args.mode == "with_phrase_minus":
            for value in PHRASE_MINUS_RE.findall(action):
                keyword = normalize_text(value)
                if keyword:
                    extracted.append(("negative_phrase", keyword))
        if not extracted:
            continue
        clicks_value = float(str(row.get("clicks") or "0").replace(",", ".") or 0)
        cost_value = float(str(row.get("cost") or "0").replace(",", ".") or 0)
        if not args.allow_zero_signal and clicks_value <= 0 and cost_value <= 0:
            continue
        for negative_kind, negative_keyword in extracted:
            if word_count(negative_keyword) > 7:
                blocked_items.append(
                    {
                        "candidate_id": candidate_id,
                        "campaign_id": campaign_id,
                        "campaign_name": campaign_name,
                        "ad_group_name": ad_group_name,
                        "negative_keyword": negative_keyword,
                        "reason": "Минус-фраза длиннее 7 слов.",
                    }
                )
                continue
            if current_criterion_conflict(negative_keyword, criterion):
                blocked_items.append(
                    {
                        "candidate_id": candidate_id,
                        "campaign_id": campaign_id,
                        "campaign_name": campaign_name,
                        "ad_group_name": ad_group_name,
                        "negative_keyword": negative_keyword,
                        "reason": "Negative keyword конфликтует с current criterion группы.",
                    }
                )
                continue
            candidate_items.append(
                {
                    "candidate_id": candidate_id,
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "ad_group_name": ad_group_name,
                    "negative_kind": negative_kind,
                    "negative_keyword": negative_keyword,
                    "assistant_action": action,
                    "assistant_reason": normalize_text(row.get("assistant_reason")),
                    "clicks": normalize_text(row.get("clicks")) or "0",
                    "cost": normalize_text(row.get("cost")) or "0.00",
                    "current_criterion": criterion,
                    "query": query,
                }
            )
            affected_campaign_ids.add(campaign_id)

    keyword_frequency: dict[str, int] = {}
    for item in candidate_items:
        keyword = normalize_text(item.get("negative_keyword")).casefold().replace("ё", "е")
        if keyword:
            keyword_frequency[keyword] = keyword_frequency.get(keyword, 0) + 1

    strict_candidate_items: list[dict[str, Any]] = []
    for item in candidate_items:
        ok, strict_reason = high_confidence_stop_word(item, keyword_frequency)
        if ok:
            strict_candidate_items.append(item)
            continue
        blocked_items.append(
            {
                "candidate_id": item["candidate_id"],
                "campaign_id": item["campaign_id"],
                "campaign_name": item["campaign_name"],
                "ad_group_name": item["ad_group_name"],
                "negative_keyword": item["negative_keyword"],
                "reason": f"Strict stop-word gate rejected candidate: {strict_reason}.",
            }
        )

    login, token = load_runtime(project_root)
    adgroup_rows = fetch_campaign_adgroups(token, login, sorted(affected_campaign_ids))
    adgroup_index: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in adgroup_rows:
        key = (int(row.get("CampaignId") or 0), normalize_text(row.get("Name")))
        adgroup_index.setdefault(key, []).append(row)

    operations_by_adgroup: dict[int, dict[str, Any]] = {}
    unresolved_items: list[dict[str, Any]] = []
    for item in strict_candidate_items:
        matches = adgroup_index.get((int(item["campaign_id"]), normalize_text(item["ad_group_name"]))) or []
        if not matches:
            unresolved_items.append({**item, "reason": "Не найдена live-группа по campaign_id + ad_group_name."})
            continue
        for adgroup in matches:
            adgroup_id = int(adgroup.get("Id") or 0)
            before_keywords = get_negative_keywords(adgroup)
            bucket = operations_by_adgroup.setdefault(
                adgroup_id,
                {
                    "campaign_id": int(item["campaign_id"]),
                    "campaign_name": item["campaign_name"],
                    "adgroup_id": adgroup_id,
                    "adgroup_name": item["ad_group_name"],
                    "before_keywords": before_keywords,
                    "phrases_to_add": [],
                    "evidence_rows": [],
                },
            )
            existing_soft = {soft_phrase_key(value) for value in bucket["before_keywords"] if soft_phrase_key(value)}
            current_soft = {soft_phrase_key(value) for value in bucket["phrases_to_add"] if soft_phrase_key(value)}
            target_soft = soft_phrase_key(item["negative_keyword"])
            if target_soft and target_soft not in existing_soft and target_soft not in current_soft:
                bucket["phrases_to_add"].append(item["negative_keyword"])
            bucket["evidence_rows"].append(item)

    operations: list[dict[str, Any]] = []
    for adgroup_id, bucket in sorted(operations_by_adgroup.items(), key=lambda pair: (pair[1]["campaign_name"], pair[1]["adgroup_name"], pair[0])):
        if not bucket["phrases_to_add"]:
            continue
        operations.append(
            {
                **bucket,
                "after_keywords": bucket["before_keywords"] + bucket["phrases_to_add"],
                "keywords_to_add": list(bucket["phrases_to_add"]),
                "added_count": len(bucket["phrases_to_add"]),
            }
        )

    pack = {
        "pack_kind": "search_negatives",
        "status": "ready" if operations else "blocked",
        "generated_locally": True,
        "affected_campaign_count": len({op["campaign_id"] for op in operations}),
        "affected_adgroup_count": len(operations),
        "negative_phrase_count": sum(len(op["phrases_to_add"]) for op in operations),
        "stop_word_count": 0,
        "operations": operations,
        "blocked_items": blocked_items,
        "unresolved_items": unresolved_items,
    }
    summary = {
        "status": pack["status"],
        "affected_campaign_count": pack["affected_campaign_count"],
        "affected_adgroup_count": pack["affected_adgroup_count"],
        "negative_phrase_count": pack["negative_phrase_count"],
        "blocked_item_count": len(blocked_items),
        "unresolved_item_count": len(unresolved_items),
    }

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "search_negatives_local_pack.json", pack)
    write_json(output_dir / "search_negatives_local_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if operations else 1


if __name__ == "__main__":
    raise SystemExit(main())
