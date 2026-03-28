#!/usr/bin/env python3
"""Apply or dry-run a validated ad replacement pack without moderation."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
import re


API_V5 = "https://api.direct.yandex.com/json/v5"


def api_call(token, login, service, method, params):
    req = urllib.request.Request(
        f"{API_V5}/{service}",
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


def load_token(args):
    if args.token:
        return args.token
    if args.token_file:
        data = json.loads(Path(args.token_file).read_text(encoding="utf-8"))
        token = data.get("access_token")
        if token:
            return token
    raise SystemExit("No token provided. Use --token or --token-file.")


def load_entries(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        entries = payload.get("items") or payload.get("plans") or []
    else:
        entries = payload
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("status") == "OK"]


def compact_dict(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            compacted = compact_dict(item)
            if compacted is None:
                continue
            cleaned[key] = compacted
        return cleaned or None
    if isinstance(value, list):
        cleaned = [compact_dict(item) for item in value]
        cleaned = [item for item in cleaned if item is not None]
        return cleaned or None
    if isinstance(value, str) and value == "":
        return None
    return value


def get_ads(token, login, adgroup_ids):
    if not adgroup_ids:
        return []
    resp = api_call(
        token,
        login,
        "ads",
        "get",
        {
            "SelectionCriteria": {"AdGroupIds": adgroup_ids},
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "Status", "State", "Type"],
            "TextAdFieldNames": [
                "Title",
                "Title2",
                "Text",
                "Href",
                "Mobile",
                "DisplayUrlPath",
                "AdImageHash",
                "SitelinkSetId",
                "AdExtensions",
            ],
        },
    )
    if "error" in resp:
        raise RuntimeError(f"ads.get failed: {json.dumps(resp['error'], ensure_ascii=False)}")
    return resp.get("result", {}).get("Ads", [])


def ad_signature_from_text_ad(text_ad):
    ext_ids = []
    for ext in text_ad.get("AdExtensions") or []:
        ext_id = ext.get("AdExtensionId") if isinstance(ext, dict) else None
        if ext_id:
            ext_ids.append(str(ext_id))
    for ext_id in text_ad.get("AdExtensionIds") or []:
        if ext_id:
            ext_ids.append(str(ext_id))
    return "|".join(
        [
            text_ad.get("Title") or "",
            text_ad.get("Title2") or "",
            text_ad.get("Text") or "",
            text_ad.get("Href") or "",
            text_ad.get("DisplayUrlPath") or "",
            text_ad.get("AdImageHash") or "",
            str(text_ad.get("SitelinkSetId") or ""),
            text_ad.get("Mobile") or "",
            ",".join(sorted(ext_ids)),
        ]
    )


def ad_signature(ad_obj):
    return ad_signature_from_text_ad(ad_obj.get("TextAd") or {})


def trim_text(value, limit):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def derive_title2(entry, new_ad):
    explicit = " ".join(str(new_ad.get("Title2") or "").split())
    if explicit:
        return trim_text(explicit, 30)
    text = " ".join(
        [
            str(entry.get("adgroup_name") or ""),
            str(entry.get("campaign_name") or ""),
            str(new_ad.get("Href") or ""),
            " ".join(str(marker or "") for marker in entry.get("product_markers") or []),
        ]
    ).lower()
    candidates = [
        (r"(tip7|штор|карниз)", "Карниз для штор"),
        (r"(tip8|откос|двер)", "Откосы и двери"),
        (r"(tip5|раздел)", "Разделительный профиль"),
        (r"(tip2|панел|керамогран)", "Для панелей"),
        (r"(tip1|стен)", "Стеновой профиль"),
        (r"(плинтус)", "Скрытый плинтус"),
    ]
    for pattern, label in candidates:
        if re.search(pattern, text):
            return trim_text(label, 30)
    markers = [str(marker or "").strip() for marker in entry.get("product_markers") or [] if str(marker or "").strip()]
    if markers:
        return trim_text(markers[0], 30)
    return "Теневой профиль"


def build_payload(entry):
    new_ad = entry["new_ad"]
    ad_extension_ids = []
    for ext in new_ad.get("AdExtensions") or []:
        ext_id = ext.get("AdExtensionId") if isinstance(ext, dict) else None
        if ext_id:
            ad_extension_ids.append(ext_id)
    payload = {
        "AdGroupId": entry["adgroup_id"],
        "TextAd": {
            "Title": new_ad.get("Title"),
            "Title2": derive_title2(entry, new_ad),
            "Text": new_ad.get("Text"),
            "Href": new_ad.get("Href"),
            "DisplayUrlPath": new_ad.get("DisplayUrlPath"),
            "Mobile": new_ad.get("Mobile"),
            "SitelinkSetId": new_ad.get("SitelinkSetId"),
            "AdImageHash": new_ad.get("AdImageHash"),
            "AdExtensionIds": ad_extension_ids,
        },
    }
    return compact_dict(payload)


def write_output(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Apply a validated ad replacement pack")
    parser.add_argument("--token", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--login", required=True)
    parser.add_argument("--validation-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true", help="live changes; default is dry-run")
    args = parser.parse_args()

    token = load_token(args)
    entries = load_entries(args.validation_json)
    adgroup_ids = sorted({entry["adgroup_id"] for entry in entries})
    live_ads_before = get_ads(token, args.login, adgroup_ids)
    live_by_group = {}
    for ad in live_ads_before:
        live_by_group.setdefault(ad["AdGroupId"], []).append(ad)

    plans = []
    payloads = []
    signature_to_entry = {}
    for entry in entries:
        payload = build_payload(entry)
        signature = ad_signature(payload)
        existing = live_by_group.get(entry["adgroup_id"], [])
        duplicate = next((ad for ad in existing if ad_signature(ad) == signature), None)
        plan = {
            "campaign_id": entry["campaign_id"],
            "adgroup_id": entry["adgroup_id"],
            "replace_ad_id": entry["replace_ad_id"],
            "control_ad_id": entry.get("control_ad_id"),
            "payload": payload,
            "signature": signature,
            "duplicate_ad_id": duplicate.get("Id") if duplicate else None,
            "status": "SKIP" if duplicate else ("PENDING" if args.apply else "DRY_RUN"),
        }
        plans.append(plan)
        if duplicate:
            continue
        payloads.append(payload)
        signature_to_entry[signature] = plan

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "validation_json": args.validation_json,
        "entries_total": len(entries),
        "apply_candidates": len(payloads),
        "plans": plans,
    }

    error_summary = ""
    if args.apply and payloads:
        try:
            add_responses = []
            added_ids = []
            for offset in range(0, len(payloads), 10):
                chunk = payloads[offset : offset + 10]
                resp = api_call(token, args.login, "ads", "add", {"Ads": chunk})
                if "error" in resp:
                    raise RuntimeError(f"ads.add failed: {json.dumps(resp['error'], ensure_ascii=False)}")
                add_results = resp.get("result", {}).get("AddResults", [])
                errors = [item.get("Errors") for item in add_results if item.get("Errors")]
                if errors:
                    raise RuntimeError(f"ads.add item errors: {json.dumps(errors, ensure_ascii=False)}")
                add_responses.append(resp)
                added_ids.extend(item.get("Id") for item in add_results if item.get("Id"))
            report["add_responses"] = add_responses
            report["added_ids"] = added_ids

            live_ads_after = get_ads(token, args.login, adgroup_ids)
            live_after_by_group = {}
            for ad in live_ads_after:
                live_after_by_group.setdefault(ad["AdGroupId"], []).append(ad)

            for plan in plans:
                if plan["status"] == "SKIP":
                    continue
                matches = [
                    ad
                    for ad in live_after_by_group.get(plan["adgroup_id"], [])
                    if ad_signature(ad) == plan["signature"]
                ]
                plan["readback_matches"] = [
                    {"Id": ad["Id"], "Status": ad.get("Status"), "State": ad.get("State")}
                    for ad in matches
                ]
                ok = any(ad.get("Status") == "DRAFT" and ad.get("State") == "OFF" for ad in matches)
                plan["status"] = "OK" if ok else "FAIL"
        except Exception as exc:
            error_summary = f"{type(exc).__name__}: {exc}"
            for plan in plans:
                if plan["status"] in {"PENDING", "DRY_RUN"}:
                    plan["status"] = "FAIL"
            report["error_summary"] = error_summary
    write_output(Path(args.output), report)
    print(
        json.dumps(
            {
                "ok": not error_summary,
                "mode": report["mode"],
                "output": args.output,
                "error_summary": error_summary,
            },
            ensure_ascii=False,
        )
    )
    if error_summary:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
