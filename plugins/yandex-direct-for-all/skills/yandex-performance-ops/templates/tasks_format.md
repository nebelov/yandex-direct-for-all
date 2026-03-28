# Формат tasks.tsv — спецификация

## Назначение
Единый машинночитаемый формат для ВСЕХ задач оптимизации кампании.
Создаётся агентами-аналитиками. Потребляется скриптами apply_tasks.py и sync_yougile.py.

## Формат
TSV (Tab-Separated Values), UTF-8, с заголовком.

## Колонки

| # | Колонка | Тип | Описание | Пример |
|---|---------|-----|----------|--------|
| 1 | task_id | string | Уникальный ID: PREFIX-NNN | NEG-001 |
| 2 | priority | enum | CRITICAL / HIGH / MEDIUM / LOW | HIGH |
| 3 | category | enum | см. ниже | NEGATIVE_KEYWORD |
| 4 | scope | enum | campaign / group / ad / keyword | campaign |
| 5 | target_id | int | ID объекта в Директе | 91307551 |
| 6 | target_name | string | Человекочитаемое имя | Поиск/Типы |
| 7 | action | string | Действие (см. ниже) | ADD_NEGATIVE |
| 8 | params_json | JSON | Параметры для API | {"word":"вентиляц"} |
| 9 | evidence | string | Метрики-доказательство | 3clicks,52р,0conv |
| 10 | savings_30d | float | Потенциальная экономия руб/30д | 52 |
| 11 | description | string | Описание для YouGile | Мусорный запрос "вытяжка" |

## Префиксы task_id

| Префикс | Категория |
|----------|-----------|
| SET- | SETTING_CHANGE |
| PLC- | PLACEMENT_CHANGE |
| NEG- | NEGATIVE_KEYWORD |
| AD- | AD_COMPONENT |
| BID- | BID_ADJUSTMENT |
| STR- | STRUCTURE_CHANGE |

## Категории (category)

| Категория | Описание |
|-----------|----------|
| SETTING_CHANGE | Настройки кампании (Settings) |
| PLACEMENT_CHANGE | Типы размещений (PlacementTypes) |
| NEGATIVE_KEYWORD | Минус-слова (кампания/группа) |
| AD_COMPONENT | Замена компонента объявления |
| BID_ADJUSTMENT | Корректировка ставок |
| STRUCTURE_CHANGE | Создание/изменение групп, кросс-минусы |

## Действия (action)

### SETTING_CHANGE
- `DISABLE_SETTING` — params: {"option": "...", "value": "NO"}
- `ENABLE_SETTING` — params: {"option": "...", "value": "YES"}

### PLACEMENT_CHANGE
- `DISABLE_PLACEMENT` — params: {"placement": "ProductGallery|DynamicPlaces|Maps|SearchOrganizationList", "value": "NO"}

### NEGATIVE_KEYWORD
- `ADD_NEGATIVE` — params: {"word": "слово", "level": "campaign|group", "group_id": N (если group)}
- `ADD_NEGATIVE_PHRASE` — params: {"phrase": "фраза из слов", "level": "campaign|group"}
- `REMOVE_NEGATIVE` — params: {"word": "слово", "level": "campaign|shared_set", "set_id": N}

### AD_COMPONENT
- `REPLACE_TITLE` — params: {"ad_id": N, "old": "текст", "new": "текст"}
- `REPLACE_TITLE2` — params: {"ad_id": N, "old": "текст", "new": "текст"}
- `REPLACE_TEXT` — params: {"ad_id": N, "old": "текст", "new": "текст"}
- `REPLACE_HREF` — params: {"ad_id": N, "old": "url", "new": "url"}
- `PAUSE_AD` — params: {"ad_id": N}
- `RESUME_AD` — params: {"ad_id": N}

### BID_ADJUSTMENT
- `LOWER_BID` — params: {"criterion_id": N, "current_avg_cpc": X, "recommendation": "reduce_N_pct"}
- `RAISE_BID` — params: {"criterion_id": N, "current_avg_cpc": X, "recommendation": "increase_N_pct"}
- `ADD_DEVICE_ADJUSTMENT` — params: {"device": "DESKTOP|MOBILE|TABLET", "pct": -20}

### STRUCTURE_CHANGE
- `CREATE_GROUP` — params: {"name": "тип 7", "keywords": ["...", "..."]}
- `ADD_CROSS_NEGATIVES` — params: {"group_id": N, "negatives": ["тип 1", "тип 2"]}
- `REMOVE_SHARED_SET` — params: {"set_id": N, "reason": "..."}

## Priority правила

| Priority | Когда |
|----------|-------|
| CRITICAL | Настройки, сливающие бюджет (AREA_OF_INTEREST, ALTERNATIVE_TEXTS) |
| HIGH | Минус-слова с расходом > 100р/30д, ключи с Cost > CPA и 0 conv |
| MEDIUM | Минус-слова с расходом 10-100р, A/B замены компонентов |
| LOW | Минус-слова < 10р, структурные улучшения на будущее |

## Пример файла

```tsv
task_id	priority	category	scope	target_id	target_name	action	params_json	evidence	savings_30d	description
SET-001	CRITICAL	SETTING_CHANGE	campaign	91307551	Поиск/Типы	DISABLE_SETTING	{"option":"ALTERNATIVE_TEXTS_ENABLED","value":"NO"}	current=YES	0	Отключить автоподмену текстов
NEG-001	HIGH	NEGATIVE_KEYWORD	campaign	91307551	Поиск/Типы	ADD_NEGATIVE	{"word":"вытяжк","level":"campaign"}	1click,53р,0conv	53	Мусор: "теневая вытяжка"
AD-001	MEDIUM	AD_COMPONENT	ad	14683059351	тип 1	REPLACE_TITLE2	{"ad_id":14683059351,"old":"Старый","new":"Новый"}	CTR:18.7%vs23.4%	0	Заменить заголовок 2
BID-001	HIGH	BID_ADJUSTMENT	keyword	46118002858	[теневой профиль тип 1]	LOWER_BID	{"criterion_id":46118002858,"current_avg_cpc":318,"recommendation":"reduce_30_pct"}	8clicks,2546р,0conv	760	CPC слишком высокий
```
