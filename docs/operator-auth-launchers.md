# Запуски авторизации и чтения

Все команды ниже безопасны для истории оболочки: в них нет токена, секрета приложения или одноразового кода.

## Получить доступ

```bash
./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct
./plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service metrika
```

Совместимая команда для продолжения сохранённого обмена Метрики:

```bash
./plugins/yandex-direct-for-all/scripts/exchange_yandex_user_code.sh --service metrika
```

Код будет запрошен скрыто. Ключи `--code`, `--token`, `--client-secret`, `--skip-preflight` не поддерживаются.

## Подготовить защищённый файл чтения Директа

```json
{
  "environment": "production",
  "client_login": "ваш-логин-клиента",
  "token_file": ".codex/auth/direct_oauth_token.json"
}
```

Сохраните его вне Git и выполните `chmod 600`. Вместо пути можно задать `YANDEX_DIRECT_ACCESS_FILE`.

## Проверить и собрать

```bash
python3 plugins/yandex-direct-for-all/skills/yandex-performance-ops/scripts/check_access_paths.py \
  --access-file .codex/direct-access.json

plugins/yandex-direct-for-all/scripts/collect_direct_bundle.sh \
  --access-file .codex/direct-access.json \
  --output-dir .codex/snapshots/current
```

Сборщик сохраняет отдельный манифест каждого источника. Итог считается полным только тогда, когда все обязательные источники завершены.
