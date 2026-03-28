#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


RULE_FIELDS = [
    "rule_id",
    "rule_source",
    "decision",
    "marker_kind",
    "match_mode",
    "marker_norm",
    "marker_display",
    "scope_level",
    "campaign_id",
    "ad_group_name",
    "ad_group_name_regex",
    "include_pattern",
    "exclude_pattern",
    "assistant_action",
    "assistant_reason",
    "source_reference",
]

FUNCTION_WORDS = {
    "а", "без", "бы", "в", "во", "все", "всё", "где", "да", "для", "до", "его", "ее", "её",
    "если", "же", "за", "и", "из", "или", "им", "их", "к", "как", "ко", "ли", "на", "над",
    "не", "но", "о", "об", "от", "по", "под", "при", "про", "с", "со", "то", "у", "что",
    "это", "этот", "эта", "эти", "тот", "та", "те", "для", "из", "под", "над", "при",
}
NEGATIVE_NOISE_STEMS = {
    "куп", "цен", "стоим", "размер", "ширин", "длин", "высот", "толщ", "цвет",
    "черн", "бел", "сер", "мат", "глянц", "фото", "видео", "отзыв", "обзор",
    "сдел", "дел", "нужн", "лучш", "можн", "нуж", "скольк", "какой", "какая",
    "какие", "зачем", "чем", "где", "когд", "монтаж", "установ", "установк",
    "интерьер", "иде", "пример", "вариант", "схем", "угол", "угл", "ценник",
}
BROAD_BLOCK_PREFIXES = (
    "тенев", "скрыт", "профил", "плинтус", "карниз", "откос", "подсвет", "светод",
    "потол", "двер", "окон", "алюмин", "парящ", "стенов", "гипсокарт", "встроенн",
    "напольн", "потолоч", "дверн", "ламинат", "пол", "гкл",
)
NEGATIVE_NOISE_PREFIXES = (
    "куп", "цен", "стоим", "размер", "ширин", "длин", "высот", "толщ", "цвет",
    "черн", "бел", "сер", "мат", "глянц", "фото", "видео", "отзыв", "обзор",
    "сдел", "дел", "лучш", "скольк", "како", "зачем", "чем", "монтаж", "установ",
    "интерьер", "пример", "вариант", "схем", "угол", "креплен", "крепеж", "соедин",
    "провод", "ванн", "комнат",
)
TOKEN_RE = re.compile(r"[a-zа-яё0-9-]+", re.IGNORECASE)
STOP_WORD_RE = re.compile(r"(?:стоп|минус)-?слово `([^`]+)`", re.IGNORECASE)
PHRASE_MINUS_RE = re.compile(r"фразовый минус `([^`]+)`", re.IGNORECASE)
GROWTH_RE = re.compile(r"(?:growth-тест|Выделить|вынести запрос в growth-тест) `([^`]+)`", re.IGNORECASE)
TARGET_SYNONYM_RE = re.compile(r"^- (.+)$", re.MULTILINE)
SECTION_HEADER_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
COMMON_RUSSIAN_ENDINGS = [
    "иями", "ями", "ами", "его", "ого", "ему", "ому", "ыми", "ими", "иях", "иях", "ях", "ах",
    "ию", "ью", "ия", "ья", "ие", "ье", "ий", "ый", "ой", "ая", "яя", "ое", "ее", "ые", "ие",
    "ым", "им", "ом", "ем", "ую", "юю", "ов", "ев", "ей", "ам", "ям", "ом", "ем", "ах", "ях",
    "ы", "и", "а", "я", "е", "о", "у", "ю",
]


