# Yandex Direct For All

Переносимый набор навыков и подключаемых служб для Яндекс.Директа, Метрики, Wordstat v2, Yandex Search API и XMLRiver; Roistat и amoCRM подключаются, если они у вас есть.

## Главное

- Единая точка входа: plugins/yandex-direct-for-all/skills/yandex-direct-unified/SKILL.md.
- Встроены два общих приложения авторизации: для Директа и для Метрики. Любой пользователь может разрешить доступ к своему Яндекс-аккаунту без создания собственного приложения.
- Открытые идентификаторы приложений опубликованы намеренно; секретов приложений и пользовательских токенов в хранилище нет.
- Wordstat использует текущий программный интерфейс v2 Yandex Cloud, общий межпроцессный учёт 10 запросов в секунду и 100 тарифицируемых запросов в час.
- Нет Yandex Cloud — выдачу Яндекса и Google и частотности Wordstat можно собирать через XMLRiver (навык `xmlriver-serp-research`): это альтернатива облаку, сборщики выбирают путь по заданному доступу.
- Чтение отделено от записи. Запись требует явного разрешения, точного пакета, снимка до изменения и чтения после него.
- Установщик сначала показывает план, не перезаписывает пользовательские файлы, подготавливает закреплённые зависимости поиска и Wordstat и умеет точно откатывать свой запуск.
- Платный Search API по умолчанию выключен; ручной и заранее разрешённый режимы имеют точные лимиты и закрытый журнал.

## Установка

Claude Code 2.1.275 и новее — одной командой в окне Claude Code:

    /plugin install yandex-direct-for-all --marketplace nebelov/yandex-direct-for-all

Claude Code 2.1.78–2.1.274:

    /plugin marketplace add nebelov/yandex-direct-for-all
    /plugin install yandex-direct-for-all@yandex-direct-for-all

Codex — добавить маркетплейс и установить плагин в интерфейсе Codex:

    codex plugin marketplace add nebelov/yandex-direct-for-all

Нужны `uv`, Node.js 20+ и npm: через них стартуют серверы MCP.

Ручная установка из клона хранилища (если маркетплейс недоступен). Сначала план, он ничего не записывает:

    bash plugins/yandex-direct-for-all/scripts/install_bundle.sh --target both

Если план верен:

    bash plugins/yandex-direct-for-all/scripts/install_bundle.sh --target both --apply

Команда выдаст RUN_ID, точную команду отката и готовые команды регистрации MCP. Повторный запуск обновляет только неизменённые управляемые каталоги. Если навык с тем же именем у вас уже стоит вручную, установщик остановится с конфликтом: переименуйте свой каталог (например, в `yandex-direct-unified.bak`) и повторите.

## Первый запуск

1. Открыть единый навык `yandex-direct-unified`.
2. Для Директа или Метрики запустить встроенную авторизацию (команды — в QUICKSTART.md). Токен после обмена сразу проверяется чтением службы.
3. Подключить токен к серверу MCP Директа: задать `YANDEX_DIRECT_ACCESS_FILE` с путём к файлу доступа (формат — docs/operator-auth-launchers.md) и запустить Claude Code или Codex из того же терминала.
4. Для Wordstat создать защищённый файл с api_key и folder_id, права 600, затем использовать `collect_wordstat_wave.sh --provider yandex-cloud --config <файл>`.

## Для разработчиков

Полная проверка выпуска (нужны также bun 1.3+, gitleaks и git):

    bash plugins/yandex-direct-for-all/scripts/release_gate.sh

Подробности: QUICKSTART.md, docs/component-inventory.md и docs/auth-model-matrix.md.
