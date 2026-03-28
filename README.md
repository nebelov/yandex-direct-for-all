# Yandex Direct For All

GitHub-ready набор для агентной работы с `Yandex Direct`, `Wordstat`, `Metrika`, `Roistat`, `Yandex Search API` и связанными сценариями `Yandex Audiences`.
Сборка в этой папке перепроверена против официальных страниц OpenAI `Codex Plugins` на `2026-03-28` и оформлена как repo-local plugin + marketplace для установки в Codex.

Репозиторий собран как стартовая база для:
- `Codex`
- `Claude Code`
- `Gemini CLI`
- любых других агентных CLI, которым нужен локальный набор skills, MCP-серверов, шаблонов и скриптов

Если репозиторий впервые открывает другой ИИ, начинать лучше с:

- `AI_ONBOARDING.md`
- `QUICKSTART.md`
- `README.md`
- `docs/operator-auth-launchers.md`
- `docs/oauth-and-app-setup.md`

## Start Here

- Новый ИИ-оператор: `AI_ONBOARDING.md`
- Самый короткий безопасный запуск: `QUICKSTART.md`
- Развилка install-paths без путаницы: `docs/install-paths.md`
- Типовые вопросы первого запуска: `FAQ.md`
- Auth-модели без путаницы: `docs/auth-model-matrix.md`
- Карта bundled skills: `docs/skill-index.md`
- Operator OAuth launchers: `docs/operator-auth-launchers.md`
- Полный inventory collector-скриптов: `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`

## Path Contract

- `<repo-root>` = корень этого репозитория.
- `<plugin-root>` = `<repo-root>/plugins/yandex-direct-for-all`.
- Для `Codex` основной путь = repo-local plugin через `./.agents/plugins/marketplace.json`.
- `install_codex_bundle.sh` = optional personal home-install в `${CODEX_HOME:-~/.codex}/plugins` + `~/.agents/plugins/marketplace.json`; он не нужен, если вы работаете прямо из этого repo.

## Prerequisites

- `python3` (`validated on 3.11`)
- `node` и `npm` (`validated on Node 20`)
- `rsync`
- Python package `requests`
- браузер для OAuth
- для `Direct` default path: свободный `localhost:8080`

## Режимы запуска

| Что хотите сделать | Откуда запускать | Как сделать | Нужен restart |
|---|---|---|---|
| Проверить bundle | `<repo-root>` | `bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh` | нет |
| Подключить repo-local plugin в `Codex` | `<repo-root>` | Ничего не копировать: использовать `./.agents/plugins/marketplace.json`, затем перезапустить `Codex` после clone/update | обычно да |
| Сделать personal home-install в `Codex` | `<repo-root>` | `bash ./plugins/yandex-direct-for-all/scripts/install_codex_bundle.sh` | да |
| Сделать home-install в `Claude` | `<repo-root>` | `bash ./plugins/yandex-direct-for-all/scripts/install_claude_bundle.sh` | да |
| Получить token для `Direct` | `<repo-root>` | `bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct` | нет |
| Получить token для `Metrika/Audience` | `<repo-root>` | `bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service metrika` | нет |
| Работать только внутри plugin-root | `<plugin-root>` | `bash ./scripts/validate_bundle.sh` | нет |

## Что внутри

- `plugins/yandex-direct-for-all/skills/yandex-performance-ops` — основной канонический ops-skill по `Direct/Wordstat/Metrika/Roistat`.
- `plugins/yandex-direct-for-all/skills/yandex-direct-client-lifecycle` — upstream-слой: intake, research, proposal, handoff.
- `plugins/yandex-direct-for-all/skills/roistat-reports-api` — отдельный API-слой по `Roistat`.
- `plugins/yandex-direct-for-all/skills/amocrm-api-control` — companion-skill для `amoCRM -> Yandex Audiences / VK Ads`.
- `plugins/yandex-direct-for-all/mcp/yandex-direct` — локальный MCP-сервер для `Yandex Direct`.
- `plugins/yandex-direct-for-all/mcp/yandex-search` — локальный MCP-сервер для `Yandex Search API`.
- `plugins/yandex-direct-for-all/mcp/yandex-wordstat` — локальный MCP-сервер для `Wordstat`.
- `plugins/yandex-direct-for-all/scripts/*.sh` — быстрые launcher-скрипты для collector/parsing paths.

## Где именно skills

Bundled skills лежат прямо в plugin-root:

- `plugins/yandex-direct-for-all/skills/yandex-performance-ops`
- `plugins/yandex-direct-for-all/skills/yandex-direct-client-lifecycle`
- `plugins/yandex-direct-for-all/skills/roistat-reports-api`
- `plugins/yandex-direct-for-all/skills/amocrm-api-control`

Skill index:

- `docs/skill-index.md`
- `plugins/yandex-direct-for-all/skills/README.md`
- `plugins/yandex-direct-for-all/docs/skill-index.md`

