---
name: roistat-reports-api
description: Use when the task is to inspect existing Roistat saved reports through API, assemble a new report from scratch via analytics/data, fetch attribution slices, split new vs repeated leads/sales/clients, validate report logic against orders, or export a reproducible report pack without using the UI.
---

# Roistat Reports API

## Overview

Навык для работы с отчетами `Roistat` только через API.
Он нужен, когда надо:

- снять список существующих отчетов в кабинете;
- собрать новый отчет с нуля, не редактируя старый;
- выгрузить отчет по атрибуциям, новым/повторным заявкам и продажам;
- проверить, не врет ли отчет из-за поздних CRM-событий;
- сохранить reproducible report-pack локально в файлы.

## Когда использовать

Используй этот навык, если задача относится к одному из сценариев:

- пользователь просит работать с отчетами `Roistat` без UI;
- нужно понять, какие отчеты уже есть в кабинете и как они устроены;
- нужно собрать новый отчет через `analytics/data`;
- нужно сравнить `default / first_click / last_click / last_paid_click`;
- нужно выделить `leads`, `first_leads`, `repeated_leads`, `sales`, `new_sales`, `repeated_sales`, `clients`, `paid_clients`;
- нужно выгрузить Excel-отчет через API;
- нужно сверить отчет с сырыми сделками через `integration/order/list`.

## Правила

- Никакого UI.
- Не редактируй существующие отчеты, если пользователь явно не попросил это отдельно.
- `POST /project/analytics/reports` используй как discovery-layer для чтения уже сохраненных отчетов.
- Публично документированный канон для нового отчета: `POST /project/analytics/data` и при необходимости `POST /project/analytics/data/export/excel`.
- Для saved report внутри кабинета используй только подтвержденный контракт:
  `POST /project/analytics/report` с телом `{"report": {...}}`.
- Создание нового saved report: передай `report` без `id`.
- Обновление уже созданного saved report: передай тот же объект с `report.id`.
- Этот write-контракт подтвержден live на проекте `192319` 2026-03-16. Не подменяй им существующие отчеты: создавай новый объект с уникальным `title`, затем отдельно обновляй только его.
- Для проверки “реально ли заявка относится к визиту источника в этом окне” не ограничивайся агрегатом: добавляй сверку через `integration/order/list` c `extend=["visit"]`.
- Для директорских отчетов все кастомные столбцы называй человеко-понятно на русском и в каждом заголовке явно указывай источник логики:
  `Roistat, системный расчет`, `CRM, ручная отметка менеджера`, `Диагностика расхождений`.
- Не смешивай в одном заголовке технический жаргон и английские сокращения, если это можно объяснить простым русским названием.
- Если в отчете есть кастомные обертки над built-in метриками, убирай старые дубль-колонки без source-label, чтобы в интерфейсе не было смысловых повторов.
- Если пользователь просит “сделать колонки шире”, сначала проверь live saved-report JSON.
  На проекте `192319` 2026-03-16 в saved-report контракте не подтвердились поля ширины колонок или table layout.
  Пока не найден отдельный hidden-contract, не обещай менять ширину колонок через API.
- Для lead-слоя всегда отдельно проверяй late CRM events: часть поздних неоплаченных сделок может быть привязана к более старым визитам и тогда `integration/order/list` даст больше строк, чем `analytics/data`. Это не обязательно ошибка формулы; это может быть особенность движка Roistat.
- Если пользователь просит “разные атрибуции рядом”, не считай это выполненным, пока не проверишь live-значения через `analytics/data`.
  На проекте `192319` 2026-03-16 подтвержден кейс, где saved-report принимал разные `attributionModel`, но значения в результатах оставались одинаковыми.
  В таком случае:
  - не оставляй ложные атрибуционные дубли в боевом отчете;
  - честно фиксируй, что текущий тип отчета не дает рабочей развилки по атрибуции для этой задачи;
  - не маскируй проблему переименованием колонок.
- Для built-in метрик мультиканального отчета на проекте `192319` 2026-03-16 saved-report контракт подтвержден как
  `{"id","attributionModel","isAvailable"}` без отдельного поля `title` или `label` на уровне колонки.
  Следствие:
  - через API нельзя честно переписать названия самих built-in атрибуционных колонок;
  - если пользователю нужно объяснение моделей, давай легенду в названии отчета, в сопроводительном тексте или в отдельном поясняющем артефакте;
  - не обещай “подписать каждую модель в названии столбца”, пока не найдешь live-контракт с editable label.
