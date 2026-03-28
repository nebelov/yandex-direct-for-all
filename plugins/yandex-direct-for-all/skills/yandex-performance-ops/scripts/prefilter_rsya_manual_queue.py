#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply deterministic low-signal/anomaly prefilter to an RSYA manual-review queue."
    )
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--keep-resolved",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep already resolved rows in the prefiltered queue output.",
    )
    return parser.parse_args()


def load_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def load_rules(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def to_float(value: str | None) -> float:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def is_resolved(row: dict[str, str]) -> bool:
    return bool(str(row.get("assistant_status") or "").strip())


def classify_placement(placement: str, rules: dict) -> set[str]:
    placement_norm = placement.lower().strip()
    labels: set[str] = set()
    if any(hint.lower() in placement_norm for hint in rules.get("protected_platform_hints", [])):
        labels.add("protected")
    if any(hint.lower() in placement_norm for hint in rules.get("yandex_hints", [])):
        labels.add("yandex")
    if any(hint.lower() in placement_norm for hint in rules.get("content_hints", [])):
        labels.add("content")
    if "." in placement_norm and placement_norm.startswith(("com.", "ru.", "air.", "io.", "net.", "org.")):
        labels.add("app_like")
    return labels


def annotate(row: dict[str, str], bucket: str, reason: str) -> dict[str, str]:
    out = dict(row)
    out["prefilter_bucket"] = bucket
    out["prefilter_reason"] = reason
    return out


def classify_review_gate(labels: set[str]) -> str:
    if labels & {"protected", "yandex"}:
        return "protected_yandex"
    if "app_like" in labels:
        return "app_like"
    if "content" in labels:
        return "content"
    return "default"


def passes_review_gate(
    labels: set[str],
    clicks: float,
    ctr: float,
    cost: float,
    gate_rules: dict,
) -> tuple[bool, str]:
    gate_key = classify_review_gate(labels)
    config = dict((gate_rules or {}).get(gate_key) or (gate_rules or {}).get("default") or {})
    logic = str(config.get("logic") or "clicks_and_(cost_or_ctr)").strip()
    min_clicks = float(config.get("min_clicks", 0))
    min_cost = float(config.get("min_cost", 0))
    min_ctr = float(config.get("min_ctr", 0))
    if logic == "clicks_or_cost":
        passed = clicks >= min_clicks or cost >= min_cost
        reason = (
            f"review_gate={gate_key}: требуется clicks >= {min_clicks:g} "
            f"или cost >= {min_cost:.2f}."
        )
        return passed, reason
    passed = clicks >= min_clicks and (cost >= min_cost or ctr >= min_ctr)
    reason = (
        f"review_gate={gate_key}: требуется clicks >= {min_clicks:g} "
        f"и (cost >= {min_cost:.2f} или CTR >= {min_ctr:.2f})."
    )
    return passed, reason


def main() -> int:
    args = parse_args()
    args.queue = args.queue.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    args.rules = args.rules.expanduser().resolve() if args.rules else None

    rows, fieldnames = load_tsv(args.queue)
    rules = load_rules(args.rules)
    thresholds = rules.get("thresholds", {})
    queue_prefilter = rules.get("queue_prefilter", {})

    max_ctr_for_low_signal_skip = float(queue_prefilter.get("max_ctr_for_low_signal_skip", 1.0))
    max_clicks_for_low_signal_skip = float(queue_prefilter.get("max_clicks_for_low_signal_skip", thresholds.get("min_clicks_for_monitor", 3)))
    max_cost_for_low_signal_skip = float(queue_prefilter.get("max_cost_for_low_signal_skip", thresholds.get("min_cost_for_monitor", 20.0)))
    max_clicks_for_zero_cost_impression_skip = float(queue_prefilter.get("max_clicks_for_zero_cost_impression_skip", 0))
    max_impressions_for_zero_cost_impression_skip = float(queue_prefilter.get("max_impressions_for_zero_cost_impression_skip", thresholds.get("min_impressions_for_monitor", 150)))
    protected_max_clicks_for_skip = float(queue_prefilter.get("protected_max_clicks_for_skip", thresholds.get("protected_min_clicks_for_review", 5)))
    protected_max_cost_for_skip = float(queue_prefilter.get("protected_max_cost_for_skip", thresholds.get("protected_min_cost_for_review", 100.0)))
    app_like_max_clicks_for_skip = float(queue_prefilter.get("app_like_max_clicks_for_skip", 2))
    app_like_max_cost_for_skip = float(queue_prefilter.get("app_like_max_cost_for_skip", thresholds.get("min_cost_for_risky_inventory_stop", 35.0)))
    review_gate_rules = dict(queue_prefilter.get("review_gate") or {})

    remaining_rows: list[dict[str, str]] = []
    auto_skipped_rows: list[dict[str, str]] = []
    anomaly_rows: list[dict[str, str]] = []

    for row in rows:
        if is_resolved(row):
            if args.keep_resolved:
                remaining_rows.append(dict(row))
            continue

        placement = str(row.get("placement") or "").strip()
        labels = classify_placement(placement, rules)
        clicks = to_float(row.get("clicks"))
        ctr = to_float(row.get("ctr"))
        cost = to_float(row.get("cost"))
        impressions = to_float(row.get("impressions"))
        conversions = to_float(row.get("conversions"))

        if clicks > 0 and cost == 0:
            anomaly_rows.append(
                annotate(
                    row,
                    "anomaly_quarantine",
                    "clicks > 0 при cost = 0. Нужен raw/source recheck, не manual stop review.",
                )
            )
            continue
        if conversions > 0 and cost == 0:
            anomaly_rows.append(
                annotate(
                    row,
                    "anomaly_quarantine",
                    "conversions > 0 при cost = 0. Нужен raw/source recheck, не manual stop review.",
                )
            )
            continue

        if (
            conversions == 0
            and clicks < max_clicks_for_low_signal_skip
            and ctr < max_ctr_for_low_signal_skip
            and cost < max_cost_for_low_signal_skip
        ):
            auto_skipped_rows.append(
                annotate(
                    row,
                    "low_signal_skip",
                    f"Low-signal tail: clicks < {max_clicks_for_low_signal_skip:g}, CTR < {max_ctr_for_low_signal_skip:.2f}, cost < {max_cost_for_low_signal_skip:.2f}, conversions = 0.",
                )
            )
            continue

        if (
            conversions == 0
            and clicks <= max_clicks_for_zero_cost_impression_skip
            and cost == 0
            and impressions < max_impressions_for_zero_cost_impression_skip
        ):
            auto_skipped_rows.append(
                annotate(
                    row,
                    "zero_click_tail_skip",
                    f"Zero-click/zero-cost tail below {max_impressions_for_zero_cost_impression_skip:g} impressions.",
                )
            )
            continue

        if (
            conversions == 0
            and labels & {"protected", "yandex"}
            and clicks < protected_max_clicks_for_skip
            and cost < protected_max_cost_for_skip
        ):
            auto_skipped_rows.append(
                annotate(
                    row,
                    "protected_low_signal_skip",
                    f"Protected/Yandex inventory below {protected_max_clicks_for_skip:g} clicks and {protected_max_cost_for_skip:.2f} cost goes to monitor, not manual stop review.",
                )
            )
            continue

        if (
            conversions == 0
            and "app_like" in labels
            and clicks < app_like_max_clicks_for_skip
            and cost < app_like_max_cost_for_skip
        ):
            auto_skipped_rows.append(
                annotate(
                    row,
                    "app_like_low_signal_skip",
                    f"App-like low-signal tail below {app_like_max_clicks_for_skip:g} clicks and {app_like_max_cost_for_skip:.2f} cost.",
                )
            )
            continue

        if conversions == 0:
            review_gate_ok, review_gate_reason = passes_review_gate(labels, clicks, ctr, cost, review_gate_rules)
            if not review_gate_ok:
                auto_skipped_rows.append(
                    annotate(
                        row,
                        "review_gate_skip",
                        review_gate_reason + " Строка уходит в monitor/skip-from-manual-review, не в stop-pack.",
                    )
                )
                continue

        remaining_rows.append(dict(row))

    extended_fields = fieldnames + [field for field in ("prefilter_bucket", "prefilter_reason") if field not in fieldnames]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output_dir / "rsya_placements_manual_review_prefiltered.tsv", remaining_rows, fieldnames)
    write_tsv(args.output_dir / "rsya_placements_auto_skipped.tsv", auto_skipped_rows, extended_fields)
    write_tsv(args.output_dir / "rsya_placements_anomaly_quarantine.tsv", anomaly_rows, extended_fields)

    summary = {
        "queue": str(args.queue),
        "rules": str(args.rules) if args.rules else None,
        "total_rows": len(rows),
        "resolved_rows_seen": sum(1 for row in rows if is_resolved(row)),
        "resolved_rows_kept": sum(1 for row in remaining_rows if is_resolved(row)),
        "remaining_rows": len(remaining_rows),
        "remaining_unresolved_rows": sum(1 for row in remaining_rows if not is_resolved(row)),
        "auto_skipped_rows": len(auto_skipped_rows),
        "anomaly_rows": len(anomaly_rows),
        "auto_skip_breakdown": {},
    }
    breakdown: dict[str, int] = {}
    for row in auto_skipped_rows:
        breakdown[row.get("prefilter_bucket", "")] = breakdown.get(row.get("prefilter_bucket", ""), 0) + 1
    summary["auto_skip_breakdown"] = breakdown
    (args.output_dir / "rsya_placements_prefilter_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
