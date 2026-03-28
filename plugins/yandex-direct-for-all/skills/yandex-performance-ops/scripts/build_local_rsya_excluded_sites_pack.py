#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT_DOMAIN_BLOCKLIST = {"yandex.ru", "ya.ru"}
API_V501 = "https://api.direct.yandex.com/json/v501"
PACKAGE_LIKE_RE = re.compile(r"^(?:com|ru|io|net|org|air)\.[a-z0-9_.-]+$", re.IGNORECASE)
DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$", re.IGNORECASE)
VPN_HINTS = ("vpn", "proxy", "unblock", "secure")
GAME_HINTS = (
    "game", "games", "puzzle", "match", "solitaire", "mahjong", "craft",
    "simulator", "chess", "checkers", "durak", "bubble", "rope", "birdsort",
    "jigsaw", "coloring", "arrowout", "block", "line98", "deeer", "stress",
)
DEFAULT_FORMULA = {
    "vpn_block": {"min_clicks": 3, "min_cost": 20.0, "min_ctr": 10.0},
    "retarget_app_block": {"min_clicks": 5, "min_cost": 20.0, "min_ctr": 10.0},
    "prospecting_app_block": {"min_clicks": 8, "min_cost": 60.0, "min_ctr": 12.0},
    "retarget_site_block": {"min_clicks": 3, "min_cost": 35.0, "min_ctr": 5.0},
    "prospecting_site_block": {"min_clicks": 4, "min_cost": 70.0, "min_ctr": 5.0},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local RSYA ExcludedSites after-packs from approved manual decisions.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--manual-decisions", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--placements-root", type=Path, default=None)
    parser.add_argument("--rules", type=Path, default=None)
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def load_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def load_rules(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_candidate_id(candidate_id: str) -> tuple[int, str]:
    left, _, right = str(candidate_id or "").partition("||")
    try:
        campaign_id = int(left.strip())
    except ValueError:
        return 0, ""
    return campaign_id, normalize_text(right)


def normalize(value: Any) -> str:
    return normalize_text(value).casefold()


def is_retarget_campaign(campaign_name: str) -> bool:
    text = normalize(campaign_name)
    return "ретаргет" in text or "retarget" in text


def to_float(value: Any) -> float:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def load_placements_for_campaigns(placements_root: Path | None, campaign_ids: list[int]) -> dict[tuple[int, str], dict[str, str]]:
    if placements_root is None or not placements_root.exists():
        return {}
    rows: dict[tuple[int, str], dict[str, str]] = {}
    all_path = placements_root / "all_placements.tsv"
    if all_path.exists():
        source_paths = [all_path]
    else:
        source_paths = [placements_root / f"placements_{campaign_id}.tsv" for campaign_id in campaign_ids]
    for path in source_paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    campaign_id = int(str(row.get("CampaignId") or row.get("campaign_id") or "").strip())
                except ValueError:
                    continue
                if campaign_id not in campaign_ids:
                    continue
                placement = normalize_text(row.get("Placement") or row.get("placement"))
                if not placement:
                    continue
                rows[(campaign_id, placement)] = row
    return rows


def classify_placement(placement: str, rules: dict[str, Any]) -> set[str]:
    placement_norm = normalize(placement)
    labels: set[str] = set()
    if placement_norm in {normalize(item) for item in rules.get("safe_exact_placements", [])}:
        labels.add("exact_safe_block")
    if placement_norm in {normalize(item) for item in rules.get("yandex_root_blocklist", [])}:
        labels.add("yandex_root")
    if any(hint in placement_norm for hint in map(normalize, rules.get("protected_platform_hints", []))):
        labels.add("protected")
    if any(hint in placement_norm for hint in map(normalize, rules.get("yandex_hints", []))):
        labels.add("yandex")
    if PACKAGE_LIKE_RE.match(placement_norm):
        labels.add("app_like")
    elif DOMAIN_RE.match(placement_norm):
        labels.add("site")
    if any(hint in placement_norm for hint in VPN_HINTS):
        labels.add("vpn")
    if any(hint in placement_norm for hint in GAME_HINTS):
        labels.add("game")
    if any(hint in placement_norm for hint in map(normalize, rules.get("content_hints", []))):
        labels.add("content")
    return labels


def formula_gate(placement: str, campaign_name: str, row: dict[str, str], rules: dict[str, Any]) -> tuple[bool, str, set[str]]:
    labels = classify_placement(placement, rules)
    formula = dict(DEFAULT_FORMULA)
    formula.update((rules.get("tail_formula_v3") or {}))
    clicks = to_float(row.get("Clicks") or row.get("clicks"))
    ctr = to_float(row.get("Ctr") or row.get("ctr"))
    cost = to_float(row.get("Cost") or row.get("cost"))
    conversions = to_float(row.get("Conversions_289498769_LC") or row.get("conversions"))
    if conversions > 0:
        return False, "Placement has conversions > 0 in evidence window.", labels
    if labels & {"protected", "yandex", "yandex_root"}:
        return False, "Protected/Yandex inventory is not eligible for auto-block pack.", labels
    if "exact_safe_block" in labels:
        return True, "Exact safe blocklist placement.", labels
    if "vpn" in labels:
        cfg = formula["vpn_block"]
        ok = clicks >= cfg["min_clicks"] or cost >= cfg["min_cost"] or (clicks >= 2 and ctr >= cfg["min_ctr"])
        return ok, "vpn_block" if ok else "Does not pass vpn_block formula.", labels
    retarget = is_retarget_campaign(campaign_name)
    if "app_like" in labels:
        cfg = formula["retarget_app_block" if retarget else "prospecting_app_block"]
        ok = clicks >= cfg["min_clicks"] or cost >= cfg["min_cost"] or (clicks >= 3 and ctr >= cfg["min_ctr"])
        return ok, "app_formula" if ok else "Does not pass app-like formula.", labels
    if labels & {"site", "content", "game"}:
        cfg = formula["retarget_site_block" if retarget else "prospecting_site_block"]
        ok = (clicks >= cfg["min_clicks"] and cost >= cfg["min_cost"]) or (clicks >= max(cfg["min_clicks"], 3) and ctr >= cfg["min_ctr"])
        return ok, "site_formula" if ok else "Does not pass site/content formula.", labels
    return False, "Placement not classified into formula risk lane.", labels


def priority_key(item: dict[str, Any]) -> tuple[int, float, float, float]:
    labels = item.get("labels", set())
    exact = 1 if "exact_safe_block" in labels else 0
    vpn = 1 if "vpn" in labels else 0
    cost = float(item.get("cost") or 0.0)
    clicks = float(item.get("clicks") or 0.0)
    ctr = float(item.get("ctr") or 0.0)
    return (exact + vpn, cost, clicks, ctr)


def load_runtime(project_root: Path) -> tuple[str, str]:
    package_root = project_root / "direct-orchestrator" / "src"
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from direct_orchestrator.services.audience_apply_runtime import load_direct_runtime  # type: ignore

    config_path = project_root / ".codex" / "yandex-performance-client.json"
    _runtime, login, token = load_direct_runtime(project_root, config_path)
    return login, token


def direct_call(token: str, login: str, service: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    import urllib.error
    import urllib.request

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


def fetch_campaigns(token: str, login: str, campaign_ids: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for start in range(0, len(campaign_ids), 10):
        batch = campaign_ids[start : start + 10]
        payload = direct_call(
            token,
            login,
            "campaigns",
            "get",
            {
                "SelectionCriteria": {"Ids": batch},
                "FieldNames": ["Id", "Name", "ExcludedSites"],
            },
        )
        rows.extend(payload.get("result", {}).get("Campaigns", []) or [])
    return rows


def get_excluded_sites(campaign: dict[str, Any]) -> list[str]:
    raw = campaign.get("ExcludedSites")
    if isinstance(raw, dict):
        items = raw.get("Items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    clean: list[str] = []
    for item in items:
        site = normalize_text(item)
        if site and site not in clean:
            clean.append(site)
    return clean


def is_add_action(action: str) -> bool:
    lowered = normalize_text(action).casefold()
    return lowered.startswith("добавить в список запрещ")


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    decision_rows = load_tsv(args.manual_decisions.expanduser().resolve())
    rules = load_rules(args.rules.expanduser().resolve() if args.rules else None)

    candidate_sites_by_campaign: dict[int, list[dict[str, str]]] = {}
    blocked_items: list[dict[str, Any]] = []
    for row in decision_rows:
        action = normalize_text(row.get("assistant_action"))
        if not is_add_action(action):
            continue
        campaign_id, placement = parse_candidate_id(normalize_text(row.get("candidate_id")))
        if not campaign_id or not placement:
            blocked_items.append(
                {
                    "candidate_id": normalize_text(row.get("candidate_id")),
                    "reason": "Unable to parse campaign_id or placement from candidate_id.",
                }
            )
            continue
        if placement.casefold() in ROOT_DOMAIN_BLOCKLIST:
            blocked_items.append(
                {
                    "candidate_id": normalize_text(row.get("candidate_id")),
                    "campaign_id": campaign_id,
                    "placement": placement,
                    "reason": "Root Yandex domains are not allowed in ExcludedSites apply-pack.",
                }
            )
            continue
        candidate_sites_by_campaign.setdefault(campaign_id, []).append(
            {
                "candidate_id": normalize_text(row.get("candidate_id")),
                "placement": placement,
                "assistant_reason": normalize_text(row.get("assistant_reason")),
            }
        )

    campaign_ids = sorted(candidate_sites_by_campaign)
    if not campaign_ids:
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "rsya_excluded_sites_local_summary.json", {"status": "blocked", "reason": "No approved add-actions found."})
        return 1

    login, token = load_runtime(project_root)
    live_campaigns = fetch_campaigns(token, login, campaign_ids)
    live_by_id = {int(row.get("Id") or 0): row for row in live_campaigns if int(row.get("Id") or 0) > 0}
    placements_map = load_placements_for_campaigns(args.placements_root.expanduser().resolve() if args.placements_root else None, campaign_ids)

    campaign_packs: list[dict[str, Any]] = []
    for campaign_id in campaign_ids:
        live = live_by_id.get(campaign_id)
        if not live:
            blocked_items.append({"campaign_id": campaign_id, "reason": "Live campaign baseline not found."})
            continue
        current_items = get_excluded_sites(live)
        current_set = set(current_items)
        candidate_items: list[dict[str, Any]] = []
        candidate_seen: set[str] = set()
        for item in candidate_sites_by_campaign[campaign_id]:
            site = item["placement"]
            if site in current_set or site in candidate_seen:
                blocked_items.append(
                    {
                        "candidate_id": item["candidate_id"],
                        "campaign_id": campaign_id,
                        "placement": site,
                        "reason": "Site already exists in live ExcludedSites baseline.",
                    }
                )
                continue
            candidate_seen.add(site)
            placement_row = placements_map.get((campaign_id, site))
            if args.placements_root:
                if not placement_row:
                    blocked_items.append(
                        {
                            "candidate_id": item["candidate_id"],
                            "campaign_id": campaign_id,
                            "placement": site,
                            "reason": "Missing placement evidence row in placements_root.",
                        }
                    )
                    continue
                ok, formula_reason, labels = formula_gate(site, normalize_text(live.get("Name")), placement_row, rules)
                if not ok:
                    blocked_items.append(
                        {
                            "candidate_id": item["candidate_id"],
                            "campaign_id": campaign_id,
                            "placement": site,
                            "reason": formula_reason,
                        }
                    )
                    continue
                candidate_items.append(
                    {
                        **item,
                        "labels": labels,
                        "cost": to_float(placement_row.get("Cost") or placement_row.get("cost")),
                        "clicks": to_float(placement_row.get("Clicks") or placement_row.get("clicks")),
                        "ctr": to_float(placement_row.get("Ctr") or placement_row.get("ctr")),
                    }
                )
            else:
                candidate_items.append({**item, "labels": set(), "cost": 0.0, "clicks": 0.0, "ctr": 0.0})
        candidate_items.sort(key=priority_key, reverse=True)
        free_slots = max(0, 1000 - len(current_items))
        selected_items = candidate_items[:free_slots]
        overflow_items = candidate_items[free_slots:]
        for item in overflow_items:
            blocked_items.append(
                {
                    "candidate_id": item["candidate_id"],
                    "campaign_id": campaign_id,
                    "placement": item["placement"],
                    "reason": "No free ExcludedSites slots left after slot-aware prioritization.",
                }
            )
        add_sites = [item["placement"] for item in selected_items]
        evidence_rows = [
            {
                "candidate_id": item["candidate_id"],
                "placement": item["placement"],
                "assistant_reason": item["assistant_reason"],
                "clicks": item["clicks"],
                "cost": item["cost"],
                "ctr": item["ctr"],
                "labels": ",".join(sorted(item["labels"])),
            }
            for item in selected_items
        ]
        if not add_sites:
            continue
        after_items = current_items + add_sites
        campaign_packs.append(
            {
                "campaign_id": campaign_id,
                "campaign_name": normalize_text(live.get("Name")),
                "current_count": len(current_items),
                "after_count": len(after_items),
                "add_sites": add_sites,
                "remove_sites": [],
                "after_items": after_items,
                "evidence_rows": evidence_rows,
            }
        )

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        output_dir / "campaigns_meta_live.json",
        {"result": {"Campaigns": live_campaigns}},
    )
    for pack in campaign_packs:
        write_json(output_dir / f"excluded_pack_{pack['campaign_id']}.json", pack)

    aggregated_pack = {
        "pack_kind": "rsya_excluded_sites",
        "status": "ready" if campaign_packs else "blocked",
        "affected_campaign_count": len(campaign_packs),
        "campaign_packs": campaign_packs,
        "blocked_items": blocked_items,
    }
    summary = {
        "status": aggregated_pack["status"],
        "affected_campaign_count": len(campaign_packs),
        "add_sites_count": sum(len(pack["add_sites"]) for pack in campaign_packs),
        "blocked_item_count": len(blocked_items),
    }
    write_json(output_dir / "rsya_excluded_sites_local_pack.json", aggregated_pack)
    write_json(output_dir / "rsya_excluded_sites_local_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if campaign_packs else 1


if __name__ == "__main__":
    raise SystemExit(main())
