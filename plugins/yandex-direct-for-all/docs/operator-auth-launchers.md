# Запуски авторизации и чтения

Все команды ниже безопасны для истории оболочки: в них нет токена, секрета приложения или одноразового кода.

## Получить доступ

```bash
./scripts/start_yandex_user_auth.sh --service direct --client-login 'логин-рекламодателя'
./scripts/start_yandex_user_auth.sh --service metrika
```

Совместимая команда для продолжения сохранённого обмена Метрики:

```bash
./scripts/exchange_yandex_user_code.sh --service metrika
```

Код будет запрошен скрыто. Ключи `--code`, `--token`, `--client-secret`, `--skip-preflight` не поддерживаются.

## Подготовить защищённый файл чтения Директа

```json
{
  "environment": "production",
  "token_file": "auth/direct_oauth_token.json",
  "client_login": "логин-рекламодателя"
}
```

Файл кладите в `.codex/direct-access.json`: относительный `token_file` считается от папки самого файла доступа, поэтому `auth/direct_oauth_token.json` указывает на `.codex/auth/direct_oauth_token.json` при любой текущей папке.

Прямой рекламодатель указывает в `client_login` собственный логин. Представитель
агентства указывает логин клиента-рекламодателя. Без явной области чтение
отклоняется до обращения к сети.

Сохраните его вне Git и выполните `chmod 600`. Вместо пути можно задать `YANDEX_DIRECT_ACCESS_FILE`.

## Проверить и собрать

```bash
python3 skills/yandex-performance-ops/scripts/check_access_paths.py \
  --access-file .codex/direct-access.json

scripts/collect_direct_bundle.sh \
  --access-file .codex/direct-access.json \
  --output-dir .codex/snapshots/current
```

Сборщик сохраняет отдельный манифест каждого источника. Итог считается полным только тогда, когда все обязательные источники завершены.
