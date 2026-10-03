"""Finite-horizon producer illustration, with explicit forward operating premises.

Historical financial statements are context, never silently annualized. This is
not a reserves valuation or a complete EXE underwriting model.
"""
from datetime import date
from math import isfinite

from .valuation import ModelError, _number, _timestamp, _unavailable, validate_evidence


PARAMETERS = {
    "annual_production", "realized_price", "cash_cost", "annual_capex",
    "discount_rate", "reserve_life_years", "production_growth",
    "realized_price_growth", "cost_growth", "tax_rate", "da_per_unit", "nwc_ratio",
}


def _inputs(company, overrides):
    for key in ("financials", "assumptions", "balance_sheet_bridge"):
        if not isinstance(company.get(key), dict):
            raise ModelError(f"{key}: an object is required")
    f = company.get("financials", {})
    if f.get("currency") != "USD" or f.get("amount_unit") != "USD millions" or f.get("share_unit") != "million shares":
        raise ModelError("Commodity amounts require USD millions and million shares")
    decision = _timestamp(company.get("as_of"), "as_of")
    try:
        start, end = (date.fromisoformat(f[key]) for key in ("period_start", "period_end"))
    except (KeyError, ValueError, TypeError):
        raise ModelError("A dated complete annual historical context is required") from None
    if f.get("period_type") != "annual" or not 364 <= (end-start).days <= 366 or not 0 <= (decision.date()-end).days <= 450:
        raise ModelError("Annual historical context must precede the cutoff by at most 450 days")
    bridge = company.get("balance_sheet_bridge", {})
    if bridge.get("method") != "hold_last_reported" or bridge.get("classification") != "model_assumption" or bridge.get("as_of") != company.get("as_of"):
        raise ModelError("A dated, explicit hold-last-reported balance-sheet assumption is required")
    if company.get("forecast_basis") != "explicit_forward_12_month_assumptions":
        raise ModelError("Forward rates must be explicit assumptions, not annualized quarterly facts")
    for key in ("debt", "cash", "minorities"):
        _number(f, key, lower=0)
    _number(f, "diluted_shares", lower=0.000001)
    for key in ("preferred", "preferred_stock", "convertible_debt", "restricted_cash"):
        if key in f and _number(f, key) != 0:
            raise ModelError(f"{key}: unsupported equity claim or cash restriction")
    _number(f, "operating_nwc")
    if not isinstance(company.get("evidence"), list) or not company["evidence"]:
        raise ModelError("Dated evidence is required")
    for item in company["evidence"]:
        errors = validate_evidence(item, company["as_of"])
        if errors:
            raise ModelError("; ".join(errors))
    a = dict(company.get("assumptions", {}))
    if overrides is not None:
        if not isinstance(overrides, dict) or set(overrides) - PARAMETERS:
            raise ModelError("Unsupported commodity scenario parameters")
        a.update(overrides)
    if set(a) != PARAMETERS:
        raise ModelError("Commodity assumptions must explicitly supply all supported parameters")
    for key in PARAMETERS:
        _number(a, key)
    for key in ("annual_production", "realized_price", "annual_capex", "discount_rate"):
        _number(a, key, lower=0.000001)
    for key in ("cash_cost", "da_per_unit"):
        _number(a, key, lower=0)
    for key in ("tax_rate", "nwc_ratio"):
        _number(a, key, lower=0, upper=1)
    _number(a, "discount_rate", lower=0.01, upper=0.50)
    _number(a, "production_growth", lower=-0.25, upper=0)
    for key in ("realized_price_growth", "cost_growth"):
        _number(a, key, lower=-0.20, upper=0.20)
    horizon = _number(a, "reserve_life_years", lower=1, upper=10)
    if not horizon.is_integer():
        raise ModelError("reserve_life_years: use an integer assumed cash-flow horizon")
    return f, a


def _finite(values):
    if any(not isfinite(value) for value in values):
        raise ModelError("Calculated commodity arithmetic is nonfinite")


