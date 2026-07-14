# Запуски без утечки доступов

```bash
./scripts/start_yandex_user_auth.sh --service direct
./scripts/start_yandex_user_auth.sh --service metrika
./scripts/exchange_yandex_user_code.sh --service metrika
```

Код Метрики вводится скрыто. Токен, код и секрет приложения не принимаются аргументами процесса.

Для чтения Директа создайте защищённый файл:

```json
{
  "environment": "production",
  "token_file": ".codex/auth/direct_oauth_token.json"
}
```

Прямой рекламодатель не добавляет `client_login`. Представитель агентства
добавляет `"client_login": "логин-клиента-рекламодателя"`.

Задайте файлу права `0600`, затем проверьте его:

```bash
python3 skills/yandex-performance-ops/scripts/check_access_paths.py \
  --access-file .codex/direct-access.json
```

Снимки и отчёты принимают только `--access-file` либо локальные переменные. Каждый источник получает собственный манифест полноты и контрольную сумму.
