from getpass import getpass

from kalo_api import KaloClient
from kalo_api.client import KaloError


def main():
    username = input("Kalo Benutzername: ")
    password = getpass("Kalo Passwort: ")

    resident_id = input("Resident-ID: ")
    billing_unit_id = input("Billing-Unit-ID: ")
    occupancy_id = input("Occupancy-ID: ")
    residential_unit_number = input("Residential-Unit-Nummer: ")

    client = KaloClient()

    try:
        token = client.login(username, password)
        print(f"Login erfolgreich, Scopes: {token.get('scope', '<unbekannt>')}")

        resident = client.get_resident(resident_id)
        print(f"Resident API erfolgreich: {list(resident)}")

        details = client.get_consumption_details(
            resident_id,
            billing_unit_id,
            occupancy_id,
        )
        print(f"Verbrauchsdetails erfolgreich: {list(details.get('currentConsumptions', {}))}")

        history = client.get_consumption_history(
            resident_id,
            billing_unit_id,
            residential_unit_number,
            occupancy_id,
        )
        months = sorted(history.get("consumptions", {}))
        print(f"Historie erfolgreich: {len(months)} Monate")
        if months:
            print(f"Zeitraum: {months[0]} bis {months[-1]}")

    except KaloError as error:
        print(f"Smoke-Test fehlgeschlagen: {type(error).__name__}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()