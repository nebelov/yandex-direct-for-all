# Official amoCRM notes used by this skill

- Private integration risk:
  amoCRM states that when a private integration is connected on an account that is not a technical account, the client may need to sign a waiver of amoCRM technical support, and this condition is irreversible for that account.

- Integration form:
  Required fields include name, description, redirect URI, icon, and permissions.

- Redirect URI:
  The `redirect_uri` used in token exchange must exactly match the redirect URI stored in the integration settings.

- Uninstall hook:
  Optional.

- Duplicate control:
  Enable only if the integration really implements duplicate-control behavior.

- Multiple sources:
  Enable only if the integration manages its own sources via API.

- Token exchange endpoint:
  `POST https://{subdomain}.amocrm.ru/oauth2/access_token`

- Refresh token lifetime:
  3 months without refresh activity.

- Access token lifetime:
  1 day.
