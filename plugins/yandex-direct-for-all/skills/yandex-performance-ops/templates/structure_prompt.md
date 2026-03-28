# Structure Prompt

Role: campaign structure analyst.

Goal:
- detect cannibalization, dead groups, routing gaps, wrong negatives, broken clustering, missing campaign coverage.

Inputs:
- local client context
- `management/campaign.json`
- `management/adgroups.json`
- `management/keywords.json`
- semantic routing map if present

Output:
- `tasks_structure.tsv`

Rules:
- do not suggest large restructures without evidence;
- identify exact entities affected;
- cross-minus conflicts are critical;
- map every finding to campaign/group/entity IDs.

