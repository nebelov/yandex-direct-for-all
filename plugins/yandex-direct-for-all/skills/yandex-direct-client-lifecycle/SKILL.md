---
name: yandex-direct-client-lifecycle
description: "Use when onboarding a new or stale Yandex Direct client, building a reusable client knowledge base, collecting company/site/social/analytics context, gathering raw competitor and keyword data, preparing a human-reviewable research pack and client proposal, or handing the account into yandex-performance-ops for build and long-term management."
---

# Yandex Direct Client Lifecycle

## Overview

Этот навык закрывает upstream-слой работы с клиентом по Яндекс.Директ: `intake -> база знаний -> raw research -> analysis -> human review -> client proposal -> handoff`.

Новый skill не имеет права заменять канонические source-skills по `Wordstat`, `Direct semantics` и `Direct`.

Перед любым sematics/Direct блоком считай обязательным upstream contract:

1. `references/source_skill_contract.md`

Используй его, когда задача не про “ежедневно вести уже живой кабинет”, а про:

1. онбординг нового клиента;
2. re-onboarding старого/непонятного клиента;
3. сбор первой базы знаний о компании, продуктах, сайтах, соцсетях, кейсах и аналитике;
4. подготовку research-backed плана и предложения для клиента;
5. сбор и систематизацию всех данных перед build/launch;
6. передачу клиента в downstream-слой `yandex-performance-ops`.

Товарный или фидовый слой не предлагай по умолчанию.
Включать его в клиентский пакет можно только по прямому запросу пользователя или после отдельного решения, что такой слой действительно нужен.

Не используй этот навык как замену `yandex-performance-ops` для day-2/day-N операций. Когда контекст собран, структура согласована и начинается build/live/monitoring, переключайся на `yandex-performance-ops`.

Если работа идет по уже начатому клиенту, сначала искать готовые артефакты исследования, generated tables, готовую клиентскую страницу и deploy bundle, а не поднимать новый слой поверх старого.
Перед таким продолжением сначала опираться на:

1. `~/.codex/skills/yandex-performance-ops/references/future_session_start_checklist.md`

## Quick Start

Если в проекте еще нет локального клиентского слоя, сначала создай его:

```bash
python3 ~/.codex/skills/yandex-direct-client-lifecycle/scripts/scaffold_client_lifecycle.py \
  --output-dir . \
  --client-key acme \
  --client-name "Acme"
```

Скрипт создает локальный стартовый пакет:

1. `./client-kb.md`
2. `./source-register.tsv`
3. `./competitor-raw-register.tsv`
4. `./human-review.tsv`
5. `./proposal-pack.md`
6. `./product-map.md`
7. `./routing-map.tsv`
8. `./research/analysis/company-footprint.md`
9. `./research/analysis/landing-inventory.md`
10. `./research/analysis/research-backlog.md`
11. `./research/analysis/единая-карта-конкурентов.md`
12. `./research/analysis/пакет-структуры-будущего-кабинета.md`
13. `./research/analysis/пакет-текстов-и-офферов.md`
14. `./research/analysis/готовые-тексты-для-директа.tsv`
15. `./research/jobs/organic-serp-jobs.tsv`
16. `./research/jobs/ad-serp-jobs.tsv`
17. `./research/jobs/page-capture-jobs.tsv`
18. `./research/jobs/sitemap-jobs.tsv`
19. `./research/jobs/search-api.env.example`
20. `./.codex/yandex-performance-client.json`
21. `./research/semantics/__CLIENT_KEY__/00-product-map.md`
22. `./research/semantics/__CLIENT_KEY__/01-masks-wave1.tsv`

Для batch-сбора используй канонические job-spec -> collector paths:

```bash
python3 ~/.codex/skills/yandex-direct-client-lifecycle/scripts/yandex_search_batch.py \
  --jobs-file ./research/jobs/organic-serp-jobs.tsv \
  --output-dir ./research/raw/competitor-search/wave-01
```

```bash
python3 ~/.codex/skills/yandex-direct-client-lifecycle/scripts/yandex_search_ads_batch.py \
  --jobs-file ./research/jobs/ad-serp-jobs.tsv \
  --output-dir ./research/raw/ad-serp/wave-01
```

