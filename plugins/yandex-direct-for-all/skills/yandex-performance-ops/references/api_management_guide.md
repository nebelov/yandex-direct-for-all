# Яндекс.Директ API: Полный гайд по управлению кампаниями

> **Последнее обновление:** 2026-02-24
> **Источник:** Официальная документация Яндекс.Директ API (https://yandex.ru/dev/direct/doc/ru/)

## Содержание

1. [Создание кампаний (ЕПК / UnifiedCampaign)](#1-создание-кампаний-епк--unifiedcampaign)
2. [Управление группами объявлений](#2-управление-группами-объявлений)
3. [Объявления](#3-объявления)
4. [Ключевые слова](#4-ключевые-слова)
5. [Мониторинг и управление](#5-мониторинг-и-управление)
6. [Отличия v501 от v5](#6-отличия-v501-от-v5)
7. [Баллы API и лимиты](#7-баллы-api-и-лимиты)

---

## 1. Создание кампаний (ЕПК / UnifiedCampaign)

### Критически важно

- **С мая 2024 года все новые кампании = `UNIFIED_CAMPAIGN` (ЕПК)**
- **Endpoint: `https://api.direct.yandex.com/v501/`** (НЕ v5!)
- Старый TEXT_CAMPAIGN создать НЕЛЬЗЯ
- Деньги в API = **микроединицы** (1 рубль = 1,000,000)

### Endpoints

| Протокол | Адрес v501 |
|----------|------------|
| JSON | `https://api.direct.yandex.com/json/v501/campaigns` |
| SOAP | `https://api.direct.yandex.com/v501/campaigns` |
| WSDL | `https://api.direct.yandex.com/v501/campaigns?wsdl` |

### Заголовки запроса

```http
Authorization: Bearer <OAuth-токен>
Client-Login: <логин-клиента>  # только для агентств
Accept-Language: ru
Content-Type: application/json
```

### Полная структура создания ЕПК

```json
{
  "method": "add",
  "params": {
    "Campaigns": [{
      "Name": "Моя ЕПК кампания",
      "StartDate": "2026-03-01",
      "EndDate": "2026-12-31",
      "TimeZone": "Europe/Moscow",

      "NegativeKeywords": {
        "Items": ["бесплатно", "скачать", "реферат"]
      },

      "BlockedIps": {
        "Items": ["192.168.1.1"]
      },

      "ExcludedSites": {
        "Items": ["spam-site.ru"]
      },

      "TimeTargeting": {
        "Schedule": {
          "Items": [
            "1,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,0,0,0",
            "2,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,0,0,0",
            "3,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,0,0,0",
            "4,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,0,0,0",
            "5,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,0,0,0",
            "6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
            "7,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0"
          ]
        },
        "ConsiderWorkingWeekends": "YES",
        "HolidaysSchedule": {
          "SuspendOnHolidays": "NO",
          "BidPercent": 50,
          "StartHour": 9,
          "EndHour": 18
        }
      },

      "UnifiedCampaign": {
        "BiddingStrategy": {
          "Search": {
            "BiddingStrategyType": "WB_MAXIMUM_CLICKS",
            "WbMaximumClicks": {
              "WeeklySpendLimit": 10000000000,
              "BidCeiling": 50000000
            },
            "PlacementTypes": {
              "SearchResults": "YES",
              "ProductGallery": "YES",
              "DynamicPlaces": "YES",
              "Maps": "YES"
            }
          },
          "Network": {
            "BiddingStrategyType": "WB_MAXIMUM_CLICKS",
            "WbMaximumClicks": {
              "WeeklySpendLimit": 5000000000
            },
            "PlacementTypes": {
              "Network": "YES",
              "Maps": "YES"
            }
          }
        },

        "Settings": [
          {"Option": "ADD_METRICA_TAG", "Value": "YES"},
          {"Option": "ENABLE_SITE_MONITORING", "Value": "YES"},
          {"Option": "ENABLE_COMPANY_INFO", "Value": "YES"}
        ],

        "CounterIds": {
          "Items": [12345678]
        },

        "AttributionModel": "AUTO",

        "NegativeKeywordSharedSetIds": {
          "Items": [111222333]
        }
      }
    }]
  }
}
```

### Доступные стратегии назначения ставок для ЕПК

#### На поиске (Search)

| BiddingStrategyType | Описание | Параметры |
|---------------------|----------|-----------|
| `WB_MAXIMUM_CLICKS` | Оптимизация кликов (недельный бюджет) | WeeklySpendLimit (required), BidCeiling |
| `WB_MAXIMUM_CONVERSION_RATE` | Оптимизация конверсий (без ср. цены) | WeeklySpendLimit (required), GoalId (required), BidCeiling |
| `AVERAGE_CPC` | Ср. цена клика | AverageCpc (required), WeeklySpendLimit |
| `AVERAGE_CPA` | Ср. цена конверсии | AverageCpa (required), GoalId (required), WeeklySpendLimit, BidCeiling |
| `PAY_FOR_CONVERSION` | Оплата за конверсии | Cpa (required), GoalId (required), WeeklySpendLimit |
| `AVERAGE_CRR` | Доля рекламных расходов | Crr (required), GoalId (required), WeeklySpendLimit |
| `PAY_FOR_CONVERSION_CRR` | Оплата за конверсии (ДРР) | Crr (required), GoalId (required), WeeklySpendLimit |
| `HIGHEST_POSITION` | Ручное управление | - |
| `SERVING_OFF` | Показы выключены | - |

#### В сетях (Network)

| BiddingStrategyType | Описание |
|---------------------|----------|
| `NETWORK_DEFAULT` | Показы в сетях по настройкам поиска |
| `WB_MAXIMUM_CLICKS` | Оптимизация кликов |
| `WB_MAXIMUM_CONVERSION_RATE` | Оптимизация конверсий |
| `AVERAGE_CPC` | Средняя цена клика |
| `AVERAGE_CPA` | Средняя цена конверсии |
| `PAY_FOR_CONVERSION` | Оплата за конверсии |
| `SERVING_OFF` | Показы выключены |

### Пример создания ЕПК с curl

```bash
curl -X POST "https://api.direct.yandex.com/json/v501/campaigns" \
  -H "Authorization: Bearer YOUR_OAUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ru" \
  -d '{
    "method": "add",
    "params": {
      "Campaigns": [{
        "Name": "Тестовая ЕПК",
        "StartDate": "2026-03-01",
        "UnifiedCampaign": {
          "BiddingStrategy": {
            "Search": {
              "BiddingStrategyType": "WB_MAXIMUM_CLICKS",
              "WbMaximumClicks": {
                "WeeklySpendLimit": 10000000000
              }
            },
            "Network": {
              "BiddingStrategyType": "NETWORK_DEFAULT"
            }
          }
        }
      }]
    }
  }'
```

### Пример создания ЕПК с Python

```python
import requests

API_URL = "https://api.direct.yandex.com/json/v501/campaigns"
OAUTH_TOKEN = "YOUR_OAUTH_TOKEN"

headers = {
    "Authorization": f"Bearer {OAUTH_TOKEN}",
    "Content-Type": "application/json",
    "Accept-Language": "ru"
}

payload = {
    "method": "add",
    "params": {
        "Campaigns": [{
            "Name": "Тестовая ЕПК через Python",
            "StartDate": "2026-03-01",
            "UnifiedCampaign": {
                "BiddingStrategy": {
                    "Search": {
                        "BiddingStrategyType": "AVERAGE_CPC",
                        "AverageCpc": {
                            "AverageCpc": 30000000,  # 30 руб
                            "WeeklySpendLimit": 10000000000  # 10000 руб
                        }
                    },
                    "Network": {
                        "BiddingStrategyType": "NETWORK_DEFAULT"
                    }
                },
                "Settings": [
                    {"Option": "ADD_METRICA_TAG", "Value": "YES"},
                    {"Option": "ENABLE_SITE_MONITORING", "Value": "YES"}
                ],
                "CounterIds": {"Items": [12345678]},
                "AttributionModel": "AUTO"
            }
        }]
    }
}

response = requests.post(API_URL, headers=headers, json=payload)
result = response.json()
print(f"Campaign ID: {result['result']['AddResults'][0]['Id']}")
```

### Лимиты

- Максимум **10 кампаний** в одном вызове метода
- Дата начала должна быть >= текущей даты
- Минус-фразы: до 7 слов, до 35 символов/слово, до 20000 символов суммарно

---

## 2. Управление группами объявлений

### Endpoint

```
https://api.direct.yandex.com/json/v501/adgroups
```

### Типы групп

| Тип группы | Описание | Допустимые объявления |
|------------|----------|----------------------|
| `UNIFIED_AD_GROUP` | Единая перфоманс группа | TextAd, TextImageAd, TextAdBuilderAd, ShoppingAd |
| `TEXT_AD_GROUP` | Текстово-графическая | TextAd, ImageAd |
| `SMART_AD_GROUP` | Смарт-баннеры | SmartAd |
| `DYNAMIC_TEXT_AD_GROUP` | Динамические объявления | DynamicTextAd |

### Создание группы для ЕПК

```json
{
  "method": "add",
  "params": {
    "AdGroups": [{
      "Name": "Группа объявлений #1",
      "CampaignId": 123456789,
      "RegionIds": [1, 10174],
      "NegativeKeywords": {
        "Items": ["бесплатно", "скачать"]
      },
      "NegativeKeywordSharedSetIds": {
        "Items": [111222333]
      },
      "TrackingParams": "utm_source=yandex&utm_medium=cpc",
      "UnifiedAdGroup": {
        "OfferRetargeting": "NO"
      }
    }]
  }
}
```

### Параметры UnifiedAdGroup

| Параметр | Описание |
|----------|----------|
| `OfferRetargeting` | Включить офферный ретаргетинг (YES/NO) |

### Пример с Python

```python
def create_adgroup(campaign_id: int, name: str, region_ids: list):
    payload = {
        "method": "add",
        "params": {
            "AdGroups": [{
                "Name": name,
                "CampaignId": campaign_id,
                "RegionIds": region_ids,
                "UnifiedAdGroup": {
                    "OfferRetargeting": "NO"
                }
            }]
        }
    }

    response = requests.post(
        "https://api.direct.yandex.com/json/v501/adgroups",
        headers=headers,
        json=payload
    )
    return response.json()

# Использование
result = create_adgroup(
    campaign_id=123456789,
    name="Комбинезоны защитные",
    region_ids=[1, 10174]  # Москва и область
)
```

### Регионы

- `0` - показывать во всех регионах
- Минус перед ID - исключить регион (например, `[1, -219]` = Москва и область, кроме Черноголовки)
- Справочник регионов: метод `Dictionaries.get`

### Лимиты

- Максимум **1000 групп** в одном вызове метода
- Нельзя добавлять группы в архивную кампанию

---

## 3. Объявления

### Endpoint

```
https://api.direct.yandex.com/json/v501/ads
```

### Типы объявлений для UNIFIED_AD_GROUP

| Тип | Структура | Описание |
|-----|-----------|----------|
| TEXT_AD | TextAd | Текстово-графическое |
| IMAGE_AD | TextImageAd | Графическое (изображение) |
| IMAGE_AD | TextAdBuilderAd | Графическое (креатив) |
| SHOPPING_AD | ShoppingAd | Товарное |
| LISTING_AD | ListingAd | Страницы каталога |

### Ограничения текстов

| Элемент | Лимит | Примечание |
|---------|-------|------------|
| Заголовок 1 (Title) | 56 символов | Обязательный, каждое слово до 22 символов |
| Заголовок 2 (Title2) | 30 символов | Показывается не всегда |
| Текст (Text) | 81 символ | Обязательный, каждое слово до 23 символов |
| Отображаемая ссылка | 20 символов | Только при наличии Href |
| Быстрые ссылки | до 8 шт | Текст: 30 симв, описание: 60 симв |
| Уточнения | до 50 шт | - |

> "Узкие" символы: `!,.;:"` - не учитываются в лимите (до 15 шт)

### Создание текстово-графического объявления

```json
{
  "method": "add",
  "params": {
    "Ads": [{
      "AdGroupId": 987654321,
      "TextAd": {
        "Title": "Комбинезоны защитные оптом",
        "Title2": "От производителя",
        "Text": "Защитные комбинезоны от 150 руб. Доставка по РФ. Сертификаты.",
        "Href": "https://example.com/kombinezon?utm_source=yandex",
        "Mobile": "NO",
        "DisplayUrlPath": "kombinezon",
        "SitelinkSetId": 111222333,
        "AdExtensionIds": [444555666, 777888999],
        "AdImageHash": "abc123def456",
        "BusinessId": 123456,
        "PriceExtension": {
          "Price": 150000000,
          "OldPrice": 200000000,
          "PriceQualifier": "FROM",
          "PriceCurrency": "RUB"
        }
      }
    }]
  }
}
```

### Создание товарного объявления (ShoppingAd)

```json
{
  "method": "add",
  "params": {
    "Ads": [{
      "AdGroupId": 987654321,
      "ShoppingAd": {
        "FeedId": 123456789,
        "FeedFilterConditions": [
          {
            "Operand": "categoryId",
            "Operator": "EQUALS_ANY",
            "Arguments": ["101", "102", "103"]
          },
          {
            "Operand": "price",
            "Operator": "IN_RANGE",
            "Arguments": ["100-500", "1000-5000"]
          }
        ],
        "TitleSources": ["name", "model"],
        "TextSources": ["description"],
        "DefaultTexts": ["Товар по выгодной цене"],
        "SitelinkSetId": 111222333,
        "BusinessId": 123456
      }
    }]
  }
}
```

### Операторы фильтрации для FeedFilterConditions

| Operator | Описание | Пример |
|----------|----------|--------|
| `EQUALS_ANY` | Равно любому из значений | `["Audi", "BMW"]` |
| `CONTAINS_ANY` | Содержит любое из значений | `["защит", "комбин"]` |
| `NOT_CONTAINS_ALL` | Не содержит все значения | `["б/у", "ремонт"]` |
| `GREATER_THAN` | Больше | `["1000"]` |
| `LESS_THAN` | Меньше | `["5000"]` |
| `IN_RANGE` | В диапазоне | `["100-500"]` |
| `EXISTS` | Поле существует | `["1"]` |

### Быстрые ссылки (Sitelinks)

#### Создание набора быстрых ссылок

```json
{
  "method": "add",
  "params": {
    "SitelinksSets": [{
      "Sitelinks": [
        {
          "Title": "Комбинезоны",
          "Href": "https://example.com/kombinezon",
          "Description": "Защитные комбинезоны от производителя"
        },
        {
          "Title": "Халаты",
          "Href": "https://example.com/halat",
          "Description": "Медицинские халаты оптом"
        },
        {
          "Title": "Маски",
          "Href": "https://example.com/maski",
          "Description": "Медицинские маски FFP2, KN95"
        },
        {
          "Title": "Перчатки",
          "Href": "https://example.com/perchatki",
          "Description": "Нитриловые и латексные перчатки"
        }
      ]
    }]
  }
}
```

#### Ограничения быстрых ссылок

- От 1 до 8 ссылок в наборе
- Текст: до 30 символов
- Описание: до 60 символов
- Суммарная длина текстов ссылок 1-4: до 66 символов
- Суммарная длина текстов ссылок 5-8: до 66 символов

### Уточнения (AdExtensions)

```json
{
  "method": "add",
  "params": {
    "AdExtensions": [{
      "Callout": {
        "CalloutText": "Сертификаты качества"
      }
    }, {
      "Callout": {
        "CalloutText": "Доставка по РФ"
      }
    }, {
      "Callout": {
        "CalloutText": "Образцы бесплатно"
      }
    }]
  }
}
```

### Загрузка изображений

```json
{
  "method": "add",
  "params": {
    "AdImages": [{
      "Name": "kombinezon-banner",
      "ImageData": "BASE64_ENCODED_IMAGE_DATA"
    }]
  }
}
```

Типы изображений:
- `REGULAR` - обычное (для TextAd)
- `WIDE` - широкоформатное (для TextAd)
- `FIXED_IMAGE` - фиксированный размер (для графических объявлений)

### Лимиты

- Максимум **1000 объявлений** в одном вызове метода
- Нельзя добавлять в архивную кампанию

---

## 4. Ключевые слова

### Endpoint

```
https://api.direct.yandex.com/json/v5/keywords
```

> **Примечание:** для Keywords используется v5, не v501

### Добавление ключевых фраз

```json
{
  "method": "add",
  "params": {
    "Keywords": [
      {
        "AdGroupId": 987654321,
        "Keyword": "комбинезон защитный купить",
        "Bid": 30000000,
        "ContextBid": 15000000
      },
      {
        "AdGroupId": 987654321,
        "Keyword": "защитный костюм одноразовый -бесплатно -скачать",
        "Bid": 25000000
      }
    ]
  }
}
```

### Автотаргетинг

Автотаргетинг добавляется как специальная "фраза":

```json
{
  "method": "add",
  "params": {
    "Keywords": [{
      "AdGroupId": 987654321,
      "Keyword": "---autotargeting",
      "Bid": 20000000,
      "AutotargetingSearchBidIsAuto": "YES",
      "AutotargetingSettings": {
        "Categories": {
          "Exact": "YES",
          "Narrow": "YES",
          "Alternative": "YES",
          "Accessory": "NO",
          "Broader": "NO"
        },
        "BrandOptions": {
          "WithoutBrands": "YES",
          "WithAdvertiserBrand": "YES",
          "WithCompetitorsBrand": "NO"
        }
      }
    }]
  }
}
```

### Категории автотаргетинга

| Категория | Описание |
|-----------|----------|
| `Exact` | Целевые запросы - точное соответствие |
| `Narrow` | Узкие запросы - объявление шире запроса |
| `Alternative` | Альтернативные запросы - замена продукта |
| `Accessory` | Сопутствующие запросы |
| `Broader` | Широкие запросы - общий интерес |

### Минус-слова

**3 уровня минус-слов:**

1. **Уровень аккаунта** (NegativeKeywordSharedSets)
```json
{
  "method": "add",
  "params": {
    "NegativeKeywordSharedSets": [{
      "Name": "Общие минус-слова",
      "NegativeKeywords": {
        "Items": ["бесплатно", "скачать", "реферат", "курсовая", "диплом"]
      }
    }]
  }
}
```

2. **Уровень кампании** - параметр `NegativeKeywords` в структуре кампании

3. **Уровень группы** - параметр `NegativeKeywords` в структуре группы

### Правила минус-слов

- Указывать **без минуса** перед первым словом
- Яндекс **сам склоняет** минус-слова
- Писать "реферат", а НЕ "реферат реферата рефератов"
- Не более 7 слов в минус-фразе
- Каждое слово не более 35 символов
- Суммарная длина: 20000 символов (кампания) / 4096 символов (группа)

### Батчинг ключевых слов

```python
def add_keywords_batch(adgroup_id: int, keywords: list):
    """Добавление ключевых слов батчами по 1000"""
    BATCH_SIZE = 1000
    results = []

    for i in range(0, len(keywords), BATCH_SIZE):
        batch = keywords[i:i + BATCH_SIZE]

        payload = {
            "method": "add",
            "params": {
                "Keywords": [
                    {
                        "AdGroupId": adgroup_id,
                        "Keyword": kw["keyword"],
                        "Bid": kw.get("bid", 10000000)
                    }
                    for kw in batch
                ]
            }
        }

        response = requests.post(
            "https://api.direct.yandex.com/json/v5/keywords",
            headers=headers,
            json=payload
        )
        results.append(response.json())

        # Пауза для соблюдения лимитов
        time.sleep(0.5)

    return results
```

### Лимиты

- Максимум **1000 ключевых фраз** в одном вызове метода
- Не более **1 автотаргетинга** в группе

---

## 5. Мониторинг и управление

### Получение статуса кампаний

```json
{
  "method": "get",
  "params": {
    "SelectionCriteria": {
      "Ids": [123456789]
    },
    "FieldNames": [
      "Id", "Name", "Type", "Status", "State",
      "StatusPayment", "StartDate", "EndDate",
      "DailyBudget", "Statistics"
    ],
    "UnifiedCampaignFieldNames": [
      "BiddingStrategy", "Settings", "CounterIds"
    ]
  }
}
```

### Статусы кампании

| Status | Описание |
|--------|----------|
| `DRAFT` | Не отправлена на модерацию |
| `MODERATION` | На модерации |
| `ACCEPTED` | Хотя бы одно объявление принято |
| `REJECTED` | Все объявления отклонены |

| State | Описание |
|-------|----------|
| `ON` | Кампания активна |
| `OFF` | Кампания неактивна |
| `SUSPENDED` | Остановлена |
| `ENDED` | Завершилась |
| `ARCHIVED` | В архиве |

### Отправка на модерацию

```json
{
  "method": "moderate",
  "params": {
    "SelectionCriteria": {
      "Ids": [111, 222, 333, 444, 555]
    }
  }
}
```

**Ограничения:**
- Только объявления со статусом `DRAFT`
- В группе должны быть условия показа (ключевые фразы/автотаргетинг)
- Не более 10000 объявлений в одном вызове

### Включение/выключение кампаний

**Приостановка:**
```json
{
  "method": "suspend",
  "params": {
    "SelectionCriteria": {
      "Ids": [123456789]
    }
  }
}
```

**Возобновление:**
```json
{
  "method": "resume",
  "params": {
    "SelectionCriteria": {
      "Ids": [123456789]
    }
  }
}
```

### Архивация/разархивация

```json
{
  "method": "archive",
  "params": {
    "SelectionCriteria": {
      "Ids": [123456789]
    }
  }
}
```

```json
{
  "method": "unarchive",
  "params": {
    "SelectionCriteria": {
      "Ids": [123456789]
    }
  }
}
```

### Изменение ставок

```json
{
  "method": "set",
  "params": {
    "KeywordBids": [
      {
        "KeywordId": 111222333,
        "SearchBid": 35000000,
        "NetworkBid": 20000000
      }
    ]
  }
}
```

### Получение статистики (Reports)

```json
{
  "method": "get",
  "params": {
    "SelectionCriteria": {
      "DateFrom": "2026-02-01",
      "DateTo": "2026-02-24"
    },
    "FieldNames": [
      "Date", "CampaignId", "CampaignName",
      "Impressions", "Clicks", "Ctr", "Cost",
      "AvgCpc", "Conversions", "CostPerConversion"
    ],
    "ReportName": "Campaign Report",
    "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
    "DateRangeType": "CUSTOM_DATE",
    "Format": "TSV",
    "IncludeVAT": "YES"
  }
}
```

**Типы отчетов:**
- `CAMPAIGN_PERFORMANCE_REPORT` - по кампаниям
- `ADGROUP_PERFORMANCE_REPORT` - по группам
- `AD_PERFORMANCE_REPORT` - по объявлениям
- `CRITERIA_PERFORMANCE_REPORT` - по условиям показа
- `SEARCH_QUERY_PERFORMANCE_REPORT` - по поисковым запросам

---

## 6. Отличия v501 от v5

### Когда использовать v501

| Сервис | v5 | v501 |
|--------|----|----|
| Campaigns (ЕПК) | - | **v501** |
| AdGroups (UNIFIED_AD_GROUP) | - | **v501** |
| Ads (ShoppingAd, ListingAd) | - | **v501** |
| Keywords | **v5** | - |
| Sitelinks | **v5** | - |
| AdExtensions | **v5** | - |
| Reports | **v5** | - |

### Изменения в структурах

**Кампании:**
- `UnifiedCampaign` вместо `TextCampaign`
- Нельзя задать `ClientInfo` и `Notification`
- Изменился формат `PlacementTypes`
- Недоступна стратегия `AVERAGE_ROI`

**Группы:**
- `UnifiedAdGroup` вместо `TextAdGroup`
- Параметр `OfferRetargeting` для офферного ретаргетинга
- Автотаргетинг в РСЯ по умолчанию выключен

**Объявления:**
- Не поддерживается `VCardId` (визитка)
- Не поддерживается `Mobile="YES"`
- Не поддерживается `PreferVCardOverBusiness="YES"`
- Не поддерживается `TurboPageId`

### Миграция с TEXT_CAMPAIGN на ЕПК

1. Существующие TEXT_CAMPAIGN продолжают работать
2. Новые кампании создаются только как UNIFIED_CAMPAIGN
3. API в режиме совместимости: при создании TextCampaign создается ЕПК

---

## 7. Баллы API и лимиты

### Система баллов

Баллы регулируют нагрузку на API. Каждому рекламодателю выделяется **суточный лимит**.

**Информация в заголовках ответа:**
```
Units: 10/20828/64000
```
Формат: `потрачено / остаток / суточный лимит`

```
Units-Used-Login: my_login
```
Логин, с которого списаны баллы.

### Стоимость операций

| Сервис | Метод | За вызов | За объект |
|--------|-------|----------|-----------|
| Campaigns | add | 10 | 5 |
| Campaigns | get | 10 | 1 |
| Campaigns | update | 10 | 3 |
| AdGroups | add | 20 | 20 |
| AdGroups | get | 15 | 1 |
| Ads | add | 20 | 20 |
| Ads | get | 15 | 1 |
| Ads | moderate | 15 | 0 |
| Keywords | add | 20 | 2 |
| Keywords | get | 15 | 1-3 |
| Sitelinks | add | 20 | 20 |
| Dictionaries | get | 1 | 0 |

### Ошибки

- За ошибку вызова метода: **20 баллов**
- За ошибку операции: **20 баллов за объект**

### Оптимальный батчинг

```python
# Оптимальные размеры батчей
BATCH_SIZES = {
    "campaigns": 10,      # максимум
    "adgroups": 500,      # оптимально (макс 1000)
    "ads": 500,           # оптимально (макс 1000)
    "keywords": 1000,     # максимум
    "sitelinks": 500      # оптимально (макс 1000)
}

# Рекомендуемая пауза между запросами
DELAY_SECONDS = 0.2  # 5 запросов в секунду
```

### Технические ограничения

- Не более **5 одновременных запросов** от одного рекламодателя
- Суточный лимит зависит от активности кампаний (показы, клики, расходы)
- Баллы начисляются по скользящему окну (1/24 суточного лимита каждый час)

### Пример с отслеживанием баллов

```python
import requests
import time

class DirectApiClient:
    def __init__(self, token: str):
        self.token = token
        self.units_remaining = None
        self.units_limit = None

    def call(self, endpoint: str, payload: dict):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept-Language": "ru"
        }

        response = requests.post(
            f"https://api.direct.yandex.com/json/v501/{endpoint}",
            headers=headers,
            json=payload
        )

        # Парсинг баллов из заголовков
        units_header = response.headers.get("Units", "0/0/0")
        parts = units_header.split("/")
        spent = int(parts[0])
        self.units_remaining = int(parts[1])
        self.units_limit = int(parts[2])

        print(f"[Units] Spent: {spent}, Remaining: {self.units_remaining}/{self.units_limit}")

        # Если осталось мало баллов - подождать
        if self.units_remaining < 100:
            print("Low on units, sleeping 60 seconds...")
            time.sleep(60)

        return response.json()
```

---

## Полный порядок создания кампании через API

```python
# 1. Создать набор минус-слов (аккаунт)
negative_set_id = create_negative_keyword_shared_set([
    "бесплатно", "скачать", "реферат", "курсовая"
])

# 2. Создать быстрые ссылки
sitelinks_set_id = create_sitelinks_set([
    {"Title": "Комбинезоны", "Href": "https://site.ru/kombinezon"},
    {"Title": "Халаты", "Href": "https://site.ru/halat"},
])

# 3. Создать уточнения
extension_ids = create_ad_extensions([
    "Сертификаты качества",
    "Доставка по РФ",
    "Образцы бесплатно"
])

# 4. Создать кампанию (ЕПК)
campaign_id = create_unified_campaign(
    name="СИЗ - Комбинезоны",
    start_date="2026-03-01",
    weekly_budget=10000000000,  # 10000 руб
    counter_ids=[12345678],
    negative_set_ids=[negative_set_id]
)

# 5. Создать группу объявлений
adgroup_id = create_adgroup(
    campaign_id=campaign_id,
    name="Комбинезоны защитные",
    region_ids=[1, 10174]
)

# 6. Создать объявления
ad_ids = create_ads(
    adgroup_id=adgroup_id,
    ads=[{
        "title": "Комбинезоны защитные оптом",
        "title2": "От производителя",
        "text": "Защитные комбинезоны от 150 руб. Доставка по РФ.",
        "href": "https://site.ru/kombinezon",
        "sitelinks_set_id": sitelinks_set_id,
        "extension_ids": extension_ids
    }]
)

# 7. Добавить ключевые слова
keyword_ids = add_keywords(
    adgroup_id=adgroup_id,
    keywords=[
        {"keyword": "комбинезон защитный купить", "bid": 30000000},
        {"keyword": "одноразовый костюм защитный", "bid": 25000000}
    ]
)

# 8. Добавить автотаргетинг
add_autotargeting(adgroup_id=adgroup_id, bid=20000000)

# 9. Отправить на модерацию
moderate_ads(ad_ids)

print(f"Campaign {campaign_id} created and submitted for moderation!")
```

---

## Источники

- [Официальная документация Яндекс.Директ API](https://yandex.ru/dev/direct/doc/ru/)
- [Справочник методов v5](https://yandex.ru/dev/direct/doc/ru/ref-v5/)
- [Обновление до ЕПК](https://yandex.ru/dev/direct/doc/ru/unified-campaign-update)
- [Ограничения и баллы](https://yandex.ru/dev/direct/doc/ru/concepts/units)
- [Быстрый старт](https://yandex.ru/dev/direct/doc/ru/best-practice/quick-start)
