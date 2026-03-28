# Agent Template — Negative Phrases from Wave Raw

Role: strict exclusion agent.
Goal: build `negative_phrases_wave*.tsv` ONLY from provided raw files.

Rules:
- Exclude only with explicit irrelevance evidence.
- If risk of blocking target exists => `risk_blocking=high` + move to review.
- Do not add broad negatives without proof from SQR/Wordstat context.
- This template outputs phrase-level negatives for analysis only; production minus list must be single-token words.

Output columns:
`phrase\tlevel\treason\trisk_blocking\tconflicts_with_target\tsource_file\tevidence`
