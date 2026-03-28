# Skill Index

Этот файл нужен, чтобы другой ИИ не потерял skills в bundle.

## Canonical bundled skills

| Skill | Когда использовать | Entry point |
|---|---|---|
| `yandex-performance-ops` | live ops, audit, Wordstat, Direct, Metrika, Roistat, apply/readback | `skills/yandex-performance-ops/SKILL.md` |
| `yandex-direct-client-lifecycle` | onboarding, research, proposal, handoff | `skills/yandex-direct-client-lifecycle/SKILL.md` |
| `roistat-reports-api` | Roistat API reporting | `skills/roistat-reports-api/SKILL.md` |
| `amocrm-api-control` | amoCRM OAuth/control and companion CRM automation | `skills/amocrm-api-control/SKILL.md` |

## Minimal first read

Если вы не уверены, с чего начать:

1. `skills/yandex-performance-ops/SKILL.md`
2. `skills/yandex-direct-client-lifecycle/SKILL.md`
3. `docs/operator-auth-launchers.md`
4. `docs/data-collection-scripts.md`

## Important

Skills не лежат отдельно от plugin. Они уже bundled внутри:

- `plugins/yandex-direct-for-all/skills/`

И именно эта директория указана в plugin manifest.
