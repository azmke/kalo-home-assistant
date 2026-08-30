<p align="center">
  <img src="https://raw.githubusercontent.com/azmke/kalo-home-assistant/main/custom_components/kalo/brand/icon.png" alt="KALO for Home Assistant" width="112">
</p>

# KALO for Home Assistant

This is an unofficial HACS integration for the KALO resident portal. It adds monthly heating and
warm-water consumption to Home Assistant for every residential unit linked to a KALO account.

## Highlights

- Setup entirely through the Home Assistant UI.
- One device per residential unit, named from its address.
- Separate heating and warm-water consumption sensors.
- Monthly long-term statistics that retain history beyond KALO's rolling data window.
- Automatic discovery of newly assigned residential units.
- German and English user-interface translations.

## Requirements

- Home Assistant 2026.8.0 or newer.
- HACS.
- An active KALO resident-portal account.

## Installation

1. Open **HACS** in Home Assistant and add this repository as a custom repository of type
   **Integration**.
2. Install **KALO** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, then select **KALO**.
4. Enter the email address or username and password used for the KALO resident portal.

The integration stores credentials in Home Assistant's config entry. They are not included in
entity attributes, diagnostics, or integration logs. Protect your Home Assistant storage and
backups as you would for any other integration credentials.

## Entities and residential units

Each residential unit returned by KALO appears as a Home Assistant device. Its display name uses
the KALO address; resident, occupancy, and residential-unit UUIDs are never exposed in the UI.

| Entity | Purpose |
| --- | --- |
| Heating consumption | Latest reported monthly heating consumption in kWh |
| Warm water consumption | Latest reported monthly warm-water consumption in kWh |

New residential units are discovered automatically during the regular update. To trigger an
immediate rediscovery, use **Reload** from the KALO integration's three-dot menu. Existing devices
and their historic statistics are retained when KALO returns a changing set of residential units.

## History and dashboard charts

KALO returns a limited, rolling range of monthly values. This integration writes those values as
external long-term statistics, using the calendar month as the unique key. A corrected KALO value
replaces the existing point for that month; months no longer returned by KALO remain available.

To create the two history charts:

1. Edit a dashboard and add a **Statistics graph** card.
2. Select the address-labelled statistic ending in **Heating / Heizung**.
3. Choose a monthly period, the **Change** statistic type, and the desired time range.
4. Add a second card for **Warm water / Warmwasser**.

Long-term statistics are retained independently of the normal Recorder state-history purge.

## Updates and recovery

By default, KALO is queried every 24 hours. The polling interval can be set from 24 to 168 hours
in the integration's **Configure** dialog. After a failed poll, the integration retries once on
each of the following days. The default retry budget is two retries, for three attempts in total.

If that budget is exhausted, Home Assistant creates a Repair issue and polling pauses. Submit the
repair, or reload the integration, to resume polling immediately. Invalid credentials start Home
Assistant's standard reauthentication flow.

## Development

Use a project-local virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt
.venv/bin/pytest -q
.venv/bin/ruff check .
```

## License

This project is licensed under the [MIT License](LICENSE).

## Disclaimer

This project is not affiliated with, endorsed by, or supported by KALO. See [DISCLAIMER.md](DISCLAIMER.md) for the full disclaimer.
