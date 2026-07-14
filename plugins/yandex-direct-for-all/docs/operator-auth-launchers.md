# Запуски без утечки доступов

```bash
./scripts/start_yandex_user_auth.sh --service direct --client-login 'логин-рекламодателя'
./scripts/start_yandex_user_auth.sh --service metrika
./scripts/exchange_yandex_user_code.sh --service metrika
```

Код Метрики вводится скрыто. Токен, код и секрет приложения не принимаются аргументами процесса.

Для чтения Директа создайте защищённый файл:

```json
{
  "environment": "production",
  "token_file": ".codex/auth/direct_oauth_token.json",
  "client_login": "логин-рекламодателя"
}
```

Прямой рекламодатель указывает в `client_login` собственный логин. Представитель
агентства указывает логин клиента-рекламодателя. Без явной области чтение
отклоняется до обращения к сети.

Задайте файлу права `0600`, затем проверьте его:

```bash
python3 skills/yandex-performance-ops/scripts/check_access_paths.py \
  --access-file .codex/direct-access.json
```

Снимки и отчёты принимают только `--access-file` либо локальные переменные. Каждый источник получает собственный манифест полноты и контрольную сумму.
