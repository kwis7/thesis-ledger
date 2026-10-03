# EXE: filing evidence to a reviewed operating premise

Run `python3 run.py case EXE`, then open Research Lab. This case uses public data from Expand Energy Corporation, EXE, Nasdaq, CIK 0000895126. It does not contain the author's private research, positions or trading history.

## The real inputs

| Report | Period end | Filed | Accession |
| --- | --- | --- | --- |
| [2024 10-K](https://www.sec.gov/Archives/edgar/data/895126/000089512625000021/exe-20241231.htm) | 2024-12-31 | 2025-02-26 | 0000895126-25-000021 |
| [2025 10-K](https://www.sec.gov/Archives/edgar/data/895126/000089512626000011/exe-20251231.htm) | 2025-12-31 | 2026-02-18 | 0000895126-26-000011 |

The canonical packaged fixture is `src/thesisledger/data/exe-facts.json`. It contains 36 selected fact records with exact units, periods, accessions, source pointers and actual response hashes. `examples/sec/` preserves small attributed JSON excerpts for inspecting the selection. They are curated subsets, not complete SEC response snapshots; their own hashes and full-source response hashes are labeled separately.

Current downloads can reconstruct disclosed information, not prove what a historical research run possessed. SEC date-only filing metadata is conservatively eligible after the next Eastern midnight, converted to UTC. Actual acquisition is recorded separately on October 3 UTC, October 2 Chicago time. The source records are historical, not an assertion of current October operating or financial balances.

2024 includes Southwestern only after the October 1 merger, while 2025 includes the full year. The period lengths and tagged definitions match, but business scope differs. Reported production growth must not become an organic-growth or forward-production forecast automatically.

## Try a conditional model

Move realized price from 3.5 to 4.0 USD/Mcfe. Keep production, cost, capital and other premises fixed. The first forecast year's revenue changes by `annual_production * price_change`; taxes and cash flow are then recalculated in Python. The curve varies one price input while holding the other sandbox premises fixed.

The case starts with explicit annual production, price, aggregate cash cost, capex, DD&A, taxes and an eight-year assumed horizon. Bcfe is numerically equivalent to million Mcfe. These forward quantities are premises, even where a reported number provides an anchor. Reported cash capex does not establish sustaining capital, and reported lifting cost excludes transportation, overhead and other costs.

Cash flow is `production * (realized_price - cash_cost) - modeled_cash_tax - capex - change_in_working_capital`. Taxes use positive modeled EBIT after DD&A; loss carryforwards are not inferred. All cash-flow amounts are USD millions. Enterprise value is discounted finite cash flow with zero terminal and salvage value. Common equity subtracts dated debt/minority premises, adds cash and divides by the annual weighted diluted EPS share proxy in millions.

The model requires an explicit `hold_last_reported` balance-sheet assumption at its cutoff. Annual history can be at most 450 days old. This is an acknowledged illustration rather than a verified interim reconciliation. Industrial and recurring adapters retain their stricter 31-day rule.

Cumulative output exceeding reported proved reserves, an undefined financing requirement or unsupported claims withholds the value. The reserve constraint is necessary but insufficient: developed/undeveloped mix, decline, drilling, development and retirement obligations still need dedicated underwriting. No verified market quote, price-implied requirement or complete EXE target price is supplied.

## Inspect the research workflow

Click Run evidence review. The offline planner reads the validated context, compares adjacent reported facts, runs the unchanged Python model and proposes source-linked reviews for production, capital and cost. Proposals keep `new: null`; there is no silent numerical forecast update. The optional LLM adapter can choose bounded tools and conditional proposals but has not been run against a real provider.

The browser review uses the saved baseline, not unsaved slider values. A local historical review alert is recorded once. Repeating a review preserves one alert and returns the same content-addressed run when inputs and code match. No provider or email call occurs.

The manifest and embedded inputs let Verify saved run rerun recorded planner decisions offline. It checks source-code, input, output and bundle hashes. A changed runtime requires the matching code to reproduce an older run. This checks computation and local integrity, not source authenticity or LLM reasoning quality.

CLI equivalents:

```sh
python3 run.py agent EXE --workspace .thesisledger/exe-case
python3 run.py verify-run .thesisledger/exe-case/runs/run-<bundle-sha>.json
python3 run.py benchmark
```

Replace the bundle placeholder with the saved filename. Existing exports and unrelated workspaces remain preserved.

## Check for a later filing

```sh
python3 run.py sec-watch EXE --user-agent '<app-name/version contact>' --once
```

The operator supplies the SEC identity/contact and explicitly starts network collection. Removing `--once` checks every 900 seconds while the process runs. It checks the latest eligible periodic filing in the recent submissions window, records a source-linked local review alert, and deduplicates repeated checks. It does not extract interim figures into a model or claim complete historical coverage.

Workbench pause prevents new collection requests. A failed check stops the monitor process, preserves a redacted status and last-attempt time, and creates one local alert per outage. Research Lab and Monitor & Timeline display this status after refreshing saved state. Refresh preserves sandbox inputs and the selected run if the accepted baseline is unchanged. Recovery after an explicit restart is recorded quietly; it updates source coverage without changing financial inputs or forecast history. A successful check describes the last outcome, not proof that a background process is still running.

The v0.2.1 live check returned HTTP 403. Its cause remains unknown. Review your declared application identity/contact and network access against the [SEC access guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions); the app does not retry or change network identity to bypass a refusal.

After source review, prepare a complete company packet with updated periods, facts, assumptions and balance bridge. `baseline packet.json --workspace PATH` proposes it. Inspect the old/new model and explicitly accept the pinned event in the company view. Acceptance checks the complete proposed packet and recomputes the candidate under the write transaction. It preserves previous revisions and frozen forecasts.

## What the public benchmark proves

`benchmark` checks 16 manually cross-checked records and three bounded workflow guards. `evaluate` tests parser ambiguities, chronology, scalar/unit relationships, safe tool behavior, review integrity, hash replay, HTTP boundaries and mocked delivery. These small fixed cases do not measure general extraction accuracy, unseen issuers, live-model quality or investment returns.
