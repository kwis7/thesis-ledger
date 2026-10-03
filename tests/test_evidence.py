"""Point-in-time and unit/period guards with explicit negative controls."""

from copy import deepcopy
from datetime import datetime
import math
import unittest

from thesisledger.fixtures import DECISION_TS, build_demo_companies
from thesisledger.valuation import validate_evidence, value_company


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.company = build_demo_companies()[0]
        self.evidence = deepcopy(self.company["evidence"][0])

    def test_every_baseline_source_is_available_at_decision(self):
        cutoff = datetime.fromisoformat(DECISION_TS)
        for company in build_demo_companies():
            for evidence in company["evidence"]:
                self.assertEqual(validate_evidence(evidence, DECISION_TS), [])
                for key in ("published_at", "retrieved_at", "usable_at"):
                    self.assertLessEqual(datetime.fromisoformat(evidence[key]), cutoff)
                self.assertEqual(evidence["source"], "Synthetic fixture")
                self.assertEqual(evidence["source_type"], "synthetic")
                self.assertTrue(evidence["url"].startswith("fixture://"))

    def test_later_source_is_excluded_before_release_and_accepted_after(self):
        item = deepcopy(self.evidence)
        item.update(published_at="2026-08-01T12:00:00+00:00", retrieved_at="2026-08-01T13:00:00+00:00",
                    usable_at="2026-08-01T14:00:00+00:00")
        self.assertTrue(any("look-ahead" in error for error in validate_evidence(item, DECISION_TS)))
        self.assertEqual(validate_evidence(item, "2026-08-01T15:00:00+00:00"), [])
        self.company["evidence"].append(item)
        self.assertEqual(value_company(self.company)["state"], "unavailable")

    def test_timestamps_must_exist_and_be_timezone_aware(self):
        for key in ("published_at", "retrieved_at", "usable_at"):
            for invalid in (None, "2026-07-01T12:00:00", "not a timestamp"):
                with self.subTest(key=key, invalid=invalid):
                    item = deepcopy(self.evidence)
                    item[key] = invalid
                    self.assertTrue(any(key in error for error in validate_evidence(item, DECISION_TS)))
        self.assertTrue(any("decision_ts" in error for error in validate_evidence(self.evidence, "2026-07-01")))

    def test_usable_cannot_precede_publication_or_retrieval(self):
        item = deepcopy(self.evidence)
        item["usable_at"] = "2026-07-01T11:00:00+00:00"
        self.assertTrue(any("precede publication" in error for error in validate_evidence(item, DECISION_TS)))
        item["usable_at"] = "2026-07-01T12:30:00+00:00"
        self.assertTrue(any("precede retrieval" in error for error in validate_evidence(item, DECISION_TS)))

    def test_retrieval_after_cutoff_cannot_support_ex_ante_acquisition(self):
        item = deepcopy(self.evidence)
        item["retrieved_at"] = "2026-07-02T13:00:00+00:00"
        errors = validate_evidence(item, DECISION_TS)
        self.assertTrue(any("acquired after" in error for error in errors))

    def test_unit_currency_period_and_locator_are_required(self):
        for key in ("unit", "currency", "period", "locator", "content"):
            item = deepcopy(self.evidence)
            del item[key]
            self.assertTrue(any(key in error for error in validate_evidence(item, DECISION_TS)))

    def test_unverified_fact_and_missing_classification_are_explicit_errors(self):
        item = deepcopy(self.evidence)
        item["verified"] = False
        self.assertTrue(any("unverified facts" in error for error in validate_evidence(item, DECISION_TS)))
        del item["classification"]
        self.assertTrue(any("classification" in error for error in validate_evidence(item, DECISION_TS)))
        item["classification"] = []
        self.assertTrue(any("classification" in error for error in validate_evidence(item, DECISION_TS)))

    def test_nested_nonfinite_values_are_rejected(self):
        item = deepcopy(self.evidence)
        item["model_input"] = {"value": math.inf}
        self.assertTrue(any("model_input.value" in error for error in validate_evidence(item, DECISION_TS)))

    def test_quarterly_evidence_can_have_provenance_but_cannot_be_annualized(self):
        item = deepcopy(self.evidence)
        item["period"] = "Q2 2026"
        item["period_type"] = "quarterly"
        self.assertEqual(validate_evidence(item, DECISION_TS), [])
        item["annualized_from_quarter"] = True
        self.assertTrue(any("silently annualized" in error for error in validate_evidence(item, DECISION_TS)))
        self.company["financials"].update(period_type="quarterly", period="Q2 2026", period_start="2026-04-01")
        result = value_company(self.company)
        self.assertEqual(result["state"], "unavailable")
        self.assertTrue(any("quarterly input is not annualized" in gap for gap in result["data_gaps"]))

    def test_fake_annual_label_short_period_and_wrong_unit_fail_closed(self):
        quarter = deepcopy(self.company)
        quarter["financials"]["period_start"] = "2026-04-01"
        self.assertTrue(any("complete annual" in gap for gap in value_company(quarter)["data_gaps"]))
        for key, wrong in (("currency", "EUR"), ("amount_unit", "USD thousands"), ("share_unit", "shares")):
            company = deepcopy(self.company)
            company["financials"][key] = wrong
            self.assertEqual(value_company(company)["state"], "unavailable")

    def test_stale_annual_data_requires_interim_stub_bridge(self):
        stale = deepcopy(self.company)
        stale["as_of"] = "2026-09-01T16:00:00+00:00"
        self.assertTrue(any("interim/stub bridge" in gap for gap in value_company(stale)["data_gaps"]))

    def test_future_price_and_naive_value_date_are_not_used(self):
        company = deepcopy(self.company)
        company["price_as_of"] = "2026-07-02T20:00:00+00:00"
        self.assertEqual(value_company(company)["state"], "unavailable")
        company["price_as_of"] = self.company["price_as_of"]
        company["as_of"] = "2026-07-01T16:00:00"
        self.assertEqual(value_company(company)["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
