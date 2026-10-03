"""Independent numerical identities and boundary checks for the demo engines."""

from copy import deepcopy
from datetime import date, timedelta
import json
import math
import unittest

from thesisledger.fixtures import build_demo_companies
from thesisledger.valuation import technical_summary, value_company


class ValuationTests(unittest.TestCase):
    def setUp(self):
        self.industrial, self.recurring, self.financial = build_demo_companies()

    def test_fixture_is_deterministic_and_fresh(self):
        self.assertEqual(build_demo_companies(), build_demo_companies())
        first = build_demo_companies()
        first[0]["assumptions"]["qualified_utilization"] = 0.1
        self.assertEqual(build_demo_companies()[0]["assumptions"]["qualified_utilization"], 0.76)
        self.assertEqual([c["symbol"] for c in first], ["ASTER", "BCN", "HBR"])
        for company in first:
            self.assertGreaterEqual(len(company["prices"]), 210)
            self.assertTrue(all(bar["close"] > 0 and bar["volume"] > 0 for bar in company["prices"]))
            self.assertEqual(company["price"], company["prices"][-1]["close"])

    def test_industrial_physical_output_and_cash_flow_identity(self):
        result = value_company(self.industrial)
        self.assertEqual(result["state"], "available")
        base = next(s for s in result["scenarios"] if s["name"] == "Base")
        row = base["forecast"][0]
        expected_installed, expected_qualified = 12 * 1.05, 10 * 1.05
        expected_units = expected_qualified * 0.76
        expected_revenue = expected_units * 50 * 1.015
        expected_da = expected_installed * 1.7
        expected_ebit = expected_revenue - expected_units * 26 * 1.018 - 80 * 1.018 - expected_da
        self.assertAlmostEqual(row["units"], expected_units)
        self.assertAlmostEqual(row["revenue"], expected_revenue)
        self.assertAlmostEqual(row["ebit"], expected_ebit)
        self.assertAlmostEqual(row["growth_capex"], (expected_installed - 12) * 24)
        self.assertLessEqual(row["qualified_capacity"], row["installed_capacity"])
        self._assert_claim_bridge(self.industrial, base)

    def test_recurring_cohort_and_acquisition_cost_bridge(self):
        result = value_company(self.recurring)
        base = next(s for s in result["scenarios"] if s["name"] == "Base")
        row = base["forecast"][0]
        expected_customers = 0.012 * 0.93 + 0.0025
        self.assertAlmostEqual(row["customers"], expected_customers)
        self.assertAlmostEqual(row["revenue"], expected_customers * 30000 * 1.02)
        self.assertAlmostEqual(row["acquisition_cost"], 0.0025 * 14000)
        self.assertAlmostEqual(row["growth_capex"], 0.0025 * 5000)
        previous = self.recurring["financials"]["customers"]
        for row in base["forecast"]:
            self.assertAlmostEqual(row["customers"], previous * 0.93 + row["new_customers"])
            self.assertLessEqual(row["new_customers"], row["onboarding_capacity"])
            previous = row["customers"]
        self._assert_claim_bridge(self.recurring, base)

    def _assert_claim_bridge(self, company, scenario):
        a, f = scenario["assumptions"], company["financials"]
        previous_nwc = f["operating_nwc"]
        for row in scenario["forecast"]:
            self.assertAlmostEqual(row["nopat"], row["ebit"] - max(0, row["ebit"]) * a["tax_rate"])
            self.assertAlmostEqual(row["capex"], row["maintenance_capex"] + row["growth_capex"])
            self.assertAlmostEqual(row["delta_nwc"], row["operating_nwc"] - previous_nwc)
            self.assertAlmostEqual(row["fcff"], row["nopat"] + row["da"] - row["capex"] - row["delta_nwc"])
            self.assertAlmostEqual(row["pv_fcff"], row["fcff"] / (1 + a["discount_rate"]) ** row["year"])
            previous_nwc = row["operating_nwc"]
        terminal_nopat = scenario["forecast"][-1]["nopat"] * (1 + a["terminal_growth"])
        terminal_reinvestment = terminal_nopat * a["terminal_growth"] / a["terminal_roic"]
        tv = (terminal_nopat - terminal_reinvestment) / (a["discount_rate"] - a["terminal_growth"])
        expected_ev = sum(row["pv_fcff"] for row in scenario["forecast"]) + tv / (1 + a["discount_rate"]) ** 5
        expected_equity = max(0, expected_ev + f["cash"] - f["debt"] - f["minorities"])
        self.assertAlmostEqual(scenario["terminal_reinvestment"], terminal_reinvestment)
        self.assertAlmostEqual(scenario["enterprise_value"], expected_ev)
        self.assertAlmostEqual(scenario["equity_value"], expected_equity)
        self.assertAlmostEqual(scenario["value"], expected_equity / f["diluted_shares"])

    def test_senior_claims_cash_and_diluted_shares_have_correct_effect(self):
        for company in (self.industrial, self.recurring):
            with self.subTest(symbol=company["symbol"]):
                baseline = value_company(company)["base"]
                debt = deepcopy(company)
                debt["financials"]["debt"] += 10
                self.assertAlmostEqual(value_company(debt)["base"], baseline - 10 / company["financials"]["diluted_shares"])
                cash = deepcopy(company)
                cash["financials"]["cash"] += 10
                self.assertAlmostEqual(value_company(cash)["base"], baseline + 10 / company["financials"]["diluted_shares"])
                diluted = deepcopy(company)
                diluted["financials"]["diluted_shares"] *= 2
                self.assertAlmostEqual(value_company(diluted)["base"], baseline / 2)

    def test_unmodeled_claims_and_restricted_cash_cannot_be_ignored(self):
        baseline = value_company(self.industrial)
        for key in ("preferred", "preferred_stock", "convertible_debt", "restricted_cash"):
            with self.subTest(claim=key):
                company = deepcopy(self.industrial)
                company["financials"][key] = 100
                result = value_company(company)
                self.assertEqual(result["state"], "unavailable")
                self.assertIsNone(result["base"])
                self.assertTrue(any(key in gap and "common-equity bridge" in gap for gap in result["data_gaps"]))
                company["financials"][key] = 0
                self.assertAlmostEqual(value_company(company)["base"], baseline["base"])

    def test_growth_requires_expansion_and_terminal_reinvestment(self):
        baseline = value_company(self.industrial)
        costlier = value_company(self.industrial, {"capacity_cost_per_unit": 36})
        self.assertLess(costlier["base"], baseline["base"])
        first_costlier = next(s for s in costlier["scenarios"] if s["name"] == "Base")["forecast"][0]
        first_base = next(s for s in baseline["scenarios"] if s["name"] == "Base")["forecast"][0]
        self.assertAlmostEqual(first_costlier["revenue"], first_base["revenue"])
        self.assertLess(first_costlier["fcff"], first_base["fcff"])
        lower_roic = value_company(self.industrial, {"terminal_roic": 0.09})
        self.assertLess(lower_roic["base"], baseline["base"])
        base_scenario = next(s for s in baseline["scenarios"] if s["name"] == "Base")
        self.assertGreater(base_scenario["terminal_reinvestment"], 0)
        self.assertLess(base_scenario["terminal_fcff"], base_scenario["terminal_nopat"])
        recurring_capital = value_company(self.recurring, {"platform_capital_per_new_customer": 10000})
        self.assertLess(recurring_capital["base"], value_company(self.recurring)["base"])

    def test_unfunded_capital_path_requires_identified_financing_and_shares(self):
        result = value_company(self.industrial, {"capacity_cost_per_unit": 180})
        self.assertEqual(result["state"], "unavailable")
        self.assertTrue(any("external financing" in gap for gap in result["data_gaps"]))
        bear = next(s for s in value_company(self.industrial)["scenarios"] if s["name"] == "Bear")
        funding = bear["funding_review"]
        self.assertGreater(funding["maximum_cumulative_fcff_deficit"], 0)
        self.assertLess(funding["maximum_cumulative_fcff_deficit"], funding["opening_available_cash"])
        self.assertEqual(funding["future_dilution"], "not modeled")
        no_cash = deepcopy(self.industrial)
        no_cash["financials"]["cash"] = 0
        stress = value_company(no_cash)
        self.assertEqual(stress["state"], "available")
        self.assertIsNone(stress["bear"])
        self.assertTrue(any("Bear scenario infeasible" in gap and "external financing" in gap for gap in stress["data_gaps"]))

    def test_scenarios_change_connected_economic_inputs(self):
        for company in (self.industrial, self.recurring):
            result = value_company(company)
            self.assertLess(result["bear"], result["base"])
            self.assertLess(result["base"], result["bull"])
            states = {s["name"]: s["assumptions"] for s in result["scenarios"]}
            self.assertGreaterEqual(sum(states["Bear"][key] != states["Base"][key] for key in states["Base"]), 4)
            self.assertEqual(result["cross_check"]["independence"], "shared assumptions")
            self.assertEqual(result["coverage"], "synthetic_preliminary")

    def test_operating_sensitivity_reuses_forward_model(self):
        for company in (self.industrial, self.recurring):
            result = value_company(company)
            for entry in result["sensitivity"]:
                if entry["state"] == "available":
                    forward = value_company(company, {entry["parameter"]: entry["value"]})
                    self.assertAlmostEqual(entry["per_share_value"], forward["base"])

    def test_reverse_requirement_back_substitutes_using_public_model(self):
        for company in (self.industrial, self.recurring):
            reverse = value_company(company)["reverse"]
            self.assertEqual(reverse["state"], "available")
            forward = value_company(company, {reverse["parameter"]: reverse["required_value"]})
            self.assertAlmostEqual(forward["base"], company["price"], places=6)
            self.assertAlmostEqual(reverse["recomputed_price"], forward["base"])
            self.assertLessEqual(abs(reverse["price_residual"]), reverse["tolerance"])
            self.assertNotIn(reverse["parameter"], reverse["held_assumptions"])
            self.assertTrue(any("cannot identify" in note for note in reverse["notes"]))

    def test_unreachable_price_declines_reverse_claim(self):
        company = deepcopy(self.industrial)
        company["price"] = 100000
        result = value_company(company)
        self.assertEqual(result["state"], "available")
        self.assertEqual(result["reverse"]["state"], "unavailable")
        self.assertIsNone(result["reverse"]["required_value"])

    def test_rejects_infeasible_and_nonfinite_inputs(self):
        cases = [
            (self.industrial, {"qualified_utilization": 1.2}, "qualified_utilization"),
            (self.industrial, {"qualified_utilization": -0.1}, "qualified_utilization"),
            (self.industrial, {"qualified_capacity_growth": 0.30}, "qualified capacity"),
            (self.industrial, {"terminal_growth": 0.10}, "terminal_growth"),
            (self.industrial, {"terminal_roic": 0.01}, "terminal_roic"),
            (self.recurring, {"new_customers": 0.005}, "onboarding capacity"),
            (self.recurring, {"retention": 1.01}, "retention"),
            (self.recurring, {"retention": math.nan}, "finite"),
            (self.recurring, {"discount_rate": math.inf}, "finite"),
            (self.recurring, {"made_up_driver": 10}, "unsupported keys"),
        ]
        for company, assumptions, message in cases:
            with self.subTest(assumptions=assumptions):
                result = value_company(company, assumptions)
                self.assertEqual(result["state"], "unavailable")
                self.assertTrue(any(message in gap for gap in result["data_gaps"]), result)
        company = deepcopy(self.industrial)
        company["financials"]["diluted_shares"] = 0
        self.assertEqual(value_company(company)["state"], "unavailable")
        company["financials"]["diluted_shares"] = 30
        company["financials"]["unmodeled_item"] = math.nan
        self.assertEqual(value_company(company)["state"], "unavailable")

    def test_regulated_financial_is_unavailable_without_generic_fallback(self):
        result = value_company(self.financial)
        self.assertEqual(result["state"], "unavailable")
        self.assertIsNone(result["base"])
        self.assertEqual(result["scenarios"], [])
        self.assertTrue(any("capital model" in gap for gap in result["data_gaps"]))

    def test_supplied_public_metadata_is_not_mislabeled_synthetic(self):
        company = deepcopy(self.industrial)
        for item in company["evidence"]:
            item["source_type"] = "official_publication"
            item["source"] = "Supplied public metadata example"
            item["url"] = "https://example.org/fictional-input"
        result = value_company(company)
        self.assertEqual(result["input_mode"], "supplied_evidence")
        self.assertEqual(result["coverage"], "preliminary")
        self.assertFalse(any("Synthetic demonstration" in gap for gap in result["data_gaps"]))
        self.assertTrue(any("not independently verified" in gap for gap in result["data_gaps"]))

    def test_result_has_no_nonstandard_json_numbers(self):
        for company in (self.industrial, self.recurring, self.financial):
            json.dumps(value_company(company), allow_nan=False)
            json.dumps(technical_summary(company["prices"]), allow_nan=False)
        extreme = deepcopy(self.recurring)
        extreme["financials"]["customers"] = 1e308
        result = value_company(extreme)
        self.assertEqual(result["state"], "unavailable")
        json.dumps(result, allow_nan=False)
        result = value_company(self.industrial, {"exit_ebit_multiple": 1e308})
        self.assertEqual(result["state"], "unavailable")
        json.dumps(result, allow_nan=False)


