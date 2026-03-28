# AI Onboarding

Этот файл нужен новому ИИ, который впервые открыл репозиторий и ничего про него не знает.

## 1. Сначала выбрать install path

Главный вопрос первого запуска не про OAuth, а про то, как именно `Codex` должен увидеть plugin.

Читать сначала:
- `docs/install-paths.md`
- `QUICKSTART.md`
- `README.md`

Коротко:
- repo-local `Codex` path = основной и рекомендуемый
- personal `~/.codex` install = optional fallback
- `Claude` home-compat = отдельный optional path

## 2. Не перепутать auth-модели

- `Direct / Metrika / Audience` = reusable OAuth app + per-user consent
- `Wordstat / Search API` = отдельный `Yandex Cloud` auth path

Нельзя запускать `Wordstat` так, будто он авторизуется через тот же launcher, что `Direct`.

## 3. Минимальный безопасный порядок

1. Выбрать install path из `docs/install-paths.md`.
2. Проверить bundle:

```bash
bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh
```

3. Если задача про `Direct / Metrika / Audience`, использовать `start_yandex_user_auth.sh`.
4. Если задача про `Wordstat / Search API`, сначала читать `docs/oauth-and-app-setup.md`.
5. Перед любым collector-run свериться с `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`.
6. Не считать auth завершённым, пока не появился `*_oauth_preflight.json`.

## 4. First run за 5 минут

1. Проверить prerequisites: `python 3.11`, `node 20`, `rsync`, `requests`, браузер.
2. Выбрать install path из `docs/install-paths.md`.
3. Из `<repo-root>` прогнать `validate_bundle.sh`.
4. Получить один read-only token:

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct
```

5. Убедиться, что `*_oauth_preflight.json` создан и показывает реальный доступ.

## 5. Где лежат skills и collectors

Стартовые skill-entrypoints:
- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/SKILL.md`
- `plugins/yandex-direct-for-all/skills/yandex-direct-client-lifecycle/SKILL.md`
- `plugins/yandex-direct-for-all/skills/roistat-reports-api/SKILL.md`
- `plugins/yandex-direct-for-all/docs/skill-index.md`

Collector inventory:
- `plugins/yandex-direct-for-all/docs/data-collection-scripts.md`
- `plugins/yandex-direct-for-all/scripts/list_data_collectors.sh`

## 6. Что нельзя делать

- не начинать с OAuth до выбора install path
- не обещать, что `Wordstat` работает через `Direct` launcher
- не читать bundled skills из `~/.codex/skills/...`, если работаете в repo-local plugin режиме
- не коммитить `.env`, `oauth*.json`, token-файлы и client-specific overlays
