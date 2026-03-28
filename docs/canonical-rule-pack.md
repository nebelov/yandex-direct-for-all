# Canonical Rule Pack

Этот документ не вводит новых правил.

Он собирает уже существующий канон из:

- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/SKILL.md`
- `plugins/yandex-direct-for-all/skills/yandex-direct-client-lifecycle/SKILL.md`
- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/references/source_inventory.md`
- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/references/completeness_audit_2026-03-05.md`

## 1. Главная иерархия истины

Порядок источников:

1. `Direct API / Reports API / Wordstat API / Roistat API / Metrika API`
2. локальные raw-файлы, собранные скриптами
3. локальный client overlay
4. локальные client-specific skills/docs
5. markdown-документация и агентские выводы

Если `live-data` конфликтует с локальными доками, приоритет у `live-data`.

## 2. Парсинг и анализ всегда разделены

Это один из главных канонов.

- `ПАРСИНГ != АНАЛИЗ`
- парсинг идёт только через официальные API и скрипты
- анализ делается только вручную по raw-артефактам
- в фазу анализа нельзя домешивать новые API-вызовы как замену уже не собранного raw-слоя
- `collector-plane` обязан быть отдельным слоем
- запрещено смешивать `parsing-stage` и `analysis-stage` внутри одного workflow

Следствие:

- collector не должен выдавать стратегический анализ или verdict
- один executor не должен одновременно парсить, анализировать, валидировать, применять и писать отчёт

## 3. Скрипты разрешены только как механический слой

Скрипты имеют право:

- собирать
- чистить
- нормализовать
- сортировать
- чанковать
- рендерить данные
- строить job-spec
- делать deterministic reduction там, где это явно разрешено каноном

Скрипты не имеют права:

- ставить финальные verdict
- предлагать стоп-слова, стоп-площадки, рост, ставки, новые группы, мониторинг
- решать `target / non-target` вместо ручного построчного анализа
- повышать generated-layer до статуса `ready_now`

Отдельно зафиксировано:

- analysis-скрипты для классификации ключей, фраз, минус-слов и масок запрещены
- анализ `Wordstat`, `SQR`, `Roistat`, `SERP/footprint/competitor pages` делается вручную по raw-слою

## 4. Ручной сбор не является нормой

Upstream и research-слой не должен собираться вручную по одной фразе.

Default path:

1. job-spec
2. batch collector script
3. raw artifacts
4. ручной analysis

Это отдельно зафиксировано для:

- competitor research
- `organic SERP`
- `ad SERP`
- page capture
- sitemap discovery
- `Wordstat`

Допустим только ранний `scout/reconnaissance`, чтобы проверить рынок или collector pipeline.
Но полный collection должен строиться только после вручную подтверждённого keyword set и через batch collectors.

## 5. Wordstat: только официальный и только collector workflow

Канон `Wordstat` жёсткий:

- запрещён веб-скрейп `Wordstat`
- запрещены one-off `wordstat_*` вызовы вместо wave-collector workflow
- парсинг вручную по одной маске через tool/MCP-вызовы запрещён
- `numPhrases=2000` обязателен для полного охвата масок
- до парсинга обязателен `product map`
- сначала `structure -> masks -> mask review -> parsing by script -> full raw success -> analysis`
- нельзя перепрыгивать из масок сразу в анализ
- сезонность и география тоже собираются тем же collector path, а не ручными вызовами

## 6. Competitor / SERP research тоже строится только через raw pipeline

Канон для конкурентов:

- сначала raw register, без оценок и выводов
- сначала `Wordstat` и ручная валидация keyword set
- затем `keyword x geo` matrix
- затем `organic/ad SERP` batch collection
- затем domain shortlist
- затем `page-capture/sitemap` follow-up jobs, тоже скриптами
- если batch большой, разбивка на чанки и merge тоже должны делаться скриптами

`Firecrawl` допустим только после discovery, не как замена discovery/serp parsing.

## 7. Manual gate обязателен

Если ручной verdict по строке не внесён:

- machine shortlist нельзя маскировать под готовый apply-pack
- верхний слой обязан показывать `manual gate incomplete` / `manual_verdict_required`

Для search negatives и SQR отдельно зафиксировано:

- сначала полный ручной row-by-row review
- потом decision table/report
- потом reduction-layer до production-safe stop-words или safe masks
- потом отдельный validation-layer
- и только потом pre-apply pack

Если user явно разрешил swarm:

- swarm допустим только как ускорение ручного verdict-слоя
- coverage каждого `candidate_id` обязателен
- merge в `manual_decisions.tsv` допустим только после validation pass

## 8. Live apply без отчёта не считается завершённой работой

После любого live apply нужен human-readable report:

- что было
- что сделал
- что стало

Минимум:

- затронутые сущности
- сколько реально изменено
- пути к `apply_results / readback / summary`
- почему именно эти правки были выбраны

Если live-правки уже сделаны, а отчёта нет, работа считается незавершённой.

## 9. OAuth и Direct UI-path запрещён

Для `Yandex Direct` нельзя использовать UI-логин/пароль как рабочий operational path.

Допустимо только:

- официальный `OAuth token`
- официальный API-path с token file
- другой явно подтверждённый пользователем официальный machine path

Если токен есть, но он привязан не к тем активам клиента, считать его рабочим нельзя.
Новый `oauth_token.json` сначала обязан пройти live-preflight:

- `Wordstat userInfo`
- `Direct campaigns.get`
- `Metrika management`

## 10. Audience-слой тоже живёт по отдельным правилам

- `Audience token` нельзя молча переиспользовать для `Direct/Metrika`
- `TEN-620`, `минус-аудитории`, `мусорные лиды`, `Яндекс Аудитории` сначала идут в специализированный collector
- raw `segment_id` нельзя использовать как `Direct GoalID/ExternalId`
- перед apply нужен `GetRetargetingGoals`
- если segment есть в `Audience API`, но отсутствует в `GetRetargetingGoals`, apply блокируется

## 11. Source-skills выше локальной интерпретации

Lifecycle skill не имеет права подменять source-skills.

Если есть конфликт:

- `yandex-wordstat`
- `direct-search-semantics`
- `yandex-direct`

побеждает source-skill.

Global `yandex-performance-ops` тоже не имеет права перепридумывать этот слой мимо исходных source-skills.

## 12. Что отсюда следует для новых plugin/MCP/skill пакетов

Если вы собираете новый bundle для агентной работы, он должен:

- тащить реальные scripts и canonical references
- не подменять batch collectors ручным сбором
- не зашивать analysis в scripts
- не вводить новые правила, если они уже есть в глобальном skill-каноне
- сохранять separation между `collector`, `analysis`, `validation`, `apply`, `report`
