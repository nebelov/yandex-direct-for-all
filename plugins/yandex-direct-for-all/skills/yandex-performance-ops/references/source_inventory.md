# Source Inventory

## Promoted into global-skill

### `kartinium/.claude/skills/direct-search-semantics`
- parsing vs analysis constitution
- reusable semantics templates
- live readiness / moderation / callouts / copy audit scripts

### `kartinium/.claude/skills/yandex-direct`
- campaign autotest
- API gotchas
- ad format references

### `kartinium/.claude/skills/yandex-wordstat`
- mask methodology
- full-depth coverage rules
- minus-word normalization lessons

### `kartinium/.claude/skills/roistat-direct`
- Roistat-first discipline
- safe file-based query pattern

### `kartinium/.claude/skills/media-plan`
- `forecast_engine.py`
- `test_forecast.py`
- `media_plan_prompt.md`

### `ads/siz/.claude/skills/direct-optimization`
- `collect_all.py`
- `apply_tasks.py`
- `change_tracker.py`
- `sync_yougile.py`
- diagnostic / validation / aggregation templates

### `ads/tenevoy/.claude/skills/direct-optimization`
- cross-check of reusable prompts and lessons
- confirmation of Roistat-first search workflow requirements

### `ads/siz/.claude/skills/yandex-metrika`
- cache-first metrika workflow
- reusable shell scripts and API references
- genericized config/cache contract

### `ads/siz/.claude/skills/competitive-ads-extractor`
- generic competitor creative research workflow

### `ads/siz/.claude/skills/ppc-data-analysis`
- statistical framing already embedded into templates and media-plan formulas

## Intentionally local-only

Причина: client-binding, секреты, локальные board IDs, product catalog, brand axioms, account quirks.

- `analyze_wave.py`
- `audit_per_mask.py`
- `build_gap_wave2.py`
- `apply_manual_final_live.py`
- `agent_prompts_diagnostic.md` in its original form
- любые analysis-скрипты, которые сами классифицируют ключи, фразы, маски, target/negative/minus слова
- local `references/product-catalog*.md`
- local campaign maps, board ids, landing rules, protected words
- local Roistat analyzers with account-specific reporting assumptions
- local YouGile skills with project/board/column UUIDs

## Sanitization applied

- removed hardcoded OAuth client secret / client id usage
- removed hardcoded Roistat API key / project ids from promoted scripts
- removed hardcoded counter ids, goal ids, hrefs, campaign ids
- removed client-local absolute paths from reusable prompts/scripts
- moved client specifics into overlay contract

## What remains to be promoted only with evidence

- any new script must support CLI/env/overlay before promotion
- any prompt with embedded product catalog must be templated first
- any analysis shortcut that bypasses manual review stays local-only
