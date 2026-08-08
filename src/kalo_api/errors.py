from __future__ import annotations


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
