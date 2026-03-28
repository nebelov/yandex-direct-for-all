# Шаблон: Диагностика проблем на Поиске + РСЯ (v3)

> Использовать когда: "плохие цифры на поиске", "большой расход мало лидов", "CPA вырос", "что с поиском", "что с РСЯ"
> Скоуп: ВСЕГДА все кампании типа ({ROISTAT_MARKER_LEVEL_1} + search) и ({ROISTAT_MARKER_LEVEL_1} + rsya), НЕ одна конкретная
> Источник конверсий: Roistat (первичный), Reports API (вторичный для SQR и площадок)

## ТРИГГЕР

Пользователь сообщает цифры за день/период по поиску (расход, лиды, CPA) и просит разобраться.

---

## ПЕРЕД ЗАПУСКОМ: Предпосылки (ОБЯЗАТЕЛЬНО!)

1. `chmod +x ~/.codex/skills/yandex-performance-ops/scripts/roistat_query.sh` — скрипт может потерять +x
2. `change_tracker.py` лежит в `~/.codex/skills/yandex-performance-ops/scripts/`, НЕ в `scripts/` проекта
3. В background bash: использовать ПОЛНЫЕ пути (НЕ `~`), НЕ добавлять `sleep` в конец
4. Reports API: retry loop (201→202→200), минимум 5 попыток с sleep 5

---

## Фаза 1. Сбор данных — 9 параллельных задач

Все данные в файлы `data/search_YYMMDD/`, НЕ в контекст.

### 1-2. Roistat: кампании + группы за день

```bash
SCRIPT=~/.codex/skills/yandex-performance-ops/scripts/roistat_query.sh
OUT="data/search_YYMMDD"

# Кампании
echo '{"dimensions":["marker_level_3"],"metrics":["visits","leads","sales","revenue","marketing_cost","profit","roi","cpl","cpo"],"period":{"from":"YYYY-MM-DDT00:00:00+0300","to":"YYYY-MM-DDT23:59:59+0300"},"filters":[{"field":"marker_level_1","operation":"=","value":"TODO"},{"field":"marker_level_2","operation":"=","value":"search"}]}' | "$SCRIPT" "$OUT/campaigns.json" project/analytics/data

# Группы
echo '{"dimensions":["marker_level_4"],"metrics":["visits","leads","sales","revenue","marketing_cost","profit","cpl"],"period":{"from":"YYYY-MM-DDT00:00:00+0300","to":"YYYY-MM-DDT23:59:59+0300"},"filters":[{"field":"marker_level_1","operation":"=","value":"TODO"},{"field":"marker_level_2","operation":"=","value":"search"}]}' | "$SCRIPT" "$OUT/adgroups.json" project/analytics/data
```

### 3. Ежедневная динамика — ЧЕРЕЗ Reports API (НЕ Roistat!)

**GOTCHA:** Roistat `dimensions=["date"]` с фильтром search → `internal_error`. Использовать Reports API:

```bash
# CAMPAIGN_PERFORMANCE_REPORT, 7 дней, с retry
TOKEN="..."
for i in 1 2 3 4 5; do
  HTTP_CODE=$(curl -s -w "%{http_code}" -o "$OUT/campaign_daily_7d.tsv" -X POST \
    "https://api.direct.yandex.com/json/v5/reports" \
    -H "Authorization: Bearer $TOKEN" -H "Client-Login: LOGIN" \
    -H "Accept-Language: ru" -H "processingMode: auto" \
    -H "returnMoneyInMicros: false" -H "skipReportHeader: true" \
    -H "skipColumnHeader: false" -H "skipReportSummary: true" \
    -d '{"params":{"SelectionCriteria":{"DateFrom":"FROM","DateTo":"TO"},"FieldNames":["Date","CampaignId","CampaignName","CampaignType","Impressions","Clicks","Cost","Conversions","AvgCpc"],"ReportName":"UNIQUE_NAME","ReportType":"CAMPAIGN_PERFORMANCE_REPORT","DateRangeType":"CUSTOM_DATE","Format":"TSV","IncludeVAT":"YES","Goals":["TODO"]}}')
  [ "$HTTP_CODE" = "200" ] && break
  sleep 5
done
```

### 4. SQR за день — Reports API с retry

```bash
# SEARCH_QUERY_PERFORMANCE_REPORT, 1 день, с retry (аналогично п.3)
# FieldNames: CampaignId, CampaignName, AdGroupId, AdGroupName, Query, Impressions, Clicks, Cost, Conversions, CostPerConversion, ConversionRate
```

