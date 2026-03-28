#!/usr/bin/env python3
"""Audit group-specific ad copy and detect cross-group duplicates."""

import argparse
import csv
import json
import os
import re
import urllib.request
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Set, Tuple

API_V5 = "https://api.direct.yandex.com/json/v5"
API_V501 = "https://api.direct.yandex.com/json/v501"


def call_api(token: str, login: str, service: str, method: str, params: dict, version: str = "v5") -> dict:
    base = API_V501 if version == "v501" else API_V5
    req = urllib.request.Request(
        f"{base}/{service}",
        data=json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": "ru",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data


def normalize(text: str) -> str:
    text = (text or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def load_target_group_names(cluster_map_path: str) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = defaultdict(set)
    with open(cluster_map_path, "r", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        for row in rd:
            cname = (row.get("campaign_name") or "").strip()
            gname = (row.get("adgroup_name") or "").strip()
            if cname and gname:
                out[cname].add(gname)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--login", required=True)
    ap.add_argument("--campaign-ids", required=True, help="comma-separated")
    ap.add_argument("--cluster-map", required=True)
    ap.add_argument("--output-tsv", required=True)
    ap.add_argument("--output-json", required=True)
    args = ap.parse_args()

    campaign_ids = [int(x.strip()) for x in args.campaign_ids.split(",") if x.strip()]
    target_group_names = load_target_group_names(args.cluster_map)

    os.makedirs(os.path.dirname(args.output_tsv), exist_ok=True)
    os.makedirs(os.path.dirname(args.output_json), exist_ok=True)

    ag_resp = call_api(
        args.token,
        args.login,
        "adgroups",
        "get",
        {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "Name", "CampaignId"],
        },
        "v501",
    )
    adgroups = ag_resp.get("result", {}).get("AdGroups", [])
    if "error" in ag_resp:
        raise RuntimeError(ag_resp["error"])

    camp_resp = call_api(
        args.token,
        args.login,
        "campaigns",
        "get",
        {"SelectionCriteria": {"Ids": campaign_ids}, "FieldNames": ["Id", "Name"]},
        "v501",
    )
    if "error" in camp_resp:
        raise RuntimeError(camp_resp["error"])
    cid_to_name = {c["Id"]: c["Name"] for c in camp_resp.get("result", {}).get("Campaigns", [])}

    target_gids = []
    gid_to_name = {}
    for g in adgroups:
        gid = g["Id"]
        cname = cid_to_name.get(g["CampaignId"], str(g["CampaignId"]))
        gname = g["Name"]
        gid_to_name[gid] = gname
        if gname in target_group_names.get(cname, set()):
            target_gids.append(gid)

    ads_resp = call_api(
        args.token,
        args.login,
        "ads",
        "get",
        {
            "SelectionCriteria": {"AdGroupIds": target_gids},
            "FieldNames": ["Id", "AdGroupId", "CampaignId", "Status", "State"],
            "TextAdFieldNames": ["Title", "Title2", "Text"],
        },
        "v5",
    )
    if "error" in ads_resp:
        raise RuntimeError(ads_resp["error"])
    ads = ads_resp.get("result", {}).get("Ads", [])

    by_group: Dict[int, List[Tuple[int, str, str, str]]] = defaultdict(list)
    copy_to_groups: Dict[Tuple[str, str, str], Set[int]] = defaultdict(set)
    for a in ads:
        t = a.get("TextAd") or {}
        title = (t.get("Title") or "").strip()
        title2 = (t.get("Title2") or "").strip()
        text = (t.get("Text") or "").strip()
        rec = (title, title2, text)
        gid = a["AdGroupId"]
        by_group[gid].append((a["Id"], title, title2, text))
        copy_to_groups[rec].add(gid)

    with open(args.output_tsv, "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f, delimiter="\t")
        wr.writerow(["adgroup_id", "adgroup_name", "ad_id", "title", "title2", "text"])
        for gid in sorted(by_group.keys(), key=lambda x: gid_to_name.get(x, "")):
            for ad_id, title, title2, text in sorted(by_group[gid], key=lambda r: r[0]):
                wr.writerow([gid, gid_to_name.get(gid, ""), ad_id, title, title2, text])

    duplicates = []
    for (title, title2, text), gids in copy_to_groups.items():
        if len(gids) <= 1:
            continue
        duplicates.append(
            {
                "title": title,
                "title2": title2,
                "text": text,
                "group_ids": sorted(gids),
                "groups_count": len(gids),
            }
        )

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "target_groups": len(target_gids),
        "ads_total_target_groups": len(ads),
        "groups_with_5_ads": sum(1 for gid in target_gids if len(by_group.get(gid, [])) == 5),
        "cross_group_duplicate_copies": len(duplicates),
        "sample_duplicates": duplicates[:20],
        "target_groups_with_non5_ads": [
            {"adgroup_id": gid, "adgroup_name": gid_to_name.get(gid, ""), "ads_count": len(by_group.get(gid, []))}
            for gid in sorted(target_gids)
            if len(by_group.get(gid, [])) != 5
        ],
    }
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps({"status": "ok", "summary": args.output_json, "duplicates": len(duplicates)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