- Не пытайся обойти это ограничение кастомными обертками над built-in метриками без live-проверки.
  На проекте `192319` 2026-03-16 `analytics/data` подтвердил, что кастомные формульные обертки вроде `{leads}` и `{first_leads}` игнорировали `attribution` и возвращали значения стандартной модели.
  Значит такие обертки годятся для human-readable названий только в одноатрибуционных отчетах, но не для честной мультиатрибуционной таблицы.
- Не обещай, что перенос в “Мультиканальную аналитику” автоматически исправит атрибуцию.
  Сначала сними live saved-report мультиканального отчета и сравни контракт/результаты.
  На проекте `192319` 2026-03-16 мультиканальный отчет тоже имел `date_filter_type=lead` и не давал автоматического решения проблемы “старый визит -> поздняя CRM-реактивация”.
  Для проверки продаж, которые попали в выбранный период по оплате, но были созданы раньше, отдельный safe-path на этом проекте:
  - создать отдельный saved report в мультиканальной аналитике с `date_filter_type=payment`;
  - на проекте `192319` такой отчет был создан 2026-03-16 как `id=38`.
- Для любых кастомных метрик с `%` в названии или долевой формулой проверяй `type`.
  На проекте `192319` 2026-03-16 кастомные метрики `80` и `81` были созданы как `integer`, хотя по смыслу были процентами.
  Канон:
  - найди все метрики с `%`, `доля`, `конверсия` в названии или с долевой формулой;
  - сверь `type` через `metrics/custom/list` и при необходимости исправь на `percent`;
  - затем перечитай тип назад из API, а не полагайся на успешный update-ответ.

## 3 уровня валидации

Для любого боевого saved report по `Roistat` используй именно трехуровневую валидацию:

1. Формула.
   Кастомная метрика должна существовать в проекте, читаться через API и иметь ожидаемый `title / type / formula`.
2. Агрегат.
   `analytics/data` должен вернуть значения по нужному окну и срезам (`search / context` или глубже), а итоговые цифры должны быть сохранены в артефакт.
3. Сырые сделки.
   `integration/order/list` c `extend=["visit"]` должен подтвердить продажи и выручку напрямую, а по lead-слою нужно отдельно фиксировать, где raw-выборка расходится с `analytics/data` из-за старых визитов, reactivate-сценариев или других особенностей привязки.
4. Формат и интерфейс.
   Для боевого директорского отчета отдельно проверь:
   - что процентные столбцы имеют `type=percent`;
   - что названия колонок не содержат ложных маркеров вроде “пользовательский”, если это мешает чтению;
   - что одинаковые по названию колонки не скрывают разные модели или, наоборот, ложные дубли.

## Truth Layer и автоматизация

Если задача не просто “показать стандартные лиды/продажи”, а построить честный директорский слой `реально новый / реально старый / продажа из старого визита`, используй такой канон:

1. Не считай ручные поля CRM (`new_lead`, `Повторный клиент`) истиной.
   Они могут быть полезны только как диагностические сигналы.
2. Сначала собери `identity coverage audit`:
   - `client_id`
   - `visit_id`
   - `roistat`
   - `_ym_uid`
   - `ym_client_id`
   - `Телефон`
   - `Доп. Телефон`
   - `ФИО`
   - любые другие контактные поля проекта
3. Построй factual-history слой:
   - `had_prior_lead`
   - `had_prior_paid_sale`
   - `had_prior_paid_sale_gt_2000`
   - `visit_older_than_30d / 90d / 180d`
4. Отдельно разделяй:
   - `Roistat, системный расчет`
   - `CRM, ручная отметка менеджера`
   - `Факт по истории`
   - `Атрибуция старого визита`

### Что можно автоматизировать в самом Roistat

Публично документировано:

- список ручных показателей: `POST /project/analytics/metrics/custom/manual/list`
- заливка значений ручного показателя: `POST /project/analytics/metrics/custom/manual/value/add`
- просмотр значений: `POST /project/analytics/metrics/custom/manual/value/list`
- удаление значения: `POST /project/analytics/metrics/custom/manual/value/delete`

Это означает:

- Да, director truth-layer можно автоматически обновлять в `Roistat`.
- Но считать его должен внешний job, а не сам движок `Roistat`.
- Job должен по расписанию:
  1. вытянуть сырые сделки и историю;
  2. посчитать factual-метрики;
  3. залить агрегированные значения в ручные показатели;
  4. при необходимости поверх ручных показателей использовать формульные показатели через `manual_custom_N`.

### Ограничения автоматизации

- Публичная документация API описывает заливку значений ручных показателей, но не описывает явный API-метод создания самих ручных показателей.
- Live подтвержден hidden contract:
  - `POST /project/analytics/metrics/custom/manual/create`
  - `POST /project/analytics/metrics/custom/manual/update`
  - `POST /project/analytics/metrics/custom/manual/delete`
