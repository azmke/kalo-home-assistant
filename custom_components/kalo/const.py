"""Constants for the KALO integration."""

from datetime import timedelta

DOMAIN = "kalo"
PLATFORMS = ["sensor", "button"]

CONF_POLL_INTERVAL_HOURS = "poll_interval_hours"
CONF_MAX_RETRIES = "max_retries"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

DEFAULT_POLL_INTERVAL_HOURS = 24
DEFAULT_MAX_RETRIES = 2
RETRY_INTERVAL = timedelta(days=1)
MIN_POLL_INTERVAL_HOURS = 24
MAX_POLL_INTERVAL_HOURS = 168
MAX_RETRIES = 10

CONSUMPTION_TYPES = ("HEAT", "WARM_WATER")
