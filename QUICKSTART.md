# Быстрый старт

## 1. Установка

Claude Code:

    /plugin marketplace add nebelov/yandex-direct-for-all
    /plugin install yandex-direct-for-all@yandex-direct-for-all

Codex:

    codex plugin marketplace add nebelov/yandex-direct-for-all

затем установить плагин в интерфейсе Codex.

Ручная установка из клона: сначала план, потом то же с `--apply`:

    bash plugins/yandex-direct-for-all/scripts/install_bundle.sh --target both
    bash plugins/yandex-direct-for-all/scripts/install_bundle.sh --target both --apply

Не удаляйте выданный RUN_ID, пока не проверите установленный набор. Установщик не меняет файл с пользовательскими правками.

## 2. Проверка набора (для разработчиков)

    bash plugins/yandex-direct-for-all/scripts/release_gate.sh

Требует дополнительно bun 1.3+, gitleaks и git. Обычному пользователю этот шаг не нужен.

## 3. Авторизация Яндекс

Для Директа и Метрики уже есть общие приложения. Создавать своё приложение не требуется:

    bash plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct --client-login 'логин-рекламодателя'
    bash plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service metrika

Прямой рекламодатель указывает собственный логин, представитель агентства — логин клиента-рекламодателя. Директ по умолчанию использует профиль legacy_direct, Метрика — master_yandex. Коды и токены не передаются параметрами командной строки. Готовность подтверждается только обязательным чтением соответствующей службы.

Чтобы сервер MCP Директа увидел токен, создайте рядом файл доступа с правами 600:

    {"environment": "production", "token_file": ".codex/auth/direct_oauth_token.json", "client_login": "логин-рекламодателя"}

и запускайте Claude Code или Codex из терминала, где задано:

    export YANDEX_DIRECT_ACCESS_FILE="$PWD/.codex/direct-access.json"

Без файла доступа сервер работает в песочнице Директа и честно сообщает, какой переменной не хватает.

## 4. Wordstat v2

Создайте вне хранилища файл с правами 600:

    {"api_key":"...","folder_id":"..."}

Проверка настройки:

    plugins/yandex-direct-for-all/skills/yandex-performance-ops/scripts/wordstat_tool.sh preflight /защищённый/путь.json

Сбор:

    plugins/yandex-direct-for-all/scripts/collect_wordstat_wave.sh --masks-file masks.tsv --output-dir result --config /защищённый/путь.json

Wordstat и Yandex Search API используют ключ Yandex Cloud, а не пользовательскую авторизацию Директа.

Платный `mcp/yandex-search` по умолчанию отклоняет все вызовы. Для его включения сначала откройте `plugins/yandex-direct-for-all/mcp/yandex-search/readme.md` и выберите ручной или заранее разрешённый режим.
