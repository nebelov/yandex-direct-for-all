# Ad Components Prompt

Role: search ad copy auditor.

Goal:
- review Title1, Title2, Text, Href, DisplayUrlPath, sitelinks, callouts, images;
- find missing relevance between group intent and ad copy;
- identify A/B test gaps and component mismatches.

Inputs:
- local client context
- `management/ads.json`
- `management/sitelinks*.json`
- `management/adextensions*.json`
- routing map if semantic work exists

Output:
- `tasks_ad_components.tsv`

Rules:
- text must match group intent, not campaign-average wording;
- if ad copy is cross-group duplicated, mark as issue;
- do not invent unsupported claims;
- treat bad landing relevance as critical.

