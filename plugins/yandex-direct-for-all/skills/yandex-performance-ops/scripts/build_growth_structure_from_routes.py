#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def parse_float(value: str) -> float:
    try:
        return float(str(value or "0").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def parse_int(value: str) -> int:
    try:
        return int(float(str(value or "0").replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def campaign_sort_key(row: dict[str, str]) -> tuple[float, float]:
    return (parse_float(row.get("direct_conversions")), -parse_float(row.get("direct_cpa") or "0"))


def aggregate_growth_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("campaign_id") or "").strip(),
            str(row.get("campaign_name") or "").strip(),
            str(row.get("route_label") or "").strip(),
        )
        bucket = agg.setdefault(
            key,
            {
                "campaign_id": key[0],
                "campaign_name": key[1],
                "route_label": key[2],
                "impressions": 0,
                "clicks": 0.0,
                "cost": 0.0,
                "ad_groups": set(),
                "queries": [],
                "recommendation": "",
                "reason": "",
            },
        )
        bucket["impressions"] += parse_int(row.get("evidence_impressions"))
        bucket["clicks"] += parse_float(row.get("evidence_clicks"))
        bucket["cost"] += parse_float(row.get("evidence_cost"))
        ad_group = str(row.get("ad_group_name") or "").strip()
        if ad_group:
            bucket["ad_groups"].add(ad_group)
        bucket["recommendation"] = str(row.get("recommendation") or bucket["recommendation"]).strip()
        bucket["reason"] = str(row.get("reason") or bucket["reason"]).strip()
        for query in str(row.get("top_queries") or "").split("|"):
            query = query.strip()
            if query and query not in bucket["queries"]:
                bucket["queries"].append(query)
    return agg


def campaign_metrics_map(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {str(row.get("campaign_id") or "").strip(): row for row in rows}


def build_new_group_candidates(agg: dict[tuple[str, str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    micro_candidates = [item for item in agg.values() if item["route_label"] == "микроплинтус"]
    micro_candidates.sort(key=lambda item: (item["clicks"], item["cost"], item["impressions"]), reverse=True)
    if micro_candidates:
        best = micro_candidates[0]
        rows.append(
            {
                "target_campaign_id": best["campaign_id"],
                "target_campaign_name": best["campaign_name"],
                "action_layer": "exact_phrase_group",
                "cluster": "микроплинтус",
                "proposed_target": "new adgroup `микроплинтус` with exact and phrase set",
                "why": (
                    f"15d route already leaks through current traffic: {best['impressions']} imp / "
                    f"{best['clicks']:.0f} clicks / {best['cost']:.2f} cost across {len(best['ad_groups'])} adgroups."
                ),
                "priority": "high",
                "confidence": "high",
                "expected_effect": "cleaner routing and отдельный CPL verdict по микроплинтусу",
                "risk": "overlap with current hidden-plinth routes unless negatives are synced",
                "status": "pre_apply_candidate",
            }
        )

    seam_candidates = [item for item in agg.values() if item["route_label"] == "теневой зазор / теневой шов"]
    seam_candidates.sort(key=lambda item: (item["clicks"], item["cost"], item["impressions"]), reverse=True)
    if seam_candidates:
        best = seam_candidates[0]
        rows.append(
            {
                "target_campaign_id": best["campaign_id"],
                "target_campaign_name": best["campaign_name"],
                "action_layer": "exact_test_group",
                "cluster": "теневой зазор + теневой шов",
                "proposed_target": "new limited-budget exact test group with hard negatives",
                "why": (
                    f"15d solution-intent already visible: {best['impressions']} imp / "
                    f"{best['clicks']:.0f} clicks / {best['cost']:.2f} cost, but current coverage is accidental."
                ),
                "priority": "medium_high",
                "confidence": "medium",
                "expected_effect": "turn opaque solution-intent into measurable exact layer",
                "risk": "info/DIY spill unless negatives are strict",
                "status": "test_only",
            }
        )
    return rows


def build_growth_review_md(
    *,
    date_from: str,
    date_to: str,
    agg: dict[tuple[str, str, str], dict[str, Any]],
    new_group_rows: list[dict[str, Any]],
    scorecard_map: dict[str, dict[str, str]],
) -> str:
    hidden_doors_rows = [item for item in agg.values() if item["route_label"] == "скрытые двери"]
    micro_rows = [item for item in agg.values() if item["route_label"] == "микроплинтус"]
    seam_rows = [item for item in agg.values() if item["route_label"] == "теневой зазор / теневой шов"]

    lines = [
        "# Missing Phrases Growth Review",
        "",
        f"Дата: `{date_to}`  ",
        "Truth layer: `Direct 15d SQR + Direct 15d campaign totals`  ",
        "Режим: `pre-apply / growth-structure review`",
        "",
        "## Главный вывод",
        "",
        "На текущих 15-дневных live-данных не подтверждается ни одна новая standalone search-кампания.",
        "",
        "Подтверждаются только group-level сценарии:",
        "",
        "1. `расширить существующую кампанию новым exact/phrase adgroup`;",
        "2. `выделить solution-intent в отдельный тестовый слой`;",
        "3. `защитить уже продающий маршрут`, а не плодить новую РК.",
        "",
    ]

    if micro_rows:
        best = sorted(micro_rows, key=lambda item: (item["clicks"], item["cost"]), reverse=True)[0]
        lines.extend(
            [
                "## Высокая уверенность",
                "",
                "### `микроплинтус`",
                "",
                f"- 15d best route: `{best['campaign_id']} / {best['campaign_name']}`",
                f"- сигнал: `{best['impressions']}` imp / `{best['clicks']:.0f}` clicks / `{best['cost']:.2f}` cost",
                f"- top queries: `{ ' | '.join(best['queries'][:6]) }`",
                "",
                "Verdict:",
                "",
                "- это не negative;",
                "- это не новая standalone campaign;",
                "- это `new exact/phrase group` внутри текущего search shell.",
                "",
            ]
        )

    if hidden_doors_rows:
        best = sorted(hidden_doors_rows, key=lambda item: (item["clicks"], item["cost"]), reverse=True)[0]
        carrier = scorecard_map.get("91494443", {})
        lines.extend(
            [
                "### `скрытые двери`",
                "",
                f"- strongest route: `{best['campaign_id']} / {best['campaign_name']}`",
                f"- сигнал: `{best['impressions']}` imp / `{best['clicks']:.0f}` clicks / `{best['cost']:.2f}` cost",
                (
                    f"- current explicit carrier: `91494443 / {carrier.get('campaign_name', 'Поиск/Типы и двери/СПб+РФ')}` | "
                    f"`{parse_float(carrier.get('clicks')):.0f}` clicks / `{parse_float(carrier.get('cost')):.2f}` cost / "
                    f"`{parse_float(carrier.get('direct_conversions')):g}` direct conv / `{parse_float(carrier.get('direct_cpa')):.2f}` CPA"
                    if carrier
                    else ""
                ),
                "",
                "Verdict:",
                "",
                "- это growth-домен, но не новая группа по умолчанию;",
                "- главный ход здесь = защитить существующий carrier-route и перестроить routing в его пользу;",
                "- traffic leakage из других кампаний надо переводить в door-route, а не масштабировать broad-слой.",
                "",
            ]
        )

    if seam_rows:
        best = sorted(seam_rows, key=lambda item: (item["clicks"], item["cost"]), reverse=True)[0]
        lines.extend(
            [
                "## Средняя уверенность",
                "",
                "### `теневой зазор` и `теневой шов`",
                "",
                f"- best current route: `{best['campaign_id']} / {best['campaign_name']}`",
                f"- сигнал: `{best['impressions']}` imp / `{best['clicks']:.0f}` clicks / `{best['cost']:.2f}` cost",
                f"- top queries: `{ ' | '.join(best['queries'][:6]) }`",
                "",
                "Verdict:",
                "",
                "- это не готовая новая РК;",
                "- это `solution-intent test layer` внутри уже работающей search-кампании;",
                "- запускать как ограниченный exact/phrase test-pack с жёсткими минусами.",
                "",
            ]
        )

    lines.extend(
        [
            "## Что делать сейчас",
            "",
        ]
    )
    for index, row in enumerate(new_group_rows, start=1):
        lines.append(f"{index}. {row['proposed_target']} в `{row['target_campaign_id']} / {row['target_campaign_name']}`.")
    lines.extend(
        [
            "",
            "## Что не делать сейчас",
            "",
            "- не создавать новую standalone search-кампанию без отдельного geo/offer/landing;",
            "- не смешивать hidden-door growth с generic broad search-layer;",
            "- не пытаться закрывать growth простым автотаргетингом.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def build_growth_pack_md(
    *,
    date_from: str,
    date_to: str,
    scorecard_map: dict[str, dict[str, str]],
    agg: dict[tuple[str, str, str], dict[str, Any]],
) -> str:
    lines = [
        "# Growth Acceleration Pack",
        "",
        f"Дата: `{date_to}`  ",
        f"Окно чтения current-state: `{date_from}` -> `{date_to}`  ",
        "Truth layer: `Direct 15d campaign totals + Direct 15d SQR growth routes`",
        "",
        "## Принцип",
        "",
        "- Здесь собраны меры `что усиливать`, `что выделять в отдельный слой`, `куда переводить spend`.",
        "- Эта 15d growth-wave не опирается на новый Roistat snapshot, поэтому решения ограничены структурой, routing и creative/growth planning.",
        "- Новая standalone search-кампания не подтверждена; рост идёт через protected routes и новые adgroups.",
        "",
    ]
    by_campaign: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in agg.values():
        by_campaign[item["campaign_id"]].append(item)

    for campaign_id, score in sorted(scorecard_map.items(), key=lambda kv: parse_float(kv[1].get("cost")), reverse=True):
        campaign_name = str(score.get("campaign_name") or campaign_id)
        if "Поиск/" not in campaign_name:
            continue
        routes = sorted(by_campaign.get(campaign_id, []), key=lambda item: (item["clicks"], item["cost"]), reverse=True)
        lines.extend(
            [
                f"## `{campaign_id} / {campaign_name}`",
                "",
                "Текущий 15d state:",
                "",
                f"- spend `{parse_float(score.get('cost')):.2f}`",
                f"- clicks `{parse_int(score.get('clicks'))}`",
                f"- direct conv `{parse_float(score.get('direct_conversions')):g}`",
                f"- direct CPA `{parse_float(score.get('direct_cpa')):.2f}`",
                "",
            ]
        )
        if routes:
            lines.append("Growth routes внутри кампании:")
            for item in routes[:3]:
                lines.append(
                    f"- `{item['route_label']}` | `{item['impressions']}` imp / `{item['clicks']:.0f}` clicks / "
                    f"`{item['cost']:.2f}` cost | `{item['recommendation']}`"
                )
            lines.append("")
            lines.append("Что усиливать / что добавлять:")
            lines.append("")
            for item in routes[:3]:
                lines.append(f"- {item['recommendation']}")
            lines.append("")
        else:
            direct_conv = parse_float(score.get("direct_conversions"))
            direct_cpa = parse_float(score.get("direct_cpa"))
            if direct_conv > 0:
                lines.extend(
                    [
                        "- В SQR 15d нет нового leakage-route, но кампания уже является current carrier по своему домену.",
                        "",
                        "Что усиливать / что добавлять:",
                        "",
                        f"- Не строить новую кампанию поверх текущего carrier-layer; сначала усиливать current winners и держать CPA около `{direct_cpa:.2f}`.",
                        "- Переводить adjacent leakage из соседних кампаний в этот shell через routing, negatives и новые тексты.",
                        "",
                    ]
                )
            else:
                lines.extend(["- Явных current growth-routes в SQR 15d не найдено.", ""])

    lines.extend(
        [
            "## Главный growth-вывод",
            "",
            "1. Рост сейчас подтверждён через `микроплинтус` и через отдельный `теневой зазор / теневой шов` test-layer.",
            "2. `скрытые двери` = protected growth-route, а не новая РК.",
            "3. Новые standalone search-кампании без отдельного offer/geo пока не подтверждены.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--growth-routes", type=Path, required=True)
    parser.add_argument("--campaign-scorecard", type=Path, required=True)
    parser.add_argument("--review-docs", type=Path, required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    args = parser.parse_args()

    growth_rows = load_tsv(args.growth_routes.resolve())
    scorecard_rows = load_tsv(args.campaign_scorecard.resolve())
    review_docs = args.review_docs.resolve()
    review_docs.mkdir(parents=True, exist_ok=True)

    agg = aggregate_growth_rows(growth_rows)
    new_group_rows = build_new_group_candidates(agg)
    write_tsv(
        review_docs / "09_new_groups_candidates.tsv",
        new_group_rows,
        [
            "target_campaign_id",
            "target_campaign_name",
            "action_layer",
            "cluster",
            "proposed_target",
            "why",
            "priority",
            "confidence",
            "expected_effect",
            "risk",
            "status",
        ],
    )
    growth_md = build_growth_review_md(
        date_from=args.date_from,
        date_to=args.date_to,
        agg=agg,
        new_group_rows=new_group_rows,
        scorecard_map=campaign_metrics_map(scorecard_rows),
    )
    (review_docs / "09_missing_phrases_growth_review.md").write_text(growth_md, encoding="utf-8")

    scorecard_map = campaign_metrics_map(scorecard_rows)
    pack_md = build_growth_pack_md(
        date_from=args.date_from,
        date_to=args.date_to,
        scorecard_map=scorecard_map,
        agg=agg,
    )
    (review_docs / "12_growth_acceleration_pack.md").write_text(pack_md, encoding="utf-8")
    print(
        {
            "ok": True,
            "growth_route_count": len(agg),
            "new_group_candidates": len(new_group_rows),
            "review_docs": str(review_docs),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
