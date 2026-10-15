"""Constants for the Cashlytics integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "cashlytics"
MANUFACTURER: Final = "Cashlytics"

# Device identifier of an account: ACCOUNT_DEVICE_PREFIX + account id
ACCOUNT_DEVICE_PREFIX: Final = "account_"

# REST API version this integration speaks (apiVersion of /api/v1/health)
SUPPORTED_API_VERSION: Final = 1

CONF_FORECAST_MONTHS: Final = "forecast_months"
CONF_UPCOMING_DAYS: Final = "upcoming_days"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)
DEFAULT_FORECAST_MONTHS: Final = 3
DEFAULT_UPCOMING_DAYS: Final = 7

MIN_SCAN_INTERVAL_MINUTES: Final = 5
MAX_SCAN_INTERVAL_MINUTES: Final = 240

# Days of scheduled payments kept in memory for the calendar's current event
CALENDAR_LOOKAHEAD_DAYS: Final = 31
# Longest range the API returns in one request
MAX_PAYMENT_RANGE_DAYS: Final = 366
