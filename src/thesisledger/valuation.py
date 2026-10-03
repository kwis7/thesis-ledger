"""Original, stdlib-only, conditional valuation engines for synthetic research.

This module values operating cash-flow claims, not trades. It supports only two
specified economic engines. Amounts and shares use millions consistently; the
resulting ratio is USD/share. All public functions return JSON-compatible data.
"""

from datetime import date, datetime
from math import isfinite


class ModelError(ValueError):
    """A missing input or infeasible economic state, never a silent default."""


def _number(mapping, key, *, lower=None, upper=None):
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ModelError(f"{key}: a finite numeric input is required")
    if lower is not None and value < lower:
        raise ModelError(f"{key}: must be at least {lower}")
    if upper is not None and value > upper:
        raise ModelError(f"{key}: must be at most {upper}")
    return float(value)


def _timestamp(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ModelError(f"{label}: a timezone-aware ISO timestamp is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ModelError(f"{label}: invalid ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ModelError(f"{label}: naive timestamp is not allowed")
    return parsed


def _nonfinite_paths(value, prefix="evidence"):
    if isinstance(value, float) and not isfinite(value):
        return [f"{prefix}: nonfinite numeric input"]
    errors = []
    if isinstance(value, dict):
        for key, child in value.items():
            errors.extend(_nonfinite_paths(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_nonfinite_paths(child, f"{prefix}[{index}]"))
    return errors


def validate_evidence(evidence: dict, decision_ts: str) -> list[str]:
    """Return provenance errors, including availability after the decision cutoff.

    verified records the supplied verification status. This function validates
    metadata and chronology, not factual correctness or independent verification.
    """
    if not isinstance(evidence, dict):
        return ["evidence: an object is required"]
    errors = _nonfinite_paths(evidence)
    for key in ("id", "title", "source", "source_type", "url", "period", "unit", "currency", "locator", "content"):
        if not isinstance(evidence.get(key), str) or not evidence[key].strip():
            errors.append(f"{key}: missing evidence context")
    classes = {"confirmed_fact", "interpretation", "model_assumption", "counterevidence", "data_gap"}
    if not isinstance(evidence.get("classification"), str) or evidence["classification"] not in classes:
        errors.append("classification: an explicit recognized evidence classification is required")
    if evidence.get("classification") == "confirmed_fact" and evidence.get("verified") is not True:
        errors.append("verified: unverified facts cannot be classified as confirmed_fact")
    stamps = {}
    for key, value in (("decision_ts", decision_ts), ("published_at", evidence.get("published_at")),
                       ("retrieved_at", evidence.get("retrieved_at")), ("usable_at", evidence.get("usable_at"))):
        try:
            stamps[key] = _timestamp(value, key)
        except ModelError as exc:
            errors.append(str(exc))
    published, retrieved, usable, cutoff = (stamps.get(k) for k in ("published_at", "retrieved_at", "usable_at", "decision_ts"))
    if published and usable and usable < published:
        errors.append("usable_at: cannot precede publication")
    if published and retrieved and retrieved < published:
        errors.append("retrieved_at: cannot precede publication")
    if retrieved and usable and usable < retrieved:
        errors.append("usable_at: cannot precede retrieval in this acquired-evidence contract")
    if cutoff and usable and usable > cutoff:
        errors.append("usable_at: look-ahead evidence is later than the decision cutoff")
    if cutoff and retrieved and retrieved > cutoff:
        errors.append("retrieved_at: evidence was acquired after the decision cutoff")
    if evidence.get("annualized_from_quarter") is True:
        errors.append("period: quarterly evidence cannot be silently annualized")
    return errors


_COMMON = {"tax_rate", "discount_rate", "terminal_growth", "terminal_roic", "nwc_ratio", "exit_ebit_multiple"}
_INDUSTRIAL = {
    "qualified_utilization", "utilization_ramp", "installed_capacity_growth", "qualified_capacity_growth",
    "unit_price_growth", "variable_cost_growth", "fixed_cost_growth", "capacity_cost_per_unit",
    "maintenance_cost_per_unit", "depreciation_per_capacity_unit",
}
_RECURRING = {
    "retention", "new_customers", "new_customer_growth", "onboarding_capacity_growth",
    "annual_revenue_per_customer_growth", "service_cost_ratio", "fixed_cost_growth",
    "acquisition_cost_per_customer", "platform_capital_per_new_customer", "maintenance_capex_ratio", "depreciation_ratio",
}


def _inputs(company, overrides):
    if not isinstance(company, dict):
        raise ModelError("company: an object is required")
    f = company.get("financials")
    if not isinstance(f, dict):
        raise ModelError("financials: an object is required")
    if f.get("currency") != "USD" or company.get("currency", "USD") != "USD":
        raise ModelError("currency: this engine requires USD inputs and does not convert FX")
    if f.get("amount_unit") != "USD millions" or f.get("share_unit") != "million shares":
        raise ModelError("unit: financial amounts must be USD millions and shares must be million shares")
    if f.get("period_type") != "annual":
        raise ModelError("period: annual financial input required; quarterly input is not annualized")
    if not isinstance(f.get("period"), str) or not f["period"].strip():
        raise ModelError("period: a named financial context is required")
    nonfinite = _nonfinite_paths(f, "financials")
    if nonfinite:
        raise ModelError("; ".join(nonfinite))
    for key in ("preferred", "preferred_stock", "convertible_debt", "restricted_cash"):
        if key in f and _number(f, key) != 0:
            raise ModelError(f"{key}: nonzero unsupported claim or cash restriction; "
                             "the common-equity bridge requires an explicit model")
    try:
        start, end = (date.fromisoformat(f[key]) for key in ("period_start", "period_end"))
    except (KeyError, ValueError, TypeError):
        raise ModelError("period: annual financial start and end dates are required") from None
    if not 364 <= (end - start).days <= 366:
        raise ModelError("period: financial input must describe a complete annual period")
    decision = _timestamp(company.get("as_of"), "as_of")
    if end > decision.date():
        raise ModelError("period_end: financial period ends after the valuation date")
    if (decision.date() - end).days > 31:
        raise ModelError("period: stale annual starting state needs a dated interim/stub bridge")
    price_ts = _timestamp(company.get("price_as_of"), "price_as_of")
    if price_ts > decision:
        raise ModelError("price_as_of: price is later than the decision cutoff")
    _number(company, "price", lower=0.0000001)
    if not isinstance(company.get("evidence"), list) or not company["evidence"]:
        raise ModelError("evidence: dated evidence context is required")
    for item in company["evidence"]:
        errors = validate_evidence(item, company["as_of"])
        if errors:
            raise ModelError("evidence: " + "; ".join(errors))
    for key in ("debt", "cash", "minorities"):
        _number(f, key, lower=0)
    _number(f, "diluted_shares", lower=0.0000001)
    _number(f, "revenue", lower=0.0000001)
    _number(f, "operating_nwc")
    if not isinstance(company.get("assumptions"), dict):
        raise ModelError("assumptions: a scalar numeric input object is required")
    a = dict(company["assumptions"])
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise ModelError("assumptions: scalar numeric overrides must be an object")
        a.update(overrides)
    allowed = _COMMON | (_INDUSTRIAL if company["archetype"] == "industrial" else _RECURRING)
    unknown = set(a) - allowed
    if unknown:
        raise ModelError("assumptions: unsupported keys " + ", ".join(sorted(unknown)))
    for key in allowed:
        _number(a, key)
    _number(a, "tax_rate", lower=0, upper=1)
    r = _number(a, "discount_rate", lower=0.0000001, upper=1)
    g = _number(a, "terminal_growth", lower=0, upper=0.20)
    roic = _number(a, "terminal_roic", lower=0.0000001, upper=1)
    if g >= r:
        raise ModelError("terminal_growth: must be below discount_rate")
    if g > roic:
        raise ModelError("terminal_roic: terminal growth requires more than all terminal operating profit")
    _number(a, "nwc_ratio", lower=0, upper=1)
    _number(a, "exit_ebit_multiple", lower=0.0000001)
    return f, a


def _forecast_industrial(f, a):
    if f.get("capacity_unit") != "million units":
        raise ModelError("capacity_unit: million units are required")
    installed = _number(f, "installed_capacity", lower=0.0000001)
    qualified = _number(f, "qualified_capacity", lower=0.0000001)
    if qualified > installed:
        raise ModelError("qualified_capacity: cannot exceed installed capacity")
    price = _number(f, "unit_price", lower=0.0000001)
    cost = _number(f, "variable_cost_per_unit", lower=0)
    fixed = _number(f, "fixed_operating_cost", lower=0)
    previous_nwc = _number(f, "operating_nwc")
    _number(a, "qualified_utilization", lower=0, upper=1)
    _number(a, "utilization_ramp", lower=0, upper=0.1)
    for key in ("installed_capacity_growth", "qualified_capacity_growth"):
        _number(a, key, lower=0, upper=0.30)
    for key in ("unit_price_growth", "variable_cost_growth", "fixed_cost_growth"):
        _number(a, key, lower=-0.20, upper=0.30)
    for key in ("capacity_cost_per_unit", "maintenance_cost_per_unit", "depreciation_per_capacity_unit"):
        _number(a, key, lower=0.0000001)
    rows = []
    for year in range(1, 6):
        previous_installed = installed
        installed *= 1 + a["installed_capacity_growth"]
        qualified *= 1 + a["qualified_capacity_growth"]
        if qualified > installed + 1e-10:
            raise ModelError(f"Year {year}: qualified capacity exceeds installed capacity")
        utilization = min(1.0, a["qualified_utilization"] + a["utilization_ramp"] * (year - 1))
        price *= 1 + a["unit_price_growth"]
        cost *= 1 + a["variable_cost_growth"]
        fixed *= 1 + a["fixed_cost_growth"]
        units = qualified * utilization
        revenue = units * price
        da = installed * a["depreciation_per_capacity_unit"]
        ebitda = revenue - units * cost - fixed
        maintenance = installed * a["maintenance_cost_per_unit"]
        growth = (installed - previous_installed) * a["capacity_cost_per_unit"]
        row = _cash_row(year, revenue, ebitda, da, maintenance, growth, previous_nwc, a)
        row.update(installed_capacity=installed, qualified_capacity=qualified,
                   qualified_utilization=utilization, units=units, unit_price=price,
                   variable_cost_per_unit=cost, fixed_operating_cost=fixed,
                   capacity_unit="million units", unit_price_unit="USD/unit")
        rows.append(row)
        previous_nwc = row["operating_nwc"]
    return rows


def _forecast_recurring(f, a):
    if f.get("customer_unit") != "million customers":
        raise ModelError("customer_unit: million customers are required")
    customers = _number(f, "customers", lower=0.0000001)
    arpc = _number(f, "annual_revenue_per_customer", lower=0.0000001)
    capacity = _number(f, "onboarding_capacity", lower=0.0000001)
    fixed = _number(f, "fixed_operating_cost", lower=0)
    previous_nwc = _number(f, "operating_nwc")
    _number(a, "retention", lower=0, upper=1)
    _number(a, "new_customers", lower=0)
    for key in ("new_customer_growth", "onboarding_capacity_growth"):
        _number(a, key, lower=0, upper=0.30)
    for key in ("annual_revenue_per_customer_growth", "fixed_cost_growth"):
        _number(a, key, lower=-0.20, upper=0.30)
    for key in ("service_cost_ratio", "maintenance_capex_ratio", "depreciation_ratio"):
        _number(a, key, lower=0, upper=1)
    for key in ("acquisition_cost_per_customer", "platform_capital_per_new_customer"):
        _number(a, key, lower=0.0000001)
    rows = []
    for year in range(1, 6):
        additions = a["new_customers"] * (1 + a["new_customer_growth"]) ** (year - 1)
        year_capacity = capacity * (1 + a["onboarding_capacity_growth"]) ** (year - 1)
        if additions > year_capacity + 1e-12:
            raise ModelError(f"Year {year}: new customers exceed onboarding capacity")
        retained = customers * a["retention"]
        customers = retained + additions
        arpc *= 1 + a["annual_revenue_per_customer_growth"]
        fixed *= 1 + a["fixed_cost_growth"]
        revenue = customers * arpc
        acquisition = additions * a["acquisition_cost_per_customer"]
        ebitda = revenue * (1 - a["service_cost_ratio"]) - fixed - acquisition
        da = revenue * a["depreciation_ratio"]
        maintenance = revenue * a["maintenance_capex_ratio"]
        growth = additions * a["platform_capital_per_new_customer"]
        row = _cash_row(year, revenue, ebitda, da, maintenance, growth, previous_nwc, a)
        row.update(customers=customers, retained_customers=retained, new_customers=additions,
                   onboarding_capacity=year_capacity, annual_revenue_per_customer=arpc,
                   acquisition_cost=acquisition, fixed_operating_cost=fixed,
                   customer_unit="million customers", arpc_unit="USD/customer/year")
        rows.append(row)
        previous_nwc = row["operating_nwc"]
    return rows


def _cash_row(year, revenue, ebitda, da, maintenance, growth, previous_nwc, a):
    ebit = ebitda - da
    taxes = max(0.0, ebit) * a["tax_rate"]
    nopat = ebit - taxes
    nwc = revenue * a["nwc_ratio"]
    delta_nwc = nwc - previous_nwc
    capex = maintenance + growth
    fcff = nopat + da - capex - delta_nwc
    df = (1 + a["discount_rate"]) ** -year
    return {
        "year": year, "period": f"Forward 12 months, year {year}", "amount_unit": "USD millions",
        "revenue": revenue, "ebitda": ebitda, "da": da, "ebit": ebit,
        "ebit_margin": ebit / revenue if revenue else 0.0, "cash_taxes": taxes, "nopat": nopat,
        "maintenance_capex": maintenance, "growth_capex": growth, "capex": capex,
        "operating_nwc": nwc, "delta_nwc": delta_nwc, "fcff": fcff,
        "discount_factor": df, "pv_fcff": fcff * df,
    }


def _scenario(company, f, a, name):
    rows = (_forecast_industrial if company["archetype"] == "industrial" else _forecast_recurring)(f, a)
    cumulative, funding_need = 0.0, 0.0
    for row in rows:
        cumulative += row["fcff"]
        funding_need = max(funding_need, -cumulative)
        row["cumulative_fcff"] = cumulative
        row["cash_after_unlevered_fcff"] = f["cash"] + cumulative
    nonfinite = _nonfinite_paths(rows, "forecast")
    if nonfinite:
        raise ModelError("; ".join(nonfinite))
    if funding_need > f["cash"] + 1e-9:
        raise ModelError(f"{name}: cumulative FCFF cash deficit requires external financing; "
                         "future debt claims and diluted shares are undefined")
    last = rows[-1]
    if last["nopat"] <= 0:
        raise ModelError(f"{name}: terminal operating profit is not positive; a sustainable terminal state is absent")
    terminal_nopat = last["nopat"] * (1 + a["terminal_growth"])
    reinvestment = terminal_nopat * a["terminal_growth"] / a["terminal_roic"]
    terminal_fcff = terminal_nopat - reinvestment
    tv = terminal_fcff / (a["discount_rate"] - a["terminal_growth"])
    pv_tv = tv * last["discount_factor"]
    ev = sum(row["pv_fcff"] for row in rows) + pv_tv
    equity_before_floor = ev + f["cash"] - f["debt"] - f["minorities"]
    # Negative equity is economically zero for limited-liability common holders.
    equity = max(0.0, equity_before_floor)
    for key, value in {"terminal_nopat": terminal_nopat, "terminal_reinvestment": reinvestment,
                       "terminal_fcff": terminal_fcff, "terminal_value": tv,
                       "enterprise_value": ev, "equity_value": equity_before_floor,
                       "per_share_value": equity / f["diluted_shares"]}.items():
        _number({key: value}, key)
    notes = [
        "Conditional preliminary range; not certified coverage.",
        "Five future 12-month cash flows, year-end discount timing, starting at as_of.",
        "Available excess cash and senior/minority claims are held at the dated opening balances.",
        "Existing fully diluted shares are used; no future issuance, buybacks, or financing model.",
        "Terminal reinvestment = next-year NOPAT * terminal growth / terminal ROIC; margins normalize at year 5.",
        "No cash-tax loss carryforward benefit is assumed.",
        "Unlevered funding guard assumes retention of interim FCFF and checks opening available cash; debt service, distributions and refinancing remain unmodeled.",
    ]
    if any(row["fcff"] < 0 for row in rows):
        notes.append("Negative FCFF requires a funding review; this demo does not model financing or dilution from shortfalls.")
    return {
        "name": name, "value": equity / f["diluted_shares"], "enterprise_value": ev,
        "equity_value": equity, "unfloored_equity_value": equity_before_floor,
        "shares": f["diluted_shares"], "share_unit": "million shares",
        "amount_unit": "USD millions", "forecast": rows, "terminal_value": tv,
        "pv_terminal_value": pv_tv, "terminal_nopat": terminal_nopat,
        "terminal_reinvestment": reinvestment, "terminal_fcff": terminal_fcff,
        "terminal_value_fraction": pv_tv / ev if ev else None,
        "assumptions": dict(a), "notes": notes,
        "funding_review": {
            "state": "opening_cash_covers_unlevered_deficit", "opening_available_cash": f["cash"],
            "maximum_cumulative_fcff_deficit": funding_need, "external_funding_required": 0.0,
            "future_dilution": "not modeled", "amount_unit": "USD millions",
            "notes": ["This necessary cash check does not establish covenant, debt-service, or refinancing feasibility."],
        },
    }


def _connected_states(archetype, a):
    bear, bull = dict(a), dict(a)
    if archetype == "industrial":
        bear.update(qualified_utilization=max(0.0, a["qualified_utilization"] - 0.14),
                    qualified_capacity_growth=a["qualified_capacity_growth"] * 0.55,
                    utilization_ramp=0.0, unit_price_growth=a["unit_price_growth"] - 0.025,
                    capacity_cost_per_unit=a["capacity_cost_per_unit"] * 1.15,
                    variable_cost_growth=a["variable_cost_growth"] + 0.015)
        bull.update(qualified_utilization=min(1.0, a["qualified_utilization"] + 0.10),
                    qualified_capacity_growth=min(a["installed_capacity_growth"], a["qualified_capacity_growth"] * 1.15),
                    unit_price_growth=a["unit_price_growth"] + 0.02,
                    capacity_cost_per_unit=a["capacity_cost_per_unit"] * 0.95)
    else:
        bear.update(retention=max(0.0, a["retention"] - 0.06),
                    new_customers=a["new_customers"] * 0.75,
                    annual_revenue_per_customer_growth=a["annual_revenue_per_customer_growth"] - 0.02,
                    acquisition_cost_per_customer=a["acquisition_cost_per_customer"] * 1.20,
                    service_cost_ratio=min(1.0, a["service_cost_ratio"] + 0.04))
        bull.update(retention=min(1.0, a["retention"] + 0.04),
                    new_customers=a["new_customers"] * 1.10,
                    annual_revenue_per_customer_growth=a["annual_revenue_per_customer_growth"] + 0.01,
                    service_cost_ratio=max(0.0, a["service_cost_ratio"] - 0.025),
                    platform_capital_per_new_customer=a["platform_capital_per_new_customer"] * 1.05)
    return [("Bear", bear), ("Base", dict(a)), ("Bull", bull)]


def _reverse(company, f, a):
    parameter = "qualified_utilization" if company["archetype"] == "industrial" else "retention"
    target = company["price"]
    notes = [
        "A conditional one-parameter solution. A single price cannot identify several operating assumptions uniquely.",
        "All other base assumptions and the claim/share bridge are held fixed; a solved input is not evidence it will occur.",
        "Back-substitution uses the same forward FCFF engine. Feasibility is limited to the supported operating and unlevered funding constraints.",
    ]
    result = {
        "state": "unavailable", "parameter": parameter, "required_value": None,
        "held_assumptions": {k: v for k, v in a.items() if k != parameter},
        "recomputed_price": None, "target_price": target, "notes": notes,
    }
    # Find a feasible monotone interval. Invalid terminal states never become roots.
    candidates = []
    for step in range(101):
        trial = dict(a, **{parameter: step / 100})
        try:
            value = _scenario(company, f, trial, "Reverse feasibility")["value"]
        except ModelError:
            continue
        candidates.append((step / 100, value))
    if len(candidates) < 2:
        result["notes"].append("No feasible operating interval with a positive terminal state.")
        return result
    if any(right[1] < left[1] - 1e-9 for left, right in zip(candidates, candidates[1:])):
        result["notes"].append("The conditional response is non-monotone; this bisection implementation declines to claim a unique solution.")
        return result
    left, right = candidates[0], candidates[-1]
    result["feasible_price_range"] = [left[1], right[1]]
    if not left[1] <= target <= right[1]:
        result["notes"].append("Target price is outside the feasible conditional value range.")
        return result
    lo, hi = left[0], right[0]
    for _ in range(80):
        mid = (lo + hi) / 2
        trial = dict(a, **{parameter: mid})
        value = _scenario(company, f, trial, "Reverse")["value"]
        if value < target:
            lo = mid
        else:
            hi = mid
    root = (lo + hi) / 2
    recomputed = _scenario(company, f, dict(a, **{parameter: root}), "Reverse back-substitution")["value"]
    result.update(state="available", required_value=root, recomputed_price=recomputed,
                  price_residual=recomputed - target, tolerance=1e-7)
    return result


def _unavailable(gaps):
    return {
        "state": "unavailable", "method": "No supported valuation", "unit": "USD/share",
        "base": None, "bear": None, "bull": None, "scenarios": [],
        "cross_check": {"method": None, "value": None, "notes": gaps, "independence": "shared assumptions"},
        "sensitivity": [], "reverse": {"state": "unavailable", "parameter": None,
        "required_value": None, "held_assumptions": {}, "recomputed_price": None,
        "target_price": None, "notes": gaps}, "data_gaps": gaps,
        "research_only": True, "human_decision": "pending", "coverage": "unavailable",
    }


def value_company(company: dict, assumptions: dict | None = None) -> dict:
    """Value a supported engine; return a clear gap for unsupported or invalid inputs."""
    if isinstance(company, dict) and company.get("archetype") == "commodity":
        from .commodity import value_commodity
        return value_commodity(company, assumptions)
    if not isinstance(company, dict) or company.get("archetype") not in ("industrial", "recurring"):
        return _unavailable(["Regulated financial and other unsupported businesses require an equity cash-flow/capital model; generic FCFF is not applied."])
    try:
        f, a = _inputs(company, assumptions)
        source_types = {item["source_type"] for item in company["evidence"]}
        input_mode = "synthetic" if source_types == {"synthetic"} else ("mixed" if "synthetic" in source_types else "supplied_evidence")
        scenarios = []
        gaps = (["Synthetic demonstration, not real-world evidence or full coverage."] if input_mode == "synthetic" else
                ["Supplied evidence metadata is validated; facts and forecast completeness are not independently verified by this engine."]) + [
                "Exit multiple is illustrative and shares the operating forecast; independent valuation confirmation is absent.",
                "Five-year transition and terminal ROIC are assumptions, not estimated facts.",
                "Funding, future dilution, acquisitions, restricted cash, and complex claims are outside this demo."]
        for name, state in _connected_states(company["archetype"], a):
            try:
                # Scenario constraints are checked by the same input/forecast path.
                _, valid = _inputs(company, state)
                scenarios.append(_scenario(company, f, valid, name))
            except ModelError as exc:
                if name == "Base":
                    raise
                gaps.append(f"{name} scenario infeasible: {exc}")
        base = next(item for item in scenarios if item["name"] == "Base")
        by_name = {item["name"]: item for item in scenarios}
        cross_ev = sum(row["pv_fcff"] for row in base["forecast"]) + (
            base["forecast"][-1]["ebit"] * a["exit_ebit_multiple"] * base["forecast"][-1]["discount_factor"])
        cross_equity = max(0.0, cross_ev + f["cash"] - f["debt"] - f["minorities"])
        if not isfinite(cross_ev) or not isfinite(cross_equity / f["diluted_shares"]):
            raise ModelError("cross_check: calculated value exceeds the finite numeric range")
        sensitivity = []
        operating = "qualified_utilization" if company["archetype"] == "industrial" else "retention"
        tests = [(operating, max(0, a[operating] - 0.05)), (operating, a[operating]),
                 (operating, min(1, a[operating] + 0.05)),
                 ("discount_rate", a["discount_rate"] - 0.01), ("discount_rate", a["discount_rate"] + 0.01),
                 ("terminal_roic", a["terminal_roic"] * 0.75), ("terminal_roic", a["terminal_roic"] * 1.25)]
        for parameter, candidate in tests:
            try:
                _, trial = _inputs(company, {parameter: candidate, **{k: v for k, v in a.items() if k != parameter}})
                per_share = _scenario(company, f, trial, "Sensitivity")["value"]
                sensitivity.append({"parameter": parameter, "value": candidate, "per_share_value": per_share, "state": "available"})
            except ModelError as exc:
                sensitivity.append({"parameter": parameter, "value": candidate, "per_share_value": None, "state": "unavailable", "notes": [str(exc)]})
        return {
            "state": "available", "method": "Operating driver FCFF", "unit": "USD/share",
            "base": base["value"], "bear": by_name.get("Bear", {}).get("value"),
            "bull": by_name.get("Bull", {}).get("value"), "scenarios": scenarios,
            "cross_check": {
                "method": "Illustrative year-5 EBIT exit multiple, discounted with interim cash flows",
                "value": cross_equity / f["diluted_shares"], "independence": "shared assumptions",
                "notes": ["An alternative terminal closure, not independent corroboration.",
                          "The illustrative multiple has no external peer evidence; the same operating forecast and claim bridge are reused."],
            },
            "sensitivity": sensitivity, "reverse": _reverse(company, f, a), "data_gaps": gaps,
            "as_of": company["as_of"], "research_only": True, "human_decision": "pending",
            "coverage": "synthetic_preliminary" if input_mode == "synthetic" else "preliminary",
            "input_mode": input_mode, "amount_unit": "USD millions",
            "scenario_notes": "Bear and Bull jointly vary demand, conversion and capital costs; no probability calibration is claimed.",
        }
    except (ModelError, OverflowError) as exc:
        return _unavailable([str(exc)])


def technical_summary(prices: list[dict], decision_ts: str | None = None) -> dict:
    """Descriptive close-only indicators, optionally bounded by an aware cutoff.

    Supplied bar dates must be no later than the cutoff date. Date-only bars have
    no intraday availability metadata; this guard does not certify same-day use.
    Future bars fail closed rather than silently being removed from the sample.
    """
    empty = {"state": "unavailable", "trend": "unknown", "ma20": None, "ma60": None,
             "ma200": None, "rsi14": None, "max_drawdown": None, "as_of": None}
    cutoff_date = None
    if decision_ts is not None:
        try:
            cutoff_date = _timestamp(decision_ts, "decision_ts").date()
        except ModelError as exc:
            return {**empty, "notes": [str(exc)]}
    if not isinstance(prices, list) or not prices:
        return {**empty, "notes": ["No price bars supplied."]}
    closes, dates = [], []
    try:
        for bar in prices:
            if not isinstance(bar, dict):
                raise ModelError("Price bar must be an object")
            closes.append(_number(bar, "close", lower=0.0000001))
            _number(bar, "volume", lower=0)
            dates.append(date.fromisoformat(bar["date"]))
            if cutoff_date is not None and dates[-1] > cutoff_date:
                raise ModelError("look-ahead: a price bar is later than the decision cutoff date")
        if any(b <= a for a, b in zip(dates, dates[1:])):
            raise ModelError("Price bars must have unique dates in increasing order")
    except (ModelError, ValueError, KeyError, TypeError) as exc:
        return {**empty, "notes": [str(exc)]}
    mas = {window: sum(close / window for close in closes[-window:]) if len(closes) >= window else None for window in (20, 60, 200)}
    rsi = None
    if len(closes) >= 15:
        changes = [b - a for a, b in zip(closes, closes[1:])]
        gain = sum(max(0.0, change) / 14 for change in changes[:14])
        loss = sum(max(0.0, -change) / 14 for change in changes[:14])
        for change in changes[14:]:
            gain = gain * (13 / 14) + max(0.0, change) / 14
            loss = loss * (13 / 14) + max(0.0, -change) / 14
        rsi = 50.0 if gain == loss == 0 else (100.0 if loss == 0 else 100 - 100 / (1 + gain / loss))
    peak, drawdown = closes[0], 0.0
    for close in closes:
        peak = max(peak, close)
        drawdown = min(drawdown, close / peak - 1)
    trend = "unknown"
    if mas[200] is not None:
        trend = "rising" if closes[-1] > mas[20] > mas[60] > mas[200] else (
            "falling" if closes[-1] < mas[20] < mas[60] < mas[200] else "mixed")
    return {
        "state": "available" if len(closes) >= 200 else "partial", "trend": trend,
        "ma20": mas[20], "ma60": mas[60], "ma200": mas[200], "rsi14": rsi,
        "max_drawdown": drawdown, "as_of": dates[-1].isoformat(), "bars": len(closes),
        "notes": ["Close-only descriptive snapshot; long averages require their full warm-up.",
                  "Wilder RSI(14); maximum close-to-close drawdown is a non-positive fraction.",
                  "Date-only bars do not establish intraday availability; same-day use requires external timing evidence.",
                  "Bar adjustment and holiday provenance are supplied externally; no actual market or liquidity verification is performed."],
    }
