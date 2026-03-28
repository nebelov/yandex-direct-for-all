# Artifact Contract

Локальный проект после старта этого skill должен иметь минимум такие файлы:

1. `client-kb.md`
   Каноническая база знаний клиента.
2. `source-register.tsv`
   Реестр всех подтвержденных источников и артефактов.
3. `competitor-raw-register.tsv`
   Реестр сырого сбора по конкурентам и их объявлениям.
4. `human-review.tsv`
   Очередь решений и согласований человеком.
5. `proposal-pack.md`
   Клиентский пакет: факты, инсайты, гипотезы, план.
6. `product-map.md`
   Карта продуктов / направлений / посадочных / доказательств.
7. `routing-map.tsv`
   Черновой или финальный routing масок/кластеров в кампании и группы.
8. `research/analysis/company-footprint.md`
   Отдельный слой по owned pages, юрсущности, адресам, логистике и внешним registry-сигналам.
9. `research/analysis/landing-inventory.md`
   Ручной инвентарь посадочных по raw HTML.
10. `research/analysis/research-backlog.md`
   Очередь следующих raw и analysis волн.
11. `research/analysis/единая-карта-конкурентов.md`
   Ручная нормализованная карта конкурентов: органика + поисковые рекламные объявления + тип игрока + сегменты.
12. `research/analysis/пакет-структуры-будущего-кабинета.md`
   Пакет будущей структуры кабинета: кампании, группы, посадочные, география, без запуска.
13. `research/analysis/пакет-текстов-и-офферов.md`
   Ручной пакет смыслов, офферов и черновых формулировок после исследования.
14. `research/analysis/готовые-тексты-для-директа.tsv`
   Машинно-читаемый пакет текстов: заголовки, описания, быстрые ссылки, уточнения.
15. `./.codex/yandex-performance-client.json`
   Локальный overlay для downstream skill `yandex-performance-ops`.

## Update Rules

1. `client-kb.md` обновляй после каждого нового confirmed discovery.
2. `source-register.tsv` обновляй при каждом новом источнике или выгрузке.
3. `competitor-raw-register.tsv` заполняй в фазе raw-research до анализа.
4. `human-review.tsv` обновляй при каждом решении, комментарии или возврате на доработку.
5. `proposal-pack.md` не должен жить отдельно от `client-kb.md`; после согласования ключевые выводы поднимай обратно в KB.
6. `company-footprint.md` обновляй после каждой волны owned pages / registry / maps / reviews.
7. `landing-inventory.md` обновляй после каждой новой волны проверки посадочных.
8. `research-backlog.md` обновляй после каждого закрытого raw/analysis блока.
9. `единая-карта-конкурентов.md`, `пакет-структуры-будущего-кабинета.md`, `пакет-текстов-и-офферов.md` и `готовые-тексты-для-директа.tsv` обновляй после завершения ручного analysis-stage и до handoff.
10. Перед handoff прогоняй машинную проверку длины текстов через reusable validator.
11. `product-map.md`, `routing-map.tsv` и overlay обновляй перед handoff в `yandex-performance-ops`.

## Confidence Discipline

Для всех артефактов явно разделяй:

1. confirmed
2. inferred
3. unknown

Нельзя выдавать inference за confirmed fact.
