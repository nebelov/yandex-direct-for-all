---
name: amocrm-api-control
description: Use when the task is to get or use amoCRM OAuth access, inspect pipelines/statuses/fields, work with amoCRM data over API, prepare full-control private integrations, or build amoCRM-driven retargeting automation for Yandex Audiences and VK Ads without relying on the web UI except for one-time OAuth setup.
---

# amoCRM API Control

Use this skill for amoCRM/kommo API work when the goal is durable OAuth access and programmatic control.

## When to use

- The user wants full amoCRM API control.
- The user wants `pipeline/stage -> retargeting audience` automation.
- You need to inspect pipelines, statuses, fields, contacts, leads, or account schema via API.
- You need to obtain or refresh amoCRM OAuth tokens.

## Important risk

Official amoCRM docs state that creating a private integration on a non-technical account can require an irreversible waiver of part of amoCRM technical support. Do not hide this. If the user explicitly accepts the private-integration path, proceed; otherwise stop.

## Canonical setup path

1. Prefer an existing integration if one already exists.
2. If the project already has a local amo seed/credentials file, prefer that over repeating browser OAuth.
3. For `amoCRM stage -> VK Ads audience`, prefer the native amoCRM Digital Pipeline integration `Реклама ВКонтакте` before designing any custom sync.
4. If a new integration is required and the user wants full control, a private integration is acceptable.
5. For a single-account technical setup, prefer a local callback listener you control from this machine.
6. Exchange `authorization_code` to `access_token/refresh_token`.
7. Save credentials locally.
8. Fetch and persist account schema read-only before writing any business logic.

## Redirect URI rule

- `redirect_uri` must exactly match the value stored in the amoCRM integration.
- Do not use placeholder domains like `example.com`.
- For single-account local technical control, the default technical callback is:

`http://localhost:8031/callback`

Use it only if the UI accepts it. If amoCRM rejects non-SSL localhost in this account, stop and switch to a real managed HTTPS domain.

## Scripts

### Exchange or refresh tokens

`scripts/exchange_amocrm_token.py`

Examples:

```bash
python3 /Users/vitalijtravin/.codex/skills/amocrm-api-control/scripts/exchange_amocrm_token.py \
  --subdomain pksclimat2 \
  --client-id XXX \
  --client-secret XXX \
  --redirect-uri http://localhost:8031/callback \
  --code XXX \
  --output /abs/path/amocrm_oauth_credentials.json
```

```bash
python3 /Users/vitalijtravin/.codex/skills/amocrm-api-control/scripts/exchange_amocrm_token.py \
  --subdomain pksclimat2 \
  --client-id XXX \
  --client-secret XXX \
  --redirect-uri http://localhost:8031/callback \
  --refresh-token XXX \
  --output /abs/path/amocrm_oauth_credentials.json
```

### Local callback listener

`scripts/amocrm_local_callback_server.py`

Use this when you need a temporary local callback URL for the authorization-code flow.

### Read-only schema dump

`scripts/fetch_amocrm_schema.py`

Example:

```bash
python3 /Users/vitalijtravin/.codex/skills/amocrm-api-control/scripts/fetch_amocrm_schema.py \
  --credentials /abs/path/amocrm_oauth_credentials.json \
  --output-dir /abs/path/amocrm-schema
```

## Minimal working pattern

For a new account:

1. Confirm whether private integration is acceptable.
2. If yes, use the local callback listener path first.
3. Save credentials JSON to disk.
4. Dump pipelines, statuses, lead fields, and contact fields.
5. Only then plan mutations or automation.

## Retargeting automation pattern

For `stage -> audience` sync:

- amoCRM source of truth: pipeline + status + lead/contact identifiers
- Yandex Audiences target: hashed email/phone CSV batches or API uploads
- VK Ads target: custom audience uploads or native platform audience sync
- If the requirement is specifically `certain funnel + certain stage -> VK audience`, check the native amoCRM trigger `Реклама ВКонтакте` first. It keeps contacts in `Active` while the deal is in the configured stage and moves them to `Inactive` when the deal leaves the stage or the user dismisses the ad.
- Native amoCRM/VK limitation: once the contact lands in `Inactive`, a later return to the same stage will not move them back to `Active`.
- add/remove logic must be explicit per status transition
- always handle dedupe and re-entry into a stage

## References

Read as needed:

- `references/official-notes.md`
