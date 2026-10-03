"""Small public-case regression benchmark; no general accuracy or alpha claim."""
import copy

from .cases import exe_agent_inputs, exe_company, exe_facts
from .valuation import value_company


# Manually cross-checked against the two linked SEC 10-K statements/tables.
# Kept separate from parsed input so a changed fixture does not change its label.
GOLD = {
    2024: {"revenue": (4235000000, "USD"), "cfo": (1565000000, "USD"),
           "capex": (1557000000, "USD"), "cash": (317000000, "USD"),
           "debt": (5680000000, "USD"), "diluted_shares": (156989000, "shares"),
           "production": (1375, "Bcfe"), "proved_reserves": (20800, "Bcfe")},
    2025: {"revenue": (12124000000, "USD"), "cfo": (4575000000, "USD"),
           "capex": (2736000000, "USD"), "cash": (616000000, "USD"),
           "debt": (5009000000, "USD"), "diluted_shares": (240370000, "shares"),
           "production": (2622, "Bcfe"), "proved_reserves": (25880, "Bcfe")},
}


def evaluate_public_case(packet=None):
    from .agent import replay_run, run_agent
    packet = exe_facts() if packet is None else packet
    results = []
    for year, metrics in GOLD.items():
        for metric, (value, unit) in metrics.items():
            rows = [row for row in packet["facts"] if row.get("id") == f"exe-{year}-{metric}"]
            passed = len(rows) == 1 and rows[0].get("val") == value and rows[0].get("unit") == unit and rows[0].get("end") == f"{year}-12-31" and rows[0].get("form") == "10-K"
            results.append({"case": f"{year}-{metric}", "passed": passed})
    company = exe_company()
    inputs = dict(exe_agent_inputs(), facts=copy.deepcopy(packet["facts"]))
    run = run_agent(company, inputs)
    replayed = replay_run(run)
    results += [{"case": "offline-output-equality", "passed": replayed["output"] == run["output"]},
                {"case": "historical-change-does-not-autoforecast", "passed": all(item.get("new") is None for item in run["output"].get("suggestions", [])) and bool(run["output"].get("suggestions"))},
                {"case": "reserve-limit-fails-closed", "passed": value_company(company, {"reserve_life_years": 10})["state"] == "unavailable"}]
    return {"benchmark": "exe-public-case/v1", "scope": "16 hand-checked facts from two annual filings and three workflow guards; offline planner only",
            "passed": all(row["passed"] for row in results), "checks": len(results),
            "passed_checks": sum(row["passed"] for row in results), "results": results,
            "generalization": "No unseen-company extraction accuracy, live LLM accuracy or investment performance is claimed",
            "sources": [row["source_url"] for row in packet["filings"]],
            "output_hash": run["manifest"].get("output_sha256")}
