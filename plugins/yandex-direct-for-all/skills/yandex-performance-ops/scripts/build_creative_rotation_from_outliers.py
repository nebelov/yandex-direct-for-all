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


def is_search_campaign(name: str) -> bool:
    return "ПОИСК/" in str(name or "").upper()


def is_rsya_campaign(name: str) -> bool:
    upper = str(name or "").upper()
    return "РСЯ" in upper or "РЕТАРГЕТ" in upper


def region_suffix(campaign_name: str) -> str:
    name = str(campaign_name or "")
    if "Мск" in name or "Москва" in name:
        return "по Москве"
    if "СПб" in name or "Санкт" in name:
        return "по Санкт-Петербургу"
    return "по РФ"


def text_score(row: dict[str, str]) -> tuple[float, float, float]:
    return (
        parse_float(row.get("conversions")),
        parse_float(row.get("clicks")),
        parse_float(row.get("cost")),
    )


def build_draft_text(loser: dict[str, str]) -> tuple[str, str]:
    campaign_name = str(loser.get("campaign_name") or "")
    title = str(loser.get("sample_title") or "").strip()
    text = str(loser.get("sample_text") or "").strip()
    surface = f"{title} {text}".lower()
    region = region_suffix(campaign_name)

    if "карниз" in surface:
        return (
            "Профиль для скрытого карниза",
            f"Алюминиевый тип 7 для скрытого карниза. Подберём размер и доставим {region}.",
        )
    if "двер" in surface:
        return (
            "Теневой профиль для скрытых дверей",
            f"Аккуратный стык двери и стены без накладного плинтуса. Подбор профиля и доставка {region}.",
        )
    if "плинтус" in surface:
        return (
            "Скрытый плинтус для пола",
            f"Алюминиевый профиль без обычного плинтуса. Подбор типа, образцы и доставка {region}.",
        )
    if "тип" in surface and "двер" in campaign_name.lower():
        return (
            "Теневой профиль для скрытых дверей",
            f"Подберём тип профиля под двери, стены и потолки. Доставка {region}.",
        )
    return (
        "Теневой профиль для стен и потолка",
        f"Алюминиевый профиль для скрытого монтажа. Подбор типа, образцы и доставка {region}.",
    )


def split_text_payload(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(value or "").split("|") if part.strip()]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def build_reason(loser: dict[str, str], winner: dict[str, str] | None) -> str:
    loser_cost = f"{parse_float(loser.get('cost')):.2f}"
    loser_clicks = int(parse_float(loser.get("clicks")))
    loser_conv = parse_float(loser.get("conversions"))
    if winner is None:
        return (
            f"Loser creative за 15 дней дал {loser_clicks} кликов, расход {loser_cost}, "
            f"конверсии {loser_conv:g}; в кампании нет доказанного text-winner, нужен точечный refresh."
        )
    win_cost = f"{parse_float(winner.get('cost')):.2f}"
    win_clicks = int(parse_float(winner.get("clicks")))
    win_conv = parse_float(winner.get("conversions"))
    return (
        f"Loser creative за 15 дней дал {loser_clicks} кликов, расход {loser_cost}, конверсии {loser_conv:g}; "
        f"current winner в той же кампании дал {win_clicks} кликов, расход {win_cost}, конверсии {win_conv:g}."
    )


