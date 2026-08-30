# KALO for Home Assistant

An unofficial HACS integration for the KALO resident portal. It imports monthly heating and
warm-water consumption for every residential unit associated with a KALO account.

> KALO does not provide a public API for this use case. Portal changes can break this integration
> without notice. This project is not affiliated with or endorsed by KALO.

## Features

- UI setup with KALO email address or username and password.
- One Home Assistant device per residential unit, named from its address rather than a KALO UUID.
- Heating and warm-water sensors for each unit.
- Monthly external long-term statistics, preserving older months beyond KALO's rolling window
  without creating duplicate points.
- Automatic unit discovery on every poll and a **Rediscover residential units** button.
- Configurable polling interval (24 to 168 hours) and retry budget; defaults to a 24-hour poll
  with two daily retries after a failure.
- Home Assistant reauthentication for invalid credentials and a Repair flow after exhausted
  retries.
- English and German user-interface translations.

## Installation

1. In HACS, add this repository as a custom repository of type **Integration**.
2. Install **KALO** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, then select **KALO**.
4. Enter the KALO account credentials. Configure the polling interval and retry count later from
   the integration's **Configure** dialog if needed.

KALO credentials are stored in Home Assistant's config entry. They are not exposed through
entity attributes, diagnostics, or integration logs. Protect Home Assistant's `.storage`
directory and backups as you would for other Home Assistant credentials.

## Residential units and history

One KALO account can be associated with more than one residential unit. The integration creates
one device for each unit, using the KALO address as its display name. Internal resident,
occupancy, and residential-unit UUIDs are never shown in the Home Assistant UI.

KALO returns monthly values for a limited rolling period. The integration imports each response
as external long-term statistics keyed by calendar month. A newer value replaces the same month;
months no longer included in a later KALO response remain available.

Add two native **Statistics graph** cards to a dashboard: choose the address-labelled external
statistic for **Heating / Heizung** and **Warm water / Warmwasser**, use a monthly period, and set
the desired time range. These long-term statistics are retained independently of the normal
Recorder state-history purge.

## Updates and recovery

The default poll runs every 24 hours. A failed poll is retried on the following two days. Once the
configured retry limit is exhausted, polling pauses and Home Assistant creates a Repair issue.
Submitting that repair, or pressing **Rediscover residential units**, immediately resumes polling
and refreshes the account's units. Invalid credentials start Home Assistant's standard
reauthentication flow.

## Development

Use only a project-local virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt
.venv/bin/pytest -q
.venv/bin/ruff check .
```

## License

See [LICENSE](LICENSE), [SECURITY.md](SECURITY.md), and [DISCLAIMER.md](DISCLAIMER.md).
