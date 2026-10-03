import copy
import tempfile
import unittest

from thesisledger.cases import exe_company, exe_facts
from thesisledger.engine import ResearchEngine
from thesisledger.lab import research_lab
from thesisledger.valuation import value_company


class EXETests(unittest.TestCase):
    def setUp(self):
        self.company = exe_company()

    def test_reported_scope_and_assumptions_are_separate(self):
        self.assertEqual(self.company["financials"]["period_end"], "2025-12-31")
        self.assertEqual(self.company["assumptions"]["annual_production"], 2622)
        self.assertEqual(self.company["financials"]["proved_reserves_million_mcfe"], 25880)
        self.assertFalse(exe_facts()["comparability"]["comparable"])
        self.assertNotIn("price", self.company)
        self.assertEqual(value_company(self.company)["reverse"]["state"], "unavailable")

    def test_finite_cash_flow_equation_and_claim_bridge(self):
        model = value_company(self.company)
        base = next(row for row in model["scenarios"] if row["name"] == "Base")
        a, f = self.company["assumptions"], self.company["financials"]
        self.assertEqual(len(base["forecast"]), 8)
        for row in base["forecast"]:
            revenue = 2622*3.5
            cash_cost = 2622*1.5
            taxes = max(0, revenue-cash_cost-2980)*.25
            self.assertAlmostEqual(row["revenue"], revenue)
            self.assertAlmostEqual(row["fcff"], revenue-cash_cost-taxes-2736)
        expected_ev = sum(row["fcff"]/(1.1**row["year"]) for row in base["forecast"])
        expected_value = max(0, expected_ev+616-5009)/240.37
        self.assertAlmostEqual(base["value"], expected_value)
        self.assertEqual(base["terminal_value"], 0)
        self.assertLess(base["cumulative_production_million_mcfe"], f["proved_reserves_million_mcfe"])

    def test_reserve_shortfall_and_unfunded_path_withhold_value(self):
        for overrides, phrase in (({"reserve_life_years": 10}, "exceeds reported proved reserves"),
                                  ({"realized_price": 2, "annual_capex": 5000}, "funding"),
                                  ({"production_growth": .05}, "production_growth")):
            model = value_company(self.company, overrides)
            self.assertEqual(model["state"], "unavailable")
            self.assertTrue(any(phrase in gap for gap in model["data_gaps"]))

    def test_explicit_balance_bridge_and_known_claims_are_required(self):
        for field, replacement in (("balance_sheet_bridge", {}), ("forecast_basis", "annualize_latest_quarter")):
            company = copy.deepcopy(self.company)
            company[field] = replacement
            self.assertEqual(value_company(company)["state"], "unavailable")
        company = copy.deepcopy(self.company)
        company["financials"]["preferred_stock"] = 100
        self.assertEqual(value_company(company)["state"], "unavailable")

    def test_sandbox_changes_money_without_mutating_inputs(self):
        baseline = copy.deepcopy(self.company)
        lab = research_lab(self.company, exe_facts()["facts"], {"realized_price": 4})
        self.assertGreater(lab["candidate"]["base"], lab["baseline"]["base"])
        self.assertEqual(self.company, baseline)
        self.assertFalse(lab["persisted"])
        with self.assertRaises(ValueError):
            research_lab(self.company, [], {"realized_price": True})
        with self.assertRaises(ValueError):
            research_lab(self.company, [], {"tax_rate": .2})

    def test_refresh_false_verification_and_changed_packet_id_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            engine.import_company(self.company)
            revised = copy.deepcopy(self.company)
            revised["financials"]["cash"] += 10
            engine.propose_baseline(revised)
            from thesisledger.store import decode
            event = decode(engine.store.rows("SELECT payload FROM source_events")[0]["payload"])
            event["proposed_company"]["assumptions"]["realized_price"] = 4
            with self.assertRaises(ValueError):
                engine.ingest_event(event)
            event["id"] = "unverified-new-refresh"
            event["verified"] = False
            event["evidence"], event["evidence_ids"] = [], []
            with self.assertRaises(ValueError):
                engine.ingest_event(event)
            self.assertEqual(len(engine.company("EXE")["history"]), 1)

    def test_sec_monitor_new_periodic_metadata_alerts_once_without_model_change(self):
        from thesisledger.sec_monitor import check_exe_filings
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            engine.import_company(self.company)
            before = engine.company("EXE")["valuation"]["base"]
            def collector(*args):
                return {"issuer": {"tickers": ["EXE"]}, "as_of": self.company["as_of"], "filings": [{
                    "form": "10-Q", "accessionNumber": "0000895126-26-999999", "filingDate": "2026-08-01", "available_at": "2026-08-02T04:00:00+00:00",
                    "reportDate": "2026-06-30", "source_url": "https://www.sec.gov/Archives/edgar/data/895126/"}]}
            first = check_exe_filings(engine, "test-app test@example.org", collector=collector)
            second = check_exe_filings(engine, "test-app test@example.org", collector=collector)
            self.assertEqual(first["alerts_created"], 1)
            self.assertEqual(second["alerts_created"], 0)
            self.assertEqual(engine.company("EXE")["valuation"]["base"], before)
            self.assertEqual(len(engine.company("EXE")["history"]), 1)

    def test_direct_agent_rejects_private_fields_before_planner(self):
        from thesisledger.agent import run_agent
        class MustNotRun:
            def next_step(self, context):
                raise AssertionError("Planner must not receive prohibited fields")
        company = copy.deepcopy(self.company)
        company["holdings"] = []
        with self.assertRaises(ValueError):
            run_agent(company, {"facts": []}, planner=MustNotRun())

    def test_refresh_acceptance_detects_saved_packet_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            engine.import_company(self.company)
            revised = copy.deepcopy(self.company)
            revised["assumptions"]["realized_price"] = 3.6
            engine.propose_baseline(revised)
            reviewed = engine.company("EXE")
            from thesisledger.store import decode, encode
            with engine.store.connect(write=True) as connection:
                row = connection.execute("SELECT payload FROM source_events WHERE id=?", (reviewed["candidate_event_id"],)).fetchone()
                altered = decode(row["payload"])
                altered["proposed_company"]["assumptions"]["realized_price"] = 4.1
                connection.execute("UPDATE source_events SET payload=? WHERE id=?", (encode(altered), reviewed["candidate_event_id"]))
            with self.assertRaises(ValueError):
                engine.accept_assumptions("EXE", reviewed["candidate_event_id"], reviewed["candidate_baseline_hash"], reviewed["candidate_hash"])
            self.assertEqual(len(engine.company("EXE")["history"]), 1)

    def test_dated_commodity_driver_proposal_keeps_explicit_balance_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            engine.import_company(self.company)
            from datetime import datetime, timedelta
            cutoff = (datetime.fromisoformat(self.company["as_of"])+timedelta(seconds=1)).isoformat()
            evidence = copy.deepcopy(self.company["evidence"][-1])
            evidence["id"] = "test-new-price-premise"
            event = {"id": "test-commodity-price", "symbol": "EXE", "kind": "driver_change",
                     "title": "Test-only price premise", "source_document": "test-commodity-price", "published_at": self.company["as_of"],
                     "decision_ts": cutoff, "verified": True, "evidence": [evidence], "evidence_ids": [evidence["id"]],
                     "changes": [{"parameter": "realized_price", "new": 4}]}
            engine.ingest_event(event)
            candidate = engine.company("EXE")
            self.assertIsNotNone(candidate["candidate_valuation"])
            engine.accept_assumptions("EXE", candidate["candidate_event_id"], candidate["candidate_baseline_hash"], candidate["candidate_hash"])
            accepted = engine.company("EXE")
            self.assertEqual(accepted["balance_sheet_bridge"]["as_of"], cutoff)
            self.assertEqual(accepted["valuation"]["state"], "available")

    def test_baseline_refresh_requires_pinned_review_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            engine.import_company(self.company)
            before = engine.company("EXE")
            revised = copy.deepcopy(self.company)
            revised["financials"]["cash"] += 10  # Test-only hypothetical opening balance.
            engine.propose_baseline(revised)
            candidate = engine.company("EXE")
            self.assertEqual(candidate["financials"]["cash"], before["financials"]["cash"])
            with self.assertRaises(ValueError):
                engine.accept_assumptions("EXE", candidate["candidate_event_id"], candidate["candidate_baseline_hash"], "wrong")
            engine.accept_assumptions("EXE", candidate["candidate_event_id"], candidate["candidate_baseline_hash"], candidate["candidate_hash"])
            after = engine.company("EXE")
            self.assertEqual(len(after["history"]), 2)
            self.assertEqual(after["history"][-1]["company"]["financials"]["cash"], 616)
            self.assertEqual(after["financials"]["cash"], 626)
            self.assertEqual(len(after["forecast_cohorts"]), 16)


if __name__ == "__main__":
    unittest.main()