- Для формульных показателей подтверждены:
  - `POST /project/analytics/metrics/custom/create`
  - `POST /project/analytics/metrics/custom/update`
  - `POST /project/analytics/metrics/custom/delete`
- `manual/value/add` не допускает пересекающиеся периоды для одного `source` и одного manual metric.
- Поэтому перед перезаписью rolling-window нужно сначала удалить старое значение за этот же период.

### Важное ограничение по уровням источника

Ручное значение в `Roistat` привязывается к конкретному `source` и уровню источника.
Оно не распределяется автоматически на дочерние кампании.

Следствие:

- если нужен только верхний слой, можно писать значения на `direct1_search` и `direct1_context`;
- если нужна truth-аналитика по кампаниям, внешний job обязан считать и писать значения по каждому `source` отдельно.
- Live отдельно подтверждено:
  - `manual/value/add` принимает не только `marker_level_1` или `marker_level_3`;
  - можно писать значение по полному `visit.source.system_name`, то есть вплоть до `marker_level_6`;
  - после этого `analytics/data` корректно разворачивает его по `marker_level_4..6`.
- Для источников без полноценного `visit.source` можно писать и в `marker_level_1`-источники вроде `telegram` или `nosource-crm`, если они существуют в аналитическом дереве проекта.

### Практическая стратегия записи

- Если нужен именно rolling-отчет “последние 30 дней”, fastest safe path: писать одно значение на весь 30-дневный период по каждому `source`.
- Если нужен корректный пересчет для произвольных дат внутри кабинета, truth-layer нужно писать по дням.
- Суточная запись правильнее, но заметно тяжелее по API и быстрее упирается в `request_limit_error`.
- Для large-scale sync по всем каналам и полной глубине закладывай:
  - rate-limit backoff;
  - ограничение числа параллельных запросов;
  - фоновый job, а не интерактивный ручной прогон.

## Workflow

### 1. Подтверди канон в документации

Перед live API-вызовами проверь официальные материалы:

- `API/methods/analytics`
- `features/Analitika_i_otchety/Analitika/Postroenie_otchetov`
- `features/Analitika_i_otchety/Polzovatelskie_pokazateli`
- `features/Analitika_i_otchety/Specialnye_otchety/Novie_klienti`

Краткий навигатор лежит в:

- [references/reporting-endpoints.md](/Users/vitalijtravin/.codex/skills/roistat-reports-api/references/reporting-endpoints.md)

### 2. Сними discovery-layer кабинета

Сначала вытащи:

- список сохраненных отчетов: `POST /project/analytics/reports`
- список кастомных метрик: `GET /project/analytics/metrics/custom/list`
- список доступных CRM-полей заказа: `POST /project/analytics/order-custom-fields`
- список моделей атрибуции: `POST /project/analytics/attribution-models`

Это не “новый отчет”, а слой для понимания, какие метрики и формулы реально доступны в проекте.

Важно:

- `order-custom-fields` подтверждает, какие поля реально приходят в проект из CRM, но сам по себе не отдает безопасный маппинг в `order_field_N`;
- в боевой отчет добавляй только те `order_field_N`, чей маппинг доказан live:
  - либо уже существующей формулой проекта;
  - либо сверкой с raw `integration/order/list`;
- если название поля CRM известно, а номер `order_field_N` не доказан, не добавляй такую метрику в директорский отчет “на глаз”.

### 3. Собери новый отчет с нуля

Новый отчет строится отдельной JSON-спекой, а не правкой существующего отчета.

Базовые измерения по умолчанию:

- `marker_level_1`
- `marker_level_2`
- `marker_level_3`

Это safe default для боевого проекта: полный срез до `marker_level_6` часто упирается в `Too many data`.
Глубокий drill-down по `marker_level_4..6` делай отдельной второй волной после успешного кампанийного среза.

Базовые метрики по умолчанию:

- `marketing_cost`
- `visits`
- `unique_visits`
- `leads`
- `first_leads`
- `repeated_leads`
- `sales`
- `new_sales`
- `repeated_sales`
- `revenue`
- `first_sales_revenue`
- `repeated_sales_revenue`
- `clients`
- `paid_clients`
- `cpl`
- `cpo`
- `cac`
- `ltv`
- `conversion_visits_to_leads`
- `conversion_leads_to_sales`

Если в проекте есть полезные кастомные метрики, добавляй их явно как `custom_<id>`.

### 4. Сними атрибуционные срезы

