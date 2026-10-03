# Bounded research Agent and reproducible runs

`thesisledger.agent` provides an original, standard-library-only tool loop. The default `OfflinePlanner` is a deterministic scripted baseline. It demonstrates evidence comparison and human review without claiming that an LLM reasoned about the company. A separately selected `ChatCompletionsPlanner` can call an OpenAI-compatible inference endpoint. Hosted inference is optional and has not been verified with a real model or account in this release.

The runtime consumes caller-supplied public or deliberately redacted research packets. It does not open research databases, original personal files, arbitrary files or URLs. Review the complete packet before opting into a hosted provider because the provider receives the supplied company and normalized fact context. Known private/credential fields are rejected before any planner call. Input-field validation cannot identify all sensitive information hidden in prose.

## Python interfaces

```python
from thesisledger.agent import run_agent, save_run, replay_run

run = run_agent(company, filings, max_steps=8)
bundle_path = save_run(run, "/path/to/your/local/workspace/runs")
replayed = replay_run(bundle_path)
assert replayed["manifest"]["output_sha256"] == run["manifest"]["output_sha256"]
```

`run_agent(company, filings, *, planner=None, max_steps=8)` returns `{manifest, inputs, output}` without writing files or modifying a baseline. A caller-supplied planner implements `next_step(context)` and may supply `manifest()` with nonsecret configuration. Each response is either `{tool, arguments}` or `{finish: {summary, evidence_ids}}`. The host validates every response. The budget is an integer from 1 through 32 and includes tool, finish and failed planner attempts. Each step executes at most one tool. Model output tokens are separately capped at 4,000 per request in the optional adapter.

`save_run(run, directory)` returns the path of one `run-<bundle SHA256>.json` file. It uses exclusive creation and makes new bundles read-only. Repeating a byte-identical save returns the same path; an existing altered file or symlink fails without overwrite. File permissions are a convenience, not a security boundary.

`replay_run(bundle)` accepts that path or an in-memory bundle dictionary. It verifies hashes and source versions, then reexecutes the recorded planner decisions and Python tools. It returns the identical run object on success and raises `AgentError` on an integrity or replay mismatch. It never calls a model, reconnects to SEC or reconstructs live market data. Replay proves the captured tool computation can be reproduced under identical code. It does not prove another inference request would produce the same reasoning.

## Public fact packet

`filings` is a flat list of facts or an object with `facts` and optional `mapping_hints`. The original supplied objects are preserved completely in the input snapshot.

```json
{
  "facts": [
    {"id": "revenue-2023", "concept": "Revenue", "unit": "USD", "start": "2023-01-01", "end": "2023-12-31", "filed": "2024-02-15", "accn": "accession-2024", "form": "10-K", "val": 100},
    {"id": "revenue-2024", "concept": "Revenue", "unit": "USD", "start": "2024-01-01", "end": "2024-12-31", "filed": "2025-02-15", "accn": "accession-2025", "form": "10-K", "val": 150}
  ],
  "mapping_hints": [
    {"parameter": "realized_price_growth", "evidence_ids": ["revenue-2023", "revenue-2024"], "kind": "historical_review", "rationale": "Review the price/volume/netback bridge before forecasting."}
  ]
}
```

This is an invented shape example. `parameter` must exist in the supplied company's `assumptions`; the example parameter fits a commodity company. Values and concepts are not converted between units. `start` may be null for balance-sheet instant facts. Duration facts must cover a complete annual period. Supported annual filing forms are 10-K, 20-F and 40-F, including amendments. Missing, invalid or unavailable facts produce visible gaps and cannot be cited. Missing IDs are deterministically derived from normalized fact content. At most 2,000 facts and 128 mapping hints are accepted. Canonical packet and run JSON are capped at 8 MiB; a saved run allows one additional byte for its trailing newline. CLI replay, HTTP replay and the run index share this boundary. Invalid or hash-mismatched files are counted and omitted from the index while valid records remain available.

The decision cutoff comes from timezone-aware `company.as_of`. SEC `filed` dates provide no intraday availability timestamp, so the runtime conservatively makes facts usable at the next Eastern midnight, converted to UTC. It cannot establish their actual intraday availability or independent factual correctness. Comparisons require the same concept, unit and period type, adjacent annual periods, and unambiguous reported values. Conflicting or restated contexts remain gaps. Issuer identity and concept applicability remain the packet supplier's research responsibility.

`historical_review` mapping hints associate sources with an assumption needing review. `model_assumption` is an explicit caller-supplied modeling link, not certification that the source proves the forecast. The offline baseline always proposes review with `new: null`, including when a modeling link exists. It never copies a reported historical growth rate into a forecast assumption.

## Four available tools

| Tool | Exact arguments | Behavior |
| --- | --- | --- |
| `read_context` | `{}` | Read supplied company, validated fact registry, cutoff, mapping hints and gaps |
| `compare_filing_facts` | `{}` | Compute historical deltas and cite the two supplied fact IDs |
| `run_scenario` | `{overrides: [{parameter, value}], evidence_ids, label}` | Run `valuation.value_company` with finite overrides to existing assumption keys |
| `propose_change` | `{parameter, new, reason, evidence_ids}` | Create a review-only or conditional numerical proposal, always pending human decision |