Если cloud-auth еще не подключен, сначала прогони только request preview:

```bash
python3 ~/.codex/skills/yandex-direct-client-lifecycle/scripts/yandex_search_batch.py \
  --jobs-file ./research/jobs/organic-serp-jobs.tsv \
  --output-dir ./research/raw/competitor-search/wave-01-preview \
  --dry-run
```

```bash
python3 ~/.codex/skills/yandex-direct-client-lifecycle/scripts/firecrawl_scrape.py \
  --jobs-file ./research/jobs/page-capture-jobs.tsv \
  --output-dir ./research/raw/competitors/firecrawl/wave-01 \
  --proxy enhanced \
  --location-country RU
```

```bash
python3 ~/.codex/skills/yandex-direct-client-lifecycle/scripts/sitemap_probe_batch.py \
  --jobs-file ./research/jobs/sitemap-jobs.tsv \
  --output-dir ./research/raw/competitors/sitemaps/wave-01
```

Пакет текстов после ручной подготовки нужно прогонять через reusable validator:

```bash
python3 ~/.codex/skills/yandex-performance-ops/scripts/validate_direct_copy_pack.py \
  --input-tsv ./research/analysis/готовые-тексты-для-директа.tsv \
  --output-dir ./research/analysis/валидация-текстов-директ
```

Если клиентский отчет выводится в веб-страницу, в него нужно включать отдельный слой `спрос из Wordstat`:

1. широкие корневые маски отдельно;
2. точные базовые маски отдельно;
3. без суммирования вложенных запросов и без складывания масок между собой.
4. использовать готовый renderer `~/.codex/skills/yandex-performance-ops/scripts/render_wordstat_mask_demand.py`, а не дописывать цифры вручную.
5. сезонность и географию считать обязательными частями этого же блока.
6. использовать готовые renderer paths:
   - `~/.codex/skills/yandex-performance-ops/scripts/render_wordstat_seasonality.py`
   - `~/.codex/skills/yandex-performance-ops/scripts/render_wordstat_geo.py`
7. raw для сезонности и географии собирать тем же wave-collector path, а не отдельными ручными `wordstat_*` вызовами:
   - `~/.codex/skills/yandex-performance-ops/scripts/wordstat_collect_wave.js --dynamics true --regions-report true --regions-tree true`

```bash
python3 ~/.codex/skills/yandex-direct-client-lifecycle/scripts/build_followup_jobs_from_serp.py \
  --serp-results ./research/raw/competitor-search/wave-01/serp_results.tsv \
  --page-capture-out ./research/jobs/page-capture-jobs.tsv \
  --sitemap-out ./research/jobs/sitemap-jobs.tsv \
  --exclude-domain yandex.ru \
  --exclude-domain ya.ru
```

## Workflow

### 1. Set The Phase

Перед работой явно зафиксируй текущую фазу:

1. `intake`
2. `knowledge-base`
3. `raw-research`
4. `analysis`
5. `proposal`
6. `handoff`
7. `ops`

Если пользователь просит “сделать стратегию / предложение / исследование / онбординг”, почти всегда это фазы `intake -> proposal`.

### 1.1. Re-read Source Skills Before Wordstat/Direct Work

Когда работа доходит до `Wordstat`, `Direct semantics` или `Direct account` слоя, этот skill обязан заново опираться на source-skills, а не на сжатое пересказанное знание.

Обязательные источники:

1. `references/source_skill_contract.md`
2. глобальный `yandex-performance-ops` Wordstat framework
3. канонический `yandex-wordstat` source skill
4. канонический `direct-search-semantics` source skill
5. канонический `yandex-direct` source skill

Если локальный lifecycle workflow конфликтует с source-skill, source-skill побеждает.

### 2. Build The Client Knowledge Base First

До глубокого анализа сначала собери и оформи клиентский контекст в `client-kb.md`.

Что вносить:

1. компания и бизнес-модель;
2. продукты / услуги / направления;
3. гео;
4. цикл сделки;
5. lead path;
6. сайт, owned company pages, лендинги, соцсети, каталоги, карты, отзывы, кейсы;
7. ограничения и red lines;
8. подтвержденные данные и неизвестные.

