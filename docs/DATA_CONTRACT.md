# Public research packet and event contracts

Use `examples/companies/aster.json` and `bcn.json` as complete invented input references. All amounts in the current numerical models are **USD millions**, all share counts are **million shares**, and output values are **USD per share**. Currency conversion and quarterly annualization are not inferred.

## Company baseline

The `import` command and `POST /api/import` read company JSON in this format, as shown in `examples/companies/`. Import creates a new company; it cannot replace an existing baseline.

Required top-level fields: `symbol`, `name`, `archetype`, timezone-aware `as_of`, `financials`, `assumptions`, nonempty `evidence`, and `thesis`. Supported model archetypes are `industrial`, `recurring` and bounded `commodity`; other archetypes retain a visible model gap.

`financials` declares currency, amount/share units, annual fiscal start/end, opening working capital, capital/operating inputs, cash, debt and diluted shares. `assumptions` supplies the complete archetype inputs. The examples and `valuation.py` are the authoritative accepted numeric fields and feasibility bounds. The engine rejects missing model inputs with an unavailable valuation rather than estimating them silently.

`thesis` contains a statement, drivers with IDs/values/units/evidence IDs, counterevidence, falsifiers and next-review conditions. Industrial and recurring valuation packets also require a finite positive `price` and dated `price_as_of` for the bundled price-expectations workflow. Optional `prices` supply technical history. Bars need increasing unique dates, finite positive closes and nonnegative volume; they cannot be later than the research date. Future imported baselines are rejected.

Each evidence record requires `id`, `title`, `source`, `source_type`, `url`, `published_at`, `retrieved_at`, `usable_at`, `period`, `unit`, `currency`, `locator`, `content`, `classification`, and appropriate boolean `verified`. `fixture://` identifies invented examples; it is not a web source. Original public documents should use their actual source URL and locator. Acquired evidence follows publication <= retrieval <= usability <= decision cutoff.

## Evidence event

Required event fields: `id`, `symbol`, `kind`, `title`, `source_document`, `published_at`, `decision_ts`, and boolean `verified`. Supported kinds: `driver_change`, `ambiguous_evidence`, `source_failure`, `source_recovered`, `review_due`, plus canonical `baseline_refresh` prepared from a validated complete packet. Include `summary`, `evidence_ids`, `evidence` and `changes` for a useful review.

Industrial proposals can change `qualified_utilization`, `unit_price_growth`, `qualified_capacity_growth` or `discount_rate`. Recurring proposals can change `retention`, `new_customers`, `service_cost_ratio` or `discount_rate`. Each change carries `parameter`, finite numeric `new`, and a useful `reason`. The baseline supplies `old`; a sender cannot overwrite it. Commodity driver proposals can change `annual_production`, `realized_price`, `cash_cost`, `annual_capex`, `discount_rate` and `reserve_life_years`. These explicit maps do not infer economic meaning from a headline.

Verified numerical proposals need nonempty references to verified `confirmed_fact` or explicit `model_assumption` evidence. Unknown mappings are rejected. Unverified or unsupported calculation proposals preserve a review need. Event decision cutoffs cannot be in the future or move an accepted thesis backwards. Accepted timestamps are normalized to UTC for ordering and deduplication.

## Agent export

`packet SYMBOL` and `GET /api/assistant-packet/SYMBOL` export selected saved research for an agent to review and use when preparing evidence events. This JSON includes calculated results but omits the complete financial and price inputs required by the company baseline format. It cannot be reimported with `import` or passed directly to `value_company`; use the company JSON for those operations.

## HTTP contract

| Endpoint | Behavior |
| --- | --- |
| `GET /api/state` | Saved overview, companies, alerts, events, settings, replay and delivery counts |
| `GET /api/company/SYMBOL` | Model, technical snapshot, history, forecast cohorts and current candidate hashes |
| `GET/POST /api/company/SYMBOL/lab` | Read-only sandbox; POST accepts only supported overrides |
| `POST /api/company/SYMBOL/agent` | Empty body; offline research run, no external provider |
| `GET /api/runs`, `GET /api/runs/ID` | Saved bundle index and complete run |
| `POST /api/runs/ID/replay` | Verify and replay captured decisions offline |
| `POST /api/baseline` | Complete validated company packet; propose a pinned financial refresh |
| `POST /api/import` | New sourced baseline; existing company is rejected |
| `POST /api/events` | Validate and ingest one event atomically |
| `POST /api/replay` | Demo only; optional `event_id` |
| `POST /api/company/SYMBOL/accept` | Requires reviewed `event_id`, `baseline_hash`, `candidate_hash` |
| `POST /api/alerts/ID/review` | `action` = `reviewed` or `deferred`; assumptions remain unchanged |
| `POST /api/research` | `symbol`; save bounded brief and immutable snapshot |
| `GET /api/reports`, `GET /api/reports/ID` | Saved report index and content |
| `GET /api/alerts/ID/preview` | Local email preview |
| `GET /api/digest?period=weekly` | Recent open items and separately listed overdue items |
| `GET /api/assistant-packet/SYMBOL` | Selected research fields; review before external sharing |
| `POST /api/settings`, `POST /api/watchlist` | Validated preferences and known-company tracking |

Requests use JSON objects, same-origin writes and bodies <=512 KiB. Nonfinite JSON values fail. Token-enabled API requests require `Authorization: Bearer ...`; the UI holds the entered token only in page memory. Source content is untrusted text and is escaped by the UI.

## Privacy boundary

Provide only public or explicitly redacted packets. The import blacklist catches common account/credential field names; it cannot detect personal information in arbitrary keys, free text or URLs. Agent exports select research fields but preserve their nested supplied contents. Review every export before upload. Runtime workspaces and secrets stay outside the publishable file set.

## Commodity and financial refresh

The complete commodity example is built by `cases.exe_company()`. `forecast_basis` must be `explicit_forward_12_month_assumptions`; `balance_sheet_bridge` requires `method=hold_last_reported`, `classification=model_assumption` and its exact `as_of`. All supported scalar assumptions must be supplied. Monetary/share units remain USD millions/million shares. Annual production and reserve bounds use million Mcfe. The model accepts an integer assumed horizon from 1 through 10 years, disallows uncapitalized production growth, and checks reserves and funding. No quote is required and reverse expectations remain unavailable.

`propose_baseline` or the `baseline` command validates a complete replacement packet and constructs the canonical event. Its ID and source identity bind the full packet, event evidence must exactly match packet evidence, and verification must be literal true. Direct malformed/noncanonical refresh events fail. Import still cannot replace a company. The existing review/accept route requires the exact event and baseline/candidate tokens; acceptance additionally validates the saved packet and recalculates under the transaction.

SEC normalized inputs and run snapshots follow [the EXE case](EXE_CASE.md) and [Agent runtime](AGENT_RUNTIME.md). Historical availability reconstruction is different from actual evidence acquisition.