@dataclass(frozen=True)
class Rule:
    row: dict[str, str]

    @property
    def rule_id(self) -> str:
        return (self.row.get("rule_id") or "").strip()

    @property
    def decision(self) -> str:
        return (self.row.get("decision") or "").strip().lower()

    @property
    def marker_kind(self) -> str:
        return (self.row.get("marker_kind") or "").strip().lower()

    @property
    def match_mode(self) -> str:
        return (self.row.get("match_mode") or "").strip().lower()

    @property
    def marker_norm(self) -> str:
        return normalize_text(self.row.get("marker_norm") or "")

    @property
    def campaign_id(self) -> str:
        return (self.row.get("campaign_id") or "").strip()

    @property
    def ad_group_name(self) -> str:
        return normalize_text(self.row.get("ad_group_name") or "")

    @property
    def ad_group_name_regex(self) -> str:
        return (self.row.get("ad_group_name_regex") or "").strip()

    @property
    def include_pattern(self) -> str:
        return (self.row.get("include_pattern") or "").strip()

    @property
    def exclude_pattern(self) -> str:
        return (self.row.get("exclude_pattern") or "").strip()

    def matches_scope(self, row: dict[str, str]) -> bool:
        campaign_id = str(row.get("campaign_id") or "").strip()
        ad_group = normalize_text(row.get("ad_group_name") or "")
        scope_level = (self.row.get("scope_level") or "").strip().lower() or "account"
        if self.campaign_id and campaign_id != self.campaign_id:
            return False
        if scope_level == "adgroup" and self.ad_group_name and ad_group != self.ad_group_name:
            return False
        if self.ad_group_name_regex:
            try:
                if not re.search(self.ad_group_name_regex, row.get("ad_group_name") or "", flags=re.IGNORECASE):
                    return False
            except re.error:
                return False
        return True

    def matches_row(self, row: dict[str, str]) -> bool:
        if not self.matches_scope(row):
            return False
        query = normalize_text(row.get("query") or "")
        token_stems = set(extract_token_stems(row.get("query") or ""))
        phrase_stems = set(build_row_phrase_stems(row.get("query") or ""))
        if self.match_mode == "token_stem":
            matched = self.marker_norm in token_stems
        elif self.match_mode == "phrase_stem":
            matched = self.marker_norm in phrase_stems
        elif self.match_mode == "query_regex":
            try:
                matched = bool(re.search(self.include_pattern, row.get("query") or "", flags=re.IGNORECASE))
            except re.error:
                return False
            if matched and self.exclude_pattern:
                try:
                    if re.search(self.exclude_pattern, row.get("query") or "", flags=re.IGNORECASE):
                        return False
                except re.error:
                    return False
        else:
            return False
        if not matched:
            return False
        if self.exclude_pattern and self.match_mode != "query_regex":
            try:
                if re.search(self.exclude_pattern, row.get("query") or "", flags=re.IGNORECASE):
                    return False
            except re.error:
                return False
        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search negative-marker engine: bootstrap rules, apply rules, build marker cards.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap-rules")
    bootstrap.add_argument("--search-rules", required=True, type=Path)
    bootstrap.add_argument("--manual-decisions", nargs="*", type=Path, default=[])
    bootstrap.add_argument("--output-rules", required=True, type=Path)

    apply_cmd = subparsers.add_parser("apply-rules")
    apply_cmd.add_argument("--queue", required=True, type=Path)
    apply_cmd.add_argument("--rules", required=True, type=Path)
    apply_cmd.add_argument("--output-active", required=True, type=Path)
    apply_cmd.add_argument("--output-excluded", required=True, type=Path)
    apply_cmd.add_argument("--output-growth", required=True, type=Path)
    apply_cmd.add_argument("--output-hold", type=Path)
    apply_cmd.add_argument("--output-summary", required=True, type=Path)
    apply_cmd.add_argument("--include-resolved", action="store_true")

    build = subparsers.add_parser("build-markers")
    build.add_argument("--queue", required=True, type=Path)
    build.add_argument("--rules", type=Path)
    build.add_argument("--search-rules", required=True, type=Path)
    build.add_argument("--product-catalog", required=True, type=Path)
    build.add_argument("--output-cards", required=True, type=Path)
    build.add_argument("--output-examples", required=True, type=Path)
    build.add_argument("--output-summary", required=True, type=Path)
    build.add_argument("--output-negative-candidates", type=Path)
    build.add_argument("--output-protected-hold", type=Path)
    build.add_argument("--top-examples", type=int, default=5)
    build.add_argument("--min-token-rows", type=int, default=2)
    build.add_argument("--min-token-cost", type=float, default=200.0)
    build.add_argument("--min-phrase-rows", type=int, default=2)
    build.add_argument("--min-phrase-cost", type=float, default=250.0)
    build.add_argument("--phrase-max-len", type=int, default=3)
    return parser.parse_args()


