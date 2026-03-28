# Future Session Start Checklist

Этот reference нужен, чтобы в новой сессии не перепридумывать уже проверенный путь.

## 1. Сначала проверить, что уже собрано в проекте

Перед новым сбором или анализом сначала искать готовые артефакты:

1. `research/analysis/validated-keyword-matrix.tsv`
2. `research/analysis/wordstat-demand-render/`
3. `research/analysis/wordstat-seasonality-render/`
4. `research/analysis/wordstat-geo-render/`
5. `research/analysis/единая-карта-конкурентов.md`
6. `research/analysis/пакет-структуры-будущего-кабинета.md`
7. `research/analysis/пакет-текстов-и-офферов.md`
8. `research/analysis/готовые-тексты-для-директа.tsv`
9. `client-report-brutalism.html`
10. `output/vercel/.../index.html`

Если это уже есть, не начинать новый цикл с нуля.

## 2. Сначала использовать готовый скрипт, потом писать новый

Проверять и переиспользовать в таком порядке:

1. `wordstat_collect_wave.js`
2. `render_wordstat_wave.py`
3. `render_wordstat_mask_demand.py`
4. `render_wordstat_seasonality.py`
5. `render_wordstat_geo.py`
6. `yandex_search_batch.py`
7. `yandex_search_ads_batch.py`
8. `build_domain_shortlist_from_serp.py`
9. `build_followup_jobs_from_serp.py`
10. `firecrawl_scrape.py`
11. `sitemap_probe_batch.py`
12. `validate_direct_copy_pack.py`
13. `build_secure_client_report.py`

## 2.1. Direct auth path

1. Для `Yandex Direct` UI по логину/паролю запрещён всегда.
2. Не использовать браузер, Playwright или ручной login в кабинет как fallback.
3. До любой Direct-операции сначала определить официальный auth path:
   - `OAuth token`;
   - официальный API token file;
   - другой явно подтвержденный machine path.
4. Если есть только логин/пароль клиента, это blocker, а не рабочий обходной путь.
5. В таком кейсе нельзя переходить к build/apply, пока не получен официальный auth path.
6. Если token file ещё нет, но есть официальный OAuth app path, сначала использовать bundle launcher:
   - `scripts/start_yandex_user_auth.sh` с service-specific default:
     - `direct` -> `local-callback`
     - `metrika/audience` -> `manual-code`
   - `scripts/exchange_yandex_user_code.sh` для обмена confirmation code;
   - built-in public profile + `PKCE` считать default path;
   - `scripts/oauth_get_token.py` с localhost callback оставлять как fallback convenience-path.
7. После callback сохранить новый token file в проект, прогнать post-auth preflight и только потом повторить Direct preflight.

## 2.2. Direct strategy and copy defaults

1. Для `Search` default стратегия = `WB_MAXIMUM_CONVERSION_RATE` с оплатой за клики.
2. Для `Search` default `GoalId` = `13`, если overlay не задаёт другой explicit search goal.
3. Для `Search` в auto strategy нужен явный `BidCeiling`; `null` оставлять нельзя.
4. Если search-кампания переводится с manual strategy на auto strategy, `DailyBudget` нужно сбросить в `null`, а лимит перенести в weekly budget.
5. Для `РСЯ` default стратегия = `PAY_FOR_CONVERSION_MULTIPLE_GOALS`.
6. Для `РСЯ` default optimisation intent = все approved lead goals клиента: звонок / форма / messenger.
7. Для unified `РСЯ` multi-goal path = exact enum `PAY_FOR_CONVERSION_MULTIPLE_GOALS` + nested `PayForConversionMultipleGoals` + полный `PriorityGoals`.
8. В `РСЯ` нельзя молча скатиться в single-goal `PAY_FOR_CONVERSION`, если пользователь просил все lead goals.
9. `WB_MAXIMUM_CLICKS` в `РСЯ` не использовать без явного подтверждения пользователя.
10. В Direct copy слово `WhatsApp` запрещено во всех текстовых полях; использовать нейтральные замены.
11. RSYA-изображения можно брать только с соответствующей landing/page нужного кластера.

## 3. Wordstat

