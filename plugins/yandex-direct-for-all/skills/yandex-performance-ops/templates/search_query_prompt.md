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
- `roistat/keywords_30d.json` if available

Output:
- `tasks_search_queries.tsv`

Rules:
- negatives must be semantically safe;
- do not minus product attributes or buying-intent tokens;
- if confidence is low, route to review/monitor, not apply;
- provide evidence per row.

