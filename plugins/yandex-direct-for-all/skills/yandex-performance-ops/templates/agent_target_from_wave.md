# Agent Template — Target Phrases from Wave Raw

Role: strict extraction agent.
Goal: build `target_phrases_wave*.tsv` ONLY from provided raw files.

Rules:
- Do not invent phrases.
- Every phrase must have `source_file` and `evidence`.
- Keep B2B intent only (business/ads/social/ecom/marketplace).
- Ambiguous phrases go to review, not target.
- Do not call new APIs during this step (analysis-only mode).

Output columns:
`phrase\tcluster\tintent_type\tpriority\tsource_file\tsource_mask\tevidence`