### 5. Устройства — Roistat

```bash
echo '{"dimensions":["device_type"],"metrics":["visits","leads","sales","revenue","marketing_cost","bounce_rate","conversion_visits_to_leads"],...}' | "$SCRIPT" "$OUT/devices.json" project/analytics/data
```

### 6. История изменений — change_tracker.py

```bash
python3 ~/.codex/skills/yandex-performance-ops/scripts/change_tracker.py \
  --token "$TOKEN" --login "$LOGIN" --days 7 \
  --data-dir ./data --output data/search_YYMMDD/changes_report.html
```

### 7. Детали заявок — Roistat order/list

**GOTCHA (v2):** Фильтр order/list на creation_date может давать "Filter is invalid".
Альтернатива: использовать analytics с marker_level_3 + marker_level_4 для получения разбивки по кампаниям/группам (уже есть в п.1-2). Детали заявок (тип: звонок/форма) — через visit/list если нужно.

### 8. Площадки РСЯ — Reports API (ОБЯЗАТЕЛЬНО!)

> РСЯ = отдельный канал. Площадки (сайты, приложения) где показывается реклама — главный источник слива в РСЯ.

```bash
# CRITERIA_PERFORMANCE_REPORT с Placement, 7 дней, retry
TOKEN="..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  HTTP_CODE=$(curl -s -w "%{http_code}" -o "$OUT/rsy_placements_7d.tsv" -X POST \
    "https://api.direct.yandex.com/json/v5/reports" \
    -H "Authorization: Bearer $TOKEN" -H "Client-Login: LOGIN" \
    -H "Accept-Language: ru" -H "processingMode: auto" \
    -H "returnMoneyInMicros: false" -H "skipReportHeader: true" \
    -H "skipColumnHeader: false" -H "skipReportSummary: true" \
    -d '{"params":{"SelectionCriteria":{"DateFrom":"FROM","DateTo":"TO","Filter":[{"Field":"CampaignType","Operator":"EQUALS","Values":["TEXT_CAMPAIGN"]}]},"FieldNames":["Placement","CampaignId","CampaignName","Impressions","Clicks","Cost","Conversions","CostPerConversion","Ctr","AvgCpc","BounceRate"],"ReportName":"UNIQUE_NAME","ReportType":"CRITERIA_PERFORMANCE_REPORT","DateRangeType":"CUSTOM_DATE","Format":"TSV","IncludeVAT":"YES","Goals":["TODO"]}}')
  [ "$HTTP_CODE" = "200" ] && break
  sleep 5
done
```

**Альтернативный ReportType:** Если CRITERIA_PERFORMANCE_REPORT не даёт Placement — попробовать CUSTOM_REPORT или AD_PERFORMANCE_REPORT с Placement.

### 9. Ручной паттерн-анализ SQR (ОБЯЗАТЕЛЬНО!)

> Вместо слепой выборки отдельных запросов нужно вручную пройти raw SQR и выписать повторяющиеся токены/связки слов, которые тянут мусор.

Выход:
- `SQR_TOKEN_PATTERNS_YYMMDD.md`

Что фиксировать вручную:
- повторяющиеся нецелевые слова;
- повторяющиеся целевые слова, которые нельзя заминусовать;
- связки слов, из-за которых broad/autotargeting тянут мусор;
- кандидаты в минус-слова с указанием, на каком уровне их добавлять.

---

## Фаза 2. Анализ (читать файлы ПОЭТАПНО)

Roistat JSON и TSV читать вручную по сохранённым raw-файлам. Никаких analysis-скриптов.

### Вопросы анализа

| # | Вопрос | Источник | Метод |
|---|--------|----------|-------|
| A | День = аномалия или тренд? | campaign_daily_7d.tsv | Агрегировать по дате, CPA дня vs медиана. >1.5x = аномалия |
| B | Какие РК сожрали больше всего? | campaigns.json | Ранжировать по расходу, найти РК с расход>0 и лиды=0 |
| C | Какие группы сливают? | adgroups.json | Группы с расходом > 2000р и 0 лидов |
| D | Мусорный трафик? | sqr.tsv | Нецелевые запросы с кликами = минус-слова |
| E | Что менялось и повлияло? | changes_report.html | Правки за 7д → могли ли увеличить CPA? Особенно: новые группы, новые ключи |
| F | Откуда пришли лиды? | campaigns.json + adgroups.json | Какие РК/группы дали лиды, звонки vs формы |
| G | Устройства провалились? | devices.json | Планшеты/мобайл 0 лидов → корректировка ставок |
| H | **Недавние правки → слив?** | changes_report + данные | Новые группы/ключи за 3 дня → расход без лидов = правки виноваты |
| I | **Какие повторяющиеся токены/связки тянут мусор?** | SQR_TOKEN_PATTERNS.md | вручную выделить повторяющиеся нецелевые слова/связки и решить уровень минуса |
| J | **Площадки РСЯ сливают?** | rsy_placements_7d.tsv | Площадки с расход>500р и 0 конв = запрещённые. Мобильные приложения = запрещать |
| K | **Какие площадки РСЯ конвертируют?** | rsy_placements_7d.tsv | Площадки с конв>0 = НЕ ТРОГАТЬ. Анализ: поиск vs РСЯ по CPA |

