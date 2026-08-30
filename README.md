# kalo-api

Unofficial Python client, JSON CLI, and Home Assistant/HACS integration for the KALO
resident portal.

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

client.logout()
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
`sub` and checks it against `account.accountId`. `get_current_resident_contexts()` returns
every occupancy record; the legacy `get_current_*` methods intentionally still require exactly
one occupancy record.
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
After a successful login, each CLI command revokes its access token before exiting.

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
- `logout()` revokes the current access token and clears local authentication state.
- The bearer token is sent only to `https://api.kalo.de`.
- There is no general network retry system; HTTP 401 triggers one token refresh and retry.
- JavaScript login steps, MFA and CAPTCHA are not bypassed.
- Multiple occupancy records can be resolved through `get_current_resident_contexts()`.
- No browser automation, keyring, database, server, background jobs or exports are included.

## Home Assistant / HACS

The repository contains one HACS integration at `custom_components/kalo`. Add this repository
as a custom **Integration** repository in HACS, install **KALO**, then restart Home Assistant
and add **KALO** from *Settings → Devices & services*.

The configuration flow asks for the KALO email address or username and password. Home Assistant
stores these as config-entry credentials: they are never included in entity attributes, logs,
or diagnostics. Protect Home Assistant's `.storage` directory and its backups, as you would for
all Home Assistant credentials.

The optional polling settings are available in the integration's *Configure* dialog:

- Polling interval: 24 to 168 hours (24 hours by default).
- Retries: 0 to 10 retries after a failed poll (2 by default, so three attempts in total).

After a failure, the integration retries once per day. Once the retry budget is exhausted, it
pauses polling and opens a Home Assistant repair. Submitting the repair or pressing **Rediscover
residential units** starts a new attempt immediately. Authentication failures instead start the
standard Home Assistant reauthentication flow.

One configured KALO account can contain multiple residential units. Each unit becomes a Home
Assistant device, named with its KALO address rather than an internal identifier, and has two
sensors: heating consumption and warm-water consumption. The rediscovery button and every normal
poll re-read the resident data, so newly assigned units are added automatically. Existing devices
are never deleted by rediscovery.

For each unit and consumption type, the integration imports KALO's monthly values as Home
Assistant external long-term statistics. Values are keyed by month, so a later response replaces
only the same month and retains months that have fallen out of KALO's rolling response window.
There are no duplicated monthly points. Add two native **Statistics graph** cards in the dashboard
editor, select the address-labelled external statistic for heating and warm water, and use a
monthly period. The statistics graph card supports external statistic IDs and long-term statistics
are retained independently of the normal Recorder purge period.

## Development

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/python -m compileall -q custom_components tests tests_home_assistant tools
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
