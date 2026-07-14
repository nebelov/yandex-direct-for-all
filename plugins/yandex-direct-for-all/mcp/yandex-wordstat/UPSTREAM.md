# Происхождение Wordstat v2

- Исходное хранилище: https://github.com/altrr2/yandex-tools-mcp
- Метка: v-wordstat-2.0.1
- Изменение: 4a3a55ecdc5a40b5c1a19fb32329df8065adbd14
- Лицензия: MIT, файл LICENSE сохранён.

Перенесены LICENSE, README.md, package.json, package-lock.json, src/convert.mjs, src/index.mjs и tests/conversions.test.mjs. README объединён с договором этого набора. В `convert.mjs` добавлен межпроцессный постоянный учёт скорости и стоимости, подключённый из `index.mjs`; его проверки добавлены в существующий `tests/conversions.test.mjs`, чтобы не расширять утверждённый список файлов.

Проверка неизменённой логики преобразований:

    bun test tests/conversions.test.mjs

Ожидается 27 успешных проверок: 24 исходные проверки преобразований и 3 проверки общего постоянного ограничителя.
