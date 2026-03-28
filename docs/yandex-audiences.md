# Yandex Audiences

Этот слой в исходном контуре был размазан между `yandex-performance-ops` и `amocrm-api-control`. Здесь он вынесен в отдельный operational memo.

## Что важно не сломать

### 1. Разделяйте токены

Если есть отдельный token для `Audience API`, не переиспользуйте его молча для:

- `Direct`
- `Metrika`
- `Search API`

Минимум:

- `Direct token`
- `Audience token`
- `Metrika token`

### 2. Не путайте `segment_id` и `GoalID`

Для связки `Yandex Audience -> Direct` нельзя брать raw `segment_id` и вставлять его как `ExternalId`/`GoalID`.

Канонический путь:

1. сегмент должен существовать и быть `processed` в `Audience API`
2. затем нужно получить `GoalID` через `Direct GetRetargetingGoals`
3. только этот `GoalID` можно использовать в `retargetinglists.add`

Если сегмент есть в `Audience API`, но отсутствует в `GetRetargetingGoals`, apply надо блокировать до production-write.

### 3. Минус-аудитории и hygiene

Запросы формата:

- `минус-аудитории`
- `мусорные лиды`
- `audience exclusions`

не надо вести через generic account snapshot как основной путь.

Нормальный порядок:

1. специализированный audience collector
2. отдельный hygiene analysis
3. только потом apply

### 4. Bid modifiers по аудиториям

Для exclusions / retarget adjustments сначала сверяйте payload rules на live-readback.

В каноническом skill уже зафиксировано:

- для `add` используется `RetargetingAdjustments[]` с `RetargetingConditionId` и `BidModifier`
- для `set` не надо подсовывать лишние поля `Type`, `Enabled`, `Accessible`

### 5. CRM -> Audiences

Если задача — автоматическая передача аудиторий из CRM, bundle закрывает это так:

- `amocrm-api-control` — OAuth и schema dump по `amoCRM`
- `yandex-performance-ops` — правила по audience hygiene и downstream apply

То есть CRM-часть и `Direct/Audiences`-часть надо держать раздельно, а не смешивать в один непрозрачный скрипт.

## Практический чек-лист

Перед любым live apply по аудиториям подтвердите:

1. какой token используется
2. где лежит audience source of truth
3. какой `GoalID` реально существует в `Direct`
4. что apply идёт в нужный `Client-Login`
5. что readback совпал

Если хотя бы один из этих пунктов не подтверждён, считайте состояние `planning only`.