`parameter` and `new` can both be null for general review. A numerical proposal requires an existing assumption, nonempty valid source IDs and a matching caller-supplied `model_assumption` link. An infeasible numerical proposal is rejected by the authoritative Python valuation. Hypothetical scenarios remain conditional; running one does not accept a new baseline. No accept, arbitrary network, file, shell, message or trade tool exists.

Every citation in tool arguments or the structured finish response must refer to a supplied fact that passed the cutoff checks. Unknown IDs, duplicated IDs, unsupported arguments, booleans as numbers and nonfinite values fail closed. The final planner summary remains explicitly labeled `unverified_planner_narrative`; structural citation validation cannot certify arbitrary prose. The unchanged baseline `output.model_result` and tool valuation results come from Python, not model arithmetic.

## Run shape and integrity

`inputs` embeds the full company and original filings. `output` contains `status`, `summary`, `summary_evidence_ids`, `summary_verification`, `suggestions`, `trace`, `planner_decisions`, `model_result`, `data_gaps`, `research_only`, `human_decision` and `baseline_changed`. A trace row is `{step, tool, arguments, result}`. A suggestion has `kind`, `parameter`, `old`, `new`, `reason`, `evidence_ids`, `human_decision`, and a Python candidate result when a numerical proposal is feasible. Status is `complete`, `needs_review`, `budget_exhausted` or `planner_error`; `complete` means the bounded loop ended, not complete investment coverage.

The manifest records the research cutoff, symbol, planner mode/configuration, step budget, package/runtime version, input SHA256, output SHA256 and source hashes for `agent.py`, `valuation.py`, `engine.py`, `sec.py` and `commodity.py` when present. The original input snapshot removes reliance on case-file contents during replay. `output_hash` aliases `output_sha256` and `planner_mode` aliases the planner mode for application indexes. `bundle_sha256` hashes the entire canonical run excluding that self-referential field. No wall-clock execution timestamp enters the run hash.

Canonical encoding sorts JSON keys, uses UTF-8 and disallows NaN/Infinity. Input/output, manifest and source-code tampering fail verification, and replay must reproduce the saved output hash. SHA256 is an integrity check, not a signature or proof of source authenticity. An attacker who can replace both inputs and their hashes can create a new, internally consistent run. Code changes intentionally invalidate old-bundle replay until the matching code is restored.

## Optional hosted planner

```python
from thesisledger.agent import ChatCompletionsPlanner, run_agent

# Caller chooses an endpoint and compatible model explicitly.
# Constructing the adapter alone performs no request.
planner = ChatCompletionsPlanner(
    "http://127.0.0.1:8080/v1/chat/completions",
    "your-compatible-local-model",
)
run = run_agent(company, filings, planner=planner, max_steps=8)
```

For explicit environment configuration, call `ChatCompletionsPlanner.from_env()` after setting `THESISLEDGER_LLM_ENDPOINT`, `THESISLEDGER_LLM_MODEL` and optionally `THESISLEDGER_LLM_API_KEY` in your own environment. The default Agent never reads these variables and never enables inference automatically. Caller-provided API keys are held only in adapter memory, placed in the Authorization header and excluded from manifests/errors. Do not embed credentials in packet content or endpoint URLs.

Remote endpoints require HTTPS. HTTP is permitted only for explicit loopback IP addresses or `localhost`. The endpoint must end in `/chat/completions` and cannot include URL credentials, a query or fragment. Redirects and ambient HTTP proxies are disabled. Each request has a timeout from 1 through 60 seconds; responses are capped at 1 MiB. There is no automatic retry, model selection, installed-provider discovery or account capability inference. Inference authorization and charges belong to the explicit caller.

The adapter follows the official OpenAI [function-calling guide](https://developers.openai.com/api/docs/guides/function-calling): JSON-schema function definitions, tool-call messages and tool results keyed by call ID. It disables parallel tool calls and additionally rejects multiple returned calls before execution. It requests `store: false`. Provider support for these fields and the selected model must be verified separately. The official guide states that GPT-6 Astra and GPT-6.1 Sol require the Responses API for tool calling, so this Chat Completions adapter does not establish compatibility with those models. Models that need reasoning disabled can be configured with `reasoning_effort="none"`. These constraints were checked against the official guide on 2026-10-02; no live model request was made.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_agent.py -v
```

The offline suite covers deterministic outputs, evidence/cutoff gaps, unknown citations and actions, budget exhaustion, scenario arithmetic against the valuation engine, rejected numerical proposals, immutable/idempotent storage, code/input/output tamper checks, failed-run replay and mocked inference tool calls. Mocked requests verify protocol shape and exclusion of credential values from bundles. They do not verify real hosted inference, a provider's privacy promises, model research quality or API account access.
