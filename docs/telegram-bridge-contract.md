# Telegram Bridge Contract

Telegram or chat bridges are operator surfaces, not background task runners.

Rules for production deployments:

- Send short human-readable checkpoints when there is meaningful progress, a blocker, or a decision request.
- Do not expose local machine paths, raw IDs, tokens, board IDs, or private artifact locations in chat by default.
- Treat a status reply as a checkpoint, not as the end of a long-running workstream.
- Retry local send-format errors locally; do not let chat helper failures block core Direct or GitHub work.

The portable plugin does not require Telegram. Projects that use Telegram should keep bridge credentials and message ledgers outside this repository.
