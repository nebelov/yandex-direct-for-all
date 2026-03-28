# Yandex Cloud Search Handoffs

## Public-safe handoff model

Этот публичный bundle не хранит реальные cloud credentials, приватные handoff-файлы и ссылки на внутренние хосты.

Ожидаемый reusable path такой:

- хранить `YANDEX_SEARCH_FOLDER_ID` и `YANDEX_SEARCH_API_KEY` только в локальном private runtime-layer вне git;
- документировать только формат handoff, а не конкретные private paths;
- при необходимости передавать оператору отдельный private note вне публичного репозитория.

Если нужен live `Yandex Cloud Search API` collector, оператор должен использовать:

- свой private credentials file вне этого репозитория;
- локальный `.env`/secret store;
- текущие batch collectors из public bundle.

## Rule

Если в локальном клиентском проекте еще нет собственных `YANDEX_SEARCH_FOLDER_ID` и `YANDEX_SEARCH_API_KEY`, но нужен срочный live `Yandex Cloud Search API` collector, сначала проверить этот localized bundle.

Использовать как временный operational bridge, а не как замену клиентскому собственному cloud-search path навсегда.
