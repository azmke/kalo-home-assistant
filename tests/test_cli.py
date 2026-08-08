from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from kalo_api.cli import EXIT_API, EXIT_IDENTITY, EXIT_OK, main
from kalo_api.errors import ApiError, IdentityError


@dataclass
class FakeClient:
    payload: dict
    error: Exception | None = None
    logged_in: tuple[str, str] | None = None

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def _result(self) -> dict:
        if self.error:
            raise self.error
        return self.payload

    def get_current_resident(self) -> dict:
        return self._result()

    def get_current_consumption_details(self) -> dict:
        return self._result()

    def get_current_consumption_history(self) -> dict:
        return self._result()


def test_resident_command_prints_pretty_json(capsys: pytest.CaptureFixture[str]):
    client = FakeClient({"account": {"accountId": "resident"}})

    result = main(
        ["resident"],
        client_factory=lambda: client,
        input_fn=lambda _: "user",
        password_fn=lambda _: "secret",
    )

    assert result == EXIT_OK
    assert client.logged_in == ("user", "secret")
    assert json.loads(capsys.readouterr().out) == client.payload


def test_identity_error_is_written_to_stderr(capsys: pytest.CaptureFixture[str]):
    client = FakeClient({}, IdentityError("identity failed"))

    result = main(
        ["details"],
        client_factory=lambda: client,
        input_fn=lambda _: "user",
        password_fn=lambda _: "secret",
    )

    captured = capsys.readouterr()
    assert result == EXIT_IDENTITY
    assert "identity failed" in captured.err
    assert captured.out == ""


def test_api_error_is_written_to_stderr(capsys: pytest.CaptureFixture[str]):
    client = FakeClient({}, ApiError("request failed", 503))

    result = main(
        ["history"],
        client_factory=lambda: client,
        input_fn=lambda _: "user",
        password_fn=lambda _: "secret",
    )

    captured = capsys.readouterr()
    assert result == EXIT_API
    assert "request failed" in captured.err
    assert captured.out == ""
