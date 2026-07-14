# Сборка дополнения

Этот каталог является самодостаточным корнем `yandex-direct-for-all`.
Обязательные части: `.codex-plugin/plugin.json`, `.mcp.json`, `skills/`, `mcp/`,
`scripts/`, `docs/`, `examples/` и `assets/`.

Основной навык — `skills/yandex-direct-unified/SKILL.md`. Старые основные
названия сохранены только как переходники.

## Проверка

Из корня дополнения:

```bash
bash scripts/release_gate.sh
```

## Установка

```bash
bash scripts/install_bundle.sh --target codex
bash scripts/install_bundle.sh --target codex --apply
```

Для Клода используйте `claude`, для обеих сред — `both`. До применения нужны
`uv`, Node.js и npm. Установщик сначала полностью готовит временную копию,
включая зависимости поиска и Wordstat, затем атомарно заменяет только
управляемые каталоги. Конфликт пользовательского файла блокирует запись.

Токены, ключи, рабочие выгрузки и состояние установки не являются частью
поставки.
