#!/usr/bin/env python3
"""
Полный сбор данных по кампании Яндекс.Директ (v2).
Management API + Reports API + Metrica API + Roistat API + помесячная динамика.

Запуск:
  python3 collect_all.py --token TOKEN --login LOGIN --campaign-id 91307551 --output-dir ./data/91307551
  python3 collect_all.py --token TOKEN --login LOGIN --campaign-id 91307551 --output-dir ./data/91307551 --skip-roistat
  python3 collect_all.py --token TOKEN --login LOGIN --campaign-id 91307551 --output-dir ./data/91307551 \
    --roistat-key YOUR_KEY --roistat-project YOUR_PROJECT

Результат: JSON + TSV файлы в output-dir (30+ файлов).
v2: добавлены блоки D (Roistat API) и E (помесячная динамика + changelog).
v3: Roistat опционален — --skip-roistat или без --roistat-key пропускает блоки D+E.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid

# === CONFIG ===
API_V5 = "https://api.direct.yandex.com/json/v5"
API_V501 = "https://api.direct.yandex.com/json/v501"
METRICA_API = "https://api-metrica.yandex.net/stat/v1/data"
METRICA_COUNTER = os.environ.get("YANDEX_METRIKA_COUNTER", "")
GOAL_ID = os.environ.get("YANDEX_DIRECT_GOAL_ID", "")
ROISTAT_API = os.environ.get("ROISTAT_BASE_URL", "https://cloud.roistat.com/api/v1")
ROISTAT_KEY = os.environ.get("ROISTAT_API_KEY", "")
ROISTAT_PROJECT = os.environ.get("ROISTAT_PROJECT", "")
ROISTAT_MARKER_LEVEL_1 = os.environ.get("ROISTAT_MARKER_LEVEL_1", "")
ROISTAT_MARKER_LEVEL_2_SEARCH = os.environ.get("ROISTAT_MARKER_LEVEL_2_SEARCH", "")

# === HELPERS ===

def api_call(endpoint, method, params, token, login, version="v5", retries=3):
    """Вызов Management API Директа."""
    base = API_V501 if version == "v501" else API_V5
    url = f"{base}/{endpoint}"
    body = json.dumps({"method": method, "params": params}).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Content-Type": "application/json",
            "Accept-Language": "ru"
        })
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"  ERROR {e.code}: {error_body[:300]}", file=sys.stderr)
            return {"error": json.loads(error_body) if error_body.startswith("{") else {"message": error_body}}
        except Exception as e:
            print(f"  Network error (attempt {attempt+1}/{retries}): {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(5)
            continue
    print(f"  api_call FAILED after {retries} attempts", file=sys.stderr)
    return {"error": {"message": f"Network failure after {retries} retries"}}


def get_report(report_type, fields, date_from, date_to, token, login, campaign_id, extra_name=""):
    """Запрос Reports API с ретраями на 201/202."""
    suffix = uuid.uuid4().hex[:8]
    report_name = f"{report_type}_{extra_name}_{campaign_id}_{int(time.time() * 1000)}_{suffix}"
    params = {
        "SelectionCriteria": {
            "DateFrom": date_from,
            "DateTo": date_to,
            "Filter": [{"Field": "CampaignId", "Operator": "EQUALS", "Values": [str(campaign_id)]}],
        },
        "FieldNames": fields,
        "ReportName": report_name,
        "ReportType": report_type,
        "DateRangeType": "CUSTOM_DATE",
        "Format": "TSV",
        "IncludeVAT": "YES",
        "IncludeDiscount": "NO",
    }
    if GOAL_ID:
        params["Goals"] = [GOAL_ID]
        params["AttributionModels"] = ["LC"]
    body = {"params": params}
    req = urllib.request.Request(
        f"{API_V5}/reports",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Content-Type": "application/json",
            "processingMode": "auto",
            "returnMoneyInMicros": "false",
            "skipReportHeader": "true",
            "skipReportSummary": "true"
        }
    )
    for attempt in range(20):
        # Fresh request each attempt
        req = urllib.request.Request(
            f"{API_V5}/reports",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Client-Login": login,
                "Content-Type": "application/json",
                "processingMode": "auto",
                "returnMoneyInMicros": "false",
                "skipReportHeader": "true",
                "skipReportSummary": "true"
            }
        )
        try:
            resp = urllib.request.urlopen(req)
            status = resp.status
            result = resp.read().decode("utf-8")
            # 201/202 can come as "successful" response with empty body
            if status in (201, 202) or (status == 200 and len(result.strip()) == 0):
                wait = int(resp.headers.get("retryIn", 15))
                if wait < 5:
                    wait = 15
                print(f"    Report queued (HTTP {status}), waiting {wait}s (attempt {attempt+1})...")
                time.sleep(wait)
                continue
            return result
        except urllib.error.HTTPError as e:
            if e.code in (201, 202):
                wait = int(e.headers.get("retryIn", 15))
                if wait < 5:
                    wait = 15
                print(f"    Report queued (HTTP {e.code}), waiting {wait}s (attempt {attempt+1})...")
                time.sleep(wait)
                continue
            error_body = e.read().decode("utf-8")
            print(f"  REPORT ERROR {e.code}: {error_body[:300]}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"    Network error (attempt {attempt+1}/20): {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(10)
            continue
    print("  REPORT TIMEOUT after 20 attempts", file=sys.stderr)
    return None


def metrica_call(dimensions, metrics, token, date1, date2, campaign_filter=None, limit=50, sort="-ym:s:visits", retries=3):
    """Запрос Metrica API."""
    if not METRICA_COUNTER:
        return None
    params = {
        "ids": METRICA_COUNTER,
        "metrics": metrics,
        "dimensions": dimensions,
        "date1": date1,
        "date2": date2,
        "limit": str(limit),
        "sort": sort
    }
    if campaign_filter:
        params["filters"] = campaign_filter
    url = f"{METRICA_API}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "Authorization": f"OAuth {token}"
        })
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"  METRICA ERROR {e.code}: {error_body[:300]}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"  METRICA network error (attempt {attempt+1}/{retries}): {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(5)
            continue
    print(f"  metrica_call FAILED after {retries} attempts", file=sys.stderr)
    return None


def save_json(data, filepath):
    """Сохранить JSON."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    count = 0
    if isinstance(data, dict):
        result = data.get("result", data)
        for key in result:
            val = result[key]
            if isinstance(val, list):
                count = len(val)
                break
    print(f"  Saved: {filepath} ({count} items)")


