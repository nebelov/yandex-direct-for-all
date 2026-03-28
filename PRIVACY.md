# Privacy Policy

This repository is a local-tooling bundle. It does not operate a hosted SaaS service.

## What this repository stores

- source code
- documentation
- install scripts
- reusable skills and MCP bundles

## What must not be committed

- OAuth tokens
- API keys
- `.env` files with live secrets
- client-specific overlays
- any runtime auth artifacts under `.codex/` or `.claude/`

## Local runtime data

When you run auth launchers locally, token files may be created under `./.codex/auth/`.
Those files are local runtime artifacts and are intentionally excluded from version control.

## Third-party services

This bundle may help operators authenticate against Yandex services and other third-party APIs.
Those services have their own privacy policies and access-control rules.
