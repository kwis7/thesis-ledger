"""Read-only sandbox calculations. No model revision or provider call occurs."""
from .valuation import value_company


PARAMETERS = [
    {"key": "realized_price", "label": "Realized price", "unit": "USD/Mcfe", "min": 2, "max": 6, "step": .05},
    {"key": "annual_production", "label": "Annual production", "unit": "million Mcfe/year", "min": 1000, "max": 4000, "step": 1},
    {"key": "cash_cost", "label": "Cash cost", "unit": "USD/Mcfe", "min": .5, "max": 3, "step": .05},
    {"key": "annual_capex", "label": "Annual capital spending", "unit": "USD millions/year", "min": 1000, "max": 5000, "step": 1},
    {"key": "discount_rate", "label": "Discount rate", "unit": "fraction", "min": .05, "max": .2, "step": .005},
    {"key": "reserve_life_years", "label": "Assumed cash-flow horizon", "unit": "years", "min": 1, "max": 10, "step": 1},
]


def research_lab(company, facts, overrides=None):
    if company.get("archetype") != "commodity":
        raise ValueError("The first Research Lab supports the public EXE producer case")
    overrides = {} if overrides is None else overrides
    if not isinstance(overrides, dict) or set(overrides)-{item["key"] for item in PARAMETERS}:
        raise ValueError("Choose supported numeric sandbox parameters")
    limits = {item["key"]: item for item in PARAMETERS}
    for key, value in overrides.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[key]["min"] <= value <= limits[key]["max"]:
            raise ValueError(f"{key}: outside supported sandbox bounds")
    baseline, candidate = value_company(company), value_company(company, overrides)
    parameter = "realized_price"
    curve = []
    for index in range(17):
        value = 2+index*.25
        result = value_company(company, dict(overrides, realized_price=value))
        curve.append({"input": value, "per_share_value": result.get("base"), "state": result["state"]})
    def pipeline(model):
        scenario = next((item for item in model.get("scenarios", []) if item["name"] == "Base"), {})
        row = (scenario.get("forecast") or [{}])[0]
        return {**{key: row.get(key) for key in ("production", "revenue", "cash_cost", "capex", "fcff", "year")}, "value": model.get("base")}
    return {"symbol": company["symbol"], "case_label": company.get("case_label", "Public-source research"),
            "parameters": [dict(item, value=overrides.get(item["key"], company["assumptions"][item["key"]])) for item in PARAMETERS],
            "baseline": baseline, "candidate": candidate, "parameter": parameter, "curve": curve,
            "pipeline": {"baseline": pipeline(baseline), "candidate": pipeline(candidate)},
            "changed_parameters": [{"parameter": key, "old": company["assumptions"][key], "new": value} for key, value in overrides.items() if value != company["assumptions"][key]],
            "facts": facts, "limitations": candidate.get("data_gaps", []),
            "sandbox": True, "persisted": False, "as_of": company["as_of"]}
