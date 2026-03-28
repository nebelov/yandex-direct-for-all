# Quickstart

Этот файл нужен, если другой ИИ или оператор хочет быстро стартовать без чтения всего репозитория.

Все команды ниже запускать из `<repo-root>`.

`<repo-root>` = корень этого репозитория  
`<plugin-root>` = `./plugins/yandex-direct-for-all`

## 1. Prerequisites

- `python3`
- `node`
- `rsync`
- Python package `requests`
- браузер для OAuth
- для `Direct` default path: свободный `localhost:8080`

## 2. Проверить bundle

```bash
bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh
```

Если validator не прошёл, дальше идти нельзя.

## 3. Выбрать правильную auth-модель

- `Direct / Metrika / Audience` -> reusable OAuth app + per-user consent
- `Wordstat / Search API` -> отдельный `Yandex Cloud` auth path

Нельзя запускать `Wordstat` так, будто он авторизуется через тот же launcher, что и `Direct`.

## 4. Получить user token для Direct

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct
```

Ожидаемый результат:

- `./.codex/auth/direct_oauth_token.json`
- `./.codex/auth/direct_oauth.env`
- `./.codex/auth/direct_oauth_preflight.json`

Если `*_preflight.json` не появился, auth-flow нельзя считать завершённым.

`Direct` default path использует `http://localhost:8080/callback` и может открыть браузер.

## 5. Получить user token для Metrika или Audience

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service metrika
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service audience
```

## 6. Найти collector-скрипты

Быстрый список:

```bash
bash ./plugins/yandex-direct-for-all/scripts/list_data_collectors.sh
```

Полный inventory:

- `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`

## 7. Основные launchers

- `plugins/yandex-direct-for-all/scripts/collect_wordstat_wave.sh`
- `plugins/yandex-direct-for-all/scripts/collect_direct_bundle.sh`
- `plugins/yandex-direct-for-all/scripts/collect_direct_sqr.sh`
- `plugins/yandex-direct-for-all/scripts/collect_metrika.sh`
- `plugins/yandex-direct-for-all/scripts/collect_roistat.sh`

## 8. Для Codex

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_codex_bundle.sh
```

После установки смотреть:

- `~/.codex/skills/yandex-performance-ops/SKILL.md`
- `~/.codex/skills/yandex-direct-client-lifecycle/SKILL.md`
- `~/.codex/skills/roistat-reports-api/SKILL.md`

Если работаете прямо из repo/plugin без home-install, смотреть:

- `plugins/yandex-direct-for-all/skills/README.md`
- `plugins/yandex-direct-for-all/docs/skill-index.md`

## 9. Чего не делать

- Не коммитить `.env`, `oauth*.json`, `*token*.json`, `.codex/`, `.claude/`.
- Не обещать, что `Wordstat` работает через `Direct` launcher.
- Не смешивать токены разных пользователей и разных сервисов.

## 10. Что считать успехом первого запуска

- bundle validator прошёл
- нужный auth launcher создал token-файл
- нужный auth launcher создал preflight-файл
- сервис реально виден в read-only preflight
