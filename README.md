# kalo-api

Unofficial Python client and JSON CLI for the KALO resident portal.

> **Important:** This client relies on undocumented KALO portal interfaces. Provider-side
> changes can break authentication, response mapping, or the CLI without notice. Use it only
> where this kind of automation is permitted.

## Requirements

- Python 3.10 or newer
- An active KALO resident-portal account
- Network access to `meine.kalo.de` and `api.kalo.de`

## Install

From a checkout, create a project-local virtual environment and install the package:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

The `dev` extra adds the test and lint tools. For runtime-only installation, use
`.venv/bin/python -m pip install -e .` instead. Nothing is installed into the host Python
environment.

## Python API

After login, the client resolves the resident and occupancy identifiers automatically from
the validated OIDC identity:

```python
from kalo_api import KaloClient

client = KaloClient()
client.login(username, password)

resident = client.get_current_resident()
details = client.get_current_consumption_details()
history = client.get_current_consumption_history()
```

`username` and `password` are ordinary Python strings supplied by the caller. Keep them in
memory only and do not put credentials in source code, command history, or issue reports.

The explicit methods remain available for callers that already have the identifiers:

```python
resident = client.get_resident(resident_id)
details = client.get_consumption_details(resident_id, billing_unit_id, occupancy_id)
history = client.get_consumption_history(
    resident_id, billing_unit_id, residential_unit_number, occupancy_id
)
```

All API methods return raw provider JSON. Automatic resolution uses the validated ID-token
`sub`, checks it against `account.accountId`, and requires exactly one occupancy record.
Path identifiers are normalized to strings; leading zeroes are preserved when the provider
returns them as strings.

## CLI

The CLI prompts for credentials on every invocation and prints exactly one JSON resource:

```bash
kalo resident
kalo details
kalo history
```

The equivalent module invocation is:

```bash
python -m kalo_api resident
```

The commands do not take usernames, passwords, resident IDs, or other resource identifiers as
arguments. JSON is pretty-printed to stdout; errors go to stderr with a non-zero exit code.
Passwords, tokens, and sessions are never accepted as arguments or persisted.

For example, a successful call has the following shape (provider fields may change):

```json
{
    "account": {
        "accountId": "..."
    },
    "occupancyData": []
}
```

## Security and limitations

- PKCE, state, nonce and JWKS-backed ID-token validation are used.
- Tokens and cookies remain in process memory only.
- The bearer token is sent only to `https://api.kalo.de`.
- There is no general network retry system; HTTP 401 triggers one token refresh and retry.
- JavaScript login steps, MFA and CAPTCHA are not bypassed.
- Multiple occupancy records are rejected instead of guessed.
- No browser automation, keyring, database, server, background jobs or exports are included.

## Development

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/python -m compileall -q src tests tools
```

The live test is manual and opt-in:

```bash
.venv/bin/python tools/smoke_test.py
```

Provider details are intentionally kept in local development notes and are not part of the
public repository.

## Disclaimer

This project is not affiliated with, endorsed by, sponsored by, authorized by, or otherwise
officially connected to KALO. KALO and related names and marks belong to their respective
owners. See [DISCLAIMER.md](DISCLAIMER.md) for the full disclaimer.
