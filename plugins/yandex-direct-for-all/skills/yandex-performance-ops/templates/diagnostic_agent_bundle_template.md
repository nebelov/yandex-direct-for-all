# Diagnostic Bundle Template

Используй этот шаблон, когда нужно провести полный ручной аудит кампаний по уже собранным raw-данным.

## Input

- Клиент: `<client_key>`
- Аккаунт / login: `<login>`
- Scope: `<campaign ids / aliases>`
- Local overlay: `<path>`
- Raw files:
  - `<reports/search_query_30d.tsv>`
  - `<management/campaign.json>`
  - `<ads/ad dump>`
  - `<metrika or roistat raw>`
- Local rules:
  - `<product catalog path>`
  - `<landing rules path>`
  - `<protected words path>`

## Hard Rules

1. Не использовать analysis-скрипты.
2. Не делать live apply.
3. Не придумывать данные, которых нет в raw-файлах.
4. Все выводы делать только по сохранённым raw-артефактам.
5. Если Roistat подключён, считать его первичным по лидам/продажам.

## Required Outputs

1. `search_queries_audit.md`
   - waste
   - missing negatives
   - missing target coverage
   - manual notes by campaign/adgroup
2. `ad_components_audit.md`
   - alignment with adgroup intent
   - gaps in sitelinks/callouts/assets
   - duplicate copy risks
3. `bids_audit.md`
   - budget caps
   - CPC/CPA issues
   - monitor-only zones
4. `structure_audit.md`
   - mixed intent groups
   - missing routing
   - cluster collisions
5. `tasks.tsv`
   - only concrete API actions
   - each task must be verifiable

## Output Discipline

- Сначала findings по severity.
- Потом open questions / assumptions.
- Потом action plan.
- Никаких summary вместо конкретики.
