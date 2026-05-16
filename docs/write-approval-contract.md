# Write Approval Contract

Default mode is read-only.

A write is allowed only when all are true:

- the affected repository, account, campaign, group, ad, keyword, or setting is explicitly in scope;
- the exact package or mutation was shown to the owner;
- the owner gave explicit approval for that package or mutation;
- preflight and smoke checks passed;
- readback or post-apply validation is planned.

High-risk actions need separate approvals:

- stopping, pausing, suspending, archiving, or otherwise cutting live traffic;
- search-negative rewrites;
- strategy, bid, placement, or moderation changes;
- adding live mutation utilities to the public bundle.

Local helper/API failures should be recorded as debt and retried or bypassed; they do not authorize skipping approval gates.