## Где именно скрипты парсинга данных

Я исправил этот слой.

Теперь в bundle есть:

- полный inventory: `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`
- быстрый список: `plugins/yandex-direct-for-all/scripts/list_data_collectors.sh`
- top-level launchers для основных collectors:
  - `collect_wordstat_wave.sh`
  - `collect_direct_bundle.sh`
  - `collect_direct_sqr.sh`
  - `collect_metrika.sh`
  - `collect_roistat.sh`
  - `collect_organic_serp.sh`
  - `collect_ad_serp.sh`
  - `collect_page_capture.sh`
  - `collect_sitemap.sh`

Канонические скрипты при этом остались на своих исходных путях внутри `skills/*/scripts/`.

## Быстрый старт

Все команды в этом разделе запускать из `<repo-root>`.

### 1. Repo-local plugin для Codex: рекомендованный путь

- Держать repo как есть, не копируя plugin в home-директории.
- Marketplace entry уже лежит в `./.agents/plugins/marketplace.json` и указывает на `./plugins/yandex-direct-for-all`.
- После clone/update repo перезапустить `Codex`, чтобы он перечитал marketplace.

### 2. Personal home-install для Codex: optional fallback

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_codex_bundle.sh
```

Этот скрипт создаёт или обновляет managed personal copy в `${CODEX_HOME:-~/.codex}/plugins/yandex-direct-for-all` и переписывает `~/.agents/plugins/marketplace.json` на фактический installed plugin path.

### 3. Установка для Claude Code: optional compatibility path

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_claude_bundle.sh
```

`install_claude_bundle.sh` сначала refresh-ит personal Codex home-install, затем зеркалит bundle в `${CLAUDE_HOME:-~/.claude}`.

### 4. Проверка сборки

```bash
bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh
```

### 5. Zero-manual OAuth для Direct / Metrika / Audience

Для `Direct / Metrika / Audience` bundle теперь даёт готовый operator-flow:

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct
```

По умолчанию bundle сам:

- берёт public app-profile из `plugins/yandex-direct-for-all/config/yandex_oauth_public_profiles.json`
- генерирует `PKCE` verifier/challenge
- не требует ручного заполнения `client_id/client_secret`
- после сохранения token сразу запускает read-only preflight

На выходе будут:

- `./.codex/auth/direct_oauth_token.json`
- `./.codex/auth/direct_oauth.env`
- `./.codex/auth/direct_oauth_preflight.json`

Сервисные default-path такие:

- `direct` -> `local-callback`
- `metrika` -> `manual-code` / `verification_code`
- `audience` -> `manual-code` / `verification_code`

Runtime-важно:

- `direct` по умолчанию слушает `http://localhost:8080/callback`
- launcher может открыть браузер автоматически
- если local callback неудобен, используйте two-step path через `--print-only --no-browser`

