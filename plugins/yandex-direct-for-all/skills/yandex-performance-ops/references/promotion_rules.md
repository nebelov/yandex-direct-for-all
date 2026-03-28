# Promotion Rules

Любой новый урок, скрипт или промт можно поднимать в global-skill только если он:

1. Не зависит от одного клиента.
2. Не содержит секретов и хардкод-идентификаторов.
3. Явно работает от CLI/env/local overlay.
4. Имеет понятный preflight.
5. Не смешивает сбор данных и анализ.
6. Не заставляет пользователя вручную искать обязательные параметры в коде.

## Красные флаги

- `API_KEY="..."` в скрипте
- `GoalId = 123456789` без CLI/env override
- кампании/группы по имени одного бренда
- default landing/domain под одного клиента
- prompt с каталогом только одного бизнеса

## Минимум для promotion

- reusable CLI
- `--help`
- no secrets
- documented inputs/outputs
- example usage
- mention in `SKILL.md`