def _scenario(f, a, name):
    _finite(a.values())
    production, price, cost = a["annual_production"], a["realized_price"], a["cash_cost"]
    nwc, cumulative, volume = f["operating_nwc"], 0.0, 0.0
    rows = []
    for year in range(1, int(a["reserve_life_years"])+1):
        if year > 1:
            production *= 1+a["production_growth"]
            price *= 1+a["realized_price_growth"]
            cost *= 1+a["cost_growth"]
        volume += production
        revenue, cash_cost, da = production*price, production*cost, production*a["da_per_unit"]
        ebitda = revenue-cash_cost
        ebit = ebitda-da
        taxes = max(0, ebit)*a["tax_rate"]
        next_nwc = revenue*a["nwc_ratio"]
        delta_nwc = next_nwc-nwc
        fcff = ebitda-taxes-a["annual_capex"]-delta_nwc
        cumulative += fcff
        _finite((volume, revenue, cash_cost, da, ebitda, ebit, taxes,
                 next_nwc, delta_nwc, fcff, cumulative, f["cash"]+cumulative))
        if f["cash"]+cumulative < -1e-9:
            raise ModelError(f"{name}: cash deficit requires an explicit funding and dilution model")
        discount = (1+a["discount_rate"])**-year
        row = {"year": year, "period": f"Forward 12 months, year {year}",
                     "production": production, "production_unit": "million Mcfe",
                     "realized_price": price, "cash_cost_per_unit": cost,
                     "revenue": revenue, "cash_cost": cash_cost, "ebitda": ebitda, "da": da,
                     "ebit": ebit, "nopat": ebit-taxes, "cash_taxes": taxes,
                     "capex": a["annual_capex"], "operating_nwc": next_nwc,
                     "delta_nwc": delta_nwc, "fcff": fcff, "discount_factor": discount,
                     "pv_fcff": fcff*discount, "cumulative_fcff": cumulative,
                     "amount_unit": "USD millions"}
        _finite(value for value in row.values() if isinstance(value, (int, float)))
        rows.append(row)
        nwc = next_nwc
    reserve_limit = f.get("proved_reserves_million_mcfe")
    if reserve_limit is not None and volume > _number(f, "proved_reserves_million_mcfe", lower=0)+1e-9:
        raise ModelError(f"{name}: projected cumulative production exceeds reported proved reserves; replacement capital is unmodeled")
    ev = sum(row["pv_fcff"] for row in rows)
    equity = ev+f["cash"]-f["debt"]-f["minorities"]
    _finite((ev, equity))
    value = max(0, equity)/f["diluted_shares"]
    if not isfinite(value):
        raise ModelError("Calculated commodity value is nonfinite")
    return {"name": name, "value": value, "enterprise_value": ev,
            "equity_value": max(0, equity), "unfloored_equity_value": equity,
            "shares": f["diluted_shares"], "forecast": rows, "assumptions": dict(a),
            "terminal_value": 0.0, "pv_terminal_value": 0.0, "terminal_value_fraction": 0.0,
            "cumulative_production_million_mcfe": volume,
            "amount_unit": "USD millions", "share_unit": "million shares",
            "notes": ["Finite assumed operating horizon with zero terminal and salvage value.",
                      "Annual production and sustaining capital are explicit premises; reserve totals alone do not establish deliverability.",
                      "Cash costs aggregate operating, transport and overhead premises; hedging and marketing are not modeled separately."]}


def value_commodity(company, overrides=None):
    try:
        f, a = _inputs(company, overrides)
        gaps = ["Educational operating scenario, not an investment target or complete EXE valuation.",
                "Opening debt/cash and share proxy are historical; post-report changes require a reviewed balance and dilution bridge.",
                "Flat sustaining production, capital efficiency, costs and horizon are unverified forecast premises.",
                "No explicit hedge book, marketing, retirement obligations, loss carryforwards or refinancing schedule."]
        if f.get("proved_reserves_million_mcfe") is None:
            gaps.append("Reported proved reserve constraint is missing; production feasibility remains unresolved.")
        scenarios = []
        for name, state in (("Bear", dict(a, realized_price=a["realized_price"]*0.85, annual_capex=a["annual_capex"]*1.10)),
                            ("Base", a), ("Bull", dict(a, realized_price=a["realized_price"]*1.15))):
            try:
                scenarios.append(_scenario(f, state, name))
            except ModelError as exc:
                if name == "Base":
                    raise
                gaps.append(str(exc))
        values = {row["name"].lower(): row["value"] for row in scenarios}
        sensitivity = []
        for parameter, candidates in (("realized_price", [a["realized_price"]*0.9, a["realized_price"], a["realized_price"]*1.1]),
                                      ("annual_capex", [a["annual_capex"]*0.9, a["annual_capex"]*1.1])):
            for candidate in candidates:
                try:
                    value = _scenario(f, dict(a, **{parameter: candidate}), "Sensitivity")["value"]
                    sensitivity.append({"parameter": parameter, "value": candidate, "per_share_value": value, "state": "available"})
                except ModelError as exc:
                    sensitivity.append({"parameter": parameter, "value": candidate if isfinite(candidate) else None, "per_share_value": None, "state": "unavailable", "notes": [str(exc)]})
        return {"state": "available", "method": "Finite-horizon producer FCFF illustration",
                "unit": "USD/share", "base": values.get("base"), "bear": values.get("bear"), "bull": values.get("bull"),
                "scenarios": scenarios, "sensitivity": sensitivity,
                "cross_check": {"method": None, "value": None, "notes": ["Independent valuation unavailable"], "independence": "none"},
                "reverse": {"state": "unavailable", "parameter": None, "required_value": None, "target_price": None,
                            "notes": ["No verified market price supplied; no implied expectations computed."]},
                "data_gaps": gaps, "coverage": "educational_public_case", "input_mode": "public_facts_with_model_assumptions",
                "as_of": company["as_of"], "research_only": True, "human_decision": "pending", "amount_unit": "USD millions"}
    except (ModelError, ValueError, KeyError, TypeError, OverflowError) as exc:
        return _unavailable([str(exc)])