def save_tsv(data, filepath):
    """Сохранить TSV."""
    if data is None:
        print(f"  SKIP: {filepath} (no data)")
        return
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(data)
    lines = [l for l in data.strip().split("\n") if l]
    # First line is header
    data_lines = len(lines) - 1 if len(lines) > 0 else 0
    print(f"  Saved: {filepath} ({data_lines} rows)")


def save_metrica_tsv(data, filepath, dim_names, metric_names):
    """Конвертировать Metrica JSON в TSV и сохранить."""
    if data is None or "data" not in data:
        print(f"  SKIP: {filepath} (no data)")
        return
    rows = data["data"]
    header = "\t".join(dim_names + metric_names)
    lines = [header]
    for row in rows:
        dims = row["dimensions"]
        metrics = row["metrics"]
        dim_vals = []
        for d in dims:
            dim_vals.append(str(d.get("name", d.get("id", "?"))))
        metric_vals = [str(round(m, 2) if isinstance(m, float) else m) for m in metrics]
        lines.append("\t".join(dim_vals + metric_vals))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Saved: {filepath} ({len(rows)} rows)")


# === COLLECTION FUNCTIONS ===

def collect_management(token, login, campaign_id, outdir):
    """Сбор Management API → JSON."""
    print("\n=== MANAGEMENT API ===")
    mgmt_dir = os.path.join(outdir, "management")
    os.makedirs(mgmt_dir, exist_ok=True)

    # 1. Campaign (full)
    print("1. Campaign...")
    result = api_call("campaigns", "get", {
        "SelectionCriteria": {"Ids": [campaign_id]},
        "FieldNames": ["Id", "Name", "Status", "State", "StartDate", "DailyBudget",
                       "NegativeKeywords", "TimeTargeting"],
        "UnifiedCampaignFieldNames": ["BiddingStrategy", "CounterIds", "PriorityGoals",
                                       "TrackingParams", "Settings", "NegativeKeywordSharedSetIds"],
        "UnifiedCampaignSearchStrategyPlacementTypesFieldNames": [
            "SearchResults", "ProductGallery", "DynamicPlaces", "Maps", "SearchOrganizationList"
        ]
    }, token, login, version="v501")
    save_json(result, os.path.join(mgmt_dir, "campaign.json"))
    time.sleep(1)

    # Extract shared neg set IDs for later
    shared_neg_ids = []
    camps = result.get("result", {}).get("Campaigns", [])
    if camps:
        uc = camps[0].get("UnifiedCampaign", {})
        shared_neg_ids = uc.get("NegativeKeywordSharedSetIds", {}).get("Items", [])

    # 2. Ad Groups
    print("2. Ad Groups...")
    result = api_call("adgroups", "get", {
        "SelectionCriteria": {"CampaignIds": [campaign_id]},
        "FieldNames": ["Id", "Name", "CampaignId", "Status", "ServingStatus",
                       "RegionIds", "NegativeKeywords", "NegativeKeywordSharedSetIds", "TrackingParams"],
        "UnifiedAdGroupFieldNames": ["OfferRetargeting"]
    }, token, login, version="v501")
    save_json(result, os.path.join(mgmt_dir, "adgroups.json"))
    time.sleep(1)

    # Collect group-level shared neg IDs too
    for grp in result.get("result", {}).get("AdGroups", []):
        nks = grp.get("NegativeKeywordSharedSetIds")
        grp_neg_ids = nks.get("Items", []) if isinstance(nks, dict) else []
        shared_neg_ids.extend(grp_neg_ids)
    shared_neg_ids = list(set(shared_neg_ids))

    # 3. Ads
    print("3. Ads...")
    result = api_call("ads", "get", {
        "SelectionCriteria": {"CampaignIds": [campaign_id]},
        "FieldNames": ["Id", "AdGroupId", "CampaignId", "Status", "State", "Type"],
        "TextAdFieldNames": ["Title", "Title2", "Text", "Href", "DisplayUrlPath",
                             "AdImageHash", "SitelinkSetId", "Mobile",
                             "SitelinksModeration", "AdImageModeration", "AdExtensions"],
        "ShoppingAdFieldNames": ["FeedId", "DefaultTexts"]
    }, token, login, version="v501")
    save_json(result, os.path.join(mgmt_dir, "ads.json"))
    time.sleep(1)

    # Extract sitelink set IDs and extension IDs
    sitelink_ids = set()
    extension_ids = set()
    for ad in result.get("result", {}).get("Ads", []):
        ta = ad.get("TextAd", {})
        sl_id = ta.get("SitelinkSetId")
        if sl_id:
            sitelink_ids.add(sl_id)
        for ext in ta.get("AdExtensions", []):
            if ext.get("Type") == "CALLOUT":
                extension_ids.add(ext.get("AdExtensionId"))

    # 4. Keywords
    print("4. Keywords...")
    result = api_call("keywords", "get", {
        "SelectionCriteria": {"CampaignIds": [campaign_id]},
        "FieldNames": ["Id", "Keyword", "AdGroupId", "Status", "State", "AutotargetingCategories"]
    }, token, login, version="v5")
    save_json(result, os.path.join(mgmt_dir, "keywords.json"))
    time.sleep(1)

    # 5. Sitelinks
    print(f"5. Sitelinks ({len(sitelink_ids)} sets)...")
    if sitelink_ids:
        result = api_call("sitelinks", "get", {
            "SelectionCriteria": {"Ids": list(sitelink_ids)},
            "FieldNames": ["Id", "Sitelinks"]
        }, token, login, version="v5")
        save_json(result, os.path.join(mgmt_dir, "sitelinks.json"))
    else:
        save_json({"result": {"SitelinksSets": []}}, os.path.join(mgmt_dir, "sitelinks.json"))
    time.sleep(1)

    # 6. Ad Extensions (Callouts)
    print(f"6. Ad Extensions ({len(extension_ids)} callouts)...")
    if extension_ids:
        result = api_call("adextensions", "get", {
            "SelectionCriteria": {"Ids": list(extension_ids)},
            "FieldNames": ["Id", "Status", "Type"],
            "CalloutFieldNames": ["CalloutText"]
        }, token, login, version="v5")
        save_json(result, os.path.join(mgmt_dir, "adextensions.json"))
    else:
        save_json({"result": {"AdExtensions": []}}, os.path.join(mgmt_dir, "adextensions.json"))
    time.sleep(1)

    # 7. Negative Keyword Shared Sets
    print(f"7. Negative Keyword Shared Sets ({len(shared_neg_ids)} sets)...")
    if shared_neg_ids:
        result = api_call("negativekeywordsharedsets", "get", {
            "SelectionCriteria": {"Ids": shared_neg_ids},
            "FieldNames": ["Id", "Name", "NegativeKeywords"]
        }, token, login, version="v5")
        save_json(result, os.path.join(mgmt_dir, "negative_sets.json"))
    else:
        save_json({"result": {"NegativeKeywordSharedSets": []}}, os.path.join(mgmt_dir, "negative_sets.json"))

    print("Management API: DONE")


