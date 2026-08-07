from getpass import getpass

from kalo_api import KaloClient
from kalo_api.client import KaloError


def main():
    username = input("Kalo Benutzername: ")
    password = getpass("Kalo Passwort: ")

    client = KaloClient()

    try:
        token = client.login(username, password)
        print(f"Login erfolgreich, Scopes: {token.get('scope', '<unbekannt>')}")

        resident = client.get_current_resident()
        print(f"Resident API erfolgreich: {list(resident)}")

        details = client.get_current_consumption_details()
        print(f"Verbrauchsdetails erfolgreich: {list(details.get('currentConsumptions', {}))}")

        history = client.get_current_consumption_history()
        months = sorted(history.get("consumptions", {}))
        print(f"Historie erfolgreich: {len(months)} Monate")
        if months:
            print(f"Zeitraum: {months[0]} bis {months[-1]}")

    except KaloError as error:
        print(f"Smoke-Test fehlgeschlagen: {type(error).__name__}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()