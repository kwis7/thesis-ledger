"""Source-linked bounded research reports from canonical calculations."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta, timezone


def number(value: Any, places: int = 2) -> str:
    return f"{value:,.{places}f}" if isinstance(value, (float, int)) else "Unavailable"


def usd(value: Any) -> str:
    return "$" + number(value) if isinstance(value, (int, float)) else "Unavailable"


def render_report(company: dict, mode: str) -> str:
    valuation = company["valuation"]
    lines = [f"# {company['name']} Research Brief", "",
             f"Security: {company['symbol']} | Evidence cutoff: {company['as_of']}", "",
             "Synthetic example with invented evidence and prices." if company.get("synthetic") or mode == "synthetic_replay" else "Source-bound local research packet. Verify the supplied evidence independently.", "",
             "Status: bounded research. Full-coverage certification is not claimed.", "",
             "## Business and thesis", "", company.get("description", ""), "",
             company.get("thesis", {}).get("statement", "Thesis not recorded"), "",
             "## Operating assumptions", "", "| Driver | Value | Unit | Evidence | Review condition |",
             "| --- | ---: | --- | --- | --- |"]
    for driver in company.get("thesis", {}).get("drivers", []):
        lines.append(f"| {driver.get('label', driver.get('id'))} | {driver.get('value')} | {driver.get('unit', '')} | {', '.join(driver.get('evidence_ids', []))} | {driver.get('watch_condition', '')} |")
    lines += ["", "## Value and market expectations", "",
              f"Dated price: {usd(company.get('price'))} as of {company.get('price_as_of', 'unknown')}", "",
              f"Valuation state: {valuation['state']}", ""]
    if valuation["state"] == "available":
        lines += ["| Scenario | Present common equity value per share |", "| --- | ---: |"]
        for name in ("bear", "base", "bull"):
            lines.append(f"| {name.title()} | {usd(valuation.get(name))} |")
        lines += ["", "## Canonical financial bridge", "",
                  "Financial amounts and share counts are in millions. The model reconciles operating drivers, taxes, reinvestment, working capital, debt/cash and diluted shares.", "",
                  "| Year | Revenue | Operating profit | Free cash flow | Discounted free cash flow |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        base = next((row for row in valuation.get("scenarios", []) if row.get("name", "").lower() == "base"), {})
        for row in base.get("forecast", []):
            lines.append(f"| {row.get('year')} | {number(row.get('revenue'))} | {number(row.get('ebit', row.get('operating_profit')))} | {number(row.get('fcff', row.get('free_cash_flow')))} | {number(row.get('pv_fcff', row.get('discounted_fcf')))} |")
        cross = valuation.get("cross_check", {})
        reverse = valuation.get("reverse", {})
        lines += ["", f"Cross-check: {usd(cross.get('value'))} per share using {cross.get('method', 'an unavailable alternative method')}.", "",
                  " ".join(cross.get("notes", [])), "", "### Conditional price expectations", ""]
        if reverse.get("state") == "available":
            lines += [f"The dated price of {usd(reverse.get('target_price'))} requires {reverse.get('parameter', '').replace('_', ' ')} of {number(reverse.get('required_value'), 4)} when other assumptions stay fixed.", "",
                      f"Forward recomputation: {usd(reverse.get('recomputed_price'))} per share.", ""]
        else:
            lines += ["No feasible one-parameter reverse solution is available for this price.", ""]
        lines += ["A single price cannot identify every assumption. Reverse outputs hold the other assumptions fixed."]
    else:
        lines += ["No numerical valuation is fabricated. Missing inputs or an unsupported business model remain visible."]
    lines += ["", "## Counterevidence and falsifiers", ""]
    for item in company.get("thesis", {}).get("counterevidence", []):
        lines.append("- Counterevidence: " + item)
    for item in company.get("thesis", {}).get("falsifiers", []):
        lines.append("- Review condition: " + item)
    technical = company.get("technical", {})
    lines += ["", "## Technical conditions", "",
              f"State: {technical.get('state', 'unavailable')} | Trend: {technical.get('trend', 'unknown')} | Dated {technical.get('as_of', 'unknown')}", "",
              "| Indicator | Value |", "| --- | ---: |",
              f"| MA20 | {usd(technical.get('ma20'))} |",
              f"| MA60 | {usd(technical.get('ma60'))} |",
              f"| MA200 | {usd(technical.get('ma200'))} |",
              f"| RSI14 | {number(technical.get('rsi14'))} |",
              f"| Maximum drawdown (fraction) | {number(technical.get('max_drawdown'), 4)} |", "",
              "Technical conditions are descriptive, separate from business quality and valuation.", "",
              "## Sources and input lineage", "",
              "| Evidence | Source | Publication | Usable at | Period | Locator |",
              "| --- | --- | --- | --- | --- | --- |"]
    for evidence in company.get("evidence", []):
        lines.append(f"| {evidence.get('id')} | {evidence.get('source')} | {evidence.get('published_at')} | {evidence.get('usable_at')} | {evidence.get('period')} | {evidence.get('locator')} |")
    gaps = list(valuation.get("data_gaps", []))
    if company.get("data_status") != "fresh":
        gaps.append("Monitoring source coverage is stale. This report preserves the last dated baseline.")
    lines += ["", "## Scope and gaps", ""] + ["- " + item for item in gaps or ["The packet is a bounded example, not an independent full-company underwriting audit."]]
    lines += ["", "Next review: " + str(company.get("thesis", {}).get("next_review", "Not recorded")), "",
              "Research only. Human investment decisions remain pending. No trade or order is generated.", ""]
    return "\n".join(lines)


def digest_report(state: dict, *, period: str = "daily") -> dict:
    if period not in {"daily", "weekly"}:
        raise ValueError("Choose daily or weekly")
    end = datetime.fromisoformat(state["meta"]["as_of"]) if state["meta"]["mode"] == "synthetic_replay" else datetime.now(timezone.utc)
    start = end - timedelta(days=1 if period == "daily" else 7)
    def pending(item):
        return item["review_state"] != "reviewed"
    def timestamp(item):
        return datetime.fromisoformat(item["occurred_at"].replace("Z", "+00:00"))
    def display(item):
        return {key: item[key] for key in ("symbol", "title", "reason", "review_state", "occurred_at")}
    return {"period": period, "as_of": end.isoformat(), "mode": state["meta"]["mode"],
            "window_start": start.isoformat(), "window_end": end.isoformat(),
            "review_required": state["overview"]["review_required"],
            "items": [display(item) for item in state["alerts"] if pending(item) and start < timestamp(item) <= end],
            "overdue_items": [display(item) for item in state["alerts"] if pending(item) and timestamp(item) <= start],
            "delivery_state": "local_digest", "external_sent": False}