Используй шаблон:

1. `templates/client-kb-template.md`

Все источники фиксируй отдельно в `source-register.tsv`, чтобы будущие чаты не переизобретали контекст.

Используй шаблон:

1. `templates/source-register-template.tsv`

Параллельно веди отдельный операционный слой `company footprint`, если уже есть owned pages, реквизиты, адреса, логистика и внешние registry-сигналы.

Используй:

1. `templates/company-footprint-template.md`

### 3. Separate Collection From Analysis

Парсинг и сбор данных не смешивай с выводами.

Сначала собирай raw-слой, потом анализируй.

Для upstream research ручные одиночные прогоны не считать нормой. Default path теперь:

1. job-spec `.tsv`;
2. batch collector script;
3. raw `json/xml/html/md/tsv`;
4. только потом markdown analysis.

Это особенно важно для:

1. конкурентов;
2. объявлений конкурентов;
3. Wordstat;
4. старых рекламных кабинетов;
5. аналитических выгрузок;
6. креативных ассетов.

Для конкурентов сначала заполняй `competitor-raw-register.tsv`, без оценок и “кто лучше”.

Используй шаблон:

1. `templates/competitor-raw-register-template.tsv`

Для competitor research обязательно веди два раздельных raw-слоя:

1. `organic SERP`
2. `ad SERP`

Их нельзя смешивать в один без явного поля `discovery_layer`, потому что это разные поверхности рынка и разные последующие выводы.

Для самого `SERP` действуют отдельные правила:

1. `organic SERP` и `ad SERP` по Яндексу собирай только через официальный путь Яндекса:
   - API;
   - официальный экспорт;
   - подтвержденную выгрузку из интерфейса.
2. Браузерный скрейпинг Яндекс-выдачи не считать допустимым каноническим методом.
3. Не используй `Firecrawl` для discovery, parsing или эмуляции самого SERP.
4. `Firecrawl` разрешен только после discovery, чтобы забирать уже найденные landing pages и публичные страницы.
5. Для поисковых рекламных объявлений Яндекса подтвержден рабочий путь через `Yandex Search API` в `FORMAT_HTML`.
6. Канонический batch collector для этого слоя:
   - `scripts/yandex_search_ads_batch.py`
6.1. Если этот path уже был локализован глобально, не искать его заново по remote-машинам. Сначала проверять:
   - локальный private credentials file вне git
   - `../yandex-performance-ops/references/yandex_cloud_search_handoffs.md`
7. Этот слой не закрывает автоматически `РСЯ`; для `РСЯ` нужен отдельный подтвержденный официальный источник.
8. Если в поисковых рекламных объявлениях всплывают спорные хосты, их нельзя механически записывать в карту конкурентов.
   Сначала нужно посмотреть фактический `source_url` и отнести сущность к одному из слоев:
   - прямой конкурент;
   - товарная витрина;
   - теххост / квиз;
   - шум и самореклама поисковой системы.

Для `Wordstat` действуют еще более жесткие правила:

1. только `masks-file -> wave collector`, не one-off запросы по ходу работы;
2. сначала `00-product-map.md`, потом `01-masks-wave1.tsv`;
3. `Wave 1` должен включать `L1` root-маски; где возможно это однословные маски;
4. для текущего канона `Wave 1` в основном однословный; `Wave 2` добавляет двухсловные product/object masks;
5. после составления `Wave 1` обязателен `mask review` по двум плоскостям:
   - web/source synonyms review;
   - Wordstat associations review;
6. `Wave 1` и `Wave 2` обязательны;
7. до анализа обязателен completeness gate:
   - все raw-файлы на месте;
   - пустые/ошибочные raw обнаружены;
   - новые маски из associations вынесены в gap/wave2 backlog;
8. lifecycle skill не имеет права подменять этот процесс “ручным набором запросов”.

Для полноты competitor collection действуют отдельные правила очередности:

