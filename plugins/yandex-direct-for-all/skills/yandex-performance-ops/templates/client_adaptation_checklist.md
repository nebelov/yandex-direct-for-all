# Client Adaptation Checklist

Use this when connecting a new client/project to `yandex-performance-ops`.

Path contract:
- `<plugin-root>` = корень bundled plugin, например `./plugins/yandex-direct-for-all` или `~/.codex/plugins/yandex-direct-for-all`

## Required local files

1. `./.codex/yandex-performance-client.json`
2. `product-map.md`
3. `routing-map.tsv`
4. `campaign-id-map.json` if live apply/tasks need exact campaign IDs
5. optional:
   - `protected-words.txt`
   - `negative_axioms.md`
   - `copy-map.json`
   - `yougile-columns.json`
   - `yougile-board-presets.json`

## Must adapt before any real work

### Overlay

- `direct.login`
- `direct.counter_ids`
- `direct.regions`
- `direct.priority_goals`
- `metrika.counter_id`
- `metrika.goal_id`
- `roistat.enabled`
- `roistat.api_key_env`
- `roistat.project_env`
- `roistat.marker_level_1`
- `roistat.marker_level_2_search`
- `yougile.project_id`
- `yougile.boards[]`

### Routing

`routing-map.tsv` must explicitly map:
- `cluster`
- `campaign_name`
- `adgroup_name`
- `match_type`
- `landing_hint`

### Prompts

Before agent analysis, replace local business context in:
- `search_query_prompt.md`
- `ad_components_prompt.md`
- `bids_prompt.md`
- `structure_prompt.md`
- `validate_negatives_prompt.md`
- `weekly_review_prompt.md`

### Scripts

Check CLI/env for:
- `collect_all.py`
- `change_tracker.py`
- `deploy_search_campaigns.py`
- `sync_yougile.py`
- `roistat_query.sh`

## Verification

1. `rg -n "oldbrand|olddomain|oldprice|oldgoal" .`
2. `python3 <plugin-root>/skills/yandex-performance-ops/scripts/init_client_context.py --help`
3. `python3 <plugin-root>/skills/yandex-performance-ops/scripts/collect_all.py --help`
4. `python3 <plugin-root>/skills/yandex-performance-ops/scripts/build_manual_final_pack.py --help`
5. `python3 <plugin-root>/skills/yandex-performance-ops/scripts/deploy_search_campaigns.py --help`

## Red lines

- do not keep secrets in overlay
- do not reuse another client routing map
- do not run partial-scope optimization
- do not skip low-volume campaigns just because they are small
- do not promote local scripts into global-skill until hardcodes are removed
