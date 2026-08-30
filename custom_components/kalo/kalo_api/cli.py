from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Callable
from typing import Any

from . import ApiError, IdentityError, KaloClient, LoginError, TokenError

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_LOGIN = 3
EXIT_IDENTITY = 4
EXIT_API = 5
EXIT_LOGOUT = 6


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kalo",
        description="Read data from the KALO resident portal.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("resident", "fetch the current resident record"),
        ("details", "fetch current consumption details"),
        ("history", "fetch consumption history"),
    ):
        subparsers.add_parser(command, help=help_text)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[], KaloClient] = KaloClient,
    input_fn: Callable[[str], str] = input,
    password_fn: Callable[[str], str] = getpass.getpass,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    username = input_fn("KALO username: ")
    password = password_fn("KALO password: ")
    client = client_factory()
    authenticated = False
    payload: dict[str, Any] | None = None
    exit_code = EXIT_OK

    try:
        client.login(username, password)
        authenticated = True
        payload = _fetch(client, args.command)
    except (LoginError, TokenError) as error:
        print(f"Login failed: {error}", file=sys.stderr)
        exit_code = EXIT_LOGIN
    except IdentityError as error:
        print(f"Could not resolve the logged-in identity: {error}", file=sys.stderr)
        exit_code = EXIT_IDENTITY
    except ApiError as error:
        print(f"KALO API error: {error}", file=sys.stderr)
        exit_code = EXIT_API
    finally:
        if authenticated:
            try:
                client.logout()
            except TokenError as error:
                print(f"Logout failed: {error}", file=sys.stderr)
                if exit_code == EXIT_OK:
                    exit_code = EXIT_LOGOUT

    if payload is not None:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return exit_code


def _fetch(client: KaloClient, command: str) -> dict[str, Any]:
    if command == "resident":
        return client.get_current_resident()
    if command == "details":
        return client.get_current_consumption_details()
    if command == "history":
        return client.get_current_consumption_history()
    raise RuntimeError(f"unsupported command: {command}")
