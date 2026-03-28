#!/usr/bin/env python3
"""Apply or dry-run new search adgroups from a simple manifest."""

from __future__ import annotations

import argparse
import copy
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_V5 = "https://api.direct.yandex.com/json/v5"
API_V501 = "https://api.direct.yandex.com/json/v501"
PUNCT = set(r'.,;:!?—-()[]{}«»""\'/\\@#$%^&*+=~<>|₽')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply new search adgroups from JSON manifest.")
    parser.add_argument("--token", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--login", required=True)
    parser.add_argument("--manifest-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def load_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token
    if args.token_file:
        payload = json.loads(Path(args.token_file).read_text(encoding="utf-8"))
        token = payload.get("access_token")
        if token:
            return token
    raise SystemExit("No token provided. Use --token or --token-file.")


def api_call(service: str, method: str, params: dict[str, Any], token: str, login: str, version: str = "v5") -> dict[str, Any]:
    base = API_V501 if version == "v501" else API_V5
    url = f"{base}/{service}"
    body = json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Login": login,
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Language": "ru",
    }
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} {service}.{method}: {raw}") from exc


def fatal_if_error(resp: dict[str, Any], label: str) -> None:
    if "error" in resp:
        raise RuntimeError(f"{label} failed: {json.dumps(resp['error'], ensure_ascii=False)}")


def maybe_items(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict) and "Items" in value:
        items = [item for item in list(value.get("Items") or []) if item not in {None, ""}]
        return {"Items": items} if items else None
    if isinstance(value, list):
        items = [item for item in value if item not in {None, ""}]
        return {"Items": items} if items else None
    return None


def compact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            compacted = compact(item)
            if compacted is None:
                continue
            out[key] = compacted
        return out or None
    if isinstance(value, list):
        out = [compact(item) for item in value]
        out = [item for item in out if item is not None]
        return out or None
    if value in {"", None}:
        return None
    return value


def normalize_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def sanitize_display_path(value: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ\\s-]", "", str(value or "").strip().lower())
    raw = re.sub(r"[\s-]+", "-", raw).strip("-")
    return raw[:20] if raw else "search"


def sanitize_copy(copy_data: dict[str, Any]) -> dict[str, str]:
    def trim(text: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(text or "").strip())
        return text if len(text) <= limit else text[:limit].rstrip(" ,.;:-")

    def base_len(value: str) -> int:
        return sum(1 for char in str(value or "") if char not in PUNCT)

    def fit_text(text: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(text or "").strip())
        if base_len(text) <= limit:
            return text
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        while len(sentences) > 1 and base_len(" ".join(sentences)) > limit:
            sentences = sentences[:-1]
        candidate = " ".join(sentences).strip()
        if candidate and base_len(candidate) <= limit:
            return candidate
        words = candidate.split() if candidate else text.split()
        while words and base_len(" ".join(words)) > limit:
            words = words[:-1]
        return " ".join(words).strip()

    return {
        "title": trim(copy_data.get("title", ""), 56),
        "title2": trim(copy_data.get("title2", ""), 30),
        "text": fit_text(copy_data.get("text", ""), 80),
    }


def get_template_groups(token: str, login: str, campaign_ids: list[int]) -> list[dict[str, Any]]:
    resp = api_call(
        "adgroups",
        "get",
        {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "CampaignId", "Name", "RegionIds", "TrackingParams"],
            "UnifiedAdGroupFieldNames": ["OfferRetargeting"],
        },
        token,
        login,
        version="v501",
    )
    fatal_if_error(resp, "adgroups.get")
    return resp.get("result", {}).get("AdGroups", [])


def get_group_keywords(token: str, login: str, adgroup_id: int) -> list[dict[str, Any]]:
    resp = api_call(
        "keywords",
        "get",
        {
            "SelectionCriteria": {"AdGroupIds": [adgroup_id]},
            "FieldNames": ["Id", "Keyword", "Bid", "ContextBid"],
        },
        token,
        login,
        version="v5",
    )
    fatal_if_error(resp, "keywords.get")
    return resp.get("result", {}).get("Keywords", [])


def get_group_ads(token: str, login: str, adgroup_id: int) -> list[dict[str, Any]]:
    resp = api_call(
        "ads",
        "get",
        {
            "SelectionCriteria": {"AdGroupIds": [adgroup_id]},
            "FieldNames": ["Id", "AdGroupId", "Status", "State"],
            "TextAdFieldNames": ["Title", "Title2", "Text", "Href", "DisplayUrlPath", "SitelinkSetId", "AdImageHash", "Mobile", "AdExtensions"],
        },
        token,
        login,
        version="v5",
    )
    fatal_if_error(resp, "ads.get")
    return resp.get("result", {}).get("Ads", [])