1. ранний competitor scout до семантики допустим только как `reconnaissance`, чтобы понять рынок и проверить collectors;
2. исчерпывающий competitor raw collection нельзя считать начатым, пока не собран и вручную не валидирован keyword set;
3. после валидации семантики `organic SERP` и `ad SERP` jobs должны генерироваться от матрицы `validated keyword x geo`, а не от произвольного shortlist запросов;
4. для каждой валидированной фразы нужно сохранять `query`, `region`, `timestamp`, `domain`, `landing`, `discovery_layer`, а затем запускать `sitemap` и `page-capture` уже по найденным доменам;
4.1. после `organic SERP` wave домены и landing URLs должны переводиться в `page-capture-jobs.tsv` и `sitemap-jobs.tsv` только через reusable builder script, а не вручную;
4.2. перед follow-up сбором обязателен отдельный шаг shortlist:
   - сводка повторяемости доменов по подтвержденной выдаче;
   - ручное утверждение укороченного списка сильных доменов;
   - ориентир по умолчанию = `топ-15` доменов, которые повторяются по большинству целевых фраз;
   - страницы статей, новостей, справочников, PDF и прочие некоммерческие URL должны исключаться механическими паттернами до `page-capture` и `sitemap`;
5. pre-semantics waves нельзя выдавать человеку как полный competitor set: это только разведка и proof-of-pipeline.

Канонический batch collector для Yandex-native organic SERP:

1. `scripts/yandex_search_batch.py`
2. job template: `templates/serp-job-template.tsv`

Канонический batch collector для поисковых рекламных объявлений Яндекса:

1. `scripts/yandex_search_ads_batch.py`
2. вход = `research/jobs/ad-serp-jobs.tsv`
3. источник = `Yandex Search API` в `FORMAT_HTML`

Канонический рендер доменного shortlist из поисковой выдачи:

1. `scripts/build_domain_shortlist_from_serp.py`
2. использовать после подтвержденной поисковой волны и до follow-up jobs
3. скрипт только сортирует и рендерит повторяемость доменов, не принимает решения

Канонический batch collector для second-pass page capture:

1. `scripts/firecrawl_scrape.py --jobs-file ...`
2. job template: `templates/page-capture-job-template.tsv`

Канонический batch collector для sitewide discovery по конкуренту:

1. `scripts/sitemap_probe_batch.py`
2. job template: `templates/sitemap-job-template.tsv`

Канонический utility для batch chunking:

1. `scripts/split_tsv_batch.py`
2. использовать когда один большой jobs-файл нужно распараллелить на несколько workers

Канонический utility для merge chunked sitemap waves:

1. `scripts/merge_sitemap_batch_outputs.py`
2. использовать после параллельного `sitemap_probe_batch.py`, чтобы собрать единый `sitemap_manifest.tsv` и `candidate_urls.tsv`

Канонические render utilities для ручного review:

1. `scripts/render_serp_wave.py`
2. `scripts/render_ad_serp_wave.py`
3. `scripts/render_sitemap_candidates.py`
4. `scripts/render_page_capture_inventory.py`
4. эти scripts только сортируют, чанкуют и рендерят verified raw для ручного анализа

Канонический builder между `organic SERP` raw и follow-up collectors:

1. `scripts/build_followup_jobs_from_serp.py`
2. вход: `serp_results.tsv`
3. выход:
   - `page-capture-jobs.tsv`
   - `sitemap-jobs.tsv`
4. script не анализирует конкурентов и не фильтрует таргетность по смыслу; он только преобразует raw SERP в batch job-spec для следующего шага.
3. использовать после domain discovery, чтобы не ограничиваться одним landing URL

Все operator-facing и client-facing отчеты, summary и proposal-паки писать на русском языке.
По возможности не использовать англицизмы, если есть ясный русский эквивалент.

Если доступен `FIRECRAWL_API_KEY`, предпочитай `scripts/firecrawl_scrape.py` для raw-сбора публичных страниц, особенно когда:

1. страница сильно JS-driven;
2. `curl` возвращает anti-bot, `403`, security-check или обрезанный HTML;
3. нужен нормализованный markdown/html/json-слой для дальнейшего ручного анализа.

`Firecrawl` не заменяет source register и raw register: он только улучшает слой извлечения.

Если second-pass нужен для антиботных доменов:

1. сначала обычный `Firecrawl`;
2. затем retry с `proxy=enhanced`;
3. при geo-sensitive сайте можно передать `location.country` и `location.languages`;
4. но даже в таком режиме это page-capture tool, а не SERP tool.

