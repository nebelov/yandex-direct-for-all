# Contributing

## Before opening a PR

Run:

```bash
bash ./plugins/yandex-direct-for-all/scripts/validate_bundle.sh
```

## Scope rules

- Keep the bundle self-contained inside `plugins/yandex-direct-for-all/`.
- Do not reintroduce docs that force manual `.env` filling for the default `Direct / Metrika / Audience` auth path.
- Keep `Wordstat / Search API` documented as a separate cloud auth model.
- Preserve the post-auth read-only preflight flow.

## Secrets and local artifacts

Never commit:

- `.env`
- `oauth*.json`
- `*token*.json`
- `credentials*.json`
- `.codex/`
- `.claude/`
- any client-specific overlay or runtime auth artifact

## Documentation changes

If you change auth behavior, update all of:

- `README.md`
- `AI_ONBOARDING.md`
- `docs/operator-auth-launchers.md`
- `docs/oauth-and-app-setup.md`
- `plugins/yandex-direct-for-all/README.md`
- `plugins/yandex-direct-for-all/docs/operator-auth-launchers.md`

## Validation expectation

Changes are not publish-ready until `validate_bundle.sh` passes.

## Release checklist

- update public metadata in `plugins/yandex-direct-for-all/.codex-plugin/plugin.json`
- keep root docs and plugin-root docs consistent
- verify no private paths, hostnames or handoff files leaked into public tree