def sanitize_adgroup_payload(template: dict[str, Any], target_campaign_id: int, name: str, negative_keywords: list[str]) -> dict[str, Any]:
    payload = {
        "CampaignId": target_campaign_id,
        "Name": name,
        "RegionIds": copy.deepcopy(template.get("RegionIds")),
        "TrackingParams": template.get("TrackingParams"),
        "NegativeKeywords": maybe_items(negative_keywords),
        "UnifiedAdGroup": copy.deepcopy(template.get("UnifiedAdGroup")),
    }
    return compact(payload)


def ad_signature(ad_obj: dict[str, Any]) -> tuple[str, str, str]:
    text_ad = ad_obj.get("TextAd") or {}
    return (
        normalize_phrase(text_ad.get("Title") or ""),
        normalize_phrase(text_ad.get("Title2") or ""),
        normalize_phrase(text_ad.get("Text") or ""),
    )


def set_exact_only_autotargeting(token: str, login: str, keyword_ids: list[int]) -> dict[str, Any]:
    if not keyword_ids:
        return {"updated_count": 0, "keyword_ids": []}
    keywords = [
        {
            "Id": keyword_id,
            "AutotargetingSettings": {
                "Categories": {
                    "Exact": "YES",
                    "Narrow": "NO",
                    "Alternative": "NO",
                    "Accessory": "NO",
                    "Broader": "NO",
                },
                "BrandOptions": {
                    "WithoutBrands": "YES",
                    "WithAdvertiserBrand": "YES",
                    "WithCompetitorsBrand": "NO",
                },
            },
        }
        for keyword_id in keyword_ids
    ]
    resp = api_call("keywords", "update", {"Keywords": keywords}, token, login, version="v5")
    fatal_if_error(resp, "keywords.update")
    return {"updated_count": len(keyword_ids), "response": resp, "keyword_ids": keyword_ids}


