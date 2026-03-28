# AI Onboarding

Этот файл нужен для нового ИИ-оператора, который впервые открыл репозиторий.

## 1. Сначала понять, что здесь есть

Главная точка входа:

- `README.md`
- `QUICKSTART.md`
- `FAQ.md`

Критичные docs:

- `docs/operator-auth-launchers.md`
- `docs/oauth-and-app-setup.md`
- `docs/auth-model-matrix.md`
- `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`

## 2. Не перепутать auth-модели

- `Direct / Metrika / Audience` идут через reusable OAuth app + per-user consent.
- `Wordstat / Search API` идут через отдельный `Yandex Cloud` auth path.
- Нельзя описывать `Wordstat` так, будто он работает через тот же launcher, что `Direct`.

## 3. Минимальный безопасный порядок действий

1. Запустить `bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh`.
2. Если задача про `Direct / Metrika / Audience`, использовать `start_yandex_user_auth.sh`.
3. Если задача про `Wordstat / Search API`, сначала читать `docs/oauth-and-app-setup.md`.
4. Перед любым collector-run свериться с `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`.
5. Не считать auth завершённым, пока не появился `*_oauth_preflight.json`.

## 4. 5-minute first run

1. Проверить prerequisites: `python3`, `node`, `rsync`, `requests`, браузер.
2. Из `<repo-root>` прогнать `validate_bundle.sh`.
3. Получить один read-only token через `start_yandex_user_auth.sh`.
4. Убедиться, что `*_oauth_preflight.json` создан и показывает реальный доступ.

## 5. Безопасный первый запуск

Сначала проверить bundle:

```bash
bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh
```

Если нужен user token:

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct
```

После успешной авторизации launcher сам должен создать:

- `./.codex/auth/<service>_oauth_token.json`
- `./.codex/auth/<service>_oauth.env`
- `./.codex/auth/<service>_oauth_preflight.json`

Если preflight не появился или упал, auth-flow нельзя считать завершённым.

## 6. Что нельзя делать

- Не использовать UI-логин/пароль Яндекса как operational path для `Direct`.
- Не смешивать токены разных пользователей.
- Не коммитить `.env`, `oauth*.json`, token-файлы, client-specific overlays и credentials docs.
- Не обещать, что `Audience` token автоматически заменяет `Direct` token.

## 7. Где лежат data-collection scripts

Top-level launchers:

- `plugins/yandex-direct-for-all/scripts/collect_wordstat_wave.sh`
- `plugins/yandex-direct-for-all/scripts/collect_direct_bundle.sh`
- `plugins/yandex-direct-for-all/scripts/collect_direct_sqr.sh`
- `plugins/yandex-direct-for-all/scripts/collect_metrika.sh`
- `plugins/yandex-direct-for-all/scripts/collect_roistat.sh`

Полный inventory:

- `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`

## 8. Если публикуешь или меняешь bundle

Перед push:

```bash
bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh
```

И проверь, что в diff нет:

- `AGENTS.md`
- `задача.md`
- `.codex/`
- `.claude/`
- `.env`
- `oauth*.json`
- `*token*.json`

## 9. Если нужен правильный skill

Стартовые skill-entrypoints:

- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/SKILL.md`
- `plugins/yandex-direct-for-all/skills/yandex-direct-client-lifecycle/SKILL.md`
- `plugins/yandex-direct-for-all/skills/roistat-reports-api/SKILL.md`
