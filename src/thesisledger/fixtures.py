"""Deterministic fictional research inputs. No provider or account data is used.

Financial amounts are USD millions, shares are million shares, capacity/customer
counts are millions, and prices per unit/customer/share are plain USD.
"""

from datetime import date, timedelta
from math import sin


DECISION_TS = "2026-07-01T16:00:00+00:00"


def _evidence(symbol, suffix, title, content, unit):
    return {
        "id": f"{symbol.lower()}-{suffix}",
        "title": title,
        "source": "Synthetic fixture",
        "source_type": "synthetic",
        "url": f"fixture://{symbol.lower()}/{suffix}",
        "published_at": "2026-07-01T12:00:00+00:00",
        "retrieved_at": "2026-07-01T13:00:00+00:00",
        "usable_at": "2026-07-01T14:00:00+00:00",
        "period": "LTM ending 2026-06-30",
        "period_type": "annual",
        "unit": unit,
        "currency": "USD",
        "locator": "Synthetic demonstration, operating bridge table",
        "content": content,
        "classification": "confirmed_fact",
        "verified": True,
    }


def _prices(spot, phase):
    """Create 240 weekday bars ending June 30. Holidays are not simulated."""
    dates = []
    cursor = date(2026, 6, 30)
    while len(dates) < 240:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    levels = [0.78 + i * 0.001 + 0.025 * sin(i / 13 + phase) for i in range(240)]
    normalizer = levels[-1]
    return [
        {
            "date": day.isoformat(),
            "close": round(spot * levels[i] / normalizer, 6),
            "volume": 700000 + (i * 7919 + int(phase * 10000)) % 500000,
        }
        for i, day in enumerate(dates)
    ]


def _financials(**values):
    return {
        "currency": "USD",
        "amount_unit": "USD millions",
        "share_unit": "million shares",
        "period": "LTM ending 2026-06-30",
        "period_type": "annual",
        "period_start": "2025-07-01",
        "period_end": "2026-06-30",
        **values,
    }