def main() -> int:
    args = parse_args()
    token = load_token(args)
    manifest_path = Path(args.manifest_json).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    groups = list(manifest.get("groups") or [])
    campaign_ids = sorted({int(group.get("campaign_id") or 0) for group in groups if int(group.get("campaign_id") or 0) > 0})
    templates = get_template_groups(token, args.login, campaign_ids)
    templates_by_id = {int(group.get("Id") or 0): group for group in templates if int(group.get("Id") or 0) > 0}
    groups_by_campaign: dict[int, list[dict[str, Any]]] = {}
    for group in templates:
        groups_by_campaign.setdefault(int(group.get("CampaignId") or 0), []).append(group)

    results: list[dict[str, Any]] = []
    added_ad_ids: list[int] = []
    added_keyword_ids: list[int] = []

    for group_spec in groups:
        campaign_id = int(group_spec.get("campaign_id") or 0)
        name = normalize_phrase(group_spec.get("name") or "")
        template_id = int(group_spec.get("template_adgroup_id") or 0)
        template = templates_by_id.get(template_id)
        if template is None:
            raise RuntimeError(f"template adgroup {template_id} not found for campaign {campaign_id}")

        existing_group = next((item for item in groups_by_campaign.get(campaign_id, []) if normalize_phrase(item.get("Name")) == name), None)
        negative_keywords = [normalize_phrase(item) for item in list(group_spec.get("negative_keywords") or []) if normalize_phrase(item)]
        keywords = [normalize_phrase(item) for item in list(group_spec.get("keywords") or []) if normalize_phrase(item)]
        bid_micros = int(group_spec.get("bid_micros") or 0)
        copy_data = sanitize_copy(group_spec.get("copy") or {})
        href = str(group_spec.get("href") or "").strip()
        display_url_path = str(group_spec.get("display_url_path") or "").strip() or sanitize_display_path(name)
        payload_preview = sanitize_adgroup_payload(template, campaign_id, name, negative_keywords)

        result: dict[str, Any] = {
            "campaign_id": campaign_id,
            "name": name,
            "template_adgroup_id": template_id,
            "mode": "dry-run" if not args.apply else "apply",
            "adgroup_payload": payload_preview,
            "created_adgroup_id": None,
            "keyword_result": {},
            "autotargeting_result": {},
            "ad_result": {},
            "errors": [],
        }

        if existing_group:
            target_adgroup_id = int(existing_group.get("Id") or 0)
            result["created_adgroup_id"] = target_adgroup_id
            result["adgroup_status"] = "REUSE"
        elif not args.apply:
            target_adgroup_id = 0
            result["adgroup_status"] = "DRY_RUN_ADD"
        else:
            add_resp = api_call("adgroups", "add", {"AdGroups": [payload_preview]}, token, args.login, version="v501")
            fatal_if_error(add_resp, "adgroups.add")
            add_results = add_resp.get("result", {}).get("AddResults", [])
            if not add_results or not add_results[0].get("Id"):
                raise RuntimeError(f"adgroups.add returned no Id: {json.dumps(add_resp, ensure_ascii=False)}")
            target_adgroup_id = int(add_results[0]["Id"])
            result["created_adgroup_id"] = target_adgroup_id
            result["adgroup_status"] = "ADDED"
            groups_by_campaign.setdefault(campaign_id, []).append({"Id": target_adgroup_id, "CampaignId": campaign_id, "Name": name})

        existing_keywords = get_group_keywords(token, args.login, target_adgroup_id) if target_adgroup_id else []
        existing_keyword_values = {normalize_phrase(item.get("Keyword") or "") for item in existing_keywords}
        keyword_payload = []
        for keyword in keywords:
            if keyword in existing_keyword_values:
                continue
            item: dict[str, Any] = {"AdGroupId": target_adgroup_id, "Keyword": keyword}
            if bid_micros > 0:
                item["Bid"] = bid_micros
                item["ContextBid"] = bid_micros
            keyword_payload.append(item)
        if not args.apply:
            result["keyword_result"] = {"planned_add_count": len(keyword_payload), "payload_preview": keyword_payload[:10]}
        elif keyword_payload:
            keyword_responses = []
            keyword_ids = []
            for offset in range(0, len(keyword_payload), 1000):
                chunk = keyword_payload[offset : offset + 1000]
                resp = api_call("keywords", "add", {"Keywords": chunk}, token, args.login, version="v5")
                fatal_if_error(resp, "keywords.add")
                keyword_responses.append(resp)
                for item in resp.get("result", {}).get("AddResults", []):
                    if item.get("Id"):
                        keyword_ids.append(int(item["Id"]))
            added_keyword_ids.extend(keyword_ids)
            result["keyword_result"] = {"added_count": len(keyword_ids), "responses": keyword_responses}
            result["autotargeting_result"] = set_exact_only_autotargeting(token, args.login, keyword_ids)
        else:
            result["keyword_result"] = {"added_count": 0, "responses": []}
            result["autotargeting_result"] = {"updated_count": 0, "keyword_ids": []}

        group_ads = get_group_ads(token, args.login, target_adgroup_id) if target_adgroup_id else []
        desired_signature = (
            normalize_phrase(copy_data.get("title")),
            normalize_phrase(copy_data.get("title2")),
            normalize_phrase(copy_data.get("text")),
        )
        duplicate_ad = next((ad for ad in group_ads if ad_signature(ad) == desired_signature), None)
        ad_payload = compact(
            {
                "AdGroupId": target_adgroup_id,
                "TextAd": {
                    "Title": copy_data.get("title"),
                    "Title2": copy_data.get("title2"),
                    "Text": copy_data.get("text"),
                    "Href": href,
                    "DisplayUrlPath": display_url_path,
                },
            }
        )
        if duplicate_ad:
            result["ad_result"] = {"status": "SKIP_DUPLICATE", "ad_id": int(duplicate_ad.get("Id") or 0), "payload": ad_payload}
        elif not args.apply:
            result["ad_result"] = {"status": "DRY_RUN_ADD", "payload": ad_payload}
        else:
            ad_resp = api_call("ads", "add", {"Ads": [ad_payload]}, token, args.login, version="v5")
            fatal_if_error(ad_resp, "ads.add")
            add_results = ad_resp.get("result", {}).get("AddResults", [])
            if add_results and add_results[0].get("Errors"):
                raise RuntimeError(f"ads.add item errors: {json.dumps(add_results[0]['Errors'], ensure_ascii=False)}")
            added_id = int(add_results[0].get("Id") or 0) if add_results else 0
            if added_id:
                added_ad_ids.append(added_id)
            result["ad_result"] = {"status": "ADDED", "ad_id": added_id, "response": ad_resp, "payload": ad_payload}

        if args.apply and target_adgroup_id:
            result["readback"] = {
                "adgroup_id": target_adgroup_id,
                "keywords_total": len(get_group_keywords(token, args.login, target_adgroup_id)),
                "ads_total": len(get_group_ads(token, args.login, target_adgroup_id)),
            }
        results.append(result)

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "manifest_json": str(manifest_path),
        "groups_total": len(groups),
        "results": results,
        "added_ad_ids": added_ad_ids,
        "added_keyword_ids": added_keyword_ids,
        "campaign_ids": campaign_ids,
    }
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output_path), "mode": report["mode"], "groups_total": len(groups), "added_ad_ids": added_ad_ids}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
