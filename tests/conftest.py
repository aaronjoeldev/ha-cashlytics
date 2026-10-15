"""Fixtures for the Cashlytics tests."""

from __future__ import annotations

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cashlytics.const import DOMAIN

USER_ID = "00000000-0000-0000-0000-000000000001"
TOKEN = "csk_" + "a" * 64
URL = "http://cashlytics.local:3000"

CHECKING_ID = "a0000000-0000-0000-0000-000000000001"
SAVINGS_ID = "a0000000-0000-0000-0000-000000000002"

ME = {
    "userId": USER_ID,
    "name": "Demo User",
    "email": "demo@cashlytics.online",
    "baseCurrency": "EUR",
    "locale": "de",
    "version": "0.9.0",
    "apiVersion": 1,
}

HEALTH = {"status": "ok", "version": "0.9.0", "apiVersion": 1}

SUMMARY: dict[str, Any] = {
    "generatedAt": "2026-10-15T13:21:32.717Z",
    "currency": "EUR",
    "totalAssets": 24496.05,
    "hasMultiCurrency": False,
    "month": {
        "year": 2026,
        "month": 10,
        "cashflow": {
            "income": 4150,
            "expenses": 1663.28,
            "surplus": 2486.72,
            "incomeChangePct": 0,
            "expensesChangePct": -29.6,
        },
        "reserve": {
            "income": 4151.56,
            "expenses": 1663.28,
            "surplus": 2488.28,
            "incomeChangePct": 0,
            "expensesChangePct": -29.6,
        },
    },
    "recurring": {
        "fixedCostsMonthly": 1162.44,
        "fixedCostsCount": 10,
        "subscriptionsMonthly": 34.97,
        "subscriptionsCount": 3,
    },
    "upcoming": {
        "days": 7,
        "count": 1,
        "total": 850,
        "next": {
            "id": "e0000000-0000-0000-0000-000000000001",
            "type": "expense",
            "name": "Miete",
            "date": "2026-10-18",
            "amount": 850,
            "category": {"name": "Wohnen", "icon": "🏠", "color": "#3b82f6"},
            "isSubscription": False,
        },
        "payments": [
            {
                "id": "e0000000-0000-0000-0000-000000000001",
                "type": "expense",
                "name": "Miete",
                "date": "2026-10-18",
                "amount": 850,
                "category": {"name": "Wohnen", "icon": "🏠", "color": "#3b82f6"},
                "isSubscription": False,
            }
        ],
    },
    "forecast": {
        "months": 3,
        "projectedIncome": 12450,
        "projectedExpenses": 4989.84,
        "projectedBalance": 7460.16,
        "monthly": [
            {"year": 2026, "month": 10, "income": 4150, "expenses": 1663.28, "balance": 2486.72}
        ],
    },
    "insights": {
        "unread": 1,
        "bySeverity": {"warning": 1},
        "byType": {"spending_anomaly": 1},
    },
}


def _account(account_id: str, name: str, account_type: str, balance: float) -> dict[str, Any]:
    cumulative = account_type != "checking"
    return {
        "id": account_id,
        "name": name,
        "type": account_type,
        "currency": "EUR",
        "balance": balance,
        "balanceInBaseCurrency": balance,
        "createdAt": "2026-01-01T00:00:00.000Z",
        "forecast": {
            "months": 3,
            "isCumulative": cumulative,
            "projectedBalance": balance + 900 if cumulative else None,
            "monthly": [
                {
                    "year": 2026,
                    "month": 11,
                    "income": 0 if cumulative else 4150,
                    "expenses": 0 if cumulative else 1662.44,
                    "transfersIn": 300 if cumulative else 0,
                    "transfersOut": 0,
                    "net": 300 if cumulative else 2487.56,
                    "balance": balance + 300 if cumulative else None,
                }
            ],
        },
    }


ACCOUNTS = [
    _account(CHECKING_ID, "Hauptkonto", "checking", 3245.8),
    _account(SAVINGS_ID, "Notgroschen", "savings", 12500),
]

PAYMENTS = [
    {
        "id": "d0000000-0000-0000-0000-000000000001",
        "type": "daily_expense",
        "name": "Bäcker",
        "date": "2026-10-15",
        "amount": 8.5,
        "originalAmount": 8.5,
        "originalCurrency": "EUR",
        "accountId": CHECKING_ID,
        "category": None,
        "isSubscription": False,
    },
    {
        "id": "i0000000-0000-0000-0000-000000000001",
        "type": "income",
        "name": "Gehalt",
        "date": "2026-10-16",
        "amount": 3200,
        "originalAmount": 3200,
        "originalCurrency": "EUR",
        "accountId": CHECKING_ID,
        "category": None,
        "isSubscription": False,
    },
    {
        "id": "e0000000-0000-0000-0000-000000000001",
        "type": "expense",
        "name": "Miete",
        "date": "2026-10-18",
        "amount": 850,
        "originalAmount": 850,
        "originalCurrency": "EUR",
        "accountId": CHECKING_ID,
        "category": {"name": "Wohnen", "icon": "🏠", "color": "#3b82f6"},
        "isSubscription": False,
    },
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A configured Cashlytics entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Cashlytics (Demo User)",
        unique_id=USER_ID,
        data={CONF_URL: URL, CONF_API_TOKEN: TOKEN, CONF_VERIFY_SSL: True},
    )


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Patch the API client used by the integration and the config flow."""
    with (
        patch("custom_components.cashlytics.CashlyticsClient", autospec=True) as client_class,
        patch("custom_components.cashlytics.config_flow.CashlyticsClient", new=client_class),
    ):
        client = client_class.return_value
        client.health.return_value = copy.deepcopy(HEALTH)
        client.me.return_value = copy.deepcopy(ME)
        client.summary.return_value = copy.deepcopy(SUMMARY)
        client.accounts.return_value = copy.deepcopy(ACCOUNTS)
        client.payments.return_value = copy.deepcopy(PAYMENTS)
        yield client