Если нужен именно явный two-step `confirmation-code` flow:

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service metrika --print-only --no-browser
bash ./plugins/yandex-direct-for-all/scripts/exchange_yandex_user_code.sh --service metrika --code <confirmation-code>
```

Подробно:

- `docs/operator-auth-launchers.md`
- `plugins/yandex-direct-for-all/docs/operator-auth-launchers.md`

### 5.1. Что реально обязательно по env

`examples/yandex.env.example` больше не является обязательным шагом для получения user token в `Direct / Metrika / Audience`.

Матрица:

- `Direct / Metrika / Audience`, default launcher path -> обязательных env нет
- `Direct` runtime без launcher -> обычно `YD_TOKEN` и `YD_CLIENT_LOGIN`
- `Wordstat` -> `YANDEX_WORDSTAT_TOKEN` и `YANDEX_WORDSTAT_CLIENT_PATH`
- `Yandex Search API` -> `YANDEX_SEARCH_API_KEY` и `YANDEX_SEARCH_FOLDER_ID`

Env-файл нужен только если вы хотите:

- переопределить built-in public profile своим app
- задать runtime env для уже полученных token
- настроить отдельный `Wordstat / Search API` cloud layer

### 6. Проверка структуры Codex plugin

Изучить собранный manifest и plugin notes:

- `plugins/yandex-direct-for-all/.codex-plugin/plugin.json`
- `plugins/yandex-direct-for-all/docs/codex-plugin-build-notes.md`

## Режимы авторизации

Старый текст здесь был слишком грубым. Правильная модель теперь разделена по сервисам.

### Reusable app + per-user consent

Это корректный путь для:

- `Yandex Direct`
- `Yandex Metrika`
- `Yandex Audience`

Смысл:

1. приложение зарегистрировано вами один раз;
2. для `Direct` доступ к API одобрен один раз на приложение;
3. другой пользователь логинится своим аккаунтом на странице `Yandex OAuth`;
4. подтверждает доступ приложению;
5. агент получает токен именно этого пользователя.

### Отдельный cloud auth model

Это current official path для:

- `Wordstat`
- `Yandex Search API`

Там нельзя обещать тот же самый flow `открыли consent page -> пользователь залогинился -> всё готово`.

Там важны:

- `Yandex Cloud`
- `folder`
- `role`
- `IAM token` или `API key`

Подробно:

- `docs/oauth-and-app-setup.md`
- `docs/auth-model-matrix.md`

### Два операционных сценария

1. `Ваше приложение`: вы храните свой `Client ID / Client Secret`, выдаёте токены клиентам и работаете как оператор.
2. `Собственное приложение пользователя`: человек регистрирует свой `Yandex OAuth` app там, где это нужно, и поднимает свой cloud setup там, где reusable app path не подходит.

Подробно:
- `docs/oauth-and-app-setup.md`
- `docs/auth-model-matrix.md`
- `docs/operator-auth-launchers.md`
- `plugins/yandex-direct-for-all/docs/operator-auth-launchers.md`
- `docs/yandex-audiences.md`

## Как этим пользоваться агенту

### Codex

Repo-local режим для `Codex` считать основным:

1. открыть repo-root так, чтобы `Codex` видел `./.agents/plugins/marketplace.json`
2. читать bundled entrypoints прямо из `<plugin-root>/skills/...`
3. если задача onboarding/research — перейти в `<plugin-root>/skills/yandex-direct-client-lifecycle`
4. если задача по отчётам — использовать `<plugin-root>/skills/roistat-reports-api`
5. если задача про `audiences`/CRM-sync — дочитать `docs/yandex-audiences.md` и при необходимости подключить `<plugin-root>/skills/amocrm-api-control`

Если вы сознательно сделали personal home-install через `install_codex_bundle.sh`, тот же bundle дополнительно доступен в `${CODEX_HOME:-~/.codex}/plugins/yandex-direct-for-all` и зеркалах `skills/...` внутри `${CODEX_HOME:-~/.codex}`.

### Claude Code / Gemini CLI

У этих клиентов нет единого универсального стандарта skill-installation. Поэтому пакет даёт два слоя:

- готовые локальные директории `skills/` и `mcp/`
- install-скрипты под `Codex` и `Claude`

Для `Gemini CLI` безопасный путь такой:

1. клонировать репозиторий
2. использовать этот repo как knowledge base
3. подключать MCP-серверы из `plugins/yandex-direct-for-all/.mcp.json`
4. при необходимости реплицировать `skills/*` в собственную папку навыков/пресетов

## Важные правила

- Для `Yandex Direct` не использовать UI-логин/пароль как operational path.
- Для `Yandex Audiences`, `Direct` и `Metrika` желательно держать раздельные токены.
- Не коммитить `oauth*.json`, `.env`, API keys и client-specific overlays.
- Клиентские правила, board IDs, каталоги товаров и brand-axioms не зашивать обратно в bundle.

## Документы

- `AI_ONBOARDING.md` — короткий безопасный старт для нового ИИ-оператора.
- `QUICKSTART.md` — минимальный deterministic path без лишних развилок.
- `docs/install-paths.md` — чёткая развилка между repo-local Codex plugin, personal Codex install и Claude home-compat.
- `docs/component-inventory.md` — что именно собрано и откуда.
- `docs/canonical-rule-pack.md` — собранный канон правил из реальных глобальных skills.
- `docs/codex-plugin-build-notes.md` — как bundle собран под официальный Codex Plugins contract.
- `docs/auth-model-matrix.md` — какая auth-модель у `Direct`, `Metrika`, `Audience`, `Wordstat`, `Search API`.
- `docs/operator-auth-launchers.md` — практический launcher-path для `Direct/Metrika/Audience`.
- `plugins/yandex-direct-for-all/docs/data-collection-scripts.md` — где лежат все collector/parsing scripts.
- `plugins/yandex-direct-for-all/docs/operator-auth-launchers.md` — как поднять reusable app + per-user consent flow без путаницы с `Wordstat`.
- `docs/rule-source-map.md` — где именно в исходных skills лежат ключевые правила.
- `docs/oauth-and-app-setup.md` — как поднимать auth-path официально.
- `docs/yandex-audiences.md` — отдельные правила по `Yandex Audiences`.
- `docs/skill-index.md` — карта bundled skills и entry points.
- `CONTRIBUTING.md` — что прогонять перед PR/push.
- `SECURITY.md` — как обращаться с секретами и security-репортами.
- `FAQ.md` — быстрые ответы на типовые вопросы первого запуска.
- `LICENSE` — условия использования публичного репозитория.

## Что изменено относительно старого bundle

- plugin-root сделан self-contained: у него есть собственные `README`, `docs/` и `examples/`.
- `apps`-слой убран из manifest, потому что этот пакет распространяет skills + MCP, а не app connector.
- repo marketplace остаётся в `.agents/plugins/marketplace.json`, как рекомендует Codex docs.
