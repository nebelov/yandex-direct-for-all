# Quickstart

Этот файл нужен, если другой ИИ или оператор хочет быстро стартовать без чтения всего репозитория.

## 0. Path Contract

- `<repo-root>` = корень этого репозитория
- `<plugin-root>` = `<repo-root>/plugins/yandex-direct-for-all`
- Основной путь для `Codex` = repo-local plugin через `<repo-root>/.agents/plugins/marketplace.json`
- `install_codex_bundle.sh` = optional personal home-install в `${CODEX_HOME:-~/.codex}/plugins`

## 1. Prerequisites

- `python3` (`validated on 3.11`)
- `node` (`validated on Node 20`)
- `rsync`
- Python package `requests`
- браузер для OAuth
- для `Direct` default path: свободный `localhost:8080`

## 2. Выбрать режим подключения

- `Codex repo-local, recommended`:
  - ничего не копировать;
  - открыть repo так, чтобы `Codex` видел `<repo-root>/.agents/plugins/marketplace.json`;
  - после clone/update repo перезапустить `Codex`.
- `Codex personal home-install, optional`:

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_codex_bundle.sh
```

  - повторный запуск refresh-ит managed install in-place;
  - `~/.agents/plugins/marketplace.json` переписывается на фактический installed plugin path.

- `Claude compatibility copy, optional`:

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_claude_bundle.sh
```

## 3. Проверить bundle

```bash
bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh
```

Если validator не прошёл, дальше идти нельзя.

## 4. Выбрать правильную auth-модель

- `Direct / Metrika / Audience` -> reusable OAuth app + per-user consent
- `Wordstat / Search API` -> отдельный `Yandex Cloud` auth path

Нельзя запускать `Wordstat` так, будто он авторизуется через тот же launcher, что и `Direct`.

## 5. Получить user token для Direct

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct
```

Ожидаемый результат:

- `./.codex/auth/direct_oauth_token.json`
- `./.codex/auth/direct_oauth.env`
- `./.codex/auth/direct_oauth_preflight.json`

Если `*_preflight.json` не появился, auth-flow нельзя считать завершённым.

`Direct` default path использует `http://localhost:8080/callback` и может открыть браузер.

## 6. Получить user token для Metrika или Audience

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service metrika
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service audience
```

## 7. Найти collector-скрипты

Быстрый список:

```bash
bash ./plugins/yandex-direct-for-all/scripts/list_data_collectors.sh
```

Полный inventory:

- `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`

## 8. Основные launchers

- `plugins/yandex-direct-for-all/scripts/collect_wordstat_wave.sh`
- `plugins/yandex-direct-for-all/scripts/collect_direct_bundle.sh`
- `plugins/yandex-direct-for-all/scripts/collect_direct_sqr.sh`
- `plugins/yandex-direct-for-all/scripts/collect_metrika.sh`
- `plugins/yandex-direct-for-all/scripts/collect_roistat.sh`

## 9. Где смотреть skills

- Repo-local `Codex`, основной путь:
  - `plugins/yandex-direct-for-all/skills/README.md`
  - `plugins/yandex-direct-for-all/docs/skill-index.md`
  - `plugins/yandex-direct-for-all/skills/yandex-performance-ops/SKILL.md`
  - `plugins/yandex-direct-for-all/skills/yandex-direct-client-lifecycle/SKILL.md`
  - `plugins/yandex-direct-for-all/skills/roistat-reports-api/SKILL.md`
- Home-install, optional fallback:
  - `~/.codex/plugins/yandex-direct-for-all/skills/yandex-performance-ops/SKILL.md`
  - `~/.codex/plugins/yandex-direct-for-all/skills/yandex-direct-client-lifecycle/SKILL.md`
  - `~/.codex/plugins/yandex-direct-for-all/skills/roistat-reports-api/SKILL.md`

## 10. Чего не делать

- Не коммитить `.env`, `oauth*.json`, `*token*.json`, `.codex/`, `.claude/`.
- Не обещать, что `Wordstat` работает через `Direct` launcher.
- Не смешивать токены разных пользователей и разных сервисов.
- Не путать repo-local plugin и optional home-install.

## 11. Что считать успехом первого запуска

- bundle validator прошёл
- выбранный режим подключения понятен и не смешан с другим
- нужный auth launcher создал token-файл
- нужный auth launcher создал preflight-файл
- сервис реально виден в read-only preflight
