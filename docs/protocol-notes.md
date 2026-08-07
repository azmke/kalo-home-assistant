# Kalo protocol notes

These notes describe the observed provider flow without storing credentials or token values.

## OIDC

- Issuer: `https://meine.kalo.de/auth/realms/consumer`
- Client ID: `web`
- Authorization response type: `code`
- Redirect URI: `https://meine.kalo.de/bewohnerportal/`
- PKCE: `S256`
- Observed requested scopes: `openid profile email roles`
- Observed effective token scopes: `openid email profile`
- Access token lifetime: 300 seconds
- Refresh token lifetime: 1800 seconds

The callback contains `code`, `state`, `session_state` and `iss`. The token request is
form-encoded and contains `grant_type=authorization_code`, `code`, the same `redirect_uri`,
`code_verifier` and `client_id=web`. No client secret or Authorization header was observed.

Keycloak completes the browser interaction through a current `login-actions/authenticate`
form. Its `session_code`, `execution`, `tab_id`, `client_data` and cookies are short-lived
session data and must be read from the current response, never copied from an old capture.

## Resident API

Base URL: `https://api.kalo.de`

All observed calls use `Authorization: Bearer ...` and returned HTTP 200.

- `GET /resident/v2/residents/{resident_id}`
- `GET /resident/v2/residents/{resident_id}/billing-units/{billing_unit_id}/occupancies/{occupancy_id}/consumption-details`
- `GET /resident/v2/residents/{resident_id}/billing-units/{billing_unit_id}/residential-units/{residential_unit_number}/occupancies/{occupancy_id}/consumptions-report`

The validated ID-token `sub` is the resident identifier used by the API and matches
`account.accountId` in the resident response. The observed response shape provides the
remaining path parameters through one `occupancyData` entry:

- `occupancyData[].uuid` → `occupancy_id`
- `occupancyData[].residentialUnit.billingUnitNumber` → `billing_unit_id`
- `occupancyData[].residentialUnit.residentialUnitNumber` → `residential_unit_number`

The client requires exactly one occupancy entry for automatic resolution and keeps the
residential-unit number as a string. It rejects missing data, identity mismatches and
multiple entries rather than guessing.

The access-token JWT had `aud=account`, `azp=web`, `scope=openid email profile`, and only
generic account roles. The observed API accepts the token; the client therefore does not
invent a different audience requirement. It sends the token only to `api.kalo.de`.

The examples shared during analysis used anonymized IDs. Billing-unit display values and
URL path IDs remain separate inputs in the client.