class TechnicalTests(unittest.TestCase):
    def _bars(self, closes):
        start = date(2025, 1, 1)
        return [{"date": (start + timedelta(days=i)).isoformat(), "close": value, "volume": 1000}
                for i, value in enumerate(closes)]

    def test_full_warmup_and_known_average(self):
        result = technical_summary(self._bars(list(range(1, 221))))
        self.assertEqual(result["state"], "available")
        self.assertEqual(result["trend"], "rising")
        self.assertAlmostEqual(result["ma20"], (201 + 220) / 2)
        self.assertAlmostEqual(result["ma200"], (21 + 220) / 2)
        self.assertEqual(result["rsi14"], 100)
        self.assertEqual(result["max_drawdown"], 0)

    def test_missing_long_history_is_not_relabelled(self):
        result = technical_summary(self._bars(list(range(1, 61))))
        self.assertEqual(result["state"], "partial")
        self.assertIsNone(result["ma200"])
        self.assertIsNotNone(result["ma60"])
        self.assertEqual(result["trend"], "unknown")

    def test_future_bar_is_rejected_at_decision_cutoff_without_truncation(self):
        company = build_demo_companies()[0]
        baseline = technical_summary(company["prices"], company["as_of"])
        self.assertEqual(baseline["state"], "available")
        self.assertEqual(baseline["bars"], 240)
        future = company["prices"] + [{"date": "2035-01-01", "close": 100, "volume": 1000}]
        result = technical_summary(future, company["as_of"])
        self.assertEqual(result["state"], "unavailable")
        self.assertIsNone(result["ma200"])
        self.assertTrue(any("look-ahead" in note for note in result["notes"]))

    def test_technical_cutoff_requires_an_aware_timestamp(self):
        company = build_demo_companies()[0]
        for cutoff in ("2026-07-01T16:00:00", "2026-07-01", "invalid cutoff"):
            with self.subTest(cutoff=cutoff):
                result = technical_summary(company["prices"], cutoff)
                self.assertEqual(result["state"], "unavailable")
                self.assertTrue(any("decision_ts" in note for note in result["notes"]))

    def test_flat_rsi_and_drawdown(self):
        flat = technical_summary(self._bars([10] * 220))
        self.assertEqual(flat["rsi14"], 50)
        decline = technical_summary(self._bars([10, 20, 10, 15]))
        self.assertAlmostEqual(decline["max_drawdown"], -0.5)
        self.assertIsNone(decline["rsi14"])

    def test_bad_or_reordered_bars_fail_closed(self):
        for bars in ([], self._bars([1, 0]), self._bars([1, math.nan]), list(reversed(self._bars([1, 2])))):
            self.assertEqual(technical_summary(bars)["state"], "unavailable")
        extreme = technical_summary(self._bars([1e308] * 220))
        self.assertEqual(extreme["state"], "available")
        json.dumps(extreme, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
