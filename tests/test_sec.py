"""SEC negative controls, source-excerpt integrity, and offline collector tests."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from thesisledger import sec


ROOT = Path(__file__).resolve().parents[1]
EXCERPT = ROOT / "examples" / "sec" / "companyfacts-excerpt.json"
BUNDLE = ROOT / "src" / "thesisledger" / "data" / "exe-facts.json"
EARLY = "0000895126-25-000021"
LATE = "0000895126-26-000011"


def _pointer(document, pointer):
    for key in pointer.strip("/").split("/"):
        document = document[int(key)] if isinstance(document, list) else document[key]
    return document


class SECSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(EXCERPT.read_text())
        cls.bundle = json.loads(BUNDLE.read_text())

    def test_fixture_hashes_and_original_rows_are_traceable(self):
        for source in self.bundle["sources"]:
            excerpt = ROOT / source["excerpt_file"]
            self.assertEqual(hashlib.sha256(excerpt.read_bytes()).hexdigest(), source["excerpt_sha256"])
            metadata = json.loads(excerpt.read_text())["_provenance"]["source"]
            self.assertEqual(metadata["sha256"], source["sha256"])
            self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(len(self.bundle["filings"]), 2)
        self.assertEqual(len({f["id"] for f in self.bundle["facts"]}), len(self.bundle["facts"]))
        for fact in self.bundle["facts"]:
            original = _pointer(self.source, fact["excerpt_pointer"])
            for field in ("start", "end", "filed", "accn", "form", "val"):
                self.assertEqual(fact[field], original.get(field))
            self.assertEqual(fact["source_sha256"], self.source["_provenance"]["source"]["sha256"])

    def test_same_day_date_cannot_prove_intraday_public_availability(self):
        self.assertEqual(sec.select_facts(self.source, "2025-02-26", accession=EARLY), [])
        self.assertEqual(sec.select_facts(self.source, "2025-02-26T23:59:59Z", accession=EARLY), [])
        self.assertEqual(sec.select_facts(self.source, "2025-02-27T04:59:59Z", accession=EARLY), [])
        self.assertGreater(len(sec.select_facts(self.source, "2025-02-27T05:00:00Z", accession=EARLY)), 0)
        self.assertEqual(sec.select_facts(self.source, "2026-02-18T23:59:59Z", accession=LATE), [])

    def test_later_filing_comparative_cannot_leak_into_earlier_cutoff(self):
        earlier = sec.select_facts(self.source, "2025-02-27T05:00:00Z")
        self.assertEqual({f["accn"] for f in earlier}, {EARLY})
        latest = sec.select_facts(self.source, "2026-02-19T05:00:00Z")
        comparative = [f for f in latest if f["concept"] == "Revenues" and f["end"] == "2024-12-31"]
        self.assertEqual({f["accn"] for f in comparative}, {EARLY, LATE})
        # A 2025 fiscal-year filing carries a 2024 economic-period comparative.
        original = self.source["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
        self.assertTrue(any(r["fy"] == 2025 and r["end"] == "2024-12-31" for r in original))

    def test_metric_selection_requires_accession_for_comparative_ambiguity(self):
        facts = sec.select_facts(self.source, "2026-02-19")
        query = dict(taxonomy="us-gaap", concept="Revenues", unit="USD", start="2024-01-01", end="2024-12-31")
        with self.assertRaisesRegex(sec.SECError, "found 2"):
            sec.require_fact(facts, **query)
        selected = sec.require_fact(facts, **query, accession=EARLY)
        self.assertEqual(selected["val"], 4235000000)

    def test_unit_and_duration_are_not_inferred_or_annualized(self):
        facts = sec.select_facts(self.source, "2026-02-19", accession=LATE)
        query = dict(taxonomy="srt", concept="ProvedDevelopedAndUndevelopedReserveProductionEnergy",
                     unit="Bcfe", start="2025-01-01", end="2025-12-31", accession=LATE)
        self.assertEqual(sec.require_fact(facts, **query)["val"], 2622)
        for change in ({"unit": "Bcf"}, {"unit": "USD millions"}, {"start": "2025-10-01"}, {"start": None}):
            with self.subTest(change=change), self.assertRaises(sec.SECError):
                sec.require_fact(facts, **{**query, **change})

    def test_stock_balance_and_duration_share_definitions_stay_distinct(self):
        facts = {f["id"]: f for f in self.bundle["facts"]}
        self.assertEqual(facts["exe-2025-common_outstanding_shares"]["end"], "2026-02-11")
        self.assertEqual(facts["exe-2025-diluted_shares"]["start"], "2025-01-01")
        self.assertIsNone(facts["exe-2025-issued_shares"]["start"])
        self.assertNotEqual(facts["exe-2025-common_outstanding_shares"]["val"],
                            facts["exe-2025-diluted_shares"]["val"])
        self.assertFalse(self.bundle["comparability"]["comparable"])

    def test_acquisition_is_honest_and_debt_components_reconcile(self):
        self.assertTrue(self.bundle["as_of"].startswith("2026-10-03"))
        for fact in self.bundle["facts"]:
            self.assertGreater(fact["retrieved_at"], fact["available_at"])
        for year in (2024, 2025):
            facts = {f["metric"]: f["val"] for f in self.bundle["facts"] if f["id"].startswith(f"exe-{year}-")}
            self.assertEqual(facts["debt"], facts["debt_current"] + facts["debt_noncurrent"])

    def test_conflicting_duplicates_fail_and_equivalent_contexts_collapse(self):
        source = deepcopy(self.source)
        rows = source["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
        rows.append(deepcopy(rows[0]))
        concepts = ["us-gaap:Revenues"]
        self.assertEqual(len(sec.select_facts(source, "2026-02-19", concepts=concepts)), 3)
        rows[-1]["val"] += 1
        with self.assertRaisesRegex(sec.SECError, "conflicting duplicate"):
            sec.select_facts(source, "2026-02-19", concepts=concepts)

    def test_malformed_nonfinite_and_future_period_rows_fail_closed(self):
        for field, value in (("val", float("nan")), ("val", True), ("end", "2026-12-31"),
                             ("start", "2026-01-01"), ("filed", "bad"), ("accn", "bad"), ("form", "")):
            source = deepcopy(self.source)
            source["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(sec.SECError):
                sec.select_facts(source, "2027-01-01", concepts=["us-gaap:Revenues"])
        with self.assertRaisesRegex(sec.SECError, "timezone"):
            sec.select_facts(self.source, "2026-02-19T12:00:00")

    def test_eastern_midnight_handles_summer_winter_and_dst_boundaries(self):
        try:
            sec.ZoneInfo("America/New_York")
        except sec.ZoneInfoNotFoundError:
            self.skipTest("host has no IANA database; conservative fallback is tested separately")
        expected = {
            "2026-01-01": "2026-01-02T05:00:00+00:00",
            "2026-07-01": "2026-07-02T04:00:00+00:00",
            "2026-03-07": "2026-03-08T05:00:00+00:00",
            "2026-03-08": "2026-03-09T04:00:00+00:00",
            "2026-10-31": "2026-11-01T04:00:00+00:00",
            "2026-11-01": "2026-11-02T05:00:00+00:00",
        }
        for filed, available in expected.items():
            with self.subTest(filed=filed):
                self.assertEqual(sec.public_available_at(filed), available)

    def test_timezone_database_absence_uses_conservative_five_utc(self):
        with patch.object(sec, "ZoneInfo", side_effect=sec.ZoneInfoNotFoundError("no IANA data")):
            self.assertEqual(sec.public_available_at("2026-07-01"), "2026-07-02T05:00:00+00:00")
            self.assertEqual(sec.public_available_at("2026-01-01"), "2026-01-02T05:00:00+00:00")


class SECCollectorTests(unittest.TestCase):
    def setUp(self):
        self.submissions = json.loads((ROOT / "examples" / "sec" / "submissions-excerpt.json").read_text())
        self.companyfacts = json.loads(EXCERPT.read_text())

    def fetch(self, url, user_agent):
        data = self.submissions if "/submissions/" in url else self.companyfacts
        raw = json.dumps(data).encode()
        metadata = {"url": url, "retrieved_at": "2026-10-03T02:45:44+00:00", "http_status": 200,
                    "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "headers": {"Content-Type": "application/json"}}
        return data, raw, metadata

    def test_explicit_collector_only_gets_fixed_endpoints_and_hashes_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sec, "_fetch_json", side_effect=self.fetch) as fetch, patch.object(sec.time, "sleep") as sleep:
            result = sec.collect_company("895126", directory, "Research App researcher@example.test", "2025-02-27")
            self.assertEqual([call.args[0] for call in fetch.call_args_list], [
                "https://data.sec.gov/submissions/CIK0000895126.json",
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0000895126.json"])
            sleep.assert_called_once_with(1.0)
            self.assertEqual(result["issuer"]["tickers"], ["EXE"])
            self.assertEqual([f["accessionNumber"] for f in result["filings"]], [EARLY])
            for source in result["sources"]:
                self.assertEqual(hashlib.sha256(Path(source["cache_path"]).read_bytes()).hexdigest(), source["sha256"])
                self.assertNotIn("researcher@example.test", Path(source["metadata_path"]).read_text())
            # Same bytes are content-addressed; a second invocation cannot grow the cache.
            paths = set(Path(directory).glob("sec-*.json"))
            sec.collect_company("895126", directory, "Research App researcher@example.test")
            self.assertEqual(paths, set(Path(directory).glob("sec-*.json")))

    def test_invalid_identity_user_agent_and_naive_cutoff_make_no_request(self):
        for cik in ("https://localhost/", "895126/../", "0000000000", True, -1, "1" * 11):
            with self.subTest(cik=cik), patch.object(sec, "_fetch_json") as fetch, self.assertRaises(sec.SECError):
                sec.collect_company(cik, "/unused", "Research App")
            fetch.assert_not_called()
        with patch.object(sec, "_fetch_json") as fetch:
            for user_agent in ("", "test", "Research\nInjected"):
                with self.assertRaises(sec.SECError):
                    sec.collect_company("895126", "/unused", user_agent)
            with self.assertRaises(sec.SECError):
                sec.collect_company("895126", "/unused", "Research App", "2026-10-02T12:00:00")
            fetch.assert_not_called()

    def test_cache_budget_is_enforced_without_pruning_existing_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sec, "_fetch_json", side_effect=self.fetch), patch.object(sec, "MAX_CACHE_BYTES", 1):
            existing = Path(directory) / "keep.txt"
            existing.write_text("preserve")
            with self.assertRaisesRegex(sec.SECError, "64 MiB"):
                sec.collect_company("895126", directory, "Research App")
            self.assertEqual(existing.read_text(), "preserve")
            self.assertEqual(list(Path(directory).glob("sec-*.json")), [])

    def test_response_cik_mismatch_is_not_saved(self):
        def mismatch(url, user_agent):
            data, raw, metadata = self.fetch(url, user_agent)
            data = {**data, "cik": "1"}
            return data, raw, metadata
        with tempfile.TemporaryDirectory() as directory, patch.object(sec, "_fetch_json", side_effect=mismatch):
            with self.assertRaisesRegex(sec.SECError, "differs"):
                sec.collect_company("895126", directory, "Research App")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_links_reject_paths_and_arbitrary_urls(self):
        self.assertEqual(sec.filing_url(895126, LATE, "exe-20251231.htm"),
                         "https://www.sec.gov/Archives/edgar/data/895126/000089512626000011/exe-20251231.htm")
        self.assertTrue(sec.filing_url(895126, LATE, "xslF345X05/primary_doc.xml").endswith(
            "/xslF345X05/primary_doc.xml"))
        for document in ("../private", "https://localhost", "file?token=secret", ".."):
            with self.assertRaises(sec.SECError):
                sec.filing_url(895126, LATE, document)
        with self.assertRaisesRegex(sec.SECError, "redirect refused"):
            sec._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://localhost/private")

    def test_inconsistent_filing_arrays_fail_closed(self):
        malformed = deepcopy(self.submissions)
        malformed["filings"]["recent"]["form"].pop()
        with self.assertRaisesRegex(sec.SECError, "inconsistent"):
            sec.select_filings(malformed, "2026-10-03")

    def test_late_eastern_acceptance_does_not_leak_at_next_utc_midnight(self):
        source = deepcopy(self.submissions)
        recent = source["filings"]["recent"]
        for key, rows in recent.items():
            recent[key] = rows[:1]
        recent["filingDate"] = ["2026-07-01"]
        recent["form"] = ["4"]
        # 21:30 Eastern, still same SEC filing date, already next UTC date.
        recent["acceptanceDateTime"] = ["2026-07-02T01:30:00.000Z"]
        self.assertEqual(sec.select_filings(source, "2026-07-02T00:00:00Z"), [])
        self.assertEqual(sec.select_filings(source, "2026-07-02T03:59:59Z"), [])
        boundary = sec.public_available_at("2026-07-01")
        selected = sec.select_filings(source, boundary)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["available_at"], boundary)

    def test_fetch_rejects_arbitrary_urls_before_opening(self):
        with patch.object(sec.request, "build_opener") as opener:
            for url in ("http://localhost/", "https://data.sec.gov.evil.test/submissions/CIK0000895126.json",
                        "https://data.sec.gov/submissions/CIK0000895126.json?redirect=private"):
                with self.subTest(url=url), self.assertRaises(sec.SECError):
                    sec._fetch_json(url, "Research App")
            opener.assert_not_called()

    def test_fetch_bounds_response_and_rejects_non_json(self):
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}
            def __init__(self, raw): self.raw = raw
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, bound): return self.raw[:bound]
        url = "https://data.sec.gov/submissions/CIK0000895126.json"
        with patch.object(sec.request, "build_opener") as opener:
            opener.return_value.open.return_value = Response(b"12345")
            with patch.object(sec, "MAX_RESPONSE_BYTES", 4), self.assertRaisesRegex(sec.SECError, "limit"):
                sec._fetch_json(url, "Research App")
            opener.return_value.open.return_value = Response(b"<html>failure</html>")
            with self.assertRaisesRegex(sec.SECError, "valid JSON"):
                sec._fetch_json(url, "Research App")
            opener.return_value.open.return_value = Response(b"[]")
            with self.assertRaisesRegex(sec.SECError, "JSON object"):
                sec._fetch_json(url, "Research App")

    def test_http_errors_preserve_status_without_echoing_headers_or_contact(self):
        url = "https://data.sec.gov/submissions/CIK0000895126.json"
        for failure in (HTTPError(url, 403, "secret contact", {}, None), URLError("secret contact")):
            with patch.object(sec.request, "build_opener") as opener:
                opener.return_value.open.side_effect = failure
                with self.assertRaises(sec.SECError) as caught:
                    sec._fetch_json(url, "Research App private-contact@example.test")
                self.assertNotIn("secret", str(caught.exception))
                self.assertNotIn("private-contact", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
