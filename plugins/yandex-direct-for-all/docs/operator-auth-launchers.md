# Operator Auth Launchers

Этот bundle auth-layer покрывает только:

- `Direct`
- `Metrika`
- `Audience`

И не покрывает:

- `Wordstat`
- `Search API`

## Zero-manual default path

Главное правило теперь такое:

- launcher не требует вручную заполнять `client_id/client_secret` ради первого user token
- public app-profiles уже лежат в `../config/yandex_oauth_public_profiles.json`
- default path использует `PKCE`, поэтому `client_secret` для этого сценария не нужен

## Канонические скрипты

- `scripts/start_yandex_user_auth.sh`
- `scripts/start_yandex_user_auth.py`
- `scripts/exchange_yandex_user_code.sh`
- `scripts/preflight_yandex_user_token.py`
- `scripts/render_yandex_token_env.py`

## Service defaults

- `direct` -> `legacy_direct` -> `local-callback`
- `metrika` -> `master_yandex` -> `manual-code`
- `audience` -> `master_yandex` -> `manual-code`

`screen-code` остаётся совместимым alias к `manual-code`, но это уже не главный термин в docs.

## Базовый запуск

Direct:

```bash
bash ./scripts/start_yandex_user_auth.sh --service direct
```

Metrika:

```bash
bash ./scripts/start_yandex_user_auth.sh --service metrika
```

Audience:

```bash
bash ./scripts/start_yandex_user_auth.sh --service audience
```

## Two-step code exchange

Если нужен раздельный `print URL -> потом exchange`:

```bash
bash ./scripts/start_yandex_user_auth.sh \
  --service metrika \
  --print-only \
  --no-browser

bash ./scripts/exchange_yandex_user_code.sh \
  --service metrika \
  --code <confirmation-code>
```

`print-only` теперь сохраняет pending session в:

- `./.codex/auth/<service>_oauth_pending.json`

Так что второй шаг не требует руками передавать `client_id`, `redirect_uri` или `code_verifier`.

## Что создаётся

После успешной авторизации:

- `./.codex/auth/<service>_oauth_token.json`
- `./.codex/auth/<service>_oauth.env`
- `./.codex/auth/<service>_oauth_preflight.json`

Примеры:

- `./.codex/auth/direct_oauth_token.json`
- `./.codex/auth/direct_oauth.env`
- `./.codex/auth/direct_oauth_preflight.json`

## Пост-auth preflight обязателен

Launcher теперь сам запускает `scripts/preflight_yandex_user_token.py`.

Что он проверяет:

- `Direct` -> `campaigns.get`, human-readable названия кампаний, видимость нужного кабинета
- `Metrika` -> список счётчиков, expected `counter_id`, `counter_info`, `goals`
- `Audience` -> список сегментов, expected `segment_name`, optional `Direct Live4` cross-check

Если токен сохранился, но preflight упал, auth-flow нельзя считать завершённым.

## Optional overrides

`examples/yandex.env.example` нужен только как optional override/runtime layer:

- кастомный OAuth app вместо built-in public profile
- legacy path с явным `client_secret`
- нестандартные output paths
- runtime env
- `Wordstat/Search API` cloud auth

## Что нельзя смешивать

- `Wordstat` нельзя описывать как часть этого же launcher-path
- `Audience` token нельзя молча считать заменой `Direct`
- token разных пользователей нельзя смешивать
