# Yandex Direct For All Plugin

Self-contained plugin-root для `Codex`, который упаковывает reusable workflows по:

- `Yandex Direct`
- `Wordstat`
- `Metrika`
- `Roistat`
- `Yandex Search API`
- `Yandex Audiences` как companion layer

## Path Contract

- `<plugin-root>` = корень этого plugin bundle.
- `<repo-root>` = корень репозитория, где `<plugin-root>` лежит по пути `./plugins/yandex-direct-for-all`.
- Repo-local `Codex` usage = основной путь через `<repo-root>/.agents/plugins/marketplace.json`.
- `bash ./scripts/install_codex_bundle.sh` = optional personal home-install в `${CODEX_HOME:-~/.codex}/plugins/yandex-direct-for-all`.

## Что внутри

- `.codex-plugin/plugin.json` — manifest плагина
- `.mcp.json` — wiring для локальных MCP servers
- `skills/` — канонические reusable skills
- `mcp/` — локальные MCP servers для `Direct`, `Wordstat`, `Yandex Search`
- `scripts/` — install/validate helpers и top-level launchers для data collectors
- `docs/` — self-contained notes по bundle
- `examples/yandex.env.example` — шаблон env-переменных

## Где skills

Skills уже bundled внутри plugin:

- `skills/yandex-performance-ops`
- `skills/yandex-direct-client-lifecycle`
- `skills/roistat-reports-api`
- `skills/amocrm-api-control`

Смотреть:

- `skills/README.md`
- `docs/skill-index.md`

## Prerequisites

- `python3` (`validated on 3.11`)
- `node` (`validated on Node 20`)
- `rsync`
- Python package `requests`
- браузер для OAuth
- для `direct` default path: свободный `localhost:8080`

## Где скрипты парсинга данных

Они есть в bundle в двух формах:

1. канонические глубинные paths внутри `skills/*/scripts/`
2. быстрые top-level launchers в `scripts/`

Главные launchers:

- `scripts/list_data_collectors.sh`
- `scripts/collect_wordstat_wave.sh`
- `scripts/collect_direct_bundle.sh`
- `scripts/collect_direct_sqr.sh`
- `scripts/collect_metrika.sh`
- `scripts/collect_roistat.sh`
- `scripts/collect_organic_serp.sh`
- `scripts/collect_ad_serp.sh`
- `scripts/collect_page_capture.sh`
- `scripts/collect_sitemap.sh`

Полный inventory:

- `docs/data-collection-scripts.md`

## Operator auth launchers

Для reusable app + per-user consent flow добавлены:

- `scripts/start_yandex_user_auth.sh`
- `scripts/start_yandex_user_auth.py`
- `scripts/exchange_yandex_user_code.sh`
- `scripts/render_yandex_token_env.py`

Документация:

- `docs/operator-auth-launchers.md`
- `docs/oauth-and-app-setup.md`
- `docs/auth-model-matrix.md`

Built-in `client_id` в `config/yandex_oauth_public_profiles.json` опубликованы намеренно как policy choice именно этого репозитория для shared login через approved apps. `client_secret` в bundle не публикуется.

## Быстрый старт

Все команды ниже запускать из `<plugin-root>`.

1. Если нужен новый user token для `Direct/Metrika/Audience`, default path такой:

```bash
bash ./scripts/start_yandex_user_auth.sh --service direct
```

Теперь ручное заполнение `client_id/client_secret` не требуется. Launcher сам берёт public app-profile из `config/yandex_oauth_public_profiles.json`, генерирует `PKCE` и после сохранения токена запускает read-only preflight.

Он сам сохранит:

- `./.codex/auth/direct_oauth_token.json`
- `./.codex/auth/direct_oauth.env`
- `./.codex/auth/direct_oauth_preflight.json`

2. Service defaults:

- `direct` -> `local-callback`
- `metrika` -> `manual-code` / `verification_code`
- `audience` -> `manual-code` / `verification_code`

3. Если нужен именно явный two-step `confirmation-code` flow, использовать:

```bash
bash ./scripts/start_yandex_user_auth.sh --service metrika --print-only --no-browser
bash ./scripts/exchange_yandex_user_code.sh --service metrika --code <confirmation-code>
```

4. `examples/yandex.env.example` теперь нужен только как optional override/runtime layer:

- свой кастомный OAuth app вместо built-in public profile
- runtime env для уже полученных token
- `Wordstat/Search API` cloud auth

5. Проверить bundle:

```bash
bash ./scripts/validate_bundle.sh
```

6. Для repo-local использования в Codex ничего копировать не нужно:

- plugin entry уже лежит в `<repo-root>/.agents/plugins/marketplace.json`
- source path там = `./plugins/yandex-direct-for-all`
- после clone/update repo перезапустить `Codex`, чтобы он перечитал marketplace

7. Для personal home-install / Claude compatibility:

```bash
bash ./scripts/install_codex_bundle.sh
bash ./scripts/install_claude_bundle.sh
```

`install_codex_bundle.sh` создаёт или обновляет managed personal home-local plugin в `${CODEX_HOME:-~/.codex}/plugins/yandex-direct-for-all` и обновляет `~/.agents/plugins/marketplace.json` на фактический installed plugin path.
`install_claude_bundle.sh` сначала refresh-ит этот Codex home-install, затем зеркалит bundle в `${CLAUDE_HOME:-~/.claude}/plugins/yandex-direct-for-all`.

## Документы

- `docs/component-inventory.md`
- `docs/codex-plugin-build-notes.md`
- `docs/data-collection-scripts.md`
- `docs/install-paths.md`
- `docs/operator-auth-launchers.md`
- `docs/oauth-and-app-setup.md`
- `docs/auth-model-matrix.md`
- `docs/skill-index.md`

## Важное

- `Metrika` здесь идёт не отдельным MCP-сервером, а через готовые shell-скрипты внутри `skills/yandex-performance-ops/scripts/metrika/`
- built-in public client profiles лежат в `config/yandex_oauth_public_profiles.json`; реальные `client_secret` в bundle не живут
- user/client-specific токены, overlays и артефакты не должны жить внутри bundle
- `Wordstat/Search API` не нужно авторизовать через этот launcher; для них остаётся отдельный cloud setup