Если пользователь просит “все атрибуции”, не делай один мутный агрегат.
Добавляй отдельные значения для нужных моделей:

- `default`
- `first_click`
- `last_click`
- `last_paid_click`

Обычно имеет смысл дублировать по моделям как минимум:

- `leads`
- `sales`
- `revenue`
- `clients`
- `paid_clients`

### 5. Проверь агрегат сделками

Для проверки проблем типа “в отчете в этом месяце всплывают старые лиды” собери отдельный audit-слой:

- `POST /project/integration/order/list`
- фильтр по `creation_date`
- `extend=["visit"]`

Дальше проверь:

- дата создания сделки;
- `roistat` визита;
- источник/маркеры визита;
- статус;
- выручку;
- повторность, если она кодируется полем/тегом/кастомной метрикой проекта.

### 6. При необходимости сохрани отчет в кабинет

После того как report-pack локально собран и проверен, saved report в кабинете сохраняется отдельным шагом:

- загрузи `new_report_spec.json`;
- проверь, что `title` уникален;
- отправь `POST /project/analytics/report` с телом `{"report": <spec>}`;
- затем перечитай `POST /project/analytics/reports` и убедись, что появился новый `id`, а fingerprint остальных отчетов не изменился.

Для update уже созданного отчета:

- перечитай сохраненный объект;
- меняй только `title` и `settings` нужного `id`;
- повторно отправляй `POST /project/analytics/report` c `{"report": <saved_report_with_id>}`.

### 7. Сохрани report-pack

Итоговый pack должен содержать:

- snapshot сохраненных отчетов;
- snapshot кастомных метрик;
- новую JSON-спеку отчета;
- request body для `analytics/data`;
- raw JSON ответа;
- flat TSV;
- Excel-экспорт через API;
- order-audit raw + flat TSV;
- короткое `summary.md`.

## Скрипты

### `scripts/build_roistat_report_pack.py`

Главный reusable path.
Он:

- читает saved reports и кастомные метрики;
- собирает новую report-spec с нуля;
- вызывает `analytics/data`;
- сохраняет TSV и raw JSON;
- по желанию тянет `export/excel`;
- снимает order audit через `integration/order/list`.

Минимальный запуск:

```bash
python3 ~/.codex/skills/roistat-reports-api/scripts/build_roistat_report_pack.py \
  --project 192319 \
  --api-key-env ROISTAT_API_KEY \
  --from 2026-03-01 \
  --to 2026-03-16 \
  --report-name "API | Direct attribution MTD | new vs repeat" \
  --marker-level-1 direct1 \
  --marker-level-1 direct9 \
  --marker-level-1 direct10 \
  --marker-level-1 direct11 \
  --marker-level-1 direct13 \
  --output-dir ./output/roistat_reports/direct-attribution-mtd-20260316
```

### `scripts/save_roistat_report.py`

Reusable скрипт для create/update saved report внутри кабинета через API.
Он автоматически нормализует saved-report фильтры под формат кабинета:

- для `operator="in"` не оставляет строковые массивы;
- для source-like значений подтягивает `label` через `project/analytics/source/list`;
- добавляет безопасные служебные поля, которые ожидаются живыми отчетами.

Пример create из уже собранной спеки:

```bash
python3 ~/.codex/skills/roistat-reports-api/scripts/save_roistat_report.py \
  --project 192319 \
  --api-key-env ROISTAT_API_KEY \
  --report-spec ./output/roistat_reports/direct-attribution-mtd-20260316-v3/new_report_spec.json
```

Пример update уже созданного отчета:

```bash
python3 ~/.codex/skills/roistat-reports-api/scripts/save_roistat_report.py \
  --project 192319 \
  --api-key-env ROISTAT_API_KEY \
  --report-spec ./output/roistat_reports/direct-attribution-mtd-20260316-v3/new_report_spec.json \
  --report-id 36 \
  --title "API | Директ | Атрибуция MTD | новые/повторные"
```

### Что скрипты не делают

- не меняет существующие отчеты;
- не трогает настройки проекта;
- не пишет новые кастомные метрики.

## Выбор стратегии

Если задача пользователя звучит как:

- “пойми, почему основной отчет врет”,
- “собери новый отчет по новым/повторным лидам”,
- “дай выгрузку по атрибуциям”,

то канонический путь такой:

1. discovery saved reports;
2. новая report-spec с нуля;
3. `analytics/data`;
4. `export/excel`;
5. `integration/order/list` для верификации.

Если пользователь отдельно требует “сохранить новый отчет прямо в Roistat”, сначала исследуй write-endpoint и зафиксируй контракт в skill/reference, а уже потом выполняй запись.
