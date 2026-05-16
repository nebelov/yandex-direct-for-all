# Current Runtime Model

This repository is a portable plugin bundle plus a reference operating model for production agents.

The portable contract is:

- install or run from `<repo-root>/plugins/yandex-direct-for-all`;
- keep reusable skills, scripts, templates, and MCP servers inside the plugin;
- keep client overlays, credentials, runtime artifacts, and raw proof bundles outside the public repository;
- use repository validators before publishing any changed bundle.

Production deployments may add Telegram bridges, memory ledgers, schedulers, or project-specific runners. Those are deployment contracts, not mandatory install steps for every user of the public plugin.
