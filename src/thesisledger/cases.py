"""Packaged, public-only case inputs. No personal research is imported."""
import json
from pathlib import Path


def exe_facts():
    return json.loads((Path(__file__).parent / "data" / "exe-facts.json").read_text(encoding="utf-8"))


def exe_company():
    packet = exe_facts()
    facts = packet["facts"]
    def fact(metric, year=2025):
        matches = [row for row in facts if row.get("metric") == metric and row.get("end", "").startswith(str(year))]
        if len(matches) != 1:
            raise ValueError(f"EXE fixture needs exactly one {year} {metric} fact")
        return matches[0]
    # No synthetic quote or historical market performance is added to a real issuer.
    acquired = max(row["retrieved_at"] for row in facts)
    evidence = []
    for row in facts:
        evidence.append({"id": row["id"], "title": row.get("metric", row["concept"]),
            "accession": row["accn"], "source": "SEC EDGAR Company Facts", "source_type": "regulatory_filing",
            "url": row.get("source_url", "https://data.sec.gov/api/xbrl/companyfacts/CIK0000895126.json"),
            "published_at": row.get("available_at", row["filed"]+"T00:00:00+00:00"),
            "retrieved_at": row["retrieved_at"], "usable_at": row["retrieved_at"],
            "period": row["end"], "unit": row["unit"], "currency": "USD",
            "locator": row.get("source_pointer", row["accn"]+" / "+row["concept"]),
            "content": f"{row['concept']} = {row['val']} {row['unit']} for {row['end']}; accession {row['accn']}.",
            "classification": "confirmed_fact", "verified": True})
    assumptions = {"annual_production": fact("production")["val"], "realized_price": 3.5,
        "cash_cost": 1.5, "annual_capex": fact("capex")["val"]/1e6,
        "discount_rate": .10, "reserve_life_years": 8, "production_growth": 0.0,
        "realized_price_growth": 0.0, "cost_growth": 0.0, "tax_rate": .25,
        "da_per_unit": fact("dda")["val"]/1e6/fact("production")["val"], "nwc_ratio": 0.0}
    assumption_id = "exe-educational-assumptions"
    evidence.append({"id": assumption_id, "title": "Explicit educational forward premises", "source": "ThesisLedger case design",
        "source_type": "model_premise", "url": "https://www.sec.gov/Archives/edgar/data/895126/", "published_at": acquired,
        "retrieved_at": acquired, "usable_at": acquired, "period": "Forward 12-month operating intervals",
        "unit": "Mixed; individual parameters labeled", "currency": "USD", "locator": "cases.py / assumptions",
        "content": "Forward realized price, aggregate cash cost, horizon, tax rate and constant production are educational premises. Last annual production, reported cash capex and DD&A anchor assumptions; they do not establish future sustaining economics. Last-reported balances and weighted diluted shares are illustrative proxies.",
        "classification": "model_assumption", "verified": True})
    financials = {"currency": "USD", "amount_unit": "USD millions", "share_unit": "million shares",
        "period_type": "annual", "period": "FY2025 reported history", "period_start": "2025-01-01", "period_end": "2025-12-31",
        "revenue": fact("revenue")["val"]/1e6, "cash": fact("cash")["val"]/1e6,
        "debt": fact("debt")["val"]/1e6, "diluted_shares": fact("diluted_shares")["val"]/1e6,
        "minorities": 0.0, "operating_nwc": 0.0,
        "proved_reserves_million_mcfe": fact("proved_reserves")["val"]}
    return {"symbol": "EXE", "name": "Expand Energy Corporation", "sector": "Natural gas production",
        "archetype": "commodity", "currency": "USD", "as_of": acquired,
        "case_label": "EXE public filings with educational forecast assumptions",
        "case_id": "exe-sec-2024-2025", "forecast_basis": "explicit_forward_12_month_assumptions",
        "balance_sheet_bridge": {"method": "hold_last_reported", "classification": "model_assumption", "as_of": acquired,
            "notes": "No post-year-end acquisitions, cash movements or financing bridge is asserted."},
        "description": "A public filing case for connecting production, realized prices, costs and capital to finite-horizon cash flows. No current quote or investment target is supplied.",
        "financials": financials, "assumptions": assumptions, "evidence": evidence, "prices": [],
        "thesis": {"statement": "Gas demand becomes per-share cash only through realized prices, production, operating costs and required capital.",
            "drivers": [{"id": key, "label": key.replace("_", " ").title(), "value": value,
                "unit": {"annual_production": "million Mcfe/year", "realized_price": "USD/Mcfe", "cash_cost": "USD/Mcfe", "annual_capex": "USD millions/year", "reserve_life_years": "years"}.get(key, "ratio"),
                "evidence_ids": [assumption_id], "watch_condition": "Re-underwrite with comparable public operating evidence"} for key, value in assumptions.items() if key in {"annual_production", "realized_price", "cash_cost", "annual_capex", "discount_rate", "reserve_life_years"}],
            "counterevidence": ["2024 includes a partial-year merger contribution, so reported growth is not organic growth.",
                "Reserve totals do not prove flat deliverability or maintenance capital efficiency."],
            "falsifiers": ["Required sustaining capital or aggregate costs exceed the assumed path.", "Realized netbacks do not follow the commodity-demand thesis."],
            "next_review": "Reconcile new filings, operating guidance, hedges and financing before changing assumptions."}}


def exe_agent_inputs():
    packet = exe_facts()
    hints = []
    for parameter, metric, reason in (
        ("annual_production", "production", "Merger effects prevent reported production growth from proving a forward growth rate."),
        ("annual_capex", "capex", "Reported cash capital spending is not a proven sustaining-capital requirement."),
        ("cash_cost", "production_cost", "Lifting costs exclude other cash costs; reconcile transport, overhead and hedges.")):
        refs = [row["id"] for row in packet["facts"] if row.get("metric") == metric]
        if refs:
            hints.append({"parameter": parameter, "evidence_ids": refs, "rationale": reason})
    return {"facts": packet["facts"], "mapping_hints": hints, "comparability": packet.get("comparability", []),
            "limitations": packet.get("limitations", []), "public_only": True}


def exe_review_event(company):
    filings = exe_agent_inputs()
    refs = [key for hint in filings["mapping_hints"] for key in hint["evidence_ids"]]
    evidence = [row for row in company["evidence"] if row["id"] in refs]
    return {"id": "exe-2025-filing-review", "symbol": "EXE", "kind": "ambiguous_evidence",
        "title": "EXE annual filing changes need an operating review",
        "summary": "Compare reported production and capital spending, then reconcile merger effects, sustaining capital and total cash costs. Historical changes do not directly replace forward assumptions.",
        "source": "SEC EDGAR 2024 and 2025 10-K filings", "source_document": "exe-sec-2024-2025",
        "published_at": max(row["published_at"] for row in evidence), "decision_ts": company["as_of"],
        "verified": True, "evidence_ids": sorted(set(refs)), "changes": [], "evidence": evidence}
