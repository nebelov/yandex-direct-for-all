# Auth Model Matrix

| Layer | Reusable app for many users | Per-user consent | Auth artifact | Recommended bundle path |
|---|---|---|---|---|
| `Direct` | Yes | Yes | user OAuth token | `start_yandex_user_auth.sh` |
| `Metrika` | Yes | Yes | user OAuth token | `start_yandex_user_auth.sh` |
| `Audience` | Yes | Yes | user OAuth token | `start_yandex_user_auth.sh` |
| `Wordstat` | Not in the same official model | Usually no | IAM token / API key / cloud role | separate cloud setup |
| `Search API` | Not in the same official model | Usually no | IAM token / API key / cloud role | separate cloud setup |

## Bundle rule

- `Direct/Metrika/Audience` -> operator app + user consent is valid
- `Wordstat/Search API` -> separate cloud setup
- launcher details -> `docs/operator-auth-launchers.md`
