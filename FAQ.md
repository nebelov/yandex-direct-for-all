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

- `marketplace.json` нужен для repo-local plugin в Codex
- `install_codex_bundle.sh` и `install_claude_bundle.sh` нужны для копии skill/MCP в home directories

## Где оказываются токены после OAuth?

По умолчанию в `./.codex/auth/`.

## `client_id` у вас правда опубликован специально?

Да. В этом bundle `client_id` в `plugins/yandex-direct-for-all/config/yandex_oauth_public_profiles.json` опубликованы намеренно для shared login через approved app.

Не публикуется только `client_secret`.

## Когда нужен restart Codex?

Обычно после `install_codex_bundle.sh` или после изменения plugin marketplace/manifest.

## Что считать успешным первым запуском?

1. `validate_bundle.sh` прошёл без ошибок
2. launcher создал `*_oauth_token.json`
3. launcher создал `*_oauth_preflight.json`
4. сервис реально виден в read-only preflight
