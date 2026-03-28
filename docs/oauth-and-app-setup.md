# OAuth, Access, and Reuse Model

Этот документ отвечает на два вопроса:

1. можно ли использовать уже одобренные приложения для других пользователей
2. как именно этот bundle делает это без ручного заполнения `.env`

## Краткий verdict

На `2026-03-28` для этого bundle:

- `Yandex Direct` -> да, одно approved app можно переиспользовать для многих пользователей
- `Yandex Metrika` -> да
- `Yandex Audience` -> да
- `Wordstat` -> current official path отдельный, через `Yandex Cloud / Search API`

## Что это значит practically

Для `Direct / Metrika / Audience`:

- приложение принадлежит оператору один раз
- пользователь проходит OAuth-consent своим аккаунтом
- токен получается именно user-specific
- один app может обслуживать много пользователей
- токены пользователей нельзя смешивать между собой

## Как это теперь сделано в bundle

Auth-layer больше не построен вокруг требования “сначала руками впиши `client_id/client_secret`”.

Вместо этого bundle делает следующее:

1. берёт public profile из `plugins/yandex-direct-for-all/config/yandex_oauth_public_profiles.json`
2. генерирует `PKCE` verifier/challenge
3. открывает страницу авторизации
4. получает `code`
5. меняет `code` на token без обязательного `client_secret` в default path
6. сохраняет:
   - `./.codex/auth/<service>_oauth_token.json`
   - `./.codex/auth/<service>_oauth.env`
   - `./.codex/auth/<service>_oauth_preflight.json`
7. сразу запускает read-only `preflight_yandex_user_token.py`

## Почему `client_secret` больше не обязателен в default path

Официальный OAuth для Yandex ID поддерживает `PKCE`:

- при запросе confirmation code можно передавать `code_challenge`
- при обмене code на token можно передавать `code_verifier`
- если используется `code_verifier`, secret key передавать не обязательно

Именно это bundle теперь использует как canonical default.

## Service-specific profiles

По состоянию текущего bundle:

- `direct` -> profile `legacy_direct`, redirect `http://localhost:8080/callback`, default mode `local-callback`
- `metrika` -> profile `master_yandex`, redirect `https://oauth.yandex.ru/verification_code`, default mode `manual-code`
- `audience` -> profile `master_yandex`, redirect `https://oauth.yandex.ru/verification_code`, default mode `manual-code`

Эти профили содержат только public `client_id` и redirect metadata.

## Post-auth preflight обязателен

Технически живой token ещё не означает, что он видит нужные активы клиента.

Поэтому после авторизации bundle сразу делает read-only проверки:

- `Direct` -> `campaigns.get`
- `Metrika` -> список счётчиков, expected `counter_id`, `counter_info`, `goals`
- `Audience` -> список сегментов, expected `segment_name`, optional `Direct Live4` cross-check

Если preflight не прошёл, auth-flow нельзя считать завершённым.

## Где `.env` всё ещё нужен

`examples/yandex.env.example` остаётся в bundle, но только как optional layer:

- кастомный OAuth app вместо built-in public profile
- legacy/device flow с явным `client_secret`
- runtime env для уже полученных token
- `Wordstat / Search API` cloud auth

## Почему `Wordstat` не надо смешивать с этим launcher-layer

`Wordstat` в current official model идёт через `Yandex Search API / Yandex Cloud`.

Это значит:

- нужен cloud context
- нужен `folder`
- нужны cloud roles
- auth идёт через `IAM token` или `API key`

Поэтому сценарий `открыли OAuth-страницу -> пользователь залогинился -> bundle получил token -> Wordstat готов` нельзя описывать как универсальный официальный путь.

## Связанные документы

- `docs/operator-auth-launchers.md`
- `docs/auth-model-matrix.md`
- `plugins/yandex-direct-for-all/docs/operator-auth-launchers.md`
- `plugins/yandex-direct-for-all/config/yandex_oauth_public_profiles.json`
