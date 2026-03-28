import os
import json
import base64
from typing import Dict, Any, Optional

import requests
from requests.exceptions import RequestException

# API Configuration
GEN_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/gen/search"
WEB_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"
DEFAULT_TIMEOUT = 30


def get_search_api_credentials() -> tuple[str, str]:
    api_key = (os.getenv("SEARCH_API_KEY") or os.getenv("YANDEX_SEARCH_API_KEY") or "").strip()
    folder_id = (os.getenv("FOLDER_ID") or os.getenv("YANDEX_SEARCH_FOLDER_ID") or "").strip()
    if not api_key:
        raise ValueError("SEARCH_API_KEY or YANDEX_SEARCH_API_KEY environment variable not set")
    if not folder_id:
        raise ValueError("FOLDER_ID or YANDEX_SEARCH_FOLDER_ID environment variable not set")
    return api_key, folder_id


def make_http_request(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    decode_base64: bool = False
) -> str:
    try:
        with requests.post(url, headers=headers, json=json_body, timeout=timeout) as response:
            response.raise_for_status()
            
            if decode_base64:
                decoded_data = base64.b64decode(json.loads(response.text)["rawData"]).decode('utf-8')
                return decoded_data
            return response.text
                
    except RequestException as e:
        raise RuntimeError(f"API request failed: {str(e)}") from e


def validate_input_data(data: Dict[str, Any], required_keys: set) -> Optional[str]:
    if missing_keys := required_keys - set(data):
        return f"Missing required keys: {', '.join(missing_keys)}"
    return None


def call_ai_search_with_yazeka(data: Dict[str, Any]) -> str:
    api_key, folder_id = get_search_api_credentials()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {api_key}"
    }
    body = {
        "messages": [{"content": data["query"], "role": "ROLE_USER" }],
        "searchFilters": [ { "lang": ("tr" if data["search_region"] == 'tr' else "en")} ],
        "folderId": folder_id,
        "fixMisspell": True,
        "enableNrfmDocs": True,
        "search_type": "SEARCH_TYPE_TR" if data["search_region"] == 'tr' else "SEARCH_TYPE_COM"
    }
    return make_http_request(GEN_SEARCH_URL, headers=headers, json_body=body, timeout=200)


def call_web_search(data: Dict[str, Any]) -> str:
    api_key, folder_id = get_search_api_credentials()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {api_key}"
    }

    # Support ru, tr, en regions
    region = data["search_region"]
    if region == 'ru':
        search_type = "SEARCH_TYPE_RU"
        l10n = "LOCALIZATION_RU"
    elif region == 'tr':
        search_type = "SEARCH_TYPE_TR"
        l10n = "LOCALIZATION_TR"
    else:
        search_type = "SEARCH_TYPE_COM"
        l10n = "LOCALIZATION_EN"

    body = {
        "query": {
            "searchType": search_type,
            "queryText": data["query"],
            "familyMode": "FAMILY_MODE_NONE",
            "fixTypoMode": "FIX_TYPO_MODE_OFF",
        },
        "folderId": folder_id,
        "groupSpec": {"groupsOnPage": 10},
        "l10n": l10n,
        "region": region,
        "responseFormat": "FORMAT_XML"
    }

    return make_http_request(WEB_SEARCH_URL, headers=headers, json_body=body, timeout=10, decode_base64=True)
