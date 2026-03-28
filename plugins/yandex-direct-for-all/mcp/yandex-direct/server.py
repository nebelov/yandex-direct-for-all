#!/usr/bin/env python3
"""Yandex Direct MCP Server — управление рекламными кампаниями через API v5/v501.

Поддерживает ЕПК (Единая перфоманс-кампания), все CRUD операции с кампаниями,
группами, объявлениями, ключевыми словами, расширениями, автотаргетингом.

Транспорт: SSE (http://localhost:8765/sse) или stdio.
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from enum import Enum

import httpx
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# --- Logging (stderr, не stdout!) ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("yandex_direct_mcp")

# --- Constants ---
CHARACTER_LIMIT = 25000
API_BASE = "https://api.direct.yandex.com"
API_SANDBOX = "https://api-sandbox.direct.yandex.com"
DEFAULT_TOKEN = os.environ.get("YD_TOKEN", "")
DEFAULT_LOGIN = os.environ.get("YD_CLIENT_LOGIN", "")
USE_SANDBOX = os.environ.get("YD_SANDBOX", "").lower() == "true"
PORT = int(os.environ.get("YD_MCP_PORT", "8765"))
OUTPUT_DIR = os.environ.get("YD_OUTPUT_DIR", os.path.join(os.getcwd(), "artifacts", "yandex-direct"))

mcp = FastMCP("yandex_direct_mcp", host="127.0.0.1", port=PORT)


# ============================================================
# Shared utilities
# ============================================================
def _base_url() -> str:
    return API_SANDBOX if USE_SANDBOX else API_BASE


def _headers(token: str = "", login: str = "") -> dict:
    t = token or DEFAULT_TOKEN
    if not t:
        raise ValueError("OAuth-токен не задан. Укажите token или установите YD_TOKEN.")
    h = {"Authorization": f"Bearer {t}", "Accept-Language": "ru", "Content-Type": "application/json"}
    lo = login or DEFAULT_LOGIN
    if lo:
        h["Client-Login"] = lo
    return h


async def _api_call(service: str, method: str, params: dict,
                    version: str = "v5", token: str = "", login: str = "") -> dict:
    """Асинхронный вызов API Яндекс.Директ."""
    url = f"{_base_url()}/json/{version}/{service}"
    body = {"method": method, "params": params}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=_headers(token, login), json=body, timeout=30.0)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        return {"error": {"error_code": e.response.status_code,
                          "error_string": f"HTTP {e.response.status_code}",
                          "error_detail": str(e)}}
    except httpx.TimeoutException:
        return {"error": {"error_code": 0, "error_string": "Timeout",
                          "error_detail": "Запрос превысил таймаут 30 сек. Попробуйте снова."}}
    except ValueError as e:
        return {"error": {"error_code": 0, "error_string": "Auth Error", "error_detail": str(e)}}
    except Exception as e:
        return {"error": {"error_code": 0, "error_string": type(e).__name__, "error_detail": str(e)}}


def _fmt(data: Any) -> str:
    """Форматировать компактный ответ (саммари, ошибки). НЕ для больших данных!"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _to_file(data: Any, filename: str, summary: dict = None) -> str:
    """Сохранить данные в файл, вернуть МИНИМАЛЬНЫЙ саммари.

    ЖЕЛЕЗНОЕ ПРАВИЛО: в контекст попадает ТОЛЬКО путь + count.
    Никаких sample, никаких данных — только ссылка на файл.
    """
    path = os.path.join(OUTPUT_DIR, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if isinstance(data, list):
        count = len(data)
    elif isinstance(data, dict):
        # Для API-ответов считаем элементы в result
        res = data.get("result", data)
        first_list = None
        for v in res.values():
            if isinstance(v, list):
                first_list = v
                break
        count = len(first_list) if first_list else 1
    else:
        count = 1

    result = {"file": path, "count": count}
    if summary:
        result.update(summary)
    return json.dumps(result, ensure_ascii=False)


def _write_result(r: dict, *result_keys: str) -> str:
    """Компактный результат write-операции. В контекст — только ok/errors/total."""
    if "error" in r:
        return _fmt(r)
    res = r.get("result", {})
    items = []
    for key in result_keys:
        if key in res:
            items = res[key]
            break
    if not items:
        for k, v in res.items():
            if k.endswith("Results") and isinstance(v, list):
                items = v
                break
    ok = sum(1 for x in items if not x.get("Errors"))
    errs = [x for x in items if x.get("Errors")]
    out = {"ok": ok, "errors": len(errs), "total": len(items)}
    if errs:
        out["error_details"] = [{"Id": e.get("Id"), "Errors": e["Errors"]} for e in errs[:3]]
    return _fmt(out)


def _parse_ids(s: str) -> List[int]:
    """Парсить строку ID через запятую."""
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def _from_file(data_or_path: str) -> Any:
    """Прочитать данные из файла (@path.json) или распарсить inline JSON.

    Формат: @/path/to/file.json → читает файл
    Иначе: json.loads(data_or_path)
    """
    s = data_or_path.strip()
    if s.startswith("@"):
        fpath = s[1:].strip()
        if not os.path.isfile(fpath):
            raise ValueError(f"Файл не найден: {fpath}")
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(s)


# ============================================================
# TOOL: Raw API call
# ============================================================
@mcp.tool(
    name="yd_api",
    annotations={
        "title": "Яндекс.Директ: произвольный API-вызов",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": False, "openWorldHint": True
    }
)
async def yd_api(service: str, method: str, params: str,
                 version: str = "v5", token: str = "", login: str = "") -> str:
    """Произвольный вызов API Яндекс.Директ v5/v501.

    Используй для операций, не покрытых специализированными инструментами.
    version=v501 для кампаний/групп ЕПК, v5 для остального.
    ДАННЫЕ → ФАЙЛ _api_raw.json, в контекст — саммари.

    Args:
        service: Сервис (campaigns, adgroups, ads, keywords, sitelinks, adextensions, keywordbids, negativekeywordsharedsets)
        method: Метод (get, add, update, delete, archive, resume, suspend, moderate)
        params: JSON-строка или @путь/к/файлу.json с параметрами
        version: v5 или v501 (ЕПК)
        token: OAuth-токен (пусто = env YD_TOKEN)
        login: Client-Login для агентских аккаунтов
    """
    try:
        p = _from_file(params)
    except (json.JSONDecodeError, ValueError) as e:
        return _fmt({"error": f"Ошибка данных: {e}. Проверьте формат params."})
    r = await _api_call(service, method, p, version, token, login)
    if "error" in r:
        return _fmt(r)
    return _to_file(r, f"_api_{service}_{method}.json", {"service": service, "method": method})


# ============================================================
# TOOL: Get campaigns
# ============================================================
@mcp.tool(
    name="yd_campaigns",
    annotations={
        "title": "Яндекс.Директ: список кампаний",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_campaigns(campaign_ids: str = "", token: str = "", login: str = "") -> str:
    """Получить кампании аккаунта с настройками (стратегия, бюджет, TrackingParams, цели).

    Args:
        campaign_ids: ID через запятую (пусто = все кампании)
        token: OAuth-токен
        login: Client-Login
    """
    sel = {}
    if campaign_ids:
        sel["Ids"] = _parse_ids(campaign_ids)
    params = {
        "SelectionCriteria": sel,
        "FieldNames": ["Id", "Name", "Status", "State", "DailyBudget", "StartDate", "NegativeKeywords"],
        "UnifiedCampaignFieldNames": ["BiddingStrategy", "TrackingParams", "PriorityGoals",
                                       "CounterIds", "Settings", "NegativeKeywordSharedSetIds"]
    }
    r = await _api_call("campaigns", "get", params, "v501", token, login)
    if "result" in r:
        out = []
        for c in r["result"].get("Campaigns", []):
            uc = c.get("UnifiedCampaign") or {}
            strat = uc.get("BiddingStrategy", {}).get("Search", {})
            pt = strat.get("PlacementTypes", {})
            budget = c.get("DailyBudget") or {}
            neg_kw = c.get("NegativeKeywords") or {}
            shared_neg = uc.get("NegativeKeywordSharedSetIds", [])
            out.append({
                "Id": c["Id"], "Name": c["Name"],
                "Status": c.get("Status"), "State": c.get("State"),
                "Budget": budget.get("Amount", 0) // 1000000 if budget.get("Amount") else 0,
                "Strategy": strat.get("BiddingStrategyType", ""),
                "Maps": pt.get("Maps", "?"), "SearchOrg": pt.get("SearchOrganizationList", "?"),
                "TrackingParams": (uc.get("TrackingParams") or "")[:60],
                "Goals": len(uc.get("PriorityGoals", {}).get("Items", [])),
                "SharedNegSets": shared_neg,
                "NegKw": len(neg_kw.get("Items", []) if isinstance(neg_kw, dict) else []),
            })
        return _to_file(out, "_campaigns.json")
    return _fmt(r)


# ============================================================
# TOOL: Get groups
# ============================================================
@mcp.tool(
    name="yd_groups",
    annotations={
        "title": "Яндекс.Директ: группы объявлений",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_groups(campaign_id: int, token: str = "", login: str = "") -> str:
    """Получить группы объявлений кампании с TrackingParams и минус-словами.

    Args:
        campaign_id: ID кампании
        token: OAuth-токен
        login: Client-Login
    """
    params = {
        "SelectionCriteria": {"CampaignIds": [campaign_id]},
        "FieldNames": ["Id", "Name", "Status", "RegionIds", "TrackingParams", "NegativeKeywords"],
        "UnifiedAdGroupFieldNames": ["OfferRetargeting", "Scenario"]
    }
    r = await _api_call("adgroups", "get", params, "v501", token, login)
    if "result" in r:
        out = []
        for g in r["result"].get("AdGroups", []):
            neg = g.get("NegativeKeywords") or {}
            out.append({
                "Id": g["Id"], "Name": g["Name"], "Status": g.get("Status"),
                "RegionIds": g.get("RegionIds", []),
                "TrackingParams": (g.get("TrackingParams") or "")[:80],
                "NegKw": len(neg.get("Items", []) if isinstance(neg, dict) else []),
                "OfferRetarget": (g.get("UnifiedAdGroup") or {}).get("OfferRetargeting", ""),
            })
        return _to_file(out, f"_groups_{campaign_id}.json")
    return _fmt(r)


# ============================================================
# TOOL: Create group
# ============================================================
@mcp.tool(
    name="yd_group_create",
    annotations={
        "title": "Яндекс.Директ: создать группу",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": False, "openWorldHint": True
    }
)
async def yd_group_create(campaign_id: int, name: str,
                          region_ids: str = "225", tracking_params: str = "",
                          offer_retargeting: str = "NO",
                          token: str = "", login: str = "") -> str:
    """Создать группу объявлений в ЕПК кампании.

    Args:
        campaign_id: ID кампании
        name: Название группы
        region_ids: Регионы через запятую (225=Россия, 1=Москва, 2=СПб)
        tracking_params: UTM + roistat строка
        offer_retargeting: YES/NO
        token: OAuth-токен
        login: Client-Login
    """
    group = {
        "Name": name, "CampaignId": campaign_id,
        "RegionIds": _parse_ids(region_ids),
        "UnifiedAdGroup": {"OfferRetargeting": offer_retargeting}
    }
    if tracking_params:
        group["TrackingParams"] = tracking_params
    r = await _api_call("adgroups", "add", {"AdGroups": [group]}, "v501", token, login)
    return _write_result(r, "AddResults")


# ============================================================
# TOOL: Get ads
# ============================================================
@mcp.tool(
    name="yd_ads",
    annotations={
        "title": "Яндекс.Директ: список объявлений",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_ads(campaign_id: int = 0, group_ids: str = "",
                 token: str = "", login: str = "") -> str:
    """Получить объявления с данными о расширениях (sitelinks, callouts, display URL).

    Args:
        campaign_id: ID кампании (0 = не фильтровать)
        group_ids: ID групп через запятую
        token: OAuth-токен
        login: Client-Login
    """
    sel = {}
    if campaign_id:
        sel["CampaignIds"] = [campaign_id]
    if group_ids:
        sel["AdGroupIds"] = _parse_ids(group_ids)
    cid = campaign_id or 0
    r = await _api_call("ads", "get", {
        "SelectionCriteria": sel,
        "FieldNames": ["Id", "AdGroupId", "Status", "State"],
        "TextAdFieldNames": ["Title", "Title2", "Text", "Href", "DisplayUrlPath",
                              "SitelinkSetId", "AdExtensions", "Mobile"]
    }, "v5", token, login)
    if "result" in r:
        out = []
        for a in r["result"].get("Ads", []):
            ta = a.get("TextAd", {})
            out.append({
                "Id": a["Id"], "GroupId": a["AdGroupId"],
                "Status": a.get("Status"), "Title": ta.get("Title", ""),
                "Title2": ta.get("Title2", ""),
                "Sitelinks": "Y" if ta.get("SitelinkSetId") else "N",
                "Callouts": len(ta.get("AdExtensions", [])),
                "DisplayUrl": ta.get("DisplayUrlPath", ""),
            })
        return _to_file(out, f"_ads_{cid}.json")
    return _fmt(r)


# ============================================================
# TOOL: Create ad (WITH EXTENSIONS ENFORCED!)
# ============================================================
@mcp.tool(
    name="yd_ad_create",
    annotations={
        "title": "Яндекс.Директ: создать объявление с расширениями",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": False, "openWorldHint": True
    }
)
async def yd_ad_create(
    group_id: int, title: str, title2: str, text: str, href: str,
    display_url_path: str, sitelink_set_id: int, callout_ids: str,
    mobile: str = "NO", token: str = "", login: str = ""
) -> str:
    """Создать текстовое объявление. display_url_path, sitelink_set_id, callout_ids — ОБЯЗАТЕЛЬНЫ!

    При Ads.add: AdExtensionIds прикрепляет callouts.
    При Ads.update: используйте yd_ad_update_callouts (CalloutSetting).

    Args:
        group_id: ID группы
        title: Заголовок 1 (до 56 символов)
        title2: Заголовок 2 (до 30 символов)
        text: Текст (до 81 символа)
        href: URL страницы
        display_url_path: Отображаемая ссылка (до 20 символов) — ОБЯЗАТЕЛЬНО
        sitelink_set_id: ID набора быстрых ссылок — ОБЯЗАТЕЛЬНО
        callout_ids: ID уточнений через запятую — ОБЯЗАТЕЛЬНО
        mobile: YES/NO
        token: OAuth-токен
        login: Client-Login
    """
    ad = {
        "AdGroupId": group_id,
        "TextAd": {
            "Title": title, "Title2": title2, "Text": text,
            "Href": href, "Mobile": mobile,
            "DisplayUrlPath": display_url_path,
            "SitelinkSetId": sitelink_set_id,
            "AdExtensionIds": _parse_ids(callout_ids),
        }
    }
    r = await _api_call("ads", "add", {"Ads": [ad]}, "v5", token, login)
    return _write_result(r, "AddResults")


# ============================================================
# TOOL: Batch create ads
# ============================================================
@mcp.tool(
    name="yd_ads_batch",
    annotations={
        "title": "Яндекс.Директ: массовое создание объявлений",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": False, "openWorldHint": True
    }
)
async def yd_ads_batch(
    ads_json: str, sitelink_set_id: int, callout_ids: str,
    display_url_path: str, token: str = "", login: str = ""
) -> str:
    """Массовое создание объявлений — расширения применяются ко ВСЕМ автоматически.

    Args:
        ads_json: JSON-массив или @путь/к/файлу.json: [{"group_id":1,"title":"...","title2":"...","text":"...","href":"..."}]
        sitelink_set_id: ID набора быстрых ссылок (для ВСЕХ)
        callout_ids: ID уточнений через запятую (для ВСЕХ)
        display_url_path: Отображаемая ссылка (для ВСЕХ)
        token: OAuth-токен
        login: Client-Login
    """
    try:
        data = _from_file(ads_json)
    except (json.JSONDecodeError, ValueError) as e:
        return _fmt({"error": f"Ошибка данных: {e}"})

    ext_ids = _parse_ids(callout_ids) if callout_ids else []
    ads = []
    for ad in data:
        item = {
            "AdGroupId": ad["group_id"],
            "TextAd": {
                "Title": ad["title"], "Title2": ad["title2"],
                "Text": ad["text"], "Href": ad["href"],
                "Mobile": ad.get("mobile", "NO"),
                "DisplayUrlPath": display_url_path,
                "SitelinkSetId": sitelink_set_id,
            }
        }
        if ext_ids:
            item["TextAd"]["AdExtensionIds"] = ext_ids
        ads.append(item)

    results = []
    for i in range(0, len(ads), 50):
        r = await _api_call("ads", "add", {"Ads": ads[i:i+50]}, "v5", token, login)
        if "result" in r:
            results.extend(r["result"].get("AddResults", []))
        elif "error" in r:
            results.append(r)

    ok = sum(1 for x in results if isinstance(x, dict) and "Id" in x)
    ids = [x["Id"] for x in results if isinstance(x, dict) and "Id" in x]
    err = sum(1 for x in results if isinstance(x, dict) and "Errors" in x)
    return _fmt({"created": ok, "errors": err, "ids": ids})


# ============================================================
# TOOL: Update callouts on existing ads
# ============================================================
@mcp.tool(
    name="yd_ad_update_callouts",
    annotations={
        "title": "Яндекс.Директ: обновить callouts объявлений",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_ad_update_callouts(
    ad_ids: str, callout_ids: str, operation: str = "SET",
    token: str = "", login: str = ""
) -> str:
    """Обновить уточнения (callouts) на СУЩЕСТВУЮЩИХ объявлениях через CalloutSetting.

    ВАЖНО: AdExtensionIds НЕ работает в Ads.update! Используй этот инструмент.

    Args:
        ad_ids: ID объявлений через запятую
        callout_ids: ID уточнений через запятую
        operation: ADD (добавить к существующим) / REMOVE (удалить) / SET (заменить все — несовместим с ADD/REMOVE)
        token: OAuth-токен
        login: Client-Login
    """
    aids = _parse_ids(ad_ids)
    eids = _parse_ids(callout_ids)
    ads = [{
        "Id": aid,
        "TextAd": {"CalloutSetting": {"AdExtensions": [
            {"AdExtensionId": eid, "Operation": operation} for eid in eids
        ]}}
    } for aid in aids]

    results = []
    for i in range(0, len(ads), 10):
        r = await _api_call("ads", "update", {"Ads": ads[i:i+10]}, "v5", token, login)
        if "result" in r:
            results.extend(r["result"].get("UpdateResults", []))
        elif "error" in r:
            results.append(r)

    ok = sum(1 for x in results if isinstance(x, dict) and "Id" in x)
    err = sum(1 for x in results if isinstance(x, dict) and "Errors" in x)
    return _fmt({"updated": ok, "errors": err})


# ============================================================
# TOOL: Get keywords
# ============================================================
@mcp.tool(
    name="yd_keywords",
    annotations={
        "title": "Яндекс.Директ: ключевые слова",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_keywords(campaign_id: int = 0, group_ids: str = "",
                      token: str = "", login: str = "") -> str:
    """Получить ключевые слова кампании/групп со ставками.

    Args:
        campaign_id: ID кампании (0 = не фильтровать)
        group_ids: ID групп через запятую
        token: OAuth-токен
        login: Client-Login
    """
    sel = {}
    if campaign_id:
        sel["CampaignIds"] = [campaign_id]
    if group_ids:
        sel["AdGroupIds"] = _parse_ids(group_ids)
    cid = campaign_id or 0
    r = await _api_call("keywords", "get", {
        "SelectionCriteria": sel,
        "FieldNames": ["Id", "Keyword", "AdGroupId", "Status", "State", "Bid"]
    }, "v5", token, login)
    if "result" in r:
        kws = r["result"].get("Keywords", [])
        out = [{"Id": k["Id"], "Kw": k["Keyword"], "Gid": k["AdGroupId"],
                "St": k.get("Status"), "Bid": k.get("Bid", 0)} for k in kws]
        return _to_file(out, f"_keywords_{cid}.json")
    return _fmt(r)


# ============================================================
# TOOL: Add keywords
# ============================================================
@mcp.tool(
    name="yd_keywords_add",
    annotations={
        "title": "Яндекс.Директ: добавить ключевые слова",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": False, "openWorldHint": True
    }
)
async def yd_keywords_add(keywords_json: str, token: str = "", login: str = "") -> str:
    """Добавить ключевые слова в группы. Максимум 1000 за запрос.

    Args:
        keywords_json: JSON или @путь/к/файлу.json: [{"group_id":123,"keywords":["фраза 1","фраза 2"]}]
        token: OAuth-токен
        login: Client-Login
    """
    try:
        data = _from_file(keywords_json)
    except (json.JSONDecodeError, ValueError) as e:
        return _fmt({"error": f"Ошибка данных: {e}"})

    items = []
    for d in data:
        if "keywords" in d:
            for kw in d["keywords"]:
                items.append({"AdGroupId": d["group_id"], "Keyword": kw})
        else:
            items.append({"AdGroupId": d["group_id"], "Keyword": d["keyword"]})

    results = []
    for i in range(0, len(items), 1000):
        r = await _api_call("keywords", "add", {"Keywords": items[i:i+1000]}, "v5", token, login)
        if "result" in r:
            results.extend(r["result"].get("AddResults", []))
        elif "error" in r:
            results.append(r)

    ok = sum(1 for x in results if isinstance(x, dict) and "Id" in x)
    err = sum(1 for x in results if isinstance(x, dict) and "Errors" in x)
    return _fmt({"added": ok, "errors": err, "total": len(items)})


# ============================================================
# TOOL: Set bids
# ============================================================
@mcp.tool(
    name="yd_set_bids",
    annotations={
        "title": "Яндекс.Директ: установить ставки",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_set_bids(bids_json: str, token: str = "", login: str = "") -> str:
    """Установить ставки на ключевые слова.

    Args:
        bids_json: JSON или @путь/к/файлу.json: [{"keyword_id":123,"search_bid":1000000}] (bid в микроединицах)
        token: OAuth-токен
        login: Client-Login
    """
    try:
        data = _from_file(bids_json)
    except (json.JSONDecodeError, ValueError) as e:
        return _fmt({"error": f"Ошибка данных: {e}"})

    bids = [{"KeywordId": b["keyword_id"], "SearchBid": b["search_bid"]} for b in data]
    r = await _api_call("keywordbids", "set", {"KeywordBids": bids}, "v5", token, login)
    return _write_result(r, "SetResults")


# ============================================================
# TOOL: Extensions (callouts + sitelinks)
# ============================================================
@mcp.tool(
    name="yd_extensions",
    annotations={
        "title": "Яндекс.Директ: расширения (callouts)",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_extensions(token: str = "", login: str = "") -> str:
    """Получить все callout-расширения аккаунта (ID, текст, статус).

    Args:
        token: OAuth-токен
        login: Client-Login
    """
    r = await _api_call("adextensions", "get", {
        "SelectionCriteria": {"Types": ["CALLOUT"], "Statuses": ["ACCEPTED", "MODERATION", "DRAFT"]},
        "FieldNames": ["Id", "Type", "Status"],
        "CalloutFieldNames": ["CalloutText"]
    }, "v5", token, login)
    if "result" in r:
        out = [{"Id": e["Id"], "Status": e.get("Status"),
                "Text": e.get("Callout", {}).get("CalloutText", "")}
               for e in r["result"].get("AdExtensions", [])]
        return _to_file(out, "_extensions.json")
    return _fmt(r)


@mcp.tool(
    name="yd_sitelinks",
    annotations={
        "title": "Яндекс.Директ: быстрые ссылки",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_sitelinks(token: str = "", login: str = "") -> str:
    """Получить наборы быстрых ссылок (sitelink sets) аккаунта.

    Args:
        token: OAuth-токен
        login: Client-Login
    """
    r = await _api_call("sitelinks", "get", {
        "SelectionCriteria": {},
        "FieldNames": ["Id"],
        "SitelinkFieldNames": ["Title", "Href"]
    }, "v5", token, login)
    if "result" in r:
        out = []
        for s in r["result"].get("SitelinksSets", []):
            links = [{"t": sl.get("Title", ""), "h": sl.get("Href", "")[:60]}
                     for sl in s.get("Sitelinks", [])]
            out.append({"Id": s["Id"], "Links": links})
        return _to_file(out, "_sitelinks.json")
    return _fmt(r)


# ============================================================
# TOOL: Autotargeting
# ============================================================
@mcp.tool(
    name="yd_autotargeting",
    annotations={
        "title": "Яндекс.Директ: настроить автотаргетинг",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_autotargeting(
    group_ids: str, exact: str = "YES", narrow: str = "NO",
    alternative: str = "NO", accessory: str = "NO", broader: str = "NO",
    search_bid: int = 300000, token: str = "", login: str = ""
) -> str:
    """Настроить автотаргетинг: категории + ставка. Находит ---autotargeting в группах.

    На поиске ЕПК автотаргетинг нельзя выключить полностью (с января 2024).
    Рекомендация: Exact=YES, остальное NO, ставка 0.30 руб (300000).

    Args:
        group_ids: ID групп через запятую
        exact: Целевые YES/NO
        narrow: Узкие YES/NO
        alternative: Альтернативные YES/NO
        accessory: Сопутствующие YES/NO
        broader: Широкие YES/NO
        search_bid: Ставка в микроединицах (300000 = 0.30 руб)
        token: OAuth-токен
        login: Client-Login
    """
    gids = _parse_ids(group_ids)
    r = await _api_call("keywords", "get", {
        "SelectionCriteria": {"AdGroupIds": gids},
        "FieldNames": ["Id", "Keyword", "AdGroupId"]
    }, "v5", token, login)
    if "error" in r:
        return _fmt(r)

    auto = [k for k in r.get("result", {}).get("Keywords", []) if k["Keyword"] == "---autotargeting"]
    if not auto:
        return _fmt({"error": "Автотаргетинг не найден. Проверьте ID групп."})

    cats = {"Exact": exact, "Narrow": narrow, "Alternative": alternative,
            "Accessory": accessory, "Broader": broader}
    r1 = await _api_call("keywords", "update", {
        "Keywords": [{"Id": k["Id"], "AutotargetingSettings": {"Categories": cats}} for k in auto]
    }, "v5", token, login)
    r2 = await _api_call("keywordbids", "set", {
        "KeywordBids": [{"KeywordId": k["Id"], "SearchBid": search_bid} for k in auto]
    }, "v5", token, login)

    return _fmt({"configured": len(auto), "categories": cats, "bid": search_bid})


# ============================================================
# TOOL: TrackingParams
# ============================================================
@mcp.tool(
    name="yd_tracking",
    annotations={
        "title": "Яндекс.Директ: установить TrackingParams",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_tracking(
    entity_type: str, entity_ids: str, tracking_params: str,
    token: str = "", login: str = ""
) -> str:
    """Установить TrackingParams (UTM/roistat). ВАЖНО: группа ПЕРЕКРЫВАЕТ кампанию!

    Ставь на ОБА уровня при создании кампании.

    Args:
        entity_type: campaign / group
        entity_ids: ID через запятую
        tracking_params: UTM строка (utm_source=...&roistat=...)
        token: OAuth-токен
        login: Client-Login
    """
    ids = _parse_ids(entity_ids)
    if entity_type == "campaign":
        items = [{"Id": i, "UnifiedCampaign": {"TrackingParams": tracking_params}} for i in ids]
        r = await _api_call("campaigns", "update", {"Campaigns": items}, "v501", token, login)
    elif entity_type == "group":
        items = [{"Id": i, "TrackingParams": tracking_params} for i in ids]
        r = await _api_call("adgroups", "update", {"AdGroups": items}, "v501", token, login)
    else:
        return _fmt({"error": "entity_type: 'campaign' или 'group'"})
    return _write_result(r, "UpdateResults")


# ============================================================
# TOOL: Negatives
# ============================================================
@mcp.tool(
    name="yd_negatives",
    annotations={
        "title": "Яндекс.Директ: минус-слова",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_negatives(level: str = "account", entity_id: int = 0,
                       token: str = "", login: str = "") -> str:
    """Получить минус-слова. Три уровня: account, campaign, group.

    Args:
        level: account / campaign / group
        entity_id: ID кампании или группы (для account не нужен)
        token: OAuth-токен
        login: Client-Login
    """
    if level == "account":
        r = await _api_call("negativekeywordsharedsets", "get", {
            "SelectionCriteria": {}, "FieldNames": ["Id", "Name", "NegativeKeywords"]
        }, "v5", token, login)
        if "result" in r:
            out = [{"Id": s["Id"], "Name": s["Name"],
                    "Count": len(s.get("NegativeKeywords", [])),
                    "Keywords": s.get("NegativeKeywords", [])}
                   for s in r["result"].get("NegativeKeywordSharedSets", [])]
            return _to_file(out, "_negatives_account.json",
                            {"sets": len(out), "total_words": sum(o["Count"] for o in out)})
    elif level == "campaign":
        r = await _api_call("campaigns", "get", {
            "SelectionCriteria": {"Ids": [entity_id]}, "FieldNames": ["Id", "NegativeKeywords"]
        }, "v501", token, login)
        if "result" in r:
            nk = r["result"].get("Campaigns", [{}])[0].get("NegativeKeywords") or {}
            negs = nk.get("Items", [])
            return _to_file(negs, f"_negatives_campaign_{entity_id}.json",
                            {"campaign": entity_id, "count": len(negs)})
    elif level == "group":
        r = await _api_call("adgroups", "get", {
            "SelectionCriteria": {"Ids": [entity_id]}, "FieldNames": ["Id", "NegativeKeywords"]
        }, "v501", token, login)
        if "result" in r:
            nk = r["result"].get("AdGroups", [{}])[0].get("NegativeKeywords") or {}
            negs = nk.get("Items", [])
            return _to_file(negs, f"_negatives_group_{entity_id}.json",
                            {"group": entity_id, "count": len(negs)})
    return _fmt({"error": f"Неизвестный level: {level}. Используйте: account, campaign, group"})


# ============================================================
# TOOL: PlacementTypes (Maps, SearchOrganizationList etc.)
# ============================================================
@mcp.tool(
    name="yd_placement_types",
    annotations={
        "title": "Яндекс.Директ: управление площадками (Карты, Поиск организаций)",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_placement_types(
    campaign_ids: str, action: str = "get",
    maps: str = "", search_org: str = "",
    search_results: str = "", product_gallery: str = "", dynamic_places: str = "",
    token: str = "", login: str = ""
) -> str:
    """Управление PlacementTypes (площадки показа) в стратегии кампании.

    ВАЖНО: PlacementTypes — это ОБЪЕКТ внутри BiddingStrategy.Search, НЕ массив!
    Формат: {"SearchResults":"YES","ProductGallery":"YES","Maps":"NO",...}

    По умолчанию при создании кампании ВСЕ площадки = YES.
    Для регионального сплита рекомендуется отключить Maps и SearchOrganizationList.

    Args:
        campaign_ids: ID кампаний через запятую
        action: get (посмотреть) / set (установить)
        maps: YES/NO — Яндекс Карты
        search_org: YES/NO — Поиск по организациям
        search_results: YES/NO — Результаты поиска
        product_gallery: YES/NO — Товарная галерея
        dynamic_places: YES/NO — Динамические показы
        token: OAuth-токен
        login: Client-Login
    """
    ids = _parse_ids(campaign_ids)

    if action == "get":
        r = await _api_call("campaigns", "get", {
            "SelectionCriteria": {"Ids": ids},
            "FieldNames": ["Id", "Name"],
            "UnifiedCampaignFieldNames": ["BiddingStrategy"]
        }, "v501", token, login)
        if "result" in r:
            out = []
            for c in r["result"].get("Campaigns", []):
                search = c.get("UnifiedCampaign", {}).get("BiddingStrategy", {}).get("Search", {})
                pt = search.get("PlacementTypes", {})
                out.append({"Id": c["Id"], "Name": c["Name"], "PlacementTypes": pt})
            return _to_file(out, "_placement_types.json")
        return _fmt(r)

    # action == "set"
    # Сначала получаем текущую стратегию (нельзя потерять BiddingStrategyType!)
    r = await _api_call("campaigns", "get", {
        "SelectionCriteria": {"Ids": ids},
        "FieldNames": ["Id"],
        "UnifiedCampaignFieldNames": ["BiddingStrategy"]
    }, "v501", token, login)
    if "result" not in r:
        return _fmt(r)

    updates = []
    for c in r["result"].get("Campaigns", []):
        strat = c.get("UnifiedCampaign", {}).get("BiddingStrategy", {})
        search = strat.get("Search", {})
        pt = search.get("PlacementTypes", {})

        # Обновляем только переданные поля
        if maps: pt["Maps"] = maps
        if search_org: pt["SearchOrganizationList"] = search_org
        if search_results: pt["SearchResults"] = search_results
        if product_gallery: pt["ProductGallery"] = product_gallery
        if dynamic_places: pt["DynamicPlaces"] = dynamic_places

        search["PlacementTypes"] = pt
        strat["Search"] = search
        updates.append({"Id": c["Id"], "UnifiedCampaign": {"BiddingStrategy": strat}})

    r2 = await _api_call("campaigns", "update", {"Campaigns": updates}, "v501", token, login)
    return _write_result(r2, "UpdateResults")


# ============================================================
# TOOL: Campaign settings (ENABLE_AREA_OF_INTEREST etc.)
# ============================================================
@mcp.tool(
    name="yd_campaign_settings",
    annotations={
        "title": "Яндекс.Директ: настройки кампании",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_campaign_settings(
    campaign_ids: str, action: str = "get",
    settings_json: str = "",
    token: str = "", login: str = ""
) -> str:
    """Просмотр/обновление Settings кампании (ENABLE_AREA_OF_INTEREST_TARGETING и др.).

    ВАЖНО: SHARED_ACCOUNT_ENABLED — read-only, НЕ передавать в update!

    Args:
        campaign_ids: ID кампаний через запятую
        action: get / set
        settings_json: JSON массив для set: [{"Option":"ENABLE_AREA_OF_INTEREST_TARGETING","Value":"NO"}]
        token: OAuth-токен
        login: Client-Login
    """
    ids = _parse_ids(campaign_ids)

    if action == "get":
        r = await _api_call("campaigns", "get", {
            "SelectionCriteria": {"Ids": ids},
            "FieldNames": ["Id", "Name"],
            "UnifiedCampaignFieldNames": ["Settings"]
        }, "v501", token, login)
        if "result" in r:
            out = []
            for c in r["result"].get("Campaigns", []):
                settings = c.get("UnifiedCampaign", {}).get("Settings", [])
                out.append({"Id": c["Id"], "Name": c["Name"], "Settings": settings})
            return _to_file(out, "_campaign_settings.json")
        return _fmt(r)

    # action == "set"
    try:
        new_settings = json.loads(settings_json) if settings_json else []
    except json.JSONDecodeError as e:
        return _fmt({"error": f"Невалидный JSON settings: {e}"})

    # Фильтруем read-only настройки
    readonly = {"SHARED_ACCOUNT_ENABLED"}
    new_settings = [s for s in new_settings if s.get("Option") not in readonly]

    updates = [{"Id": cid, "UnifiedCampaign": {"Settings": new_settings}} for cid in ids]
    r = await _api_call("campaigns", "update", {"Campaigns": updates}, "v501", token, login)
    return _write_result(r, "UpdateResults")


# ============================================================
# TOOL: Moderate + Actions
# ============================================================
@mcp.tool(
    name="yd_moderate",
    annotations={
        "title": "Яндекс.Директ: отправить на модерацию",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_moderate(ad_ids: str, token: str = "", login: str = "") -> str:
    """Отправить объявления на модерацию.

    Args:
        ad_ids: ID объявлений через запятую
        token: OAuth-токен
        login: Client-Login
    """
    r = await _api_call("ads", "moderate", {"SelectionCriteria": {"Ids": _parse_ids(ad_ids)}},
                        "v5", token, login)
    return _write_result(r, "ModerateResults")


@mcp.tool(
    name="yd_campaign_action",
    annotations={
        "title": "Яндекс.Директ: действие с кампанией",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_campaign_action(campaign_ids: str, action: str,
                             token: str = "", login: str = "") -> str:
    """Действие с кампанией: resume (запустить), suspend (остановить), archive, unarchive.

    Args:
        campaign_ids: ID кампаний через запятую
        action: resume / suspend / archive / unarchive
        token: OAuth-токен
        login: Client-Login
    """
    r = await _api_call("campaigns", action, {"SelectionCriteria": {"Ids": _parse_ids(campaign_ids)}},
                        "v501", token, login)
    return _write_result(r, "SuspendResults", "ResumeResults", "ArchiveResults", "UnarchiveResults")


# ============================================================
# TOOL: Delete
# ============================================================
@mcp.tool(
    name="yd_delete",
    annotations={
        "title": "Яндекс.Директ: удалить сущности",
        "readOnlyHint": False, "destructiveHint": True,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_delete(entity_type: str, entity_ids: str,
                    token: str = "", login: str = "") -> str:
    """Удалить сущности (ads, keywords, adgroups).

    Args:
        entity_type: ads / keywords / adgroups
        entity_ids: ID через запятую
        token: OAuth-токен
        login: Client-Login
    """
    r = await _api_call(entity_type, "delete", {"SelectionCriteria": {"Ids": _parse_ids(entity_ids)}},
                        "v5", token, login)
    return _write_result(r, "DeleteResults")


# ============================================================
# TOOL: Auction data (Bids.get legacy + KeywordBids.get)
# ============================================================
LIVE4_URL = "https://api.direct.yandex.ru/live/v4/json"


async def _live4_call(method: str, param: Any, token: str = "", login: str = "") -> dict:
    """Вызов API Live 4 (deprecated, но работает для прогнозов)."""
    t = token or DEFAULT_TOKEN
    body = {"method": method, "param": param, "locale": "ru", "token": t}
    if login:
        body["login"] = login
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(LIVE4_URL, json=body, timeout=60.0)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(
    name="yd_auction_data",
    annotations={
        "title": "Яндекс.Директ: данные аукциона по ключевым словам",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_auction_data(
    campaign_id: int, output_file: str = "",
    token: str = "", login: str = ""
) -> str:
    """Получить данные аукциона для ВСЕХ ключей кампании: позиции, цены, конкуренты.

    Использует Bids.get (legacy) — возвращает SearchPrices (PREMIUMFIRST/BLOCK),
    AuctionBids (P11,P12...), CompetitorsBids, MinSearchPrice, CurrentSearchPrice.

    БОЛЬШИЕ ДАННЫЕ сохраняются В ФАЙЛ, в контекст — только саммари.

    Args:
        campaign_id: ID кампании
        output_file: Путь для сохранения (по умолчанию claude/docs/_auction_{campaign_id}.tsv)
        token: OAuth-токен
        login: Client-Login
    """
    # Сначала получаем ключи кампании (нужны KeywordId)
    kw_r = await _api_call("keywords", "get", {
        "SelectionCriteria": {"CampaignIds": [campaign_id]},
        "FieldNames": ["Id", "Keyword", "AdGroupId"]
    }, "v5", token, login)
    if "result" not in kw_r:
        return _fmt(kw_r)

    keywords = kw_r["result"].get("Keywords", [])
    kw_map = {k["Id"]: k["Keyword"] for k in keywords}
    kw_ids = [k["Id"] for k in keywords if k["Keyword"] != "---autotargeting"]

    if not kw_ids:
        return _fmt({"error": "Нет ключевых слов (кроме autotargeting)"})

    # Bids.get с полными данными аукциона
    all_bids = []
    for i in range(0, len(kw_ids), 10000):
        batch = kw_ids[i:i+10000]
        r = await _api_call("bids", "get", {
            "SelectionCriteria": {"KeywordIds": batch},
            "FieldNames": ["KeywordId", "Bid", "CompetitorsBids", "SearchPrices",
                           "MinSearchPrice", "CurrentSearchPrice", "AuctionBids"]
        }, "v5", token, login)
        if "result" in r:
            all_bids.extend(r["result"].get("Bids", []))

    # Формируем TSV
    lines = ["KeywordId\tKeyword\tBid_rub\tMinSearch_rub\tCurrentCPC_rub\tP11_bid\tP11_price\tP12_bid\tP12_price\tP13_bid\tP13_price\tPREMIUM1st\tPREMIUMblock"]
    stats = {"total": 0, "has_auction": 0, "below_min": 0, "avg_p12": 0, "sum_p12": 0}

    for b in all_bids:
        kid = b.get("KeywordId", 0)
        kw = kw_map.get(kid, "?")
        bid = b.get("Bid", 0) / 1000000
        min_s = b.get("MinSearchPrice", 0) / 1000000
        cur = b.get("CurrentSearchPrice", 0) / 1000000

        # AuctionBids по позициям
        ab = {a["Position"]: a for a in (b.get("AuctionBids") or [])}
        p11 = ab.get("P11", {})
        p12 = ab.get("P12", {})
        p13 = ab.get("P13", {})

        # SearchPrices
        sp = {s["Position"]: s["Price"] / 1000000 for s in (b.get("SearchPrices") or [])}

        p12_bid = p12.get("Bid", 0) / 1000000 if p12 else 0

        lines.append(f"{kid}\t{kw}\t{bid:.2f}\t{min_s:.2f}\t{cur:.2f}\t"
                     f"{p11.get('Bid', 0)/1000000:.2f}\t{p11.get('Price', 0)/1000000:.2f}\t"
                     f"{p12.get('Bid', 0)/1000000:.2f}\t{p12.get('Price', 0)/1000000:.2f}\t"
                     f"{p13.get('Bid', 0)/1000000:.2f}\t{p13.get('Price', 0)/1000000:.2f}\t"
                     f"{sp.get('PREMIUMFIRST', 0):.2f}\t{sp.get('PREMIUMBLOCK', 0):.2f}")

        stats["total"] += 1
        if p12: stats["has_auction"] += 1; stats["sum_p12"] += p12_bid
        if bid < min_s: stats["below_min"] += 1

    if stats["has_auction"]:
        stats["avg_p12"] = round(stats["sum_p12"] / stats["has_auction"], 2)

    # Сохраняем
    path = output_file or os.path.join(OUTPUT_DIR, f"_auction_{campaign_id}.tsv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return _fmt({
        "file": path,
        "keywords": stats["total"],
        "has_auction_data": stats["has_auction"],
        "below_min_search": stats["below_min"],
        "avg_P12_bid_rub": stats["avg_p12"],
        "hint": "P11=1-е спец, P12=2-е спец, P13=3-е спец."
    })


# ============================================================
# TOOL: Keyword analytics (combined auction + bids + recommendations)
# ============================================================
@mcp.tool(
    name="yd_keyword_analytics",
    annotations={
        "title": "Яндекс.Директ: аналитика ключей — ставки vs аукцион",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_keyword_analytics(
    campaign_id: int, target_position: str = "P12",
    output_file: str = "", token: str = "", login: str = ""
) -> str:
    """Аналитика по каждому ключу: текущая ставка vs нужная для целевой позиции.

    Показывает GAP (разницу) между текущей ставкой и нужной.
    Рекомендации: RAISE (поднять), OK (в норме), LOWER (можно снизить), NO_DATA.

    ДАННЫЕ В ФАЙЛ. В контекст — только саммари с рекомендациями.

    Args:
        campaign_id: ID кампании
        target_position: Целевая позиция: P11 (1-я), P12 (2-я), P13 (3-я), P14 (4-я)
        output_file: Путь файла (по умолчанию _analytics_{campaign_id}.tsv)
        token: OAuth-токен
        login: Client-Login
    """
    # Ключи
    kw_r = await _api_call("keywords", "get", {
        "SelectionCriteria": {"CampaignIds": [campaign_id]},
        "FieldNames": ["Id", "Keyword", "AdGroupId"]
    }, "v5", token, login)
    if "result" not in kw_r:
        return _fmt(kw_r)

    keywords = kw_r["result"].get("Keywords", [])
    kw_map = {k["Id"]: k["Keyword"] for k in keywords}
    gid_map = {k["Id"]: k["AdGroupId"] for k in keywords}
    kw_ids = [k["Id"] for k in keywords if k["Keyword"] != "---autotargeting"]

    if not kw_ids:
        return _fmt({"error": "Нет ключевых слов"})

    # Bids.get
    all_bids = []
    for i in range(0, len(kw_ids), 10000):
        r = await _api_call("bids", "get", {
            "SelectionCriteria": {"KeywordIds": kw_ids[i:i+10000]},
            "FieldNames": ["KeywordId", "Bid", "MinSearchPrice", "CurrentSearchPrice", "AuctionBids"]
        }, "v5", token, login)
        if "result" in r:
            all_bids.extend(r["result"].get("Bids", []))

    bid_map = {b["KeywordId"]: b for b in all_bids}

    # Анализ
    lines = ["KeywordId\tGroupId\tKeyword\tBid_rub\tTarget_bid_rub\tTarget_price_rub\tGAP_rub\tAction\tMinSearch_rub"]
    summary = {"total": 0, "RAISE": 0, "OK": 0, "LOWER": 0, "NO_DATA": 0,
               "raise_keywords": [], "total_raise_needed": 0}

    for kid in kw_ids:
        kw = kw_map.get(kid, "?")
        gid = gid_map.get(kid, 0)
        b = bid_map.get(kid, {})
        bid = b.get("Bid", 0) / 1000000
        min_s = b.get("MinSearchPrice", 0) / 1000000

        ab = {a["Position"]: a for a in (b.get("AuctionBids") or [])}
        target = ab.get(target_position, {})

        if not target:
            action = "NO_DATA"
            t_bid = 0; t_price = 0; gap = 0
        else:
            t_bid = target.get("Bid", 0) / 1000000
            t_price = target.get("Price", 0) / 1000000
            gap = round(t_bid - bid, 2)
            if bid >= t_bid:
                action = "OK" if bid <= t_bid * 1.3 else "LOWER"
            else:
                action = "RAISE"

        lines.append(f"{kid}\t{gid}\t{kw}\t{bid:.2f}\t{t_bid:.2f}\t{t_price:.2f}\t{gap:.2f}\t{action}\t{min_s:.2f}")

        summary["total"] += 1
        summary[action] += 1
        if action == "RAISE":
            summary["raise_keywords"].append({"kw": kw[:40], "bid": bid, "need": t_bid, "gap": gap})
            summary["total_raise_needed"] += gap

    # Топ-10 ключей с наибольшим GAP
    summary["raise_keywords"].sort(key=lambda x: x["gap"], reverse=True)
    summary["top10_raise"] = summary["raise_keywords"][:10]
    del summary["raise_keywords"]

    path = output_file or os.path.join(OUTPUT_DIR, f"_analytics_{campaign_id}.tsv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return _fmt({
        "file": path,
        "target": target_position,
        "total": summary["total"],
        "RAISE": summary["RAISE"],
        "OK": summary["OK"],
        "LOWER": summary["LOWER"],
        "NO_DATA": summary["NO_DATA"],
        "raise_rub": round(summary["total_raise_needed"], 2),
        "top5_raise": summary["top10_raise"][:5]
    })


# ============================================================
# TOOL: Set bids for target position (setAuto)
# ============================================================
@mcp.tool(
    name="yd_bids_auto",
    annotations={
        "title": "Яндекс.Директ: автоставки на целевую позицию",
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True
    }
)
async def yd_bids_auto(
    campaign_id: int = 0, keyword_ids: str = "",
    target_traffic_volume: int = 75,
    bid_ceiling: float = 0, increase_percent: int = 0,
    token: str = "", login: str = ""
) -> str:
    """Автоматически выставить ставки на целевую позицию через KeywordBids.setAuto.

    TrafficVolume: 100=1-я, 85=2-я, 75=3-я, 65=4-я позиция в премиум-блоке.

    Args:
        campaign_id: ID кампании (применить ко ВСЕМ ключам кампании)
        keyword_ids: Или конкретные KeywordId через запятую
        target_traffic_volume: Целевой объем трафика 5-100 (75=3-я позиция)
        bid_ceiling: Потолок ставки в РУБЛЯХ (0 = без ограничения)
        increase_percent: Надбавка 0-1000%
        token: OAuth-токен
        login: Client-Login
    """
    if keyword_ids:
        kids = _parse_ids(keyword_ids)
    elif campaign_id:
        r = await _api_call("keywords", "get", {
            "SelectionCriteria": {"CampaignIds": [campaign_id]},
            "FieldNames": ["Id", "Keyword"]
        }, "v5", token, login)
        if "result" not in r:
            return _fmt(r)
        kids = [k["Id"] for k in r["result"].get("Keywords", [])
                if k["Keyword"] != "---autotargeting"]
    else:
        return _fmt({"error": "Укажите campaign_id или keyword_ids"})

    if not kids:
        return _fmt({"error": "Нет ключей для установки ставок"})

    # Формируем запрос setAuto (BiddingRule.SearchByTrafficVolume)
    items = []
    for kid in kids:
        rule: Dict[str, Any] = {"TargetTrafficVolume": target_traffic_volume}
        if increase_percent:
            rule["IncreasePercent"] = increase_percent
        if bid_ceiling:
            rule["BidCeiling"] = int(bid_ceiling * 1000000)
        items.append({"KeywordId": kid, "BiddingRule": {"SearchByTrafficVolume": rule}})

    # Батчами по 10000
    results = []
    for i in range(0, len(items), 10000):
        r = await _api_call("keywordbids", "setAuto", {"KeywordBids": items[i:i+10000]},
                            "v5", token, login)
        if "result" in r:
            results.extend(r["result"].get("SetAutoResults", []))
        elif "error" in r:
            results.append(r)

    ok = sum(1 for x in results if isinstance(x, dict) and ("Id" in x or "KeywordId" in x))
    err = sum(1 for x in results if isinstance(x, dict) and "Errors" in x)
    return _fmt({
        "applied": ok, "errors": err, "total": len(items),
        "target_traffic_volume": target_traffic_volume,
        "bid_ceiling_rub": bid_ceiling or "нет",
        "position_hint": {100: "1-я", 85: "2-я", 75: "3-я", 65: "4-я"}.get(target_traffic_volume, f"~TV{target_traffic_volume}")
    })


# ============================================================
# TOOL: Forecast (Live 4 API)
# ============================================================
@mcp.tool(
    name="yd_forecast",
    annotations={
        "title": "Яндекс.Директ: прогноз бюджета (Live 4)",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": False, "openWorldHint": True
    }
)
async def yd_forecast(
    phrases_json: str, geo_ids: str = "225",
    output_file: str = "", token: str = "", login: str = ""
) -> str:
    """Прогноз показов/кликов/CTR/CPC для фраз через API Live 4 (deprecated но работает).

    Возвращает: Shows, Clicks, CTR, CPC (Min/Max/Premium) по позициям.
    ДАННЫЕ В ФАЙЛ, в контекст — только саммари.

    Args:
        phrases_json: JSON или @путь/к/файлу.json: ["купить сиз оптом", "перчатки рабочие"]
        geo_ids: ID регионов через запятую (225=Россия, 1=МО, 10174=ЛО)
        output_file: Путь файла
        token: OAuth-токен
        login: Client-Login
    """
    import asyncio

    try:
        phrases = _from_file(phrases_json)
    except (json.JSONDecodeError, ValueError) as e:
        return _fmt({"error": f"Ошибка данных: {e}"})

    geos = [int(x.strip()) for x in geo_ids.split(",") if x.strip()]

    # 1. CreateNewForecast
    r1 = await _live4_call("CreateNewForecast", {
        "Phrases": phrases[:100], "GeoID": geos
    }, token, login)

    if "data" not in r1:
        return _fmt({"error": "CreateNewForecast failed", "detail": r1})

    forecast_id = r1["data"]

    # 2. Ждём и получаем (до 3 попыток)
    forecast = None
    for attempt in range(4):
        await asyncio.sleep(15)
        r2 = await _live4_call("GetForecast", forecast_id, token, login)
        if "data" in r2 and r2["data"].get("StatusForecast") == "Processed":
            forecast = r2["data"]
            break

    if not forecast:
        return _fmt({"error": "Прогноз не готов через 60 сек. Попробуйте позже.",
                      "forecast_id": forecast_id})

    # 3. Парсим
    lines = ["Phrase\tShows\tClicks\tPremClicks\tCTR\tPremCTR\tMin_rub\tMax_rub\tPremMin_rub\tPremMax_rub"]
    total = {"shows": 0, "clicks": 0, "prem_clicks": 0, "spend_min": 0, "spend_max": 0}

    for ph in forecast.get("Phrases", []):
        shows = ph.get("Shows", 0)
        clicks = ph.get("Clicks", 0)
        prem_clicks = ph.get("PremiumClicks", 0)
        ctr = ph.get("CTR", 0)
        prem_ctr = ph.get("PremiumCTR", 0)
        mn = ph.get("Min", 0)
        mx = ph.get("Max", 0)
        pmn = ph.get("PremiumMin", 0)
        pmx = ph.get("PremiumMax", 0)

        lines.append(f"{ph.get('Phrase','?')}\t{shows}\t{clicks}\t{prem_clicks}\t"
                     f"{ctr:.2f}\t{prem_ctr:.2f}\t{mn:.2f}\t{mx:.2f}\t{pmn:.2f}\t{pmx:.2f}")

        total["shows"] += shows
        total["clicks"] += clicks
        total["prem_clicks"] += prem_clicks
        total["spend_min"] += clicks * mn if clicks else 0
        total["spend_max"] += prem_clicks * pmx if prem_clicks else 0

    path = output_file or os.path.join(OUTPUT_DIR, "_forecast.tsv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return _fmt({
        "file": path,
        "phrases": len(forecast.get("Phrases", [])),
        "geo": geos,
        "shows": total["shows"],
        "clicks_guarantee": total["clicks"],
        "clicks_premium": total["prem_clicks"],
        "spend_guarantee_rub": round(total["spend_min"], 2),
        "spend_premium_rub": round(total["spend_max"], 2),
    })


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "sse"
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse")
