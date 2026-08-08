from getpass import getpass

from kalo_api import KaloClient, KaloError


def main():
    username = input("KALO username: ")
    password = getpass("KALO password: ")

    client = KaloClient()

    try:
        token = client.login(username, password)
        print(f"Login succeeded, scopes: {token.get('scope', '<unknown>')}")

        resident = client.get_current_resident()
        print(f"Resident API succeeded: {list(resident)}")

        details = client.get_current_consumption_details()
        print(f"Consumption details succeeded: {list(details.get('currentConsumptions', {}))}")

        history = client.get_current_consumption_history()
        months = sorted(history.get("consumptions", {}))
        print(f"History succeeded: {len(months)} months")
        if months:
            print(f"Period: {months[0]} to {months[-1]}")

    except KaloError as error:
        print(f"Smoke test failed: {type(error).__name__}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