def load_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def normalize_text(value: str) -> str:
    lowered = (value or "").strip().casefold().replace("ё", "е")
    lowered = re.sub(r"[^0-9a-zа-я_-]+", " ", lowered)
    return " ".join(lowered.split())


def normalize_float(value: str | None) -> float:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def resolved(row: dict[str, str]) -> bool:
    return bool((row.get("assistant_status") or "").strip())


def token_surface(value: str) -> list[str]:
    return [token.casefold().replace("ё", "е") for token in TOKEN_RE.findall(value or "")]


def light_stem(token: str) -> str:
    token = normalize_text(token).replace(" ", "")
    if len(token) <= 4 or re.fullmatch(r"\d+", token):
        return token
    for ending in COMMON_RUSSIAN_ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 4:
            return token[: -len(ending)]
    return token


def extract_token_stems(text: str) -> list[str]:
    stems: list[str] = []
    for token in token_surface(text):
        if len(token) < 2:
            continue
        stems.append(light_stem(token))
    return stems


def token_is_suspicious(stem: str, protected_stems: set[str], ignored_stems: set[str]) -> bool:
    if not stem or len(stem) < 4:
        return False
    if stem in protected_stems or stem in ignored_stems or stem in FUNCTION_WORDS:
        return False
    if re.fullmatch(r"\d+", stem):
        return False
    if any(stem.startswith(prefix) for prefix in BROAD_BLOCK_PREFIXES):
        return False
    return True


def build_row_phrase_stems(text: str, max_len: int = 3) -> list[str]:
    surfaces = token_surface(text)
    phrases: list[str] = []
    for size in range(2, max_len + 1):
        for idx in range(0, len(surfaces) - size + 1):
            window = surfaces[idx : idx + size]
            if any(len(token) < 2 for token in window):
                continue
            stems = [light_stem(token) for token in window]
            phrases.append(" ".join(stems))
    return phrases


