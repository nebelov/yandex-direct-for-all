# Agent Template — Validation Checklist

Goal: validate final target/minus sets before clustering.

Checks:
1. No lexical conflicts: minus vs target.
2. No semantic conflicts: minus blocks relevant B2B analog/synonym.
3. Scope correctness: campaign/adgroup level.
4. No duplicates and no contradictory entries.
5. Production minus list contains single-token words only (no phrases).

Pass condition:
- `conflicts_with_target = 0`
- no `risk_blocking=high` unresolved.
