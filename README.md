# kalo-api

Small local Python client for the Kalo resident portal.

## Setup

Create and use the project-local virtual environment:

```text
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Nothing is installed into the host Python environment. The `.venv` directory is ignored by Git.

## Current scope

The client implements the Kalo Keycloak authorization-code flow with PKCE and the three
observed resident API calls. Access and refresh tokens stay in process memory. A new login
is required after the process ends.

The observed provider values are:

- issuer: `https://meine.kalo.de/auth/realms/consumer`
- client: `web`
- redirect URI: `https://meine.kalo.de/bewohnerportal/`
- scopes requested by the portal: `openid profile email roles`
- effective token scopes observed: `openid email profile`
- access-token lifetime observed: 300 seconds
- refresh-token lifetime observed: 1800 seconds

The login form is loaded from the current Keycloak response. Its short-lived form parameters
and cookies are not hardcoded or persisted. Passwords, codes, verifiers, cookies and tokens
must not be logged or committed.

## Minimal usage

```python
from kalo_api import KaloClient

client = KaloClient()
client.login(username, password)
resident = client.get_resident(resident_id)
history = client.get_consumption_history(
    resident_id,
    billing_unit_id,
    residential_unit_number,
    occupancy_id,
)
```

The bearer token is sent only to `https://api.kalo.de`. The API returns the provider JSON
without adding a larger domain model. `YYYY-MM`, `estimated`, reference values, percentages,
units and real zero values are preserved.

The first version intentionally has no browser automation, keyring, database, server,
background jobs, exports or automatic retry system. If the HTTP login requires JavaScript,
MFA or CAPTCHA, the login implementation stops with an error rather than bypassing that
interaction.