---

## Фаза 3. ГЛУБОКИЙ АНАЛИЗ проблемных групп (ОБЯЗАТЕЛЬНО!)

> НИКОГДА не останавливаться на поверхностном "группа X потратила Y без лидов → пауза".
> Пауза = ленивый совет. Нужно понять ПОЧЕМУ не конвертирует и ЧТО КОНКРЕТНО фиксить.

### Сбор данных вглубь (5 параллельных задач)

| # | Что | Как | Выход |
|---|-----|-----|-------|
| 1 | Ключевые слова проблемных групп | curl v501 keywords.get по CampaignIds (max 10) | keywords_CAMP.json |
| 2 | Объявления проблемных групп | curl v501 ads.get по CampaignIds | ads_CAMP.json |
| 3 | Настройки групп (минус-слова, автотаргетинг) | curl v501 adgroups.get | adgroups_CAMP.json |
| 4 | SQR разбивка по AdGroupId | Ручная сортировка существующего sqr.tsv по группам | sqr_by_group.md |
| 5 | Roistat utm_term по кампаниям | roistat_query.sh dimensions=utm_term | keywords_roistat.json |

### Анализ КАЖДОЙ проблемной группы (расход >500р, 0 лидов)

Для каждой группы ответить:

| Вопрос | Что ищем | Действие если проблема |
|--------|----------|----------------------|
| Ключи broad vs phrase? | Широкое = мусор | Сменить на фразовое/точное |
| SQR: % релевантных запросов? | <50% = плохая семантика | Минус-слова + новые ключи |
| Какие минус-слова нужны? | Ручной паттерн-анализ SQR | Конкретный список |
| Текст объявления = ключу? | Мисматч = низкий QS | Переписать Title1/Title2 |
| LP правильный? | href не на тот тип | Сменить href |
| Автотаргетинг? | COMPETITOR/BROADER/ACCESSORY | Отключить конкретные категории |
| Roistat лиды (звонки)? | Reports API=0, Roistat>0 | Не трогать! |

### Выход: НЕ "пауза/мониторинг", а конкретные правки

- Список минус-слов ДЛЯ КАЖДОЙ группы
- Ключи на смену матч-тайпа
- Ключи на удаление (полностью нерелевантные)
- Правки текстов объявлений
- Отключение категорий автотаргетинга
- Корректировки ставок по устройствам

---

## Фаза 3.5. АНАЛИЗ ПЛОЩАДОК РСЯ (ОБЯЗАТЕЛЬНО!)

> РСЯ = отдельный канал со своими проблемами. Главная — мусорные площадки.

### Критерии для запрещения площадок

| Критерий | Порог | Действие |
|----------|-------|----------|
| Расход > 500р, 0 конверсий, > 10 кликов | HIGH confidence | ЗАПРЕТИТЬ |
| Мобильное приложение (com.*, app.*) | Любой | ЗАПРЕТИТЬ (обычно мискликер) |
| CTR > 3% на РСЯ | Любой | ПОДОЗРИТЕЛЬНО (боты/мискликеры) |
| Bounce rate > 80% | HIGH confidence | ЗАПРЕТИТЬ |
| Внутренние площадки Яндекса (zen, dzen) | Расход > 1000р, 0 конв | ЗАПРЕТИТЬ |
| CPA площадки > 2x среднего | HIGH confidence | ЗАПРЕТИТЬ |

### Типичные мусорные площадки (чёрный список)

- Мобильные приложения (com.*, app.*, play.google.*)
- Пиратские сайты (кино, музыка, игры)
- Новостные агрегаторы с низким CTR
- Площадки с аномально высоким CTR (>5% на РСЯ = боты)
- Площадки с 100% bounce rate

