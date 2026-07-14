# Yandex Wordstat MCP 2.0.1

Сервер предоставляет актуальные методы Wordstat v2 через Yandex Cloud Search API:

- get-regions-tree и get-region-children;
- top-requests;
- dynamics;
- regions.

## Настройка

Нужны переменные YANDEX_WORDSTAT_API_KEY (или YANDEX_SEARCH_API_KEY) и YANDEX_WORDSTAT_FOLDER_ID (или YANDEX_FOLDER_ID). Ключ должен иметь область yc.search-api.execute, а субъект — роль search-api.webSearch.user.

Ключи не передаются в аргументах процесса. Локальный учёт запросов хранится в каталоге YDFALL_STATE_ROOT либо в ~/.local/state/yandex-direct-for-all. Файл и каталог создаются с правами только владельца.

## Ограничения

Все процессы совместно соблюдают не более 10 запросов в секунду и 100 тарифицируемых запросов в час. getRegionsTree входит в секундное ограничение, но записывается с нулевой стоимостью.

## Запуск и проверка

    npm ci --ignore-scripts
    npm test
    npm start

Исходник закреплён в UPSTREAM.md. Смысловая обработка ключевых фраз выполняется только по правилам навыка yandex-direct-unified.