def collect_reports(token, login, campaign_id, outdir):
    """Сбор Reports API → TSV."""
    print("\n=== REPORTS API ===")
    reports_dir = os.path.join(outdir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    # Use yesterday as DateTo (today is incomplete)
    import datetime
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    d30_start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    d90_start = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    alltime_start = "2023-07-11"
    periods = [("30d", d30_start, yesterday), ("90d", d90_start, yesterday), ("alltime", alltime_start, yesterday)]
    print(f"  Periods: 30d={d30_start}..{yesterday}, 90d={d90_start}..{yesterday}, alltime={alltime_start}..{yesterday}")

    # --- ADGROUP_PERFORMANCE_REPORT (3 periods) ---
    adgroup_fields = ["AdGroupId", "AdGroupName", "Impressions", "Clicks", "Cost",
                      "Ctr", "AvgCpc", "Conversions", "CostPerConversion", "ConversionRate",
                      "BounceRate", "AvgImpressionPosition", "AvgClickPosition", "AvgTrafficVolume"]
    for period_name, date_from, date_to in periods:
        print(f"AdGroup {period_name}...")
        data = get_report("ADGROUP_PERFORMANCE_REPORT", adgroup_fields,
                         date_from, date_to, token, login, campaign_id, f"adgroup_{period_name}")
        save_tsv(data, os.path.join(reports_dir, f"adgroup_{period_name}.tsv"))
        time.sleep(3)

    # --- CRITERIA_PERFORMANCE_REPORT (3 periods) ---
    criteria_fields = ["CriterionId", "Criterion", "CriteriaType", "AdGroupId", "AdGroupName",
                       "MatchType", "Impressions", "Clicks", "Cost", "Ctr", "AvgCpc",
                       "Conversions", "CostPerConversion", "ConversionRate", "BounceRate",
                       "AvgImpressionPosition", "AvgClickPosition", "AvgTrafficVolume"]
    for period_name, date_from, date_to in periods:
        print(f"Criteria {period_name}...")
        data = get_report("CRITERIA_PERFORMANCE_REPORT", criteria_fields,
                         date_from, date_to, token, login, campaign_id, f"criteria_{period_name}")
        save_tsv(data, os.path.join(reports_dir, f"criteria_{period_name}.tsv"))
        time.sleep(3)

    # --- AD_PERFORMANCE_REPORT (3 periods) ---
    ad_fields = ["AdId", "AdGroupId", "AdGroupName", "Impressions", "Clicks", "Cost",
                 "Ctr", "AvgCpc", "Conversions", "CostPerConversion", "ConversionRate"]
    for period_name, date_from, date_to in periods:
        print(f"Ad {period_name}...")
        data = get_report("AD_PERFORMANCE_REPORT", ad_fields,
                         date_from, date_to, token, login, campaign_id, f"ad_{period_name}")
        save_tsv(data, os.path.join(reports_dir, f"ad_{period_name}.tsv"))
        time.sleep(3)

    # --- SEARCH_QUERY_PERFORMANCE_REPORT (30d only) ---
    sq_fields = ["Query", "AdGroupId", "AdGroupName", "CriterionId", "Criterion",
                 "Impressions", "Clicks", "Cost", "Ctr", "AvgCpc", "Conversions", "CostPerConversion"]
    print("Search Query 30d...")
    data = get_report("SEARCH_QUERY_PERFORMANCE_REPORT", sq_fields,
                     d30_start, yesterday, token, login, campaign_id, "sq_30d")
    save_tsv(data, os.path.join(reports_dir, "search_query_30d.tsv"))
    time.sleep(3)

    # --- CAMPAIGN daily (30d) ---
    daily_fields = ["Date", "Impressions", "Clicks", "Cost", "Conversions",
                    "CostPerConversion", "ConversionRate", "Ctr", "AvgCpc", "BounceRate"]
    print("Campaign daily 30d...")
    data = get_report("CAMPAIGN_PERFORMANCE_REPORT", daily_fields,
                     d30_start, yesterday, token, login, campaign_id, "daily_30d")
    save_tsv(data, os.path.join(reports_dir, "campaign_daily_30d.tsv"))
    time.sleep(3)

    # --- CAMPAIGN by Device (30d) ---
    device_fields = ["Device", "Impressions", "Clicks", "Cost", "Conversions",
                     "CostPerConversion", "ConversionRate", "BounceRate"]
    print("Campaign device 30d...")
    data = get_report("CAMPAIGN_PERFORMANCE_REPORT", device_fields,
                     d30_start, yesterday, token, login, campaign_id, "device_30d")
    save_tsv(data, os.path.join(reports_dir, "campaign_device_30d.tsv"))
    time.sleep(3)

    # --- CAMPAIGN by Gender+Age (30d) ---
    demo_fields = ["Gender", "Age", "Impressions", "Clicks", "Cost", "Conversions"]
    print("Campaign demographics 30d...")
    data = get_report("CAMPAIGN_PERFORMANCE_REPORT", demo_fields,
                     d30_start, yesterday, token, login, campaign_id, "demo_30d")
    save_tsv(data, os.path.join(reports_dir, "campaign_demographics_30d.tsv"))
    time.sleep(3)

    # --- CAMPAIGN by Slot (30d) ---
    slot_fields = ["Slot", "Impressions", "Clicks", "Cost", "Conversions"]
    print("Campaign slot 30d...")
    data = get_report("CAMPAIGN_PERFORMANCE_REPORT", slot_fields,
                     d30_start, yesterday, token, login, campaign_id, "slot_30d")
    save_tsv(data, os.path.join(reports_dir, "campaign_slot_30d.tsv"))
    time.sleep(3)

    # --- ADGROUP by Device (30d) ---
    ag_device_fields = ["AdGroupId", "AdGroupName", "Device", "Impressions", "Clicks",
                        "Cost", "Conversions", "ConversionRate", "BounceRate"]
    print("AdGroup device 30d...")
    data = get_report("ADGROUP_PERFORMANCE_REPORT", ag_device_fields,
                     d30_start, yesterday, token, login, campaign_id, "ag_device_30d")
    save_tsv(data, os.path.join(reports_dir, "adgroup_device_30d.tsv"))

    print("Reports API: DONE")


def collect_metrica(token, outdir, campaign_id):
    """Сбор Metrica API → TSV."""
    if not METRICA_COUNTER or not GOAL_ID:
        print("\n=== METRICA API === SKIPPED (missing metrica counter or goal id)")
        return False

    print("\n=== METRICA API ===")
    metrica_dir = os.path.join(outdir, "metrica")
    os.makedirs(metrica_dir, exist_ok=True)

    import datetime

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    d2 = yesterday.isoformat()
    d1 = (yesterday - datetime.timedelta(days=29)).isoformat()
    metrica_campaign_id = f"1{campaign_id}"  # Metrica adds "1" prefix
    campaign_filter = f"ym:s:lastSignDirectClickOrder=='{metrica_campaign_id}'"
    metrics = f"ym:s:visits,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds,ym:s:goal{GOAL_ID}visits,ym:s:goal{GOAL_ID}reaches"
    metric_names = ["visits", "bounce_rate", "page_depth", "avg_duration", "goal_visits", "goal_reaches"]

    # 1. By ad groups
    print("1. Metrica groups...")
    data = metrica_call("ym:s:lastSignDirectBannerGroup", metrics, token, d1, d2,
                        campaign_filter=campaign_filter, limit=50)
    save_metrica_tsv(data, os.path.join(metrica_dir, "groups.tsv"),
                     ["group_name"], metric_names)
    time.sleep(2)

    # 2. By devices
    print("2. Metrica devices...")
    data = metrica_call("ym:s:deviceCategory", metrics, token, d1, d2,
                        campaign_filter=campaign_filter, limit=10)
    save_metrica_tsv(data, os.path.join(metrica_dir, "devices.tsv"),
                     ["device"], metric_names)
    time.sleep(2)

    # 3. By demographics
    print("3. Metrica demographics...")
    data = metrica_call("ym:s:gender,ym:s:ageInterval", metrics, token, d1, d2,
                        campaign_filter=campaign_filter, limit=30)
    save_metrica_tsv(data, os.path.join(metrica_dir, "demographics.tsv"),
                     ["gender", "age"], metric_names)
    time.sleep(2)

    # 4. By landing pages (try multiple dimensions)
    print("4. Metrica landing pages...")
    for dim in ["ym:s:startURLPathLevel1", "ym:s:startURLPath", "ym:s:startURL"]:
        data = metrica_call(dim, metrics, token, d1, d2,
                            campaign_filter=campaign_filter, limit=50)
        if data and data.get("data"):
            save_metrica_tsv(data, os.path.join(metrica_dir, "landing_pages.tsv"),
                             ["url_path"], metric_names)
            break
        time.sleep(2)
    else:
        print("  SKIP: landing_pages.tsv (no data from any dimension)")

    # 5. All campaigns comparison (NO filter)
    print("5. Metrica all campaigns...")
    data = metrica_call("ym:s:lastSignDirectClickOrder", metrics, token, d1, d2,
                        limit=50)
    if data and "data" in data:
        # Custom save with campaign_id + name
        rows = data["data"]
        header = "campaign_id\tcampaign_name\t" + "\t".join(metric_names)
        lines = [header]
        for row in rows:
            d = row["dimensions"][0]
            m = row["metrics"]
            cid = d.get("id", "?")
            cname = d.get("name", "?")
            mvals = [str(round(v, 2) if isinstance(v, float) else v) for v in m]
            lines.append(f"{cid}\t{cname}\t" + "\t".join(mvals))
        with open(os.path.join(metrica_dir, "all_campaigns.tsv"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"  Saved: all_campaigns.tsv ({len(rows)} rows)")

    print("Metrica API: DONE")
    return True


def validate_data(outdir, include_metrica=True):
    """Кросс-валидация собранных данных."""
    print("\n=== VALIDATION ===")
    validation = {"checks": [], "status": "OK"}

    # Check all expected files exist
    expected_files = [
        "management/campaign.json", "management/adgroups.json", "management/ads.json",
        "management/keywords.json", "management/sitelinks.json",
        "management/adextensions.json", "management/negative_sets.json",
        "reports/adgroup_30d.tsv", "reports/adgroup_90d.tsv", "reports/adgroup_alltime.tsv",
        "reports/criteria_30d.tsv", "reports/criteria_90d.tsv", "reports/criteria_alltime.tsv",
        "reports/ad_30d.tsv", "reports/ad_90d.tsv", "reports/ad_alltime.tsv",
        "reports/search_query_30d.tsv", "reports/campaign_daily_30d.tsv",
        "reports/campaign_device_30d.tsv", "reports/campaign_demographics_30d.tsv",
        "reports/campaign_slot_30d.tsv", "reports/adgroup_device_30d.tsv",
    ]
    if include_metrica:
        expected_files.extend(
            [
                "metrica/groups.tsv",
                "metrica/devices.tsv",
                "metrica/demographics.tsv",
                "metrica/all_campaigns.tsv",
            ]
        )

    for f in expected_files:
        fp = os.path.join(outdir, f)
        exists = os.path.exists(fp)
        size = os.path.getsize(fp) if exists else 0
        status = "OK" if exists and size > 10 else "FAIL"
        if status == "FAIL":
            validation["status"] = "FAIL"
        validation["checks"].append({"file": f, "exists": exists, "size": size, "status": status})
        if status == "FAIL":
            print(f"  FAIL: {f} ({'missing' if not exists else f'{size} bytes'})")

    # Check JSON files for errors
    for jf in ["management/campaign.json", "management/adgroups.json",
                "management/ads.json", "management/keywords.json"]:
        fp = os.path.join(outdir, jf)
        if os.path.exists(fp):
            with open(fp) as f:
                data = json.load(f)
            if "error" in data:
                validation["status"] = "FAIL"
                validation["checks"].append({"file": jf, "status": "API_ERROR", "error": data["error"]})
                print(f"  API ERROR in {jf}: {data['error']}")

    save_json(validation, os.path.join(outdir, "validation.json"))
    ok_count = sum(1 for c in validation["checks"] if c["status"] == "OK")
    total = len(validation["checks"])
    print(f"\nValidation: {ok_count}/{total} OK, status={validation['status']}")
    return validation["status"] == "OK"


# === ROISTAT (Block D) ===

def roistat_call(endpoint, body, retries=3):
    """Вызов Roistat API с ретраями на IncompleteRead. Читает по чанкам."""
    import http.client
    url = f"{ROISTAT_API}/{endpoint}?project={ROISTAT_PROJECT}"
    raw_data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=raw_data, headers={
            "Content-Type": "application/json",
            "Api-key": ROISTAT_KEY
        })
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            # Read in chunks to handle chunked transfer encoding
            chunks = []
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                chunks.append(chunk)
            full_body = b"".join(chunks)
            return json.loads(full_body.decode("utf-8"))
        except http.client.IncompleteRead as e:
            # Try to use partial data if it's valid JSON
            partial = e.partial if hasattr(e, 'partial') else e.args[0] if e.args else b""
            if partial:
                try:
                    return json.loads(partial.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            print(f"  ROISTAT IncompleteRead (attempt {attempt+1}/{retries}), retrying in 10s...", file=sys.stderr)
            time.sleep(10)
            continue
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"  ROISTAT ERROR {e.code}: {error_body[:300]}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"  ROISTAT EXCEPTION (attempt {attempt+1}/{retries}): {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(10)
            continue
    print(f"  ROISTAT FAILED after {retries} attempts", file=sys.stderr)
    return None


def collect_roistat(campaign_id, outdir):
    """Блок D: Roistat API — leads, sales, revenue по группам/ключам/объявлениям."""
    import datetime
    print("\n=== ROISTAT API (Block D) ===")
    roi_dir = os.path.join(outdir, "roistat")
    os.makedirs(roi_dir, exist_ok=True)

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    d30_from = (yesterday - datetime.timedelta(days=29)).strftime("%Y-%m-%dT00:00:00+0300")
    d30_to = yesterday.strftime("%Y-%m-%dT23:59:59+0300")
    d90_from = (yesterday - datetime.timedelta(days=89)).strftime("%Y-%m-%dT00:00:00+0300")
    cid = str(campaign_id)

    base_metrics = ["visits", "leads",
                    {"metric": "sales", "attribution": "first_click"},
                    {"metric": "sales", "attribution": "last_click"},
                    "revenue", "marketing_cost", "cpl", "cpo"]
    base_filter = [{"field": "marker_level_3", "operation": "=", "value": cid}]
    if ROISTAT_MARKER_LEVEL_1:
        base_filter.insert(0, {"field": "marker_level_1", "operation": "=", "value": ROISTAT_MARKER_LEVEL_1})

    queries = [
        ("adgroups_30d", ["marker_level_4"], base_metrics, d30_from, d30_to),
        ("adgroups_90d", ["marker_level_4"], base_metrics, d90_from, d30_to),
        ("keywords_30d", ["utm_term"], ["visits", "leads", "sales", "revenue", "cpl"], d30_from, d30_to),
        ("ads_30d", ["marker_level_5"], base_metrics, d30_from, d30_to),
        ("campaigns_30d", ["marker_level_3"],
         ["visits", "leads", "sales", "revenue", "marketing_cost", "profit", "roi", "cpl", "cpo"],
         d30_from, d30_to),
        ("daily_30d", ["date"], ["visits", "leads", "sales", "revenue", "marketing_cost"], d30_from, d30_to),
        ("devices_30d", ["device_type"], ["visits", "leads", "sales", "revenue", "bounce_rate"], d30_from, d30_to),
    ]

    for name, dims, metrics, dt_from, dt_to in queries:
        print(f"  Roistat {name}...")
        # campaigns_30d uses different filter (no marker_level_3)
        if name == "campaigns_30d":
            filt = []
            if ROISTAT_MARKER_LEVEL_1:
                filt.append({"field": "marker_level_1", "operation": "=", "value": ROISTAT_MARKER_LEVEL_1})
            if ROISTAT_MARKER_LEVEL_2_SEARCH:
                filt.append({"field": "marker_level_2", "operation": "=", "value": ROISTAT_MARKER_LEVEL_2_SEARCH})
        else:
            filt = base_filter

        body = {
            "dimensions": dims,
            "metrics": metrics,
            "period": {"from": dt_from, "to": dt_to},
            "filters": filt
        }
        result = roistat_call("project/analytics/data", body)
        if result:
            filepath = os.path.join(roi_dir, f"{name}.json")
            save_json(result, filepath)
        time.sleep(1)

    print("Roistat API: DONE")


def collect_monthly(campaign_id, outdir):
    """Блок E: Помесячная динамика за последние 6 месяцев."""
    import datetime
    print("\n=== MONTHLY DYNAMICS (Block E) ===")
    roi_dir = os.path.join(outdir, "roistat")
    os.makedirs(roi_dir, exist_ok=True)

    cid = str(campaign_id)
    today = datetime.date.today()
    monthly_data = []

    for months_ago in range(6, 0, -1):
        # First day of month N months ago
        year = today.year
        month = today.month - months_ago
        while month <= 0:
            month += 12
            year -= 1
        month_start = datetime.date(year, month, 1)

        # Last day of that month
        if month == 12:
            month_end = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            month_end = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

        dt_from = month_start.strftime("%Y-%m-%dT00:00:00+0300")
        dt_to = month_end.strftime("%Y-%m-%dT23:59:59+0300")
        label = month_start.strftime("%Y-%m")

        print(f"  Monthly {label}...")
        body = {
            "dimensions": ["marker_level_4"],
            "metrics": ["visits", "leads", "sales", "revenue", "marketing_cost", "cpl"],
            "period": {"from": dt_from, "to": dt_to},
            "filters": (
                ([{"field": "marker_level_1", "operation": "=", "value": ROISTAT_MARKER_LEVEL_1}] if ROISTAT_MARKER_LEVEL_1 else [])
                + [{"field": "marker_level_3", "operation": "=", "value": cid}]
            )
        }
        result = roistat_call("project/analytics/data", body)
        if result:
            filepath = os.path.join(roi_dir, f"monthly_{label}.json")
            save_json(result, filepath)
            monthly_data.append({"month": label, "data": result})
        time.sleep(1)

    # Campaign-level monthly summary
    print("  Monthly campaign summary...")
    campaign_monthly = []
    for months_ago in range(6, 0, -1):
        year = today.year
        month = today.month - months_ago
        while month <= 0:
            month += 12
            year -= 1
        month_start = datetime.date(year, month, 1)
        if month == 12:
            month_end = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            month_end = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

        dt_from = month_start.strftime("%Y-%m-%dT00:00:00+0300")
        dt_to = month_end.strftime("%Y-%m-%dT23:59:59+0300")
        label = month_start.strftime("%Y-%m")

        body = {
            "dimensions": ["marker_level_3"],
            "metrics": ["visits", "leads", "sales", "revenue", "marketing_cost", "profit", "roi", "cpl", "cpo"],
            "period": {"from": dt_from, "to": dt_to},
            "filters": (
                ([{"field": "marker_level_1", "operation": "=", "value": ROISTAT_MARKER_LEVEL_1}] if ROISTAT_MARKER_LEVEL_1 else [])
                + [{"field": "marker_level_3", "operation": "=", "value": cid}]
            )
        }
        result = roistat_call("project/analytics/data", body)
        if result:
            campaign_monthly.append({"month": label, "data": result})
        time.sleep(1)

    save_json(campaign_monthly, os.path.join(roi_dir, "monthly_campaign.json"))
    print("Monthly Dynamics: DONE")


# === MAIN ===

def main():
    parser = argparse.ArgumentParser(description="Полный сбор данных по кампании Директа")
    parser.add_argument("--token", required=True, help="OAuth token")
    parser.add_argument("--login", required=True, help="Client login")
    parser.add_argument("--campaign-id", required=True, type=int, help="Campaign ID")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--metrica-counter", default="", help="Yandex Metrika counter ID")
    parser.add_argument("--goal-id", default="", help="Primary goal ID for reports/metrika")
    parser.add_argument("--skip-metrica", action="store_true", default=False, help="Пропустить блок Metrica")
    parser.add_argument("--skip-roistat", action="store_true", default=False,
                        help="Пропустить блоки D (Roistat API) и E (monthly dynamics)")
    parser.add_argument("--roistat-key", default="", help="Roistat API key")
    parser.add_argument("--roistat-project", default="", help="Roistat project ID")
    parser.add_argument("--roistat-base-url", default="", help="Roistat base URL")
    parser.add_argument("--roistat-marker-level-1", default="", help="Roistat source marker level 1")
    parser.add_argument("--roistat-marker-level-2-search", default="", help="Roistat search marker level 2")
    args = parser.parse_args()

    # Применяем параметры из CLI к глобальным переменным
    global METRICA_COUNTER, GOAL_ID, ROISTAT_API, ROISTAT_KEY, ROISTAT_PROJECT
    global ROISTAT_MARKER_LEVEL_1, ROISTAT_MARKER_LEVEL_2_SEARCH
    if args.metrica_counter:
        METRICA_COUNTER = args.metrica_counter
    if args.goal_id:
        GOAL_ID = args.goal_id
    if args.roistat_key:
        ROISTAT_KEY = args.roistat_key
    if args.roistat_project:
        ROISTAT_PROJECT = args.roistat_project
    if args.roistat_base_url:
        ROISTAT_API = args.roistat_base_url.rstrip("/")
    if args.roistat_marker_level_1:
        ROISTAT_MARKER_LEVEL_1 = args.roistat_marker_level_1
    if args.roistat_marker_level_2_search:
        ROISTAT_MARKER_LEVEL_2_SEARCH = args.roistat_marker_level_2_search

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"Collecting data for campaign {args.campaign_id}")
    print(f"Output: {args.output_dir}")
    print(f"Goal: {GOAL_ID or 'not set'}")
    print(f"Metrica counter: {METRICA_COUNTER or 'not set'}")
    print("=" * 60)

    collect_management(args.token, args.login, args.campaign_id, args.output_dir)
    collect_reports(args.token, args.login, args.campaign_id, args.output_dir)
    metrica_enabled = False if args.skip_metrica else collect_metrica(args.token, args.output_dir, args.campaign_id)

    if args.skip_roistat:
        print("\n=== ROISTAT API (Block D) === SKIPPED (--skip-roistat)")
        print("\n=== MONTHLY DYNAMICS (Block E) === SKIPPED (--skip-roistat)")
    elif not ROISTAT_KEY or not ROISTAT_PROJECT:
        print("\n=== ROISTAT API (Block D) === SKIPPED (no --roistat-key / --roistat-project)")
        print("\n=== MONTHLY DYNAMICS (Block E) === SKIPPED (no --roistat-key / --roistat-project)")
    else:
        collect_roistat(args.campaign_id, args.output_dir)
        collect_monthly(args.campaign_id, args.output_dir)

    valid = validate_data(args.output_dir, include_metrica=bool(metrica_enabled))

    print("\n" + "=" * 60)
    if valid:
        print("ALL DATA COLLECTED SUCCESSFULLY")
    else:
        print("COLLECTION COMPLETED WITH ERRORS — check validation.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
