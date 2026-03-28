# Operator Auth Launchers

Этот auth-layer относится только к:

- `Yandex Direct`
- `Yandex Metrika`
- `Yandex Audience`

И не относится к:

- `Wordstat`
- `Yandex Search API`

Потому что это уже отдельная cloud auth-модель.

## Что изменилось

Главное исправление: launcher больше не требует, чтобы оператор или другой пользователь вручную заполнял `.env` только ради `client_id/client_secret`.

Теперь default path такой:

1. bundle берёт public app-profile из `plugins/yandex-direct-for-all/config/yandex_oauth_public_profiles.json`
2. генерирует `PKCE` verifier/challenge
3. открывает страницу логина/consent
4. сохраняет user token в `./.codex/auth/`
5. сразу запускает read-only `preflight_yandex_user_token.py`

## Канонические скрипты

- `plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh`
- `plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.py`
- `plugins/yandex-direct-for-all/scripts/exchange_yandex_user_code.sh`
- `plugins/yandex-direct-for-all/scripts/preflight_yandex_user_token.py`
- `plugins/yandex-direct-for-all/scripts/render_yandex_token_env.py`

## Default profiles

- `direct` -> profile `legacy_direct`, режим `local-callback`, redirect `http://localhost:8080/callback`
- `metrika` -> profile `master_yandex`, режим `manual-code`, redirect `https://oauth.yandex.ru/verification_code`
- `audience` -> profile `master_yandex`, режим `manual-code`, redirect `https://oauth.yandex.ru/verification_code`

Это public `client_id`-профили. В этом репозитории они опубликованы намеренно, чтобы другие пользователи могли логиниться через ваши approved apps.

Реальные `client_secret` в bundle не коммитятся и для default PKCE path не нужны.

## Базовые команды

Все команды ниже запускать из `<repo-root>`.

Direct:

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct
```

Metrika:

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service metrika
```

Audience:

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service audience
```

## Two-step flow

Если нужен явный обмен `confirmation code` отдельным шагом:

```bash
bash ./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh \
  --service metrika \
  --print-only \
  --no-browser

bash ./plugins/yandex-direct-for-all/scripts/exchange_yandex_user_code.sh \
  --service metrika \
  --code <confirmation-code>
```

В `print-only` launcher теперь сохраняет `pending`-сессию:

- `./.codex/auth/<service>_oauth_pending.json`

И второй шаг берёт из неё `client_id`, `redirect_uri` и `code_verifier`, так что руками ничего дописывать не надо.

## Troubleshooting

| Симптом | Что это значит | Что делать |
|---|---|---|
| Браузер не должен открываться автоматически | нужен non-interactive запуск | добавить `--print-only --no-browser` |
| `direct` не может завершить local callback | не подходит `localhost:8080` или redirect не зарегистрирован | перейти на two-step flow |
| Есть token, но нет `*_oauth_preflight.json` | auth не завершён operationally | повторить launcher или отдельно прогнать preflight |
| `Wordstat` не работает через этот launcher | выбрана не та auth-модель | перейти к `docs/oauth-and-app-setup.md` |

## Что появляется на диске

После успешной авторизации:

- `./.codex/auth/<service>_oauth_token.json`
- `./.codex/auth/<service>_oauth.env`
- `./.codex/auth/<service>_oauth_preflight.json`

Примеры:

- `./.codex/auth/direct_oauth_token.json`
- `./.codex/auth/direct_oauth.env`
- `./.codex/auth/direct_oauth_preflight.json`

## Что проверяет post-auth preflight

`preflight_yandex_user_token.py` работает только read-only.

Для `Direct`:

- делает `campaigns.get`
- показывает human-readable названия кампаний
- проверяет, что токен реально видит кабинет, а не просто “технически жив”

Для `Metrika`:

- получает список счётчиков
- при наличии expected `counter_id` проверяет именно его
- дополнительно тянет `counter_info` и `goals`

Для `Audience`:

- получает список сегментов
- при наличии expected `segment_name` проверяет именно его
- если рядом доступен Direct token, дополнительно делает read-only `GetRetargetingGoals` Live4 и пишет отдельный cross-check summary

## Optional overrides

`examples/yandex.env.example` теперь не обязательный шаг для auth-launcher.

Он нужен только если вы хотите:

- переопределить built-in public profile своим app
- передать свой `client_secret` для legacy/device path
- задать нестандартные output paths
- настроить runtime env или cloud auth для `Wordstat/Search API`

## Что запрещено обещать

- нельзя описывать `Wordstat` так, будто он живёт в этом же OAuth launcher-flow
- нельзя смешивать user tokens разных людей
- нельзя считать токен “готовым”, пока не пройден post-auth preflight