Перед любым analysis-stage bundle нужно закрыть отдельной машинной проверкой:

1. `scripts/verify_research_bundle.py`
2. verifier только проверяет полноту и presence raw/job artifacts
3. verifier не делает выводов и не решает достаточно ли хороши сами данные по смыслу

### 4. Cover The Full Research Surface

Не ограничивайся одной плоскостью.

Покрытие должно пройти по блокам из:

1. `references/coverage-checklist.md`

Минимальный каркас:

1. клиент и его компания;
2. продукты и офферы;
3. сайт и посадочные;
4. аналитика и lead routing;
5. конкуренты;
6. объявления конкурентов;
7. спрос / маски / ключи / минус-фразы;
8. структура кампаний;
9. тексты объявлений, изображения, расширения;
10. план, гипотезы, аналитические требования, договорный контур, build/handoff.

После закрытия ручного analysis-stage этот skill обязан выдавать еще три обязательных операторских артефакта, не откладывая их "на потом":

1. `research/analysis/единая-карта-конкурентов.md`
   Нормализованная ручная карта: органика + поисковые рекламные объявления + тип игрока + сегменты.
2. `research/analysis/пакет-структуры-будущего-кабинета.md`
   Каркас будущего кабинета: кампании, группы, посадочные, география, без запуска.
3. `research/analysis/пакет-текстов-и-офферов.md`
   Полный пакет текстов, быстрых ссылок и уточнений для ручной сборки.
4. `research/analysis/готовые-тексты-для-директа.tsv`
   Машинно-читаемый пакет текстов для проверки длин и дальнейшей сборки.

### 5. Use Other Skills Deliberately

Связки по умолчанию:

1. `playwright`
   Используй для реального браузерного сбора объявлений конкурентов, выдачи и страниц.
   Если relevant competitor pages отдают `403`, anti-bot или `DDoS` challenge при `curl`, сразу планируй second-pass через браузер вместо ложного ощущения, что raw уже собран.
2. `Firecrawl script`
   Если есть `FIRECRAWL_API_KEY`, сначала попробуй `scripts/firecrawl_scrape.py` для публичных страниц и лендингов конкурентов.
   Это preferred path для page parsing, когда нужна чистая markdown/html/json-выгрузка без ручной браузерной возни.
   Не используй его для SERP collection: поиск выдачи и ads discovery идут только через Яндекс-native paths.
   Для batch-режима используй `--jobs-file` вместо перечисления URL вручную.
3. `yandex-performance-ops`
   Используй для:
   - официального `Wordstat`;
   - client overlay;
   - Direct/Metrika/Roistat raw-сборов;
   - структуры, validation, build, launch, ongoing ops.
   Делай это по канону source-skills, а не по самодельным shortcut-правилам lifecycle skill.
4. `russian-b2b-service-contracts`
   Используй, когда нужно собрать:
   - договор;
   - ТЗ;
   - акт;
   - клиентский комплект документов.

### 6. Human Review Is A First-Class Artifact

Не делай процесс завязанным на “копировать в чат” и “смотреть скриншоты”.

Веди отдельный human-review queue:

1. `human-review.tsv`

Там должны жить:

1. что именно нужно утвердить;
2. из какого артефакта это пришло;
3. какой тип решения нужен;
4. текущий статус;
5. комментарий человека.

Используй шаблон:

1. `templates/human-review-template.tsv`

### 7. Proposal Pack Must Be Client-Facing

Когда делаешь предложение клиенту, собери не просто заметки, а читаемый пакет:

1. что исследовано;
2. какие факты подтверждены;
3. на какие источники опираемся;
4. какие гипотезы и почему;
5. какую структуру кабинета предлагаем;
6. что нужно по аналитике;
7. что будет в first wave;
8. что не обещаем;
9. что нужно согласовать.

Используй:

1. `templates/proposal-pack-template.md`

Но proposal не заменяет три операторских пакета выше.
Сначала вручную собрать:

1. единую карту конкурентов;
2. пакет структуры будущего кабинета;
3. пакет текстов и офферов;

и только потом вносить их выводы в client-facing документы.

