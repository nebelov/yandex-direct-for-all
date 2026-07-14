# Быстрый старт

## 1. Проверка

    bash plugins/yandex-direct-for-all/scripts/release_gate.sh

## 2. Подключение

Безопасный просмотр плана установки:

    bash plugins/yandex-direct-for-all/scripts/install_bundle.sh --target both

Применение:

    bash plugins/yandex-direct-for-all/scripts/install_bundle.sh --target both --apply

Не удаляйте выданный RUN_ID, пока не проверите установленный набор. Установщик не меняет файл с пользовательскими правками.

## 3. Авторизация Яндекс

Для Директа и Метрики уже есть общие приложения. Создавать своё приложение не требуется:

    bash plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service direct
    bash plugins/yandex-direct-for-all/scripts/start_yandex_user_auth.sh --service metrika

Директ по умолчанию использует профиль legacy_direct, Метрика — master_yandex. Коды и токены не передаются параметрами командной строки. Готовность подтверждается только обязательным чтением соответствующей службы.

## 4. Wordstat v2

Создайте вне хранилища файл с правами 600:

    {"api_key":"...","folder_id":"..."}

Проверка настройки:

    plugins/yandex-direct-for-all/skills/yandex-performance-ops/scripts/wordstat_tool.sh preflight /защищённый/путь.json

Сбор:

    plugins/yandex-direct-for-all/scripts/collect_wordstat_wave.sh --masks-file masks.tsv --output-dir result --config /защищённый/путь.json

Wordstat и Yandex Search API используют ключ Yandex Cloud, а не пользовательскую авторизацию Директа.

Платный `mcp/yandex-search` по умолчанию отклоняет все вызовы. Для его включения сначала откройте `plugins/yandex-direct-for-all/mcp/yandex-search/readme.md` и выберите ручной или заранее разрешённый режим.
