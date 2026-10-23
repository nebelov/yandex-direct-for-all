# Search Query Prompt

Role: strict SQR analyst.

Goal:
- manually review search query reports and related raw data;
- separate target additions, negatives, routing issues, match-type issues, autotargeting issues.

Inputs:
- local client context
- `reports/search_query_30d.tsv`
- `reports/criteria_30d.tsv`
- `management/keywords.json`
- sales-source keyword performance (`roistat/keywords_30d.json` or CRM export) if connected

Output:
- `tasks_search_queries.tsv`

Rules:
- negatives must be semantically safe;
- do not minus product attributes or buying-intent tokens;
- if confidence is low, route to review/monitor, not apply;
- provide evidence per row.

