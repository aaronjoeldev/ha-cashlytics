# Cashlytics for Home Assistant

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aaronjoeldev&repository=ha-cashlytics&category=integration)

Brings your [Cashlytics](https://cashlytics.online) budget into Home Assistant: assets, account
balances, this month's income and expenses, upcoming payments, forecasts and insights, plus a
calendar of all scheduled payments. The integration only reads data.

## Requirements

- A Cashlytics instance with REST API v1 (Cashlytics with **Settings → API tokens &
  integrations**) that Home Assistant can reach, e.g. `http://192.168.1.10:3000`.
- Home Assistant 2026.3 or newer.

## Installation

### HACS

1. Open HACS, choose **⋮ → Custom repositories**, add `https://github.com/aaronjoeldev/ha-cashlytics`
   with the category **Integration** (or use the button above).
2. Install **Cashlytics** and restart Home Assistant.

### Manual

Copy `custom_components/cashlytics` into the `custom_components` folder of your configuration and
restart Home Assistant.

## Setup

1. In Cashlytics, open **Settings → API tokens & integrations** and create a token (e.g. named
   "Home Assistant"). Copy it; it is shown only once.
2. In Home Assistant, go to **Settings → Devices & services → Add integration → Cashlytics**.
3. Enter the URL of your instance and the token. Turn off **Verify SSL certificate** only for
   self-signed certificates.

Each Cashlytics user is one entry; add another entry with that user's token for more users.

### Options

| Option                  | Default | Meaning                                           |
| ----------------------- | ------- | ------------------------------------------------- |
| Polling interval        | 15 min  | How often data is fetched (5–240 minutes)         |
| Upcoming payments window| 7 days  | Days covered by *Upcoming payments* (2–90)        |
| Forecast period         | 3 months| Months for the forecast sensors (1–24)            |

## Entities

Amounts are in your Cashlytics base currency unless noted.

### Overview device

| Entity                      | Type          | Details                                                  |
| --------------------------- | ------------- | -------------------------------------------------------- |
| Total assets                | sensor        | Sum of all account balances; long-term statistics        |
| Income / Expenses / Surplus this month | sensor | What is due this month (cashflow view); reserve view and change vs. last month as attributes |
| Income / Expenses vs. last month | sensor (%) | Disabled by default                                   |
| Fixed costs per month       | sensor        | Recurring expenses spread per month                      |
| Subscriptions per month     | sensor        | Recurring expenses marked as subscription                |
| Upcoming payments           | sensor        | Total of the next days; the payments are an attribute    |
| Next payment                | sensor (date) | Name, amount and category as attributes                  |
| Forecast balance            | sensor        | Income minus expenses over the forecast period           |
| Unread insights             | sensor        | Counts by severity and type as attributes                |
| Payment due today / tomorrow| binary sensor | Expenses only, not incomes; payments as attributes       |
| Deficit this month          | binary sensor | Expenses exceed income this month                        |
| Spending anomaly            | binary sensor | Cashlytics detected unusual spending                     |
| Budget warning              | binary sensor | Cashlytics warns about the spending pace                 |
| Payments                    | calendar      | All due dates of expenses and incomes as all-day events  |

### One device per account

| Entity               | Type          | Details                                                         |
| -------------------- | ------------- | --------------------------------------------------------------- |
| Balance              | sensor        | In the account's currency; long-term statistics                 |
| Forecast balance     | sensor        | Savings and ETF accounts only; monthly projection as attribute  |
| Net next month       | sensor        | Income, expenses and transfers of next month as attributes      |
| Negative balance     | binary sensor |                                                                 |

Balances are the values you maintain in Cashlytics. Home Assistant records them over time, so you
get a history of your assets that Cashlytics itself does not keep.

## Examples

Notification the evening before a payment:

```yaml
automation:
  - alias: "Payment due tomorrow"
    triggers:
      - trigger: time
        at: "19:00:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.cashlytics_payment_due_tomorrow
        state: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "Payment due tomorrow"
          message: >
            {% for p in state_attr('binary_sensor.cashlytics_payment_due_tomorrow', 'payments') %}
            {{ p.name }}: {{ p.amount }} {{ state_attr('binary_sensor.cashlytics_payment_due_tomorrow', 'currency') }}
            {% endfor %}
```

Warn when Cashlytics reports unusual spending:

```yaml
automation:
  - alias: "Spending anomaly"
    triggers:
      - trigger: state
        entity_id: binary_sensor.cashlytics_spending_anomaly
        to: "on"
    actions:
      - action: persistent_notification.create
        data:
          message: "Cashlytics noticed unusual spending this month."
```

Entity ids depend on the entry name; check them under **Settings → Devices & services → Cashlytics**.

## Privacy

Financial data is sensitive. The integration only reads data and talks to your own instance.
Home Assistant stores entity states and attributes in its database. Diagnostics hide the token,
the URL and all names. Revoke the token in Cashlytics at any time; the integration then asks for a
new one.

## Development

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest
```

## License

MIT