def parse_candidate_id(candidate_id: str) -> tuple[str, str, str]:
    parts = str(candidate_id or "").split("||", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


def build_rule_row(**kwargs: str) -> dict[str, str]:
    row = {field: "" for field in RULE_FIELDS}
    row.update({key: value for key, value in kwargs.items() if key in row})
    return row


def extract_phrase_minus_targets(action: str) -> list[str]:
    targets: list[str] = []
    for value in PHRASE_MINUS_RE.findall(action or ""):
        norm = normalize_text(value)
        if norm:
            targets.append(norm)
    return targets


def extract_growth_targets(action: str) -> list[str]:
    targets: list[str] = []
    for value in GROWTH_RE.findall(action or ""):
        norm = normalize_text(value)
        if norm:
            targets.append(norm)
    if "микроплинтус" in normalize_text(action or ""):
        targets.append("микроплинтус")
    if "теневой шов" in normalize_text(action or ""):
        targets.append("теневой шов")
    return sorted(set(targets))


def bootstrap_rules(args: argparse.Namespace) -> None:
    search_rules = json.loads(args.search_rules.read_text(encoding="utf-8"))
    rules: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_rule(row: dict[str, str]) -> None:
        key = (
            row.get("decision", ""),
            row.get("marker_kind", ""),
            row.get("match_mode", ""),
            row.get("marker_norm", ""),
            row.get("campaign_id", ""),
            row.get("ad_group_name", ""),
        )
        if key in seen:
            return
        seen.add(key)
        rules.append(row)

    for item in search_rules.get("safe_family_rules", []):
        add_rule(
            build_rule_row(
                rule_id=item.get("rule_id", ""),
                rule_source="search_rules.safe_family_rules",
                decision="exclude",
                marker_kind="legacy_rule",
                match_mode="query_regex",
                marker_norm=normalize_text(item.get("canonical_word", "")),
                marker_display=item.get("canonical_word", ""),
                scope_level=item.get("scope_level", "account"),
                campaign_id=str(item.get("campaign_id", "") or ""),
                ad_group_name=item.get("ad_group_name", ""),
                ad_group_name_regex=item.get("ad_group_name_regex", ""),
                include_pattern="|".join(item.get("patterns", [])),
                exclude_pattern="|".join(item.get("exclude_patterns", [])),
                assistant_action=f"Добавить стоп-слово `{item.get('canonical_word', '')}` в целевой группе.",
                assistant_reason=item.get("reason", ""),
                source_reference=item.get("rule_id", ""),
            )
        )

    for item in search_rules.get("growth_route_rules", []):
        add_rule(
            build_rule_row(
                rule_id=item.get("rule_id", ""),
                rule_source="search_rules.growth_route_rules",
                decision="park_growth",
                marker_kind="legacy_rule",
                match_mode="query_regex",
                marker_norm=normalize_text(item.get("route_label", "")),
                marker_display=item.get("route_label", ""),
                scope_level="account",
                include_pattern="|".join(item.get("patterns", [])),
                assistant_action=item.get("recommendation", ""),
                assistant_reason=item.get("reason", ""),
                source_reference=item.get("rule_id", ""),
            )
        )

    for decision_path in args.manual_decisions:
        if not decision_path.exists():
            continue
        for row in load_tsv(decision_path):
            if not resolved(row):
                continue
            candidate_id = (row.get("candidate_id") or "").strip()
            if not candidate_id:
                continue
            campaign_id, ad_group_name, _query = parse_candidate_id(candidate_id)
            action = row.get("assistant_action", "") or ""
            reason = row.get("assistant_reason", "") or ""
            for word in STOP_WORD_RE.findall(action):
                norm = light_stem(word)
                if not norm:
                    continue
                add_rule(
                    build_rule_row(
                        rule_id=f"manual-token-{abs(hash((candidate_id, norm))) % 10**10}",
                        rule_source="manual_decisions.stop_word",
                        decision="exclude",
                        marker_kind="token",
                        match_mode="token_stem",
                        marker_norm=norm,
                        marker_display=word,
                        scope_level="adgroup",
                        campaign_id=campaign_id,
                        ad_group_name=ad_group_name,
                        assistant_action=action,
                        assistant_reason=reason,
                        source_reference=candidate_id,
                    )
                )
            for phrase in extract_phrase_minus_targets(action):
                add_rule(
                    build_rule_row(
                        rule_id=f"manual-phrase-{abs(hash((candidate_id, phrase))) % 10**10}",
                        rule_source="manual_decisions.phrase_minus",
                        decision="exclude",
                        marker_kind="phrase",
                        match_mode="phrase_stem",
                        marker_norm=" ".join(light_stem(token) for token in phrase.split()),
                        marker_display=phrase,
                        scope_level="adgroup",
                        campaign_id=campaign_id,
                        ad_group_name=ad_group_name,
                        assistant_action=action,
                        assistant_reason=reason,
                        source_reference=candidate_id,
                    )
                )
            for growth in extract_growth_targets(action):
                add_rule(
                    build_rule_row(
                        rule_id=f"manual-growth-{abs(hash((candidate_id, growth))) % 10**10}",
                        rule_source="manual_decisions.growth",
                        decision="park_growth",
                        marker_kind="phrase" if " " in growth else "token",
                        match_mode="phrase_stem" if " " in growth else "token_stem",
                        marker_norm=" ".join(light_stem(token) for token in growth.split()),
                        marker_display=growth,
                        scope_level="account",
                        campaign_id="",
                        ad_group_name="",
                        assistant_action=action,
                        assistant_reason=reason,
                        source_reference=candidate_id,
                    )
                )

    write_tsv(args.output_rules, rules, RULE_FIELDS)
    print(
        json.dumps(
            {
                "output_rules": str(args.output_rules),
                "rules_total": len(rules),
                "safe_rules_bootstrapped": sum(1 for row in rules if row["rule_source"] == "search_rules.safe_family_rules"),
                "growth_rules_bootstrapped": sum(1 for row in rules if row["rule_source"] == "search_rules.growth_route_rules"),
                "manual_rules_bootstrapped": sum(1 for row in rules if row["rule_source"].startswith("manual_decisions")),
            },
            ensure_ascii=False,
        )
    )


def load_rules(path: Path) -> list[Rule]:
    return [Rule(row) for row in load_tsv(path) if (row.get("decision") or "").strip()]


def match_rules_by_decision(rules: list[Rule]) -> dict[str, list[Rule]]:
    grouped: dict[str, list[Rule]] = defaultdict(list)
    for rule in rules:
        grouped[rule.decision].append(rule)
    return grouped


def apply_rules(args: argparse.Namespace) -> None:
    queue_rows = load_tsv(args.queue)
    rules = load_rules(args.rules)
    grouped = match_rules_by_decision(rules)

    active_rows: list[dict[str, str]] = []
    excluded_rows: list[dict[str, str]] = []
    growth_rows: list[dict[str, str]] = []
    hold_rows: list[dict[str, str]] = []

    for row in queue_rows:
        if resolved(row) and not args.include_resolved:
            continue
        matched_growth = next((rule for rule in grouped.get("park_growth", []) if rule.matches_row(row)), None)
        if matched_growth:
            parked = dict(row)
            parked["matched_rule_id"] = matched_growth.rule_id
            parked["matched_rule_source"] = matched_growth.row.get("rule_source", "")
            parked["matched_rule_decision"] = matched_growth.decision
            growth_rows.append(parked)
            continue
        matched_hold = next((rule for rule in grouped.get("park_hold", []) if rule.matches_row(row)), None)
        if matched_hold:
            parked = dict(row)
            parked["matched_rule_id"] = matched_hold.rule_id
            parked["matched_rule_source"] = matched_hold.row.get("rule_source", "")
            parked["matched_rule_decision"] = matched_hold.decision
            parked["matched_action"] = matched_hold.row.get("assistant_action", "")
            parked["matched_reason"] = matched_hold.row.get("assistant_reason", "")
            hold_rows.append(parked)
            continue
        matched_exclude = next((rule for rule in grouped.get("exclude", []) if rule.matches_row(row)), None)
        if matched_exclude:
            excluded = dict(row)
            excluded["matched_rule_id"] = matched_exclude.rule_id
            excluded["matched_rule_source"] = matched_exclude.row.get("rule_source", "")
            excluded["matched_rule_decision"] = matched_exclude.decision
            excluded["matched_action"] = matched_exclude.row.get("assistant_action", "")
            excluded["matched_reason"] = matched_exclude.row.get("assistant_reason", "")
            excluded_rows.append(excluded)
            continue
        active_rows.append(dict(row))

    queue_fields = list(queue_rows[0].keys()) if queue_rows else []
    excluded_fields = queue_fields + ["matched_rule_id", "matched_rule_source", "matched_rule_decision", "matched_action", "matched_reason"]
    growth_fields = queue_fields + ["matched_rule_id", "matched_rule_source", "matched_rule_decision"]
    hold_fields = queue_fields + ["matched_rule_id", "matched_rule_source", "matched_rule_decision", "matched_action", "matched_reason"]
    write_tsv(args.output_active, active_rows, queue_fields)
    write_tsv(args.output_excluded, excluded_rows, excluded_fields)
    write_tsv(args.output_growth, growth_rows, growth_fields)
    if args.output_hold:
        write_tsv(args.output_hold, hold_rows, hold_fields)
    summary = {
        "queue": str(args.queue),
        "rules": str(args.rules),
        "total_rows_seen": len(queue_rows),
        "active_rows": len(active_rows),
        "excluded_rows": len(excluded_rows),
        "growth_rows": len(growth_rows),
        "hold_rows": len(hold_rows),
        "rule_counts": Counter(rule.decision for rule in rules),
    }
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def extract_protected_stems(search_rules: dict, product_catalog_text: str) -> tuple[set[str], set[str]]:
    protected_stems: set[str] = set()
    ignored_stems: set[str] = {light_stem(token) for token in search_rules.get("ignored_historical_tokens", [])}

    for section in ("protected_family_rules", "growth_route_rules"):
        for item in search_rules.get(section, []):
            protected_stems.add(light_stem(item.get("canonical_word", "")))
            for pattern in item.get("patterns", []):
                for token in token_surface(pattern):
                    protected_stems.add(light_stem(token))

    in_target_section = False
    for line in product_catalog_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_target_section = "ЦЕЛЕВЫЕ СИНОНИМЫ ПРОДУКТА" in stripped
            continue
        if in_target_section and stripped.startswith("- "):
            for token in token_surface(stripped[2:]):
                protected_stems.add(light_stem(token))
    for token in token_surface(product_catalog_text):
        if token in {"теневой", "профиль", "скрытый", "плинтус", "карниз", "откос", "подсветка", "светодиодный", "алюминиевый"}:
            protected_stems.add(light_stem(token))
    return protected_stems, ignored_stems


def extract_negative_driver_stems(rules: list[Rule]) -> set[str]:
    drivers: set[str] = set()
    for rule in rules:
        if rule.decision != "exclude":
            continue
        source = (rule.row.get("rule_source") or "").strip().lower()
        if source.startswith("manual_decisions.phrase_minus"):
            continue
        if rule.match_mode == "token_stem" and rule.marker_norm:
            drivers.add(rule.marker_norm)
        elif source == "search_rules.safe_family_rules":
            for token in token_surface(rule.row.get("marker_display") or ""):
                stem = light_stem(token)
                if stem:
                    drivers.add(stem)
            for token in token_surface(rule.include_pattern):
                stem = light_stem(token)
                if stem:
                    drivers.add(stem)
    return {
        stem for stem in drivers
        if stem
        and len(stem) >= 4
        and stem not in NEGATIVE_NOISE_STEMS
        and not any(stem.startswith(prefix) for prefix in NEGATIVE_NOISE_PREFIXES)
    }


def load_reviewed_marker_norms(rules_path: Path | None) -> set[tuple[str, str, str, str]]:
    if rules_path is None or not rules_path.exists():
        return set()
    reviewed: set[tuple[str, str, str, str]] = set()
    for row in load_tsv(rules_path):
        decision = (row.get("decision") or "").strip().lower()
        if decision not in {"exclude", "ignore", "park_growth", "park_hold"}:
            continue
        reviewed.add(
            (
                (row.get("marker_kind") or "").strip().lower(),
                (row.get("marker_norm") or "").strip(),
                (row.get("campaign_id") or "").strip(),
                normalize_text(row.get("ad_group_name") or ""),
            )
        )
    return reviewed


def classify_residual_row(
    row: dict[str, str],
    protected_stems: set[str],
    ignored_stems: set[str],
    negative_driver_stems: set[str],
) -> str:
    stems = [stem for stem in extract_token_stems(row.get("query") or "") if stem]
    if not stems:
        return "hold"
    suspicious_stems = [
        stem for stem in stems
        if token_is_suspicious(stem, protected_stems, ignored_stems)
        and stem not in NEGATIVE_NOISE_STEMS
        and not any(stem.startswith(prefix) for prefix in NEGATIVE_NOISE_PREFIXES)
    ]
    if not suspicious_stems:
        return "hold"
    if any(stem in negative_driver_stems for stem in suspicious_stems):
        return "negative_candidate"
    protected_hits = [stem for stem in stems if stem in protected_stems]
    if protected_hits:
        return "hold"
    return "negative_candidate"


def build_markers(args: argparse.Namespace) -> None:
    queue_rows = [row for row in load_tsv(args.queue) if not resolved(row)]
    search_rules = json.loads(args.search_rules.read_text(encoding="utf-8"))
    protected_stems, ignored_stems = extract_protected_stems(search_rules, args.product_catalog.read_text(encoding="utf-8"))
    rules = load_rules(args.rules) if args.rules and args.rules.exists() else []
    reviewed = load_reviewed_marker_norms(args.rules)
    negative_driver_stems = extract_negative_driver_stems(rules)
    negative_candidate_rows: list[dict[str, str]] = []
    protected_hold_rows: list[dict[str, str]] = []

    token_stats: dict[tuple[str, str, str], dict[str, object]] = {}
    phrase_stats: dict[tuple[str, str, str], dict[str, object]] = {}

    for row in queue_rows:
        bucket_type = classify_residual_row(row, protected_stems, ignored_stems, negative_driver_stems)
        if bucket_type == "hold":
            protected_hold_rows.append(dict(row))
            continue
        negative_candidate_rows.append(dict(row))
        campaign_id = str(row.get("campaign_id") or "").strip()
        ad_group_name = normalize_text(row.get("ad_group_name") or "")
        query = row.get("query") or ""
        cost = normalize_float(row.get("cost"))
        clicks = normalize_float(row.get("clicks"))
        surfaces = token_surface(query)
        stems = [light_stem(token) for token in surfaces]
        seen_token_keys: set[tuple[str, str, str]] = set()
        for surface, stem in zip(surfaces, stems):
            if not token_is_suspicious(stem, protected_stems, ignored_stems):
                continue
            key = (stem, campaign_id, ad_group_name)
            if key in reviewed or key in seen_token_keys:
                continue
            seen_token_keys.add(key)
            bucket = token_stats.setdefault(
                key,
                {
                    "surface_counter": Counter(),
                    "rows": [],
                    "cost": 0.0,
                    "clicks": 0.0,
                },
            )
            bucket["surface_counter"][surface] += 1
            bucket["rows"].append(row)
            bucket["cost"] += cost
            bucket["clicks"] += clicks

        seen_phrase_keys: set[tuple[str, str, str]] = set()
        for size in range(2, args.phrase_max_len + 1):
            for idx in range(0, len(surfaces) - size + 1):
                window_surfaces = surfaces[idx : idx + size]
                window_stems = stems[idx : idx + size]
                if all(not token_is_suspicious(stem, protected_stems, ignored_stems) for stem in window_stems):
                    continue
                if any(stem in FUNCTION_WORDS for stem in window_stems):
                    continue
                suspicious_window = [
                    stem for stem in window_stems
                    if token_is_suspicious(stem, protected_stems, ignored_stems)
                    and stem not in NEGATIVE_NOISE_STEMS
                    and not any(stem.startswith(prefix) for prefix in NEGATIVE_NOISE_PREFIXES)
                ]
                if not suspicious_window:
                    continue
                if any(stem in protected_stems for stem in window_stems) and not any(
                    stem in negative_driver_stems for stem in suspicious_window
                ):
                    continue
                phrase_norm = " ".join(window_stems)
                key = (phrase_norm, campaign_id, ad_group_name)
                if key in reviewed or key in seen_phrase_keys:
                    continue
                seen_phrase_keys.add(key)
                bucket = phrase_stats.setdefault(
                    key,
                    {
                        "surface_counter": Counter(),
                        "rows": [],
                        "cost": 0.0,
                        "clicks": 0.0,
                    },
                )
                bucket["surface_counter"][" ".join(window_surfaces)] += 1
                bucket["rows"].append(row)
                bucket["cost"] += cost
                bucket["clicks"] += clicks

    cards: list[dict[str, str]] = []
    examples: list[dict[str, str]] = []

    def append_marker_cards(kind: str, stats: dict[tuple[str, str, str], dict[str, object]], min_rows: int, min_cost: float) -> None:
        nonlocal cards, examples
        for (norm, campaign_id, ad_group_name), bucket in stats.items():
            rows = list(bucket["rows"])
            total_cost = float(bucket["cost"])
            if len(rows) < min_rows and total_cost < min_cost:
                continue
            display = bucket["surface_counter"].most_common(1)[0][0]
            marker_id = f"{kind}:{campaign_id}:{ad_group_name}:{norm}"
            sorted_rows = sorted(
                rows,
                key=lambda item: (
                    -normalize_float(item.get("cost")),
                    -normalize_float(item.get("clicks")),
                    str(item.get("query") or ""),
                ),
            )
            top_examples = sorted_rows[: args.top_examples]
            cards.append(
                {
                    "marker_id": marker_id,
                    "marker_kind": kind,
                    "marker_norm": norm,
                    "marker_display": display,
                    "campaign_id": campaign_id,
                    "ad_group_name": ad_group_name,
                    "matched_rows": str(len(rows)),
                    "matched_cost": f"{total_cost:.2f}",
                    "matched_clicks": f"{float(bucket['clicks']):.2f}",
                    "top_queries": " | ".join((item.get("query") or "") for item in top_examples),
                }
            )
            for rank, item in enumerate(top_examples, start=1):
                examples.append(
                    {
                        "marker_id": marker_id,
                        "marker_kind": kind,
                        "marker_norm": norm,
                        "rank": str(rank),
                        "candidate_id": item.get("candidate_id", ""),
                        "campaign_id": item.get("campaign_id", ""),
                        "ad_group_name": item.get("ad_group_name", ""),
                        "query": item.get("query", ""),
                        "clicks": item.get("clicks", ""),
                        "cost": item.get("cost", ""),
                    }
                )

    append_marker_cards("phrase", phrase_stats, args.min_phrase_rows, args.min_phrase_cost)
    append_marker_cards("token", token_stats, args.min_token_rows, args.min_token_cost)
    cards.sort(
        key=lambda row: (
            0 if row["marker_kind"] == "phrase" else 1,
            -normalize_float(row["matched_cost"]),
            -normalize_float(row["matched_clicks"]),
            -int(row["matched_rows"]),
            row["marker_display"],
        )
    )

    card_fields = [
        "marker_id",
        "marker_kind",
        "marker_norm",
        "marker_display",
        "campaign_id",
        "ad_group_name",
        "matched_rows",
        "matched_cost",
        "matched_clicks",
        "top_queries",
    ]
    example_fields = [
        "marker_id",
        "marker_kind",
        "marker_norm",
        "rank",
        "candidate_id",
        "campaign_id",
        "ad_group_name",
        "query",
        "clicks",
        "cost",
    ]
    write_tsv(args.output_cards, cards, card_fields)
    write_tsv(args.output_examples, examples, example_fields)
    if args.output_negative_candidates:
        write_tsv(args.output_negative_candidates, negative_candidate_rows, list(queue_rows[0].keys()) if queue_rows else [])
    if args.output_protected_hold:
        write_tsv(args.output_protected_hold, protected_hold_rows, list(queue_rows[0].keys()) if queue_rows else [])
    summary = {
        "queue": str(args.queue),
        "rules": str(args.rules) if args.rules else None,
        "search_rules": str(args.search_rules),
        "product_catalog": str(args.product_catalog),
        "rows_seen": len(queue_rows),
        "negative_candidate_rows": len(negative_candidate_rows),
        "protected_route_hold_rows": len(protected_hold_rows),
        "cards_total": len(cards),
        "phrase_cards": sum(1 for row in cards if row["marker_kind"] == "phrase"),
        "token_cards": sum(1 for row in cards if row["marker_kind"] == "token"),
        "protected_stems": len(protected_stems),
        "ignored_stems": len(ignored_stems),
        "negative_driver_stems": len(negative_driver_stems),
    }
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    args = parse_args()
    if args.command == "bootstrap-rules":
        bootstrap_rules(args)
        return
    if args.command == "apply-rules":
        apply_rules(args)
        return
    if args.command == "build-markers":
        build_markers(args)
        return
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
