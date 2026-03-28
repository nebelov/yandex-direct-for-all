# OAuth, Access, and Reuse Model

Короткий practical verdict для bundle:

- `Direct` -> reusable approved app + per-user consent
- `Metrika` -> reusable app + per-user consent
- `Audience` -> reusable app + per-user consent
- `Wordstat` -> отдельный `Yandex Cloud / Search API` path

## Что теперь canonical в этом bundle

Больше не считать обязательным шагом ручное заполнение `client_id/client_secret` ради получения первого user token.

Default auth path теперь такой:

1. launcher берёт public app-profile из `../config/yandex_oauth_public_profiles.json`
2. генерирует `PKCE`
3. получает `code`
4. обменивает его на token
5. сохраняет token/env/preflight artifacts
6. сразу делает read-only post-auth preflight

## Service defaults

- `direct` -> `legacy_direct` -> `local-callback`
- `metrika` -> `master_yandex` -> `manual-code`
- `audience` -> `master_yandex` -> `manual-code`

## Почему это работает без secret в default path

Официальный OAuth for Yandex ID поддерживает `PKCE`.

Если передать:

- `code_challenge` при запросе confirmation code
- `code_verifier` при обмене code на token

то `client_secret` для этого сценария не обязателен.

Именно так работает текущий launcher.

## Что создаётся

После успешной авторизации:

- `./.codex/auth/<service>_oauth_token.json`
- `./.codex/auth/<service>_oauth.env`
- `./.codex/auth/<service>_oauth_preflight.json`

Если запуск шёл в two-step mode:

- `./.codex/auth/<service>_oauth_pending.json`

## Почему preflight обязателен

Valid token != доступ к нужному кабинету/счётчику/сегменту.

Поэтому bundle сразу проверяет:

- `Direct` -> `campaigns.get`
- `Metrika` -> counters / counter_info / goals
- `Audience` -> segments + optional `Direct Live4`

## Где ещё нужен env

`../examples/yandex.env.example` остаётся как optional layer:

- свой кастомный app
- legacy flow с `client_secret`
- runtime env для уже полученного token
- cloud auth для `Wordstat / Search API`

## See also

- `docs/operator-auth-launchers.md`
- `docs/auth-model-matrix.md`
- `../config/yandex_oauth_public_profiles.json`
