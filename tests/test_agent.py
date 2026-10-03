"""Offline security, financial-authority, and reproducible-run boundaries."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from thesisledger.agent import (AgentError, ChatCompletionsPlanner, OfflinePlanner,
                                PlannerError, _NoRedirect, canonical_json,
                                replay_run, run_agent, save_run)
from thesisledger.fixtures import build_demo_companies
from thesisledger.valuation import value_company


def annual_facts():
    return {"facts": [
        {"id": "revenue-2023", "concept": "Revenue", "unit": "USD", "start": "2023-01-01",
         "end": "2023-12-31", "filed": "2024-02-15", "accn": "0000000000-24-000001", "form": "10-K", "val": 100},
        {"id": "revenue-2024", "concept": "Revenue", "unit": "USD", "start": "2024-01-01",
         "end": "2024-12-31", "filed": "2025-02-15", "accn": "0000000000-25-000001", "form": "10-K", "val": 150},
    ], "mapping_hints": [{"parameter": "unit_price_growth", "evidence_ids": ["revenue-2023", "revenue-2024"],
                          "rationale": "Review the price/volume bridge before forecasting."}]}


class ScriptedPlanner:
    def __init__(self, decisions):
        self.decisions, self.calls = decisions, 0

    def next_step(self, context):
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return decision


def finish(ids=None):
    return {"finish": {"summary": "Review complete; narrative is not verified.", "evidence_ids": ids or []}}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.company = build_demo_companies()[0]
        self.filings = annual_facts()

    def test_offline_run_is_deterministic_and_never_changes_forecast(self):
        before = deepcopy(self.company)
        first = run_agent(self.company, self.filings)
        second = run_agent(self.company, self.filings)
        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertEqual(self.company, before)
        output = first["output"]
        self.assertEqual(first["manifest"]["planner"]["mode"], "offline_baseline")
        self.assertEqual(first["manifest"]["symbol"], self.company["symbol"])
        self.assertEqual(first["manifest"]["output_hash"], first["manifest"]["output_sha256"])
        self.assertEqual(output["model_result"], value_company(self.company))
        self.assertFalse(output["baseline_changed"])
        self.assertEqual(output["human_decision"], "pending")
        comparison = output["trace"][1]["result"]["comparisons"][0]
        self.assertEqual(comparison["historical_change_ratio"], 0.5)
        self.assertEqual(output["suggestions"][0]["kind"], "review_only")
        self.assertIsNone(output["suggestions"][0]["new"])
        self.assertEqual(output["suggestions"][0]["old"], self.company["assumptions"]["unit_price_growth"])

    def test_missing_evidence_and_unsupported_model_remain_gaps(self):
        company = deepcopy(self.company)
        company["archetype"] = "unmodeled"
        output = run_agent(company, {"facts": []})["output"]
        self.assertEqual(output["status"], "needs_review")
        self.assertEqual(output["model_result"]["state"], "unavailable")
        self.assertEqual(output["suggestions"], [])
        self.assertTrue(any("No valid annual" in gap for gap in output["data_gaps"]))

    def test_step_budget_is_enforced_even_for_repeated_tools(self):
        planner = ScriptedPlanner([{"tool": "read_context", "arguments": {}}])
        run = run_agent(self.company, self.filings, planner=planner, max_steps=3)
        self.assertEqual(planner.calls, 3)
        self.assertEqual(len(run["output"]["trace"]), 3)
        self.assertEqual(run["output"]["status"], "budget_exhausted")
        for invalid in (0, 33, True, 1.5):
            with self.assertRaises(AgentError):
                run_agent(self.company, self.filings, max_steps=invalid)

    def test_invented_proposal_and_final_citations_are_rejected(self):
        proposal = {"tool": "propose_change", "arguments": {"parameter": "discount_rate", "new": None,
                    "reason": "Invented citation should never enter suggestions.", "evidence_ids": ["invented"]}}
        planner = ScriptedPlanner([proposal, finish(["invented"]), finish()])
        output = run_agent(self.company, self.filings, planner=planner)["output"]
        self.assertEqual(output["suggestions"], [])
        self.assertEqual(output["status"], "needs_review")
        self.assertEqual([row["result"]["state"] for row in output["trace"]], ["rejected", "rejected"])
        self.assertEqual(output["summary_evidence_ids"], [])

    def test_arbitrary_actions_unknown_overrides_and_extra_args_are_rejected(self):
        cases = [
            {"tool": "accept", "arguments": {}},
            {"tool": "read_context", "arguments": {"path": "/tmp/private"}},
            {"tool": "run_scenario", "arguments": {"overrides": [{"parameter": "future_revenue", "value": 999}],
                "evidence_ids": ["revenue-2024"], "label": "Invalid override"}},
            {"tool": "run_scenario", "arguments": {"overrides": [{"parameter": "discount_rate", "value": True}],
                "evidence_ids": ["revenue-2024"], "label": "Invalid number"}},
        ]
        for decision in cases:
            with self.subTest(decision=decision):
                output = run_agent(self.company, self.filings, planner=ScriptedPlanner([decision, finish()]))["output"]
                self.assertEqual(output["trace"][0]["result"]["state"], "rejected")
                self.assertFalse(output["baseline_changed"])

    def test_numerical_proposal_needs_explicit_assumption_link_and_python_validation(self):
        decision = {"tool": "propose_change", "arguments": {"parameter": "discount_rate", "new": 0.12,
                    "reason": "Conditional discount-rate review.", "evidence_ids": ["revenue-2023", "revenue-2024"]}}
        output = run_agent(self.company, self.filings, planner=ScriptedPlanner([decision, finish()]))["output"]
        self.assertEqual(output["suggestions"], [])
        self.assertIn("model_assumption", output["trace"][0]["result"]["error"])
        filings = deepcopy(self.filings)
        filings["mapping_hints"] = [{"parameter": "discount_rate", "kind": "model_assumption",
                                     "evidence_ids": ["revenue-2024"],
                                     "rationale": "Caller-supplied explicit modeling judgment, not a reported fact."}]
        output = run_agent(self.company, filings, planner=ScriptedPlanner([decision, finish()]))["output"]
        self.assertEqual(output["suggestions"][0]["candidate_model_result"], value_company(self.company, {"discount_rate": 0.12}))
        self.assertEqual(output["model_result"], value_company(self.company))
        invalid = deepcopy(decision)
        invalid["arguments"]["new"] = -1
        output = run_agent(self.company, filings, planner=ScriptedPlanner([invalid, finish()]))["output"]
        self.assertEqual(output["suggestions"], [])
        self.assertEqual(output["trace"][0]["result"]["state"], "rejected")

    def test_scenario_calculations_are_python_authoritative(self):
        decision = {"tool": "run_scenario", "arguments": {"overrides": [{"parameter": "discount_rate", "value": 0.12}],
                    "evidence_ids": ["revenue-2024"], "label": "Conditional caller scenario"}}
        output = run_agent(self.company, self.filings, planner=ScriptedPlanner([decision, finish()]))["output"]
        self.assertEqual(output["trace"][0]["result"]["model_result"], value_company(self.company, {"discount_rate": 0.12}))
        self.assertEqual(output["model_result"], value_company(self.company))

    def test_day_only_filing_cutoff_and_invalid_facts_are_not_citable(self):
        company = deepcopy(self.company)
        company["as_of"] = "2025-02-15T23:59:59+00:00"
        output = run_agent(company, self.filings)["output"]
        facts = output["trace"][0]["result"]["facts"]
        self.assertEqual([row["id"] for row in facts], ["revenue-2023"])
        self.assertTrue(any("Eastern-day boundary" in gap for gap in output["data_gaps"]))
        company["as_of"] = "2025-02-16T05:00:00+00:00"
        self.assertEqual(len(run_agent(company, self.filings)["output"]["trace"][0]["result"]["facts"]), 2)
        filings = deepcopy(self.filings)
        filings["facts"][0]["val"] = True
        self.assertTrue(any("finite number" in gap for gap in run_agent(self.company, filings)["output"]["data_gaps"]))

    def test_conflicting_restated_values_and_different_units_are_not_blended(self):
        filings = deepcopy(self.filings)
        restatement = deepcopy(filings["facts"][1])
        restatement.update(id="restated", val=900, form="10-K/A", filed="2025-03-01")
        filings["facts"].append(restatement)
        compared = run_agent(self.company, filings)["output"]["trace"][1]["result"]
        self.assertEqual(compared["comparisons"], [])
        self.assertTrue(any("restated" in gap for gap in compared["data_gaps"]))
        filings = deepcopy(self.filings)
        filings["facts"][0]["unit"] = "USD millions"
        self.assertEqual(run_agent(self.company, filings)["output"]["trace"][1]["result"]["comparisons"], [])

    def test_no_ids_are_stable_and_planner_mutation_cannot_change_authority(self):
        filings = deepcopy(self.filings)
        filings["mapping_hints"] = []
        for fact in filings["facts"]:
            fact.pop("id")
        self.assertEqual(run_agent(self.company, filings), run_agent(self.company, filings))

        class MutatingPlanner:
            def next_step(self, context):
                context["company"]["financials"]["cash"] = 1000000
                context["assumptions"]["discount_rate"] = 0.001
                return finish()

        output = run_agent(self.company, filings, planner=MutatingPlanner())["output"]
        self.assertEqual(output["model_result"], value_company(self.company))

    def test_snapshot_replay_immutable_save_and_tamper_detection(self):
        run = run_agent(self.company, self.filings)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = save_run(run, temporary)
            self.assertIsInstance(bundle, Path)
            self.assertEqual(bundle.name, "run-" + run["manifest"]["bundle_sha256"] + ".json")
            self.assertEqual(replay_run(bundle), run)
            self.assertEqual(save_run(run, temporary), bundle)
            bundle.chmod(0o644)
            bundle.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(AgentError, "refusing to overwrite"):
                save_run(run, temporary)
        changed = deepcopy(run)
        changed["inputs"]["company"]["assumptions"]["discount_rate"] = 0.99
        with self.assertRaisesRegex(AgentError, "hash mismatch"):
            replay_run(changed)
        changed = deepcopy(run)
        changed["output"]["model_result"]["base"] = 1000000
        with self.assertRaisesRegex(AgentError, "hash mismatch"):
            replay_run(changed)
        changed = deepcopy(run)
        changed["manifest"]["cutoff"] = "2030-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(AgentError, "manifest/bundle"):
            replay_run(changed)
        with patch("thesisledger.agent._code_hashes", return_value={"agent.py": "changed", "valuation.py": "changed"}):
            with self.assertRaisesRegex(AgentError, "identical runtime"):
                replay_run(run)

    def test_budget_and_failed_planner_runs_replay_without_reinvoking_model(self):
        budget = run_agent(self.company, self.filings, max_steps=2)
        self.assertEqual(replay_run(budget), budget)

        class FailingPlanner:
            def next_step(self, context):
                raise RuntimeError("credential-value-must-not-be-persisted")

        failed = run_agent(self.company, self.filings, planner=FailingPlanner())
        self.assertEqual(failed["output"]["status"], "planner_error")
        self.assertNotIn("credential-value", canonical_json(failed).decode())
        self.assertEqual(replay_run(failed), failed)

    def test_adapter_rejects_unencrypted_external_and_credential_urls(self):
        invalid = ["http://example.com/v1/chat/completions", "file:///tmp/chat/completions",
                   "https://user:secret@example.com/v1/chat/completions",
                   "https://example.com/v1/chat/completions?api_key=secret",
                   "https://example.com/v1/chat/completions#secret", "https://example.com/v1/other"]
        for endpoint in invalid:
            with self.subTest(endpoint=endpoint), self.assertRaises(AgentError):
                ChatCompletionsPlanner(endpoint, "caller-selected")
        for endpoint in ("http://127.0.0.1:8080/v1/chat/completions", "http://[::1]:8080/v1/chat/completions",
                         "https://example.com/v1/chat/completions"):
            ChatCompletionsPlanner(endpoint, "caller-selected")
        with self.assertRaises(PlannerError):
            _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://external.example")
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(AgentError):
            ChatCompletionsPlanner.from_env()

    def test_mocked_llm_tool_call_loop_and_run_replay_do_not_expose_key(self):
        responses = [
            {"choices": [{"message": {"tool_calls": [{"id": "call_1", "type": "function", "function": {
                "name": "compare_filing_facts", "arguments": "{}"}}]}}]},
            {"choices": [{"message": {"content": json.dumps(finish(["revenue-2024"]))}}]},
        ]
        requests = []

        class Response:
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size):
                return json.dumps(self.payload).encode()

        class Opener:
            def open(self, request, timeout):
                requests.append(request)
                return Response(responses.pop(0))

        planner = ChatCompletionsPlanner("https://example.com/v1/chat/completions", "caller-selected",
                                         api_key="do-not-persist-this-key", reasoning_effort="none")
        with patch("thesisledger.agent.build_opener", return_value=Opener()):
            run = run_agent(self.company, self.filings, planner=planner)
        self.assertEqual(len(requests), 2)
        body = json.loads(requests[1].data)
        self.assertFalse(body["parallel_tool_calls"])
        self.assertEqual(body["messages"][-1]["role"], "tool")
        self.assertEqual(body["messages"][-1]["tool_call_id"], "step_1")
        self.assertEqual(len(body["tools"]), 4)
        self.assertFalse(body["store"])
        self.assertNotIn("do-not-persist-this-key", canonical_json(run).decode())
        with patch("thesisledger.agent.build_opener", side_effect=AssertionError("Replay must not call a provider")):
            self.assertEqual(replay_run(run), run)

    def test_nonfinite_packets_and_inference_parallel_tool_calls_fail_closed(self):
        filings = deepcopy(self.filings)
        filings["facts"][0]["val"] = float("nan")
        with self.assertRaises(AgentError):
            run_agent(self.company, filings)
        with self.assertRaises(AgentError):
            canonical_json({1: "invalid JSON key"})
        with self.assertRaises(AgentError):
            ChatCompletionsPlanner("https://example.com/v1/chat/completions", "model", timeout=100)
        company = deepcopy(self.company)
        company["assumptions"]["discount_rate"] = 10 ** 400
        with self.assertRaises(AgentError):
            run_agent(company, self.filings)

    def test_mocked_model_multiple_calls_and_unknown_citation_are_not_executed(self):
        responses = [
            {"choices": [{"message": {"tool_calls": [
                {"id": "first", "type": "function", "function": {"name": "read_context", "arguments": "{}"}},
                {"id": "second", "type": "function", "function": {"name": "read_context", "arguments": "{}"}},
            ]}}]},
            {"choices": [{"message": {"content": json.dumps(finish(["fictional-source"]))}}]},
        ]

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size):
                return json.dumps(responses.pop(0)).encode()

        class Opener:
            def open(self, request, timeout):
                return Response()

        planner = ChatCompletionsPlanner("https://example.com/v1/chat/completions", "caller-selected")
        with patch("thesisledger.agent.build_opener", return_value=Opener()):
            multiple = run_agent(self.company, self.filings, planner=planner)
            invented = run_agent(self.company, self.filings, planner=planner, max_steps=1)
        self.assertEqual(multiple["output"]["status"], "planner_error")
        self.assertEqual(multiple["output"]["trace"], [])
        self.assertEqual(invented["output"]["trace"][0]["result"]["state"], "rejected")
        self.assertEqual(invented["output"]["summary"], "")


if __name__ == "__main__":
    unittest.main()
