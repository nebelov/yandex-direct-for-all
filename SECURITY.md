# Security

## Supported scope

This repository intentionally excludes runtime secrets and client-specific auth artifacts.

Do not publish:

- `.env` files
- OAuth token files
- credentials exports
- local agent state under `.codex/` or `.claude/`

## Reporting

If you find a security issue in the repository contents or auth flow, open a private security report through GitHub Security Advisories if available for the repo owner.

If the issue is simply an accidentally committed secret:

1. do not paste the secret into a public issue
2. rotate the secret immediately
3. remove the file from git history before treating the repository as clean