### Выход: НЕ "мониторинг", а конкретные правки

- Список площадок на запрещение (с расходом и причиной)
- Список площадок которые КОНВЕРТИРУЮТ (не трогать!)
- Общая оценка: какая доля расхода РСЯ = мусор

---

## Фаза 4. Выводы → `claude/docs/SEARCH_DIAGNOSTIC_YYMMDD.md`

Структура файла:
1. **ФАКТ:** цифры дня vs норма (таблица)
2. **ДИАГНОЗ:** конкретные РК, группы, запросы которые привели к проблеме
3. **ВЛИЯНИЕ ПРАВОК:** повлияли ли недавние изменения (из change_tracker)
4. **РУЧНОЙ ПАТТЕРН-АНАЛИЗ SQR:** повторяющиеся мусорные токены/связки, кандидаты в минус-слова, защищённые целевые токены
5. **ГЛУБОКИЙ АНАЛИЗ ПОИСКА:** по каждой проблемной группе — ключи, SQR, матч-тайпы, тексты, LP, автотаргетинг
6. **АНАЛИЗ ПЛОЩАДОК РСЯ:** мусорные площадки, запрещение, конвертирующие площадки
7. **КОНКРЕТНЫЕ ПРАВКИ:** минус-слова, матч-тайпы, тексты, ставки, запрещённые площадки — с target_id
8. **ПРОГНОЗ:** ожидаемый эффект от рекомендаций в рублях

---

## GOTCHAS (набитые шишки)

| # | Проблема | Решение |
|---|----------|---------|
| 1 | `roistat_query.sh` без +x после клонирования | `chmod +x` перед первым использованием |
| 2 | `~` не раскрывается в background bash | Использовать полный путь к global-skill или заранее сделать `SCRIPT=20 20 12 61 79 80 81 702 33 98 100 204 250 395 398 399 400 701realpath ...)` |
| 3 | `sleep` в конце background команды ломает runner | Не добавлять sleep в background |
| 4 | Roistat `dimensions=["date"]` + filter search → internal_error | Использовать Reports API для daily |
| 5 | Reports API 201/202 = отчёт строится | Retry loop: 5 попыток, sleep 5 |
| 6 | `change_tracker.py` не в scripts/ проекта | Полный путь: `~/.codex/skills/yandex-performance-ops/scripts/` |
| 7 | Roistat order/list "Filter is invalid" | Неясно, API нестабилен. Альтернатива: analytics dimensions |
| 8 | Roistat JSON: dimensions = dict (не list!) | `it['dimensions']['marker_level_3']['value']` |
| 9 | Рост расхода после создания новых групп | ВСЕГДА проверять новые группы в первые 1-3 дня |
| 10 | Временные парсеры начинают подменять ручной анализ | Не писать ad-hoc analysis-код; ограничиться raw-выгрузками и ручными заметками |
| 11 | Рекомендация "пауза" = ленивый говносовет | ВСЕГДА глубокий анализ: ключи, матч-тайп, SQR, АТ, тексты, LP. Конкретные правки |
| 12 | Нет ручного паттерн-анализа SQR | ВСЕГДА вручную выписывать повторяющиеся токены/связки из raw SQR, а не ограничиваться 5-10 примерами |
| 13 | Нет анализа площадок РСЯ | ВСЕГДА собирать площадки через Reports API и анализировать мусорные/конвертирующие |
| 14 | Рекомендации из головы | ИССЛЕДОВАТЬ лучшие практики через веб-поиск ПЕРЕД написанием рекомендаций |
| 15 | Только поиск без РСЯ | Диагностика = ПОИСК + РСЯ. Всегда оба канала! |

---

## ВЕРСИОНИРОВАНИЕ

- v4 (2026-03-05): removed analysis-script guidance; SQR patterns now only through manual review of raw files. Kept full search+RSYA diagnostic scope.
- v3 (2026-02-27): анализ площадок РСЯ (обязательно!), расширен скоуп на поиск+РСЯ, вопросы I/J/K, фаза 3.5 РСЯ, GOTCHAS 12-15, исследование лучших практик перед рекомендациями.
- v2 (2026-02-27): Добавлены GOTCHAS (9 шт), фикс daily через Reports API, фикс change_tracker path, парсинг JSON, вопрос H (влияние правок), предпосылки перед запуском.
- v1 (2026-02-27): Первая версия. 7 сборщиков + 7 вопросов анализа + итоговый файл.
