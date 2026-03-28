# Metrika Config Contract

Глобальный навык не хранит токены Метрики внутри себя.

## Что нужно для запуска

- `YANDEX_METRIKA_TOKEN`:
  OAuth token с доступом к нужным счётчикам.

## Опциональные переменные

- `YANDEX_METRIKA_PROJECT_ROOT`:
  корень локального проекта. По умолчанию используется текущая папка.
- `YANDEX_METRIKA_CONFIG_FILE`:
  путь к env-файлу. По умолчанию `./.codex/yandex-metrika.env`.
- `YANDEX_METRIKA_CACHE_DIR`:
  директория кеша. По умолчанию `./.codex/cache/yandex-metrika`.

## Рекомендуемый локальный env-файл

```bash
YANDEX_METRIKA_TOKEN=...
YANDEX_METRIKA_COUNTER_ID=12345678
YANDEX_METRIKA_GOAL_ID=987654321
```

## Почему именно так

- global-skill должен работать из любой папки;
- секреты не должны жить внутри `<plugin-root>/skills/...`;
- кеш и env должны лежать рядом с конкретным клиентом, а не глобально.

## Что запрещено

- хранить production token внутри global-skill;
- зашивать client-specific counter/goal в reusable shell scripts;
- использовать Metrika analysis scripts для классификации ключей и фраз.