def build_demo_companies() -> list[dict]:
    """Return fresh, independently mutable inputs for exactly three fake issuers."""
    industrial_evidence = [
        _evidence("ASTER", "capacity", "Qualified output, synthetic annual period",
                  "Installed capacity is 12 million units; 10 million are qualified. "
                  "Qualified utilization is 76%, with USD 50 realized revenue per unit.",
                  "million units; ratio; USD/unit"),
        _evidence("ASTER", "cash", "Capital and claims, synthetic annual period",
                  "Maintenance costs USD 2 per installed capacity unit; incremental "
                  "installed capacity costs USD 24 per unit. Debt 110, available cash 60, "
                  "minority claims 8, and diluted shares 30, all in millions.",
                  "USD millions; million shares; USD/capacity unit"),
        _evidence("ASTER", "opposition", "Qualification bottleneck, synthetic observation",
                  "Customer qualification can lag installed equipment. Qualification "
                  "does not establish shipments or recognized revenue.", "qualitative"),
    ]
    recurring_evidence = [
        _evidence("BCN", "cohort", "Customer bridge, synthetic annual period",
                  "12,000 active customers pay USD 30,000 annually on average. Gross "
                  "customer retention is 93%. Annual onboarding capacity is 3,000 customers.",
                  "million customers; USD/customer/year; ratio"),
        _evidence("BCN", "capital", "Customer acquisition and claims, synthetic annual period",
                  "A new customer requires USD 14,000 expensed acquisition cost and "
                  "USD 5,000 platform capital. Debt is 25, available cash 90, minority "
                  "claims zero, and diluted shares 40, all in millions.",
                  "USD/customer; USD millions; million shares"),
        _evidence("BCN", "opposition", "Retention challenge, synthetic observation",
                  "A synthetic competitor offers migration credits. Retention and "
                  "new-customer assumptions must be tested together.", "qualitative"),
    ]
    financial_evidence = [
        _evidence("HBR", "capital", "Regulatory perimeter, synthetic annual period",
                  "Harbor has regulated settlement and credit exposures. This fixture "
                  "does not disclose distributable equity cash flow or required capital.",
                  "qualitative"),
    ]
    return [
        {
            "symbol": "ASTER", "name": "Aster Systems", "sector": "Industrial equipment",
            "archetype": "industrial", "currency": "USD",
            "description": "Fictional capacity-led supplier. Qualified output earns value only after shipments and capital costs.",
            "price": 31.0, "price_as_of": "2026-06-30T20:00:00+00:00", "as_of": DECISION_TS,
            "financials": _financials(
                revenue=380.0, operating_nwc=45.6, installed_capacity=12.0,
                qualified_capacity=10.0, capacity_unit="million units",
                unit_price=50.0, variable_cost_per_unit=26.0, fixed_operating_cost=80.0,
                debt=110.0, cash=60.0, minorities=8.0, diluted_shares=30.0,
            ),
            "assumptions": {
                "qualified_utilization": 0.76, "utilization_ramp": 0.01,
                "installed_capacity_growth": 0.05, "qualified_capacity_growth": 0.05,
                "unit_price_growth": 0.015, "variable_cost_growth": 0.018,
                "fixed_cost_growth": 0.018, "capacity_cost_per_unit": 24.0,
                "maintenance_cost_per_unit": 2.0, "depreciation_per_capacity_unit": 1.7,
                "nwc_ratio": 0.12, "tax_rate": 0.25, "discount_rate": 0.10,
                "terminal_growth": 0.025, "terminal_roic": 0.18, "exit_ebit_multiple": 10.0,
            },
            "thesis": {
                "statement": "Qualification can convert installed equipment into profitable shipments, if reinvestment does not absorb the gains.",
                "drivers": [
                    {"id": "qualified_utilization", "label": "Qualified utilization", "value": 0.76,
                     "unit": "ratio", "evidence_ids": ["aster-capacity"],
                     "watch_condition": "Review if utilization stays below 65% for two reporting periods."},
                    {"id": "qualified_capacity_growth", "label": "Qualified capacity growth", "value": 0.05,
                     "unit": "annual ratio", "evidence_ids": ["aster-capacity", "aster-opposition"],
                     "watch_condition": "Review if qualification growth trails installed capacity for two periods."},
                    {"id": "capacity_cost_per_unit", "label": "Expansion capital per capacity unit", "value": 24.0,
                     "unit": "USD/unit", "evidence_ids": ["aster-cash"],
                     "watch_condition": "Review if expansion capital exceeds USD 30 per unit."},
                ],
                "falsifiers": ["Qualified output cannot be shipped at the assumed unit economics.",
                               "Two successive periods show capital spending above the operating cash improvement."],
                "counterevidence": ["Qualification may lag equipment availability.",
                                    "Customer substitution can reduce price while capital is already committed."],
                "next_review": "2026-08-15",
            },
            "evidence": industrial_evidence, "prices": _prices(31.0, 0.2),
        },
        {
            "symbol": "BCN", "name": "Beacon Cloud", "sector": "Recurring software",
            "archetype": "recurring", "currency": "USD",
            "description": "Fictional recurring revenue platform with explicit customer replacement and acquisition costs.",
            "price": 42.0, "price_as_of": "2026-06-30T20:00:00+00:00", "as_of": DECISION_TS,
            "financials": _financials(
                revenue=360.0, operating_nwc=7.2, customers=0.012,
                customer_unit="million customers", annual_revenue_per_customer=30000.0,
                onboarding_capacity=0.003, fixed_operating_cost=75.0,
                debt=25.0, cash=90.0, minorities=0.0, diluted_shares=40.0,
            ),
            "assumptions": {
                "retention": 0.93, "new_customers": 0.0025, "new_customer_growth": 0.04,
                "onboarding_capacity_growth": 0.05, "annual_revenue_per_customer_growth": 0.02,
                "service_cost_ratio": 0.45, "fixed_cost_growth": 0.03,
                "acquisition_cost_per_customer": 14000.0, "platform_capital_per_new_customer": 5000.0,
                "maintenance_capex_ratio": 0.035, "depreciation_ratio": 0.03,
                "nwc_ratio": 0.02, "tax_rate": 0.25, "discount_rate": 0.105,
                "terminal_growth": 0.025, "terminal_roic": 0.25, "exit_ebit_multiple": 14.0,
            },
            "thesis": {
                "statement": "Retained customer cohorts can produce cash growth, if replacement acquisition and platform investment stay affordable.",
                "drivers": [
                    {"id": "retention", "label": "Gross customer retention", "value": 0.93,
                     "unit": "annual ratio", "evidence_ids": ["bcn-cohort", "bcn-opposition"],
                     "watch_condition": "Review if retention falls below 88% in a complete annual cohort."},
                    {"id": "new_customers", "label": "Annual new customers", "value": 0.0025,
                     "unit": "million customers", "evidence_ids": ["bcn-cohort"],
                     "watch_condition": "Review if additions exceed demonstrated onboarding capacity."},
                    {"id": "acquisition_cost_per_customer", "label": "Acquisition cost per customer", "value": 14000.0,
                     "unit": "USD/customer", "evidence_ids": ["bcn-capital"],
                     "watch_condition": "Review if acquisition cost rises above USD 17,000."},
                ],
                "falsifiers": ["Customer losses consume the entire acquisition capacity.",
                               "Higher contract revenue does not convert after acquisition and platform investment."],
                "counterevidence": ["Migration credits can lower retention.",
                                    "Increasing acquisition can strain onboarding and require more capital."],
                "next_review": "2026-08-20",
            },
            "evidence": recurring_evidence, "prices": _prices(42.0, 1.1),
        },
        {
            "symbol": "HBR", "name": "Harbor Payments", "sector": "Regulated financial services",
            "archetype": "financial", "currency": "USD",
            "description": "Fictional regulated settlement and credit business; the supported FCFF engines do not apply.",
            "price": 18.0, "price_as_of": "2026-06-30T20:00:00+00:00", "as_of": DECISION_TS,
            "financials": _financials(revenue=200.0, debt=80.0, cash=50.0,
                                      minorities=0.0, diluted_shares=25.0),
            "assumptions": {"discount_rate": 0.11},
            "thesis": {
                "statement": "Payment volume alone cannot establish distributable equity value without regulatory capital and loss evidence.",
                "drivers": [],
                "falsifiers": ["Required capital absorbs the alleged distribution capacity."],
                "counterevidence": ["Missing capital and credit-loss inputs prevent a supported value estimate."],
                "next_review": "2026-08-25",
            },
            "evidence": financial_evidence, "prices": _prices(18.0, 2.0),
        },
    ]
