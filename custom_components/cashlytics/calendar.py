"""Calendar of scheduled payments for Cashlytics."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import CashlyticsError
from .const import DOMAIN, MAX_PAYMENT_RANGE_DAYS
from .coordinator import CashlyticsConfigEntry, CashlyticsCoordinator
from .entity import CashlyticsEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CashlyticsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Cashlytics calendar."""
    async_add_entities([CashlyticsPaymentsCalendar(entry.runtime_data)])


def payment_to_event(payment: dict[str, Any], currency: str) -> CalendarEvent:
    """All-day event of one due date, e.g. "Netflix -13.99 EUR"."""
    day = date.fromisoformat(payment["date"])
    sign = "+" if payment["type"] == "income" else "-"
    category = (payment.get("category") or {}).get("name")
    details = [f"{payment['amount']:.2f} {currency}"]
    if payment.get("originalCurrency") and payment["originalCurrency"] != currency:
        details.append(f"{payment['originalAmount']:.2f} {payment['originalCurrency']}")
    if category:
        details.append(category)
    return CalendarEvent(
        start=day,
        end=day + timedelta(days=1),
        summary=f"{payment['name']} {sign}{payment['amount']:.2f} {currency}",
        description="\n".join(details),
        uid=f"{payment['type']}_{payment['id']}_{payment['date']}",
    )


class CashlyticsPaymentsCalendar(CashlyticsEntity, CalendarEntity):
    """Due dates of expenses, daily expenses and incomes as all-day events."""

    _attr_translation_key = "payments"

    def __init__(self, coordinator: CashlyticsCoordinator) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator, "payments")

    @property
    def event(self) -> CalendarEvent | None:
        """The current or next due date."""
        today = dt_util.now().date().isoformat()
        for payment in self.coordinator.data.payments:
            if payment["date"] >= today:
                return payment_to_event(payment, self.coordinator.data.currency)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the due dates in a range, fetched in chunks the API accepts."""
        first = dt_util.as_local(start_date).date()
        # end_date is exclusive
        last = dt_util.as_local(end_date - timedelta(microseconds=1)).date()
        currency = self.coordinator.data.currency
        events: list[CalendarEvent] = []
        chunk_start = first
        try:
            while chunk_start <= last:
                chunk_end = min(last, chunk_start + timedelta(days=MAX_PAYMENT_RANGE_DAYS - 1))
                payments = await self.coordinator.client.payments(chunk_start, chunk_end)
                events.extend(payment_to_event(payment, currency) for payment in payments)
                chunk_start = chunk_end + timedelta(days=1)
        except CashlyticsError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="calendar_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return events