Если полезно, добавляй эмуляцию реального вида объявлений в Поиске и РСЯ, но только как наглядный mockup, а не как обещание финального live-вида.

Если собираешь клиентскую веб-страницу или веб-презентацию, действуют обязательные правила:

1. это клиентский артефакт, а не operator-dump;
2. не тянуть в страницу ссылки на исходные markdown/tsv/json документы и не показывать внутренние названия файлов;
3. не оставлять внутренние подписи вроде `главный документ`, `клиентская версия`, `полный комплект`, `сводка исследования`;
4. не дублировать один и тот же смысл в нескольких секциях;
5. длинный контент раскладывать по вкладкам, переключателям и отдельным блокам, а не сваливать в бесконечную ленту;
6. объявления на такой странице показывать в виде, максимально близком к реальному интерфейсу Яндекс.Директа, а не в стиле общей декоративной темы страницы;
7. текст страницы писать в прямом обращении к клиенту, без рассказа о клиенте в третьем лице там, где это читается как внутренняя заметка.
8. если страницу нужно отдать клиенту по ссылке, собирать отдельный deploy-пакет, а не публиковать рабочую папку целиком;
9. для защищенной ссылки использовать отдельную однофайловую сборку через `scripts/build_secure_client_report.py`, затем проверять live-страницу на десктопе и мобиле уже после выката;
10. не полагаться на внешние markdown/tsv/json в клиентском деплое: нужные данные должны быть встроены в итоговый пакет.

### 8. Handoff Cleanly

Когда `proposal` и `human review` завершены:

1. обнови `client-kb.md`;
2. обнови `source-register.tsv`;
3. обнови `product-map.md`;
4. обнови `routing-map.tsv`;
5. обнови `./.codex/yandex-performance-client.json`;
6. зафиксируй, что готово для downstream-этапа.

Дальше:

1. build / validation / live apply / daily ops веди через `yandex-performance-ops`;
2. юридический пакет веди через `russian-b2b-service-contracts`.

Границы handoff описаны в:

1. `references/handoff-map.md`

## Guardrails

1. База знаний клиента создается раньше глубокого анализа.
2. На старте задавай только блокирующие вопросы, а не длинный generic-бриф.
3. `ПАРСИНГ != АНАЛИЗ`.
4. Конкурентов сначала собирай как raw-слой, потом анализируй.
5. Для `Wordstat` действуют правила downstream skill:
   - только официальный путь;
   - `numPhrases=2000`;
   - не резать low volume;
   - собирать хвост до `1 показа/месяц`, если задача про новую семантику.
6. Не обещай клиенту лиды и продажи без доказательной базы.
7. Перед build/live этапами нужен human approval.
8. После каждого крупного цикла обновляй KB, source register и proposal artifacts, чтобы следующие чаты работали от канонического слоя, а не “из головы”.

## References

Читай по необходимости:

1. `references/artifact-contract.md`
   Что именно должно лежать в локальном проекте и когда это обновлять.
2. `references/coverage-checklist.md`
   Как не пропустить важные плоскости исследования и подготовки.
3. `references/handoff-map.md`
   Где заканчивается этот skill и начинается `yandex-performance-ops`.

## Templates

Переиспользуемые шаблоны:

1. `templates/client-kb-template.md`
2. `templates/source-register-template.tsv`
3. `templates/company-footprint-template.md`
4. `templates/competitor-raw-register-template.tsv`
5. `templates/human-review-template.tsv`
6. `templates/proposal-pack-template.md`
7. `templates/product-map-template.md`
8. `templates/routing-map-template.tsv`
9. `templates/landing-inventory-template.md`
10. `templates/research-backlog-template.md`
11. `templates/yandex-performance-client-template.json`
12. `templates/unified-competitor-map-template.md`
13. `templates/future-cabinet-structure-template.md`
14. `templates/offers-pack-template.md`

## Trigger Examples

Этот skill должен триггериться на запросы типа:

1. “Новый клиент по Директ, собери мне онбординг и базу знаний.”
2. “Подготовь исследование и предложение клиенту по Яндекс.Директ.”
3. “Собери все данные по компании, конкурентам и спросу, потом упакуй план.”
4. “Нужно системно заводить клиентов в полный цикл от онбординга до handoff.”
