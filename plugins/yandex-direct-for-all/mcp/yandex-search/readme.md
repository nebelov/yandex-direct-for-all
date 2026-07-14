# Yandex Cloud Search API

Этот MCP-сервер выполняет платный веб-поиск и порождающий поиск Yandex Cloud. Он не является Wordstat, Директом или встроенным поиском модели.

## Безопасное состояние по умолчанию

Без `YANDEX_SEARCH_ROUTE` платные вызовы отклоняются до сети. Ошибка веб-поиска не включает порождающий поиск, не повторяет запрос и не меняет режим.

Доступ передаётся только переменными:

- `YANDEX_SEARCH_API_KEY`;
- `YANDEX_SEARCH_FOLDER_ID`.

Ключ и номер папки не передаются в теле вызова, аргументах и публичных файлах.

## Ручной режим

Установите `YANDEX_SEARCH_ROUTE=manual` и задайте путь закрытого журнала в
`YANDEX_SEARCH_USAGE_LEDGER`. Каждый вызов должен содержать:

```json
{
  "query": "ПРОВЕРЕННЫЙ ЗАПРОС",
  "search_region": "ru",
  "paid_search_approval": {
    "approved": true,
    "route": "web",
    "max_calls": 1,
    "approval_ref": "ССЫЛКА_НА_ОДОБРЕНИЕ"
  }
}
```

Для инструмента `ai_search_with_yazeka` маршрут должен быть `generative`.
Ссылка `approval_ref` резервируется в журнале до сети и не может быть
использована повторно.

## Заранее разрешённый режим

Установите `YANDEX_SEARCH_ROUTE=approved`, а также пути:

- `YANDEX_SEARCH_APPROVAL_FILE` — закрытый JSON с правами `0600`;
- `YANDEX_SEARCH_USAGE_LEDGER` — закрытый журнал использования.

Схема разрешения:

```json
{
  "approved": true,
  "approval_ref": "ССЫЛКА_НА_ОДОБРЕНИЕ",
  "routes": ["web"],
  "max_calls": 10,
  "expires_at": "2030-01-01T00:00:00+00:00",
  "folder_sha256": "SHA256_НОМЕРА_ПАПКИ"
}
```

Каждый вызов резервирует единицу лимита до сети. Запросы и ключи в журнал не пишутся.

## Проверка доступа

Служебной учётной записи нужна роль, разрешающая веб-поиск, а ключу — область `yc.search-api.execute`. Актуальные названия ролей и параметров сверяйте с официальной документацией:

- <https://yandex.cloud/ru/docs/search-api/operations/web-search-sync>
- <https://yandex.cloud/ru/docs/search-api/concepts/html-response>
- <https://yandex.cloud/ru/docs/search-api/pricing>

## Зависимости и запуск

```bash
uv sync --frozen
uv run --frozen python server.py
```

`requirements.txt` содержит тот же полностью закреплённый граф для среды, где
доступен только `pip`. При запуске через настройку MCP используйте те же
переменные. Не встраивайте доступы в команду.