def build_review_md(
    *,
    date_from: str,
    date_to: str,
    text_losers: list[dict[str, str]],
    text_winners: list[dict[str, str]],
    image_losers: list[dict[str, str]],
    image_winners: list[dict[str, str]],
    normalized_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# Creative Rotation Review",
        "",
        f"Дата: `{date_to}`  ",
        f"Окно: `{date_from}` -> `{date_to}`  ",
        "Статус: `creative-wave only, moderation path`",
        "",
        "## Что просмотрено",
        "",
        f"- `{len(text_losers)}` text losers.",
        f"- `{len(text_winners)}` text winners.",
        f"- `{len(image_losers)}` image losers.",
        f"- `{len(image_winners)}` image winners.",
        f"- `{len([row for row in normalized_rows if row.get('entity_type') == 'text'])}` text rotation actions.",
        f"- `{len([row for row in normalized_rows if row.get('entity_type') == 'image'])}` image rotation actions.",
        "",
        "## Search losers",
        "",
    ]
    for row in text_losers:
        if not is_search_campaign(row.get("campaign_name", "")):
            continue
        lines.extend(
            [
                f"### `{row.get('campaign_id')}`",
                "",
                f"- loser text: `{row.get('sample_title')}`",
                f"- метрики: `{row.get('impressions')}` imp / `{row.get('clicks')}` clicks / `{row.get('cost')}` spend / `{row.get('conversions')}` conv",
                "",
            ]
        )
    lines.extend(["## Search winners", ""])
    for row in text_winners:
        if not is_search_campaign(row.get("campaign_name", "")):
            continue
        lines.append(f"- `{row.get('campaign_id')}` / `{row.get('sample_title')}` / `{row.get('clicks')}` clicks / `{row.get('conversions')}` conv")
    lines.extend(["", "## RSYA losers", ""])
    for row in text_losers:
        if not is_rsya_campaign(row.get("campaign_name", "")):
            continue
        lines.append(
            f"- `{row.get('campaign_id')}` / `{row.get('sample_title')}` / `{row.get('clicks')}` clicks / `{row.get('cost')}` spend / `{row.get('conversions')}` conv"
        )
    lines.extend(["", "## Proposed rotation map", ""])
    for row in normalized_rows:
        if row.get("entity_type") == "text":
            lines.append(
                f"- `{row.get('campaign_id')}`: `{row.get('loser_key', '').split('|')[0].strip()}` -> "
                f"`{row.get('proposed_title')}`."
            )
        elif row.get("action_mode") == "replace_image":
            lines.append(
                f"- `{row.get('campaign_id')}`: image `{row.get('loser_key')}` -> `{row.get('proposed_winner_key')}`."
            )
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "- Search/RSYA text rotation = только через новое объявление, не edit current winner.",
            "- После модерации loser выключать только после read-back и быстрой delivery-проверки.",
            "- Search image rotation не делать как default-path; для поиска это отдельный ручной слой.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-outliers", type=Path, required=True)
    parser.add_argument("--image-outliers", type=Path, required=True)
    parser.add_argument("--review-docs", type=Path, required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    args = parser.parse_args()

    text_rows = load_tsv(args.text_outliers.resolve())
    image_rows = load_tsv(args.image_outliers.resolve())
    review_docs = args.review_docs.resolve()
    review_docs.mkdir(parents=True, exist_ok=True)

    text_winners_by_campaign: dict[str, list[dict[str, str]]] = defaultdict(list)
    image_winners_by_campaign: dict[str, list[dict[str, str]]] = defaultdict(list)
    text_losers: list[dict[str, str]] = []
    image_losers: list[dict[str, str]] = []

    for row in text_rows:
        campaign_id = str(row.get("campaign_id") or "").strip()
        if row.get("classification") == "winner":
            text_winners_by_campaign[campaign_id].append(row)
        elif row.get("classification") == "loser":
            text_losers.append(row)
    for row in image_rows:
        campaign_id = str(row.get("campaign_id") or "").strip()
        if row.get("classification") == "winner":
            image_winners_by_campaign[campaign_id].append(row)
        elif row.get("classification") == "loser":
            image_losers.append(row)

    for bucket in text_winners_by_campaign.values():
        bucket.sort(key=text_score, reverse=True)
    for bucket in image_winners_by_campaign.values():
        bucket.sort(key=text_score, reverse=True)

    source_rows: list[dict[str, Any]] = []
    normalized_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []

    for loser in text_losers:
        campaign_id = str(loser.get("campaign_id") or "").strip()
        campaign_name = str(loser.get("campaign_name") or "").strip()
        winner = text_winners_by_campaign.get(campaign_id, [None])[0]
        source_row: dict[str, Any] = {
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "entity_type": "text",
            "loser_key": str(loser.get("entity_key") or "").strip(),
            "proposed_winner_key": "",
            "pack_type": "creative_wave_15d",
            "reason": build_reason(loser, winner),
        }
        normalized_row: dict[str, Any] = {
            **source_row,
            "action_mode": "create_new_ad",
            "proposed_title": "",
            "proposed_text": "",
            "confidence": "",
            "status_note": "",
            "skip_reason": "",
        }
        if winner is not None:
            source_row["proposed_winner_key"] = str(winner.get("entity_key") or "").strip()
            normalized_row["proposed_winner_key"] = source_row["proposed_winner_key"]
            normalized_row["proposed_title"] = str(winner.get("sample_title") or "").strip()
            normalized_row["proposed_text"] = str(winner.get("sample_text") or "").strip()
            normalized_row["confidence"] = "winner_proven"
            normalized_row["status_note"] = "Создать новое объявление на базе winner-like текста той же кампании."
        else:
            draft_title, draft_text = build_draft_text(loser)
            source_row["proposed_winner_key"] = f"{draft_title} | {draft_text}"
            normalized_row["proposed_winner_key"] = source_row["proposed_winner_key"]
            normalized_row["proposed_title"] = draft_title
            normalized_row["proposed_text"] = draft_text
            normalized_row["confidence"] = "draft_hypothesis"
            normalized_row["status_note"] = "В кампании нет доказанного text-winner; собрать новое объявление-тест и отправить в модерацию."
        source_rows.append(source_row)
        normalized_rows.append(normalized_row)

    for loser in image_losers:
        campaign_id = str(loser.get("campaign_id") or "").strip()
        campaign_name = str(loser.get("campaign_name") or "").strip()
        winner = image_winners_by_campaign.get(campaign_id, [None])[0]
        source_row = {
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "entity_type": "image",
            "loser_key": str(loser.get("entity_key") or "").strip(),
            "proposed_winner_key": str((winner or {}).get("entity_key") or "").strip(),
            "pack_type": "creative_wave_15d",
            "reason": build_reason(loser, winner),
        }
        normalized_row = {
            **source_row,
            "action_mode": "",
            "proposed_title": "",
            "proposed_text": "",
            "confidence": "",
            "status_note": "",
            "skip_reason": "",
        }
        if winner is None:
            normalized_row["action_mode"] = "skip"
            normalized_row["skip_reason"] = "no_same_campaign_image_winner"
            normalized_row["status_note"] = "В этой кампании нет доказанного image-winner для безопасной замены."
            skipped_rows.append(normalized_row)
            continue
        if is_search_campaign(campaign_name):
            normalized_row["action_mode"] = "skip"
            normalized_row["skip_reason"] = "search_image_rotation_forbidden"
            normalized_row["status_note"] = "Изображения ротируются только в РСЯ/ретаргете."
            skipped_rows.append(normalized_row)
            continue
        normalized_row["action_mode"] = "replace_image"
        normalized_row["confidence"] = "winner_proven"
        normalized_row["status_note"] = "Заменить изображение после preview и read-back."
        source_rows.append(source_row)
        normalized_rows.append(normalized_row)

    fieldnames_source = [
        "campaign_id",
        "campaign_name",
        "entity_type",
        "loser_key",
        "proposed_winner_key",
        "pack_type",
        "reason",
    ]
    fieldnames_v2 = [
        "campaign_id",
        "campaign_name",
        "entity_type",
        "loser_key",
        "proposed_winner_key",
        "pack_type",
        "reason",
        "action_mode",
        "proposed_title",
        "proposed_text",
        "confidence",
        "status_note",
        "skip_reason",
    ]
    write_tsv(review_docs / "03_creative_rotation_candidates.tsv", source_rows, fieldnames_source)
    write_tsv(review_docs / "03_creative_rotation_candidates_v2.tsv", normalized_rows, fieldnames_v2)
    write_tsv(review_docs / "03_creative_rotation_skipped.tsv", skipped_rows, fieldnames_v2)

    md = build_review_md(
        date_from=args.date_from,
        date_to=args.date_to,
        text_losers=text_losers,
        text_winners=[row for rows in text_winners_by_campaign.values() for row in rows],
        image_losers=image_losers,
        image_winners=[row for rows in image_winners_by_campaign.values() for row in rows],
        normalized_rows=normalized_rows,
    )
    (review_docs / "03_creative_rotation_review.md").write_text(md, encoding="utf-8")
    print(
        {
            "ok": True,
            "text_losers": len(text_losers),
            "image_losers": len(image_losers),
            "rotation_rows": len(normalized_rows),
            "skipped_rows": len(skipped_rows),
            "review_docs": str(review_docs),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
