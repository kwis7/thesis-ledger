"""Regression checks for public-case arithmetic, saved runs and SEC status."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from thesisledger.agent import MAX_BUNDLE_BYTES, canonical_json, run_agent, save_run
from thesisledger.cases import exe_agent_inputs, exe_company, exe_facts
from thesisledger.cli import main
from thesisledger.engine import ResearchEngine
from thesisledger.sec import SECError
from thesisledger.sec_monitor import check_exe_filings
from thesisledger.valuation import value_company


class PolishTests(unittest.TestCase):
    def test_overflow_withholds_result_instead_of_flooring_nan(self):
        for overrides in ({"realized_price": 1e308}, {"annual_production": 1e308}, {"cash_cost": 1e308}):
            result = value_company(exe_company(), overrides)
            self.assertEqual(result["state"], "unavailable")
            json.dumps(result, allow_nan=False)

    def test_infeasible_extreme_sensitivity_stays_valid_json(self):
        result = value_company(exe_company(), {"annual_production": 1e-6,
            "realized_price": 1.7e308, "reserve_life_years": 1})
        json.dumps(result, allow_nan=False)
        self.assertEqual(result["state"], "available")
        self.assertTrue(any(row["state"] == "unavailable" for row in result["sensitivity"]))

    def test_mapping_shapes_reject_without_persisting(self):
        for key in ("financials", "assumptions", "balance_sheet_bridge"):
            for value in (None, [], "invalid"):
                company = exe_company();company[key] = value
                self.assertEqual(value_company(company)["state"], "unavailable")
                with tempfile.TemporaryDirectory() as directory:
                    engine = ResearchEngine(directory, demo=False)
                    with self.assertRaises(ValueError):engine.import_company(company)
                    self.assertEqual(len(engine.state()["companies"]), 0)
                    self.assertEqual(engine.store.rows("SELECT id FROM forecasts"), [])

    def test_large_run_is_listed_loaded_and_replayed_by_engine_and_cli(self):
        company = exe_company();company["description"] = "Public demonstration text. "*100000
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            path = save_run(run_agent(company, exe_agent_inputs()), engine.store.workspace/"runs")
            self.assertGreater(path.stat().st_size, 2*1024*1024)
            self.assertLessEqual(path.stat().st_size, MAX_BUNDLE_BYTES)
            self.assertEqual(engine.runs()["runs"][0]["run_id"], path.stem)
            self.assertEqual(engine.run_bundle(path.stem)["inputs"]["company"]["description"], company["description"])
            self.assertTrue(engine.replay_run(path.stem)["verified"])
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["verify-run", str(path)]), 0)
            self.assertTrue(json.loads(output.getvalue())["verified"])

    def test_corrupt_run_does_not_hide_valid_run(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            path = save_run(run_agent(exe_company(), exe_agent_inputs()), engine.store.workspace/"runs")
            corrupt = path.parent/("run-"+"a"*64+".json");corrupt.write_text("broken json")
            wrong = path.parent/("run-"+"b"*64+".json");wrong.write_bytes(path.read_bytes())
            listed = engine.runs()
            self.assertEqual([row["run_id"] for row in listed["runs"]], [path.stem])
            self.assertEqual(listed["skipped"], 2)
            with self.assertRaises(ValueError):engine.run_bundle(wrong.stem)

    def _engine(self, directory):
        engine = ResearchEngine(directory, demo=False);engine.import_company(exe_company());return engine

    def _unavailable(self, *args):
        raise SECError("SEC request failed (HTTP 403); private-contact@example.test")

    def _available(self, *args):
        return {"issuer": {"tickers": ["EXE"]}, "filings": copy.deepcopy(exe_facts()["filings"])}

    def test_sec_failure_is_visible_deduplicated_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory);before = engine.company("EXE")
            for unused in range(2):
                with self.assertRaisesRegex(SECError, "HTTP 403") as caught:
                    check_exe_filings(engine, "app private-contact@example.test", collector=self._unavailable)
                self.assertNotIn("private-contact", str(caught.exception))
            state = engine.state();company = state["companies"][0]
            self.assertEqual(state["meta"]["sec_monitor"]["status"], "unavailable")
            self.assertEqual(state["meta"]["sec_monitor"]["error_code"], "http_403")
            self.assertNotIn("private-contact", json.dumps(state))
            self.assertEqual(len(state["alerts"]), 1)
            self.assertEqual(company["data_status"], "stale")
            self.assertEqual(company["assumptions"], before["assumptions"])
            self.assertEqual(company["history"], before["history"])
            self.assertEqual(company["forecast_cohorts"], before["forecast_cohorts"])

    def test_sec_recovery_is_quiet_and_keeps_model(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            with self.assertRaises(SECError):check_exe_filings(engine, "app contact", collector=self._unavailable)
            before = engine.company("EXE")
            self.assertEqual(check_exe_filings(engine, "app contact", collector=self._available)["status"], "unchanged")
            state = engine.state();company = state["companies"][0]
            self.assertEqual(state["meta"]["sec_monitor"]["status"], "available")
            self.assertIsNotNone(state["meta"]["sec_monitor"]["last_success_at"])
            self.assertEqual(company["data_status"], "fresh")
            self.assertEqual(len(state["alerts"]), 1)
            self.assertEqual(len([row for row in state["events"] if row["kind"] == "source_recovered"]), 1)
            self.assertEqual(company["history"], before["history"])
            check_exe_filings(engine, "app contact", collector=self._available)
            self.assertEqual(len(engine.state()["alerts"]), 1)

    def test_empty_response_does_not_restore_failed_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            with self.assertRaises(SECError):check_exe_filings(engine, "app contact", collector=self._unavailable)
            result = check_exe_filings(engine, "app contact", collector=lambda *args:{"issuer":{"tickers":["EXE"]},"filings":[]})
            self.assertEqual(result["status"], "data_gap")
            self.assertEqual(engine.company("EXE")["data_status"], "stale")
            self.assertIsNone(engine.store.metadata("sec_monitor")["last_success_at"])

    def test_paused_sec_monitor_does_not_call_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory);engine.update_settings({"paused": True})
            def forbidden(*args):raise AssertionError("Paused monitoring must not contact SEC")
            self.assertEqual(check_exe_filings(engine, "app contact", collector=forbidden)["status"], "paused")
            self.assertIsNone(engine.store.metadata("sec_monitor"))


if __name__ == "__main__":unittest.main()
