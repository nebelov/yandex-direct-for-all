# Промпт: Индивидуальный анализ площадок РСЯ (v1)

> Для КАЖДОЙ РСЯ-кампании ОТДЕЛЬНЫЙ анализ. НИКОГДА общий список.
> Дата создания: 2026-02-27. Урок AP-019.

## Роль
Ты — аналитик площадок РСЯ. Задача — для КАЖДОЙ РСЯ-кампании ИНДИВИДУАЛЬНО определить площадки для блокировки.

## Truth layer
- placement-level verdict = Direct Reports API по `Placement` и goal клиента;
- Roistat использовать как primary-source для campaign/adgroup/ad/keyword, но НЕ как доказательство `0 лидов` по домену площадки.

## Входные данные (заполнить перед запуском!)

```
РСЯ-кампании:
| ID | Название | Текущих ExcludedSites | Свободных слотов |
|---|---|---|---|
| {CID_1} | {NAME_1} | {COUNT_1} | {FREE_1} |
| {CID_2} | {NAME_2} | {COUNT_2} | {FREE_2} |

API:
- Token: {TOKEN}
- Login: {LOGIN}
- GoalId: {GOAL_ID}
```

## АЛГОРИТМ (для КАЖДОЙ кампании ОТДЕЛЬНО!)

### Шаг 1: Получить текущие ExcludedSites
```
yd_api(service=campaigns, method=get, params={
  "SelectionCriteria": {"Ids": [CID]},
  "FieldNames": ["Id", "Name", "ExcludedSites"]
}, version="v501", token=..., login=...)
```

### Шаг 2: Reports API — статистика площадок ПО КАЖДОЙ кампании
```
yd_api(service=reports, method=get, params={
  "params": {
    "SelectionCriteria": {
      "DateFrom": "{DATE_FROM}",
      "DateTo": "{DATE_TO}",
      "Filter": [
        {"Field": "CampaignId", "Operator": "EQUALS", "Values": ["CID"]},
        {"Field": "AdNetworkType", "Operator": "EQUALS", "Values": ["AD_NETWORK"]}
      ]
    },
    "FieldNames": ["Placement", "Impressions", "Clicks", "Cost", "Ctr", "AvgCpc", "Conversions", "CostPerConversion", "ConversionRate"],
    "ReportName": "placement_{CID}",
    "ReportType": "CUSTOM_REPORT",
    "DateRangeType": "CUSTOM_DATE",
    "Format": "TSV",
    "IncludeVAT": "YES",
    "Goals": ["{GOAL_ID}"],
    "AttributionModels": ["LC"]
  }
}, token=..., login=...)
```

### Шаг 3: Определить площадки на блокировку
Критерии (приоритет):
1. **High-confidence app/browser/VPN/spam-app:** Clicks > 5, CTR > 1%, `Conversions_{GOAL_ID}_LC = 0`, площадка выглядит как mobile app / browser / vpn / game / spam-app
2. **High-confidence junk site inventory:** Clicks > 5, CTR > 1%, `Conversions_{GOAL_ID}_LC = 0`, площадка выглядит как low-intent mobile news / video / feed / off-topic garbage-site
3. **НЕ включать** слабоподозрительные площадки только потому что у них `0` конверсий
4. **ПРОВЕРИТЬ** что площадка НЕ в текущем ExcludedSites (не дублировать!)

### Шаг 4: Для ПОЛНЫХ кампаний (1000/1000) — РОТАЦИЯ
1. Из текущего ExcludedSites определить "устаревшие" — те которые НЕ появляются в отчёте за окно review
2. Устаревшие = уже не откручиваются, блокировка бесполезна
3. Если слотов всё ещё мало — удалить наименее подозрительные площадки без явного app/browser/vpn/spam/site-trash сигнала
4. Добавить актуальные мусорные площадки на освободившиеся слоты
5. API: Campaigns.update ExcludedSites = текущие - устаревшие + новые

### Шаг 5: Для НЕполных кампаний — обычное добавление
1. Добавить ТОЛЬКО площадки из ЭТОЙ кампании (не из другой!)
2. Учитывать свободные слоты (лимит 1000)
3. API: Campaigns.update ExcludedSites = текущие + новые

## ЖЕЛЕЗНЫЕ ПРАВИЛА
1. **КАЖДАЯ кампания = СВОЙ список!** НЕ копировать один список во все
2. **Добавлять ТОЛЬКО площадки из ЭТОЙ кампании** — данные из другой РК нерелевантны
3. **Лимит 1000** — учитывать свободные слоты ПЕРЕД добавлением
4. **Ротация** — для полных РК удалять устаревшие, освобождать слоты
5. **НЕ блокировать** площадки с `Conversions_{GOAL_ID}_LC > 0`
6. **НЕ добавлять** yandex.ru, ya.ru, yandex.kz — API ошибка 5006 (нельзя блокировать корневые домены Яндекса)
7. **НЕ блокировать** тематически релевантные площадки без явного мусорного сигнала

## ФОРМАТ ВЫВОДА

Файл: `claude/docs/RSY_PLACEMENTS_INDIVIDUAL_ANALYSIS.md`

Для КАЖДОЙ кампании отдельная секция:

```markdown
### Кампания {CID} — {Name}
- Текущих ExcludedSites: N
- Свободных слотов: N
- Площадок к блокировке: N

#### Ротация (если полная РК):
| # | Устаревшая площадка (на удаление) | Причина удаления |

#### К блокировке:
| # | Площадка | Clicks | Cost | CTR | Conv | Причина |

#### API-вызов:
Campaigns.update ExcludedSites = [полный список]
```

НЕ запускай субагентов!
