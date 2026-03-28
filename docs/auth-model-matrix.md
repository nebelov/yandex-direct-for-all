# Auth Model Matrix

| Layer | Можно ли использовать одно ваше приложение для многих пользователей | Нужен ли per-user login/consent | Что получает каждый пользователь | Главный риск | Recommended bundle path |
|---|---|---|---|---|---|
| `Yandex Direct` | Да | Да | свой OAuth token | перепутать token и `Client-Login` | `start_yandex_user_auth.sh` |
| `Yandex Metrika` | Да | Да | свой OAuth token | у токена может не быть доступа к нужному счётчику | `start_yandex_user_auth.sh` |
| `Yandex Audience` | Да | Да | свой OAuth token | у пользователя может не быть прав на нужные сегменты | `start_yandex_user_auth.sh` |
| `Wordstat` | Не в том же виде | Не как основной official path | cloud auth context | спутать Wordstat с Direct-style OAuth | отдельный cloud setup |
| `Yandex Search API` | Не в том же виде | Нет, если service-account path | API key / IAM token / role | раздать cloud credentials как будто это user token | отдельный cloud setup |

## Recommended bundle model

- `Direct/Metrika/Audience` -> ваш approved app + consent пользователя
- `Wordstat/Search API` -> отдельный cloud setup
- operator launcher docs -> `docs/operator-auth-launchers.md`
