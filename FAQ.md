# FAQ

## Нужен ли `.env` для первого OAuth запуска?

Нет. Для default path `Direct / Metrika / Audience` ручной `.env` не нужен.

## Когда `.env` всё-таки нужен?

- если хотите переопределить built-in public OAuth profile
- если хотите хранить runtime token variables
- если поднимаете `Wordstat / Search API`

## Почему `Wordstat` не идёт через тот же launcher, что `Direct`?

Потому что это отдельная `Yandex Cloud` auth-модель.

## Что выбрать: marketplace или install script?

- `./.agents/plugins/marketplace.json` = основной repo-local путь для `Codex`
- `install_codex_bundle.sh` = optional personal home-install в `${CODEX_HOME:-~/.codex}/plugins`
- `install_claude_bundle.sh` = optional compatibility copy для `Claude`

## Где оказываются токены после OAuth?

По умолчанию в `./.codex/auth/`.

## `client_id` у вас правда опубликован специально?

Да. В этом bundle `client_id` в `plugins/yandex-direct-for-all/config/yandex_oauth_public_profiles.json` опубликованы намеренно для shared login через approved app.
Это policy именно этого репозитория, а не универсальное правило для любого OAuth-проекта.

Не публикуется только `client_secret`.

## Когда нужен restart Codex?

Обычно после clone/update repo-local plugin, после изменения marketplace/manifest или после `install_codex_bundle.sh`.

## Что считать успешным первым запуском?

1. `validate_bundle.sh` прошёл без ошибок
2. launcher создал `*_oauth_token.json`
3. launcher создал `*_oauth_preflight.json`
4. сервис реально виден в read-only preflight
