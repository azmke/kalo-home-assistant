from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from secrets import token_urlsafe
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.requests_client import OAuth2Session
from joserfc import jwt
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry


class KaloError(Exception):
    """Base exception for the Kalo client."""


class LoginError(KaloError):
    """Raised when the interactive login flow cannot complete."""


class TokenError(KaloError):
    """Raised when token exchange, validation, or refresh fails."""


class IdentityError(KaloError):
    """Raised when the logged-in identity cannot be mapped to a resident."""


class ApiError(KaloError):
    """Raised when the Kalo resident API returns an error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class KaloConfig:
    issuer: str = "https://meine.kalo.de/auth/realms/consumer"
    authorization_endpoint: str = (
        "https://meine.kalo.de/auth/realms/consumer/protocol/openid-connect/auth"
    )
    token_endpoint: str = (
        "https://meine.kalo.de/auth/realms/consumer/protocol/openid-connect/token"
    )
    jwks_uri: str = (
        "https://meine.kalo.de/auth/realms/consumer/protocol/openid-connect/certs"
    )
    client_id: str = "web"
    redirect_uri: str = "https://meine.kalo.de/bewohnerportal/"
    api_base_url: str = "https://api.kalo.de"
    scopes: tuple[str, ...] = ("openid", "profile", "email", "roles")
    timeout: float = 20.0


@dataclass(frozen=True)
class ResidentContext:
    resident_id: str
    billing_unit_id: str
    occupancy_id: str
    residential_unit_number: str


@dataclass(frozen=True)
class _LoginAttempt:
    state: str
    nonce: str
    code_verifier: str
    code_challenge: str


@dataclass(frozen=True)
class _Callback:
    code: str
    state: str
    issuer: str | None


class _LoginFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self.password_field: str | None = None
        self._inside_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "form" and not self._inside_form:
            self._inside_form = True
            self.action = attributes.get("action")
            return

        if tag != "input" or not self._inside_form:
            return

        name = attributes.get("name")
        if not name:
            return

        input_type = (attributes.get("type") or "text").lower()
        self.fields[name] = attributes.get("value") or ""
        if input_type == "password":
            self.password_field = name

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._inside_form:
            self._inside_form = False


class KaloClient:
    def __init__(self, config: KaloConfig | None = None):
        self.config = config or KaloConfig()
        self.auth_session = OAuth2Session(
            client_id=self.config.client_id,
            token_endpoint_auth_method="none",
            redirect_uri=self.config.redirect_uri,
        )
        self.api_session = requests.Session()
        self.public_session = requests.Session()
        self._token: dict[str, Any] | None = None
        self._id_token_claims: dict[str, Any] | None = None
        self._resident_context: ResidentContext | None = None
        self._resident_payload: dict[str, Any] | None = None

    def login(self, username: str, password: str) -> dict[str, Any]:
        self._id_token_claims = None
        self._resident_context = None
        self._resident_payload = None
        attempt = self._new_attempt()
        authorization_url, _ = self.auth_session.create_authorization_url(
            self.config.authorization_endpoint,
            state=attempt.state,
            nonce=attempt.nonce,
            scope=" ".join(self.config.scopes),
            code_challenge=attempt.code_challenge,
            code_challenge_method="S256",
        )

        page_or_callback = self._load_authorization_page(authorization_url)
        if isinstance(page_or_callback, _Callback):
            callback = page_or_callback
        else:
            response = page_or_callback
            form_action, fields, password_field = self._read_login_form(response)
            fields["username"] = username
            fields[password_field] = password
            fields.setdefault("credentialId", "")
            self._validate_navigation_url(form_action)
            response = self.auth_session.post(
                form_action,
                data=fields,
                allow_redirects=False,
                timeout=self.config.timeout,
                withhold_token=True,
            )
            callback = self._follow_login_redirects(response)

        if callback.state != attempt.state:
            raise LoginError("authorization state does not match")
        if callback.issuer is not None and callback.issuer != self.config.issuer:
            raise LoginError("authorization issuer does not match")

        return self._exchange_code(callback.code, attempt)

    def get_resident(self, resident_id: str) -> dict[str, Any]:
        return self._get_json(f"/resident/v2/residents/{self._segment(resident_id)}")

    def get_current_resident(self) -> dict[str, Any]:
        """Return the resident record for the identity established by login."""
        _, payload = self._resolve_resident()
        return payload

    def get_current_consumption_details(self) -> dict[str, Any]:
        """Return consumption details using the logged-in resident context."""
        context, _ = self._resolve_resident()
        return self.get_consumption_details(
            context.resident_id,
            context.billing_unit_id,
            context.occupancy_id,
        )

    def get_current_consumption_history(self) -> dict[str, Any]:
        """Return consumption history using the logged-in resident context."""
        context, _ = self._resolve_resident()
        return self.get_consumption_history(
            context.resident_id,
            context.billing_unit_id,
            context.residential_unit_number,
            context.occupancy_id,
        )

    def get_consumption_details(
        self,
        resident_id: str,
        billing_unit_id: str,
        occupancy_id: str,
    ) -> dict[str, Any]:
        path = (
            f"/resident/v2/residents/{self._segment(resident_id)}"
            f"/billing-units/{self._segment(billing_unit_id)}"
            f"/occupancies/{self._segment(occupancy_id)}/consumption-details"
        )
        return self._get_json(path)

    def get_consumption_history(
        self,
        resident_id: str,
        billing_unit_id: str,
        residential_unit_number: str,
        occupancy_id: str,
    ) -> dict[str, Any]:
        path = (
            f"/resident/v2/residents/{self._segment(resident_id)}"
            f"/billing-units/{self._segment(billing_unit_id)}"
            f"/residential-units/{self._segment(residential_unit_number)}"
            f"/occupancies/{self._segment(occupancy_id)}/consumptions-report"
        )
        return self._get_json(path)

    def _new_attempt(self) -> _LoginAttempt:
        code_verifier = token_urlsafe(32)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return _LoginAttempt(
            state=token_urlsafe(32),
            nonce=token_urlsafe(32),
            code_verifier=code_verifier,
            code_challenge=code_challenge,
        )

    def _load_authorization_page(self, url: str) -> requests.Response | _Callback:
        response = self.auth_session.get(
            url,
            allow_redirects=False,
            timeout=self.config.timeout,
            withhold_token=True,
        )
        for _ in range(10):
            if not response.is_redirect:
                if response.status_code >= 400:
                    raise LoginError("authorization endpoint returned an error")
                return response

            target = urljoin(response.url, response.headers.get("Location", ""))
            callback = self._callback_from_url(target)
            if callback is not None:
                return callback
            self._validate_navigation_url(target)
            if response.status_code not in (301, 302, 303):
                raise LoginError("unsupported authorization redirect")
            response = self.auth_session.get(
                target,
                allow_redirects=False,
                timeout=self.config.timeout,
                withhold_token=True,
            )
        raise LoginError("authorization redirect limit exceeded")

    def _follow_login_redirects(self, response: requests.Response) -> _Callback:
        for _ in range(10):
            if not response.is_redirect:
                raise LoginError("login did not return an authorization callback")

            target = urljoin(response.url, response.headers.get("Location", ""))
            callback = self._callback_from_url(target)
            if callback is not None:
                return callback
            self._validate_navigation_url(target)
            if response.status_code not in (301, 302, 303):
                raise LoginError("unsupported login redirect")
            response = self.auth_session.get(
                target,
                allow_redirects=False,
                timeout=self.config.timeout,
                withhold_token=True,
            )
        raise LoginError("login redirect limit exceeded")

    def _read_login_form(self, response: requests.Response) -> tuple[str, dict[str, str], str]:
        parser = _LoginFormParser()
        parser.feed(response.text)
        if not parser.action or not parser.password_field:
            raise LoginError("could not find the Kalo login form")
        action = urljoin(response.url, parser.action)
        return action, parser.fields, parser.password_field

    def _callback_from_url(self, url: str) -> _Callback | None:
        if not self._is_callback_url(url):
            return None

        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        if query.get("error"):
            raise LoginError("authorization was rejected")
        code = self._first(query, "code")
        state = self._first(query, "state")
        if not code or not state:
            raise LoginError("authorization callback is missing code or state")
        return _Callback(code=code, state=state, issuer=self._first(query, "iss"))

    def _exchange_code(self, code: str, attempt: _LoginAttempt) -> dict[str, Any]:
        try:
            token = self.auth_session.fetch_token(
                self.config.token_endpoint,
                grant_type="authorization_code",
                code=code,
                redirect_uri=self.config.redirect_uri,
                code_verifier=attempt.code_verifier,
            )
        except (OAuthError, requests.RequestException) as exc:
            raise TokenError("token exchange failed") from exc

        if not token.get("access_token") or not token.get("id_token"):
            raise TokenError("token response is missing a required token")
        if str(token.get("token_type", "")).lower() != "bearer":
            raise TokenError("token response is not a bearer token")

        self._id_token_claims = self._validate_id_token(str(token["id_token"]), attempt.nonce)
        self._set_token(dict(token))
        return dict(self._token)

    def _validate_id_token(self, id_token: str, nonce: str) -> dict[str, Any]:
        try:
            response = self.public_session.get(
                self.config.jwks_uri,
                timeout=self.config.timeout,
            )
            if response.status_code >= 400:
                raise TokenError("JWKS endpoint returned an error")
            key_set = KeySet.import_key_set(response.json())
            decoded = jwt.decode(id_token, key_set, algorithms={"RS256"})
            registry = JWTClaimsRegistry(
                iss={"essential": True, "value": self.config.issuer},
                sub={"essential": True},
                aud={"essential": True, "value": self.config.client_id},
                exp={"essential": True},
                iat={"essential": True},
                nonce={"essential": True, "value": nonce},
                leeway=60,
            )
            registry.validate(decoded.claims)
            if decoded.claims.get("azp") not in (None, self.config.client_id):
                raise TokenError("ID token authorized party does not match")
            return dict(decoded.claims)
        except TokenError:
            raise
        except Exception as exc:
            raise TokenError("ID token validation failed") from exc

    def _set_token(self, token: dict[str, Any]) -> None:
        now = time.time()
        if "expires_at" not in token and token.get("expires_in") is not None:
            token["expires_at"] = now + float(token["expires_in"])
        if "refresh_expires_at" not in token and token.get("refresh_expires_in") is not None:
            token["refresh_expires_at"] = now + float(token["refresh_expires_in"])
        self._token = token
        self.auth_session.token = token

    def _ensure_access_token(self) -> str:
        if self._token is None or not self._token.get("access_token"):
            raise TokenError("login is required")
        expires_at = self._token.get("expires_at")
        if expires_at is not None and time.time() >= float(expires_at) - 30:
            self._refresh()
        return str(self._token["access_token"])

    def _refresh(self) -> None:
        if self._token is None or not self._token.get("refresh_token"):
            raise TokenError("refresh token is unavailable")
        old_refresh_token = self._token["refresh_token"]
        try:
            refreshed = dict(
                self.auth_session.refresh_token(
                    self.config.token_endpoint,
                    refresh_token=old_refresh_token,
                )
            )
        except (OAuthError, requests.RequestException) as exc:
            raise TokenError("token refresh failed") from exc
        if not refreshed.get("access_token"):
            raise TokenError("refresh response is missing an access token")
        refreshed.setdefault("refresh_token", old_refresh_token)
        self._set_token(refreshed)

    def _resolve_resident(self) -> tuple[ResidentContext, dict[str, Any]]:
        if self._resident_context is not None and self._resident_payload is not None:
            return self._resident_context, self._resident_payload

        claims = self._id_token_claims
        if claims is None:
            raise IdentityError("login is required before resolving the resident")
        resident_id = self._identifier(claims.get("sub"), "ID token subject")
        payload = self.get_resident(resident_id)

        account = payload.get("account")
        if not isinstance(account, dict):
            raise IdentityError("resident response has no account")
        account_id = self._identifier(account.get("accountId"), "resident account ID")
        if account_id != resident_id:
            raise IdentityError("ID token subject does not match the resident account")

        occupancy_data = payload.get("occupancyData")
        if not isinstance(occupancy_data, list) or not occupancy_data:
            raise IdentityError("resident response has no occupancy data")
        if len(occupancy_data) != 1:
            raise IdentityError("resident response contains multiple occupancy records")

        occupancy = occupancy_data[0]
        if not isinstance(occupancy, dict):
            raise IdentityError("resident response contains invalid occupancy data")
        residential_unit = occupancy.get("residentialUnit")
        if not isinstance(residential_unit, dict):
            raise IdentityError("occupancy data has no residential unit")

        context = ResidentContext(
            resident_id=resident_id,
            billing_unit_id=self._identifier(
                residential_unit.get("billingUnitNumber"),
                "billing unit ID",
            ),
            occupancy_id=self._identifier(occupancy.get("uuid"), "occupancy ID"),
            residential_unit_number=self._identifier(
                residential_unit.get("residentialUnitNumber"),
                "residential unit number",
            ),
        )
        self._resident_context = context
        self._resident_payload = payload
        return context, payload

    def _get_json(self, path: str) -> dict[str, Any]:
        access_token = self._ensure_access_token()
        url = f"{self.config.api_base_url.rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = self.api_session.get(url, headers=headers, timeout=self.config.timeout)
        if response.status_code == 401:
            self._refresh()
            access_token = self._ensure_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            response = self.api_session.get(url, headers=headers, timeout=self.config.timeout)
        if response.status_code >= 400:
            raise ApiError("Kalo API request failed", response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError("Kalo API returned invalid JSON", response.status_code) from exc
        if not isinstance(payload, dict):
            raise ApiError("Kalo API returned an unexpected JSON value", response.status_code)
        return payload

    def _validate_navigation_url(self, url: str) -> None:
        parsed = urlparse(url)
        allowed_hosts = {
            urlparse(self.config.issuer).netloc,
            urlparse(self.config.redirect_uri).netloc,
        }
        if parsed.scheme != "https" or parsed.netloc not in allowed_hosts:
            raise LoginError("login redirect points to an unexpected host")

    def _is_callback_url(self, url: str) -> bool:
        actual = urlparse(url)
        expected = urlparse(self.config.redirect_uri)
        return (
            actual.scheme == expected.scheme
            and actual.netloc == expected.netloc
            and actual.path == expected.path
            and not actual.fragment
        )

    @staticmethod
    def _identifier(value: Any, name: str) -> str:
        if value is None or isinstance(value, (dict, list, tuple, set)):
            raise IdentityError(f"resident response has no valid {name}")
        identifier = str(value)
        if not identifier:
            raise IdentityError(f"resident response has no valid {name}")
        return identifier

    @staticmethod
    def _first(query: dict[str, list[str]], name: str) -> str | None:
        values = query.get(name)
        return values[0] if values else None

    @staticmethod
    def _segment(value: str) -> str:
        if not value:
            raise ValueError("path identifiers must not be empty")
        return quote(str(value), safe="")
