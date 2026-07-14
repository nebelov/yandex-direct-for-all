# Происхождение Wordstat v2

- Исходное хранилище: https://github.com/altrr2/yandex-tools-mcp
- Метка: v-wordstat-2.0.1
- Изменение: 4a3a55ecdc5a40b5c1a19fb32329df8065adbd14
- Лицензия: MIT, файл LICENSE сохранён.

Перенесены LICENSE, README.md, package.json, package-lock.json, src/convert.mjs, src/index.mjs и tests/conversions.test.mjs. README объединён с договором этого набора. В index.mjs добавлен межпроцессный постоянный учёт скорости и стоимости; его отдельные проверки находятся в tests/usage-ledger.test.mjs.

Проверка неизменённой логики преобразований:

    bun test tests/conversions.test.mjs

Ожидается 24 успешные проверки.