1. `Wave 1` = в основном однословные корни.
2. `Wave 2` = двухсловные базовые маски.
3. Любой новый слой Wordstat сначала собирать каноническим collector-ом:
   - `wordstat_collect_wave.js`
   - для сезонности: `--dynamics true`
   - для географии: `--regions-report true --regions-tree true`
   - прямые разовые вызовы `wordstat_*` инструментов запрещены
4. Для клиентского отчета спрос показывать только как:
   - широкие корневые маски;
   - точные базовые маски.
5. Вложенные запросы не суммировать.
6. Маски между собой не складывать как общий объем рынка.
7. Сезонность и географию не пропускать: это обязательные части клиентского отчета.
8. Default path всегда file-first:
   - `preflight-save`, `collect-wave-save`;
   - потом открывать уже сохранённые `_summary.json`, `_manifest.json`, `.tsv`.
9. Для каждой approved mask собирать full official ceiling:
   - `numPhrases=2000`
   - это `40 страниц`
   - затем лично просматривать каждую строку `topRequests` и `associations`
   - только потом выделять target/stop/new-mask.

## 4. Поисковая выдача Яндекса

1. `organic SERP` и поисковые рекламные объявления Яндекса брать только официальным путем.
2. Не использовать браузерный скрейпинг как канонический источник выдачи.
3. Для поисковых рекламных объявлений использовать `Yandex Search API` path.

## 5. Shared cloud path

Если клиентский cloud path не поднят, сначала проверять bridge-path:

1. `/Users/vitalijtravin/.codex/credentials/yandex-cloud-search-tenevoy.json`
2. `references/yandex_cloud_search_handoffs.md`

## 6. Клиентский веб-отчет

1. Не тянуть на страницу ссылки на внутренние markdown-документы.
2. Нужный контент встраивать прямо в HTML-отчет.
3. Писать на русском без внутренних служебных пометок.
4. Использовать `build_secure_client_report.py` для пароля и однофайловой сборки.
5. Проверять локально, на мобильной ширине `390px` и после деплоя.

## 7. Перед анализом

1. raw уже собран;
2. rendered tables уже собраны;
3. все source paths записаны;
4. анализ не подменяет сбор.

## 8. Перед optimization действующего кабинета

1. Сначала перечислить все активные кампании нужного канала.
2. Если пользователь назвал приоритетные кампании, считать это очередью работ, а не автоматическим сужением scope.
3. Сужать scope до подмножества РК только при явном `только эти` / `остальные не трогаем`.
4. Если пользователь отдельно сказал, что конверсии/лиды/звонки считаются криво, до плана явно зафиксировать новый truth-layer.
5. До первого account-wide плана открыть минимум playbook-и:
   - `01_search_negatives_7d.md`
   - `03_creative_outliers_rotation.md`
   - `06_bids_and_modifiers_review.md`
   - `09_missing_phrases_growth.md`
6. План optimisation действующего search-кабинета без creative lane считать неполным.
   Обязательный минимум:
   - current ads raw;
   - ad-level performance;
   - text outliers;
   - replacement pack;
   - новый copy/test pack.
7. Перед первым ответом определить режим:
   - `review-only`, если пользователь явно просит только план/аудит;
   - `execute`, если пользователь просит оптимизировать/внедрить/исправить.
8. В `execute`-режиме после pre-apply пакета не останавливаться на плане:
   - сделать apply или executable apply-pack;
   - затем read-back и self-check.
9. Если задача про поисковые фразы / SQR / минус-фразы:
   - сначала собрать свежий raw;
   - потом вручную просмотреть каждую строку;
   - verdict хранить в manual-layer;
   - потом сделать reduction до коротких production-safe stop-words / safe-масок;
   - и только потом собирать pre-apply/live pack.
10. Запрещено стартовать SQR-работу с auto-shortlist-а, `safe_ready` или broad stop-word pack.
11. До ручного verdict по строкам нельзя убирать уже добавленные фразы и нельзя лить live-минуса по новым поисковым фразам.
12. Phrase-level evidence нельзя считать production-ready минус-фразой.
   В client report отдельно показывать:
   - найденные проблемные поисковые фразы;
   - реально добавленные stop-words / safe-маски.
