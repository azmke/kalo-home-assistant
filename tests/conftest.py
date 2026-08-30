from __future__ import annotations

from typing import Any


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        url: str = "",
        text: str = "",
        headers: dict[str, str] | None = None,
        payload: object | None = None,
    ):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.headers = headers or {}
        self._payload = payload

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308)

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


LOGIN_HTML = """
<html>
  <form action="/auth/realms/consumer/login-actions/authenticate?session_code=current">
    <input type="hidden" name="execution" value="execution-value">
    <input type="hidden" name="tab_id" value="tab-value">
    <input type="text" name="username" value="">
    <input type="password" name="password" value="">
    <input type="hidden" name="credentialId" value="">
  </form>
</html>
"""


RESIDENT_PAYLOAD: dict[str, Any] = {
    "account": {"accountId": "resident"},
    "occupancyData": [
        {
            "uuid": "occupancy",
            "residentialUnit": {
                "uuid": "residential-unit",
                "billingUnitNumber": 654815,
                "residentialUnitNumber": 15,
            },
        }
    ],
}
