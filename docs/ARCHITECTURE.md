# Architecture

The numerical engine works without a language model. The workbench, CLI and future collectors share one `ResearchEngine` and one SQLite schema. A bounded Agent and an opt-in SEC collector share the same public-input boundaries. A separate notification worker has the only email send capability.

| Layer | Module | Responsibility |
| --- | --- | --- |
| Inputs | `fixtures.py`, `cases.py`, `sec.py`, JSON packets | Invented examples, packaged public EXE facts or explicit SEC snapshots |
| Agent | `agent.py` | Allowlisted tools, budgets, source checks, recorded decisions and immutable run bundles |
| Sandbox | `lab.py`, `commodity.py` | Read-only operating experiments and finite producer cash flows |
| SEC monitor | `sec_monitor.py` | Operator-started latest periodic-filing checks and local review alerts |
| Calculation | `valuation.py` | Business-specific cash flows, scenarios, sensitivity, reverse model and technical context |
| Workflow | `engine.py`, `events.py` | Evidence chronology, explicit mapping, materiality, idempotency, proposed changes and reviewed acceptance |
| Persistence | `store.py` | Transactions, companies, revisions, source events, alerts, outbox, reports, forecasts and activity |
| Presentation | `server.py`, `static/` | Same-origin HTTP API and cached browser reads; escaped content and responsive views |
| Research exports | `reports.py`, agent packet | Dated bounded briefs and selected research fields |
| Delivery | `notifications.py` | Local preview, claimed outbox attempts, quiet hours, stale suppression and relay outcomes |
| Operations | `cli.py` | Demo, isolated workspace, JSON intake, monitoring loop, exports and explicit delivery activation |

`BEGIN IMMEDIATE` serializes write decisions. Company import checks existence inside that transaction; replacement uses a separately reviewed full-packet proposal. Event and alert/outbox creation are atomic. Event fingerprinting ignores headline wording, uses normalized UTC publication time and includes source identity and changed inputs. Reused IDs with changed facts are rejected.

Events never mutate accepted financial assumptions directly. Financial-refresh fingerprints bind the complete proposed company packet; acceptance checks event integrity, packet identity and a fresh calculation inside the write transaction. Acceptance pins event, baseline and candidate hashes, checks again inside the write transaction and creates a revision. Forecast predictions belong to that revision and remain frozen. Source-health observations cannot replace newer health states.

The UI does not call providers or trigger SMTP. Its polling/refresh reads persisted state. The local directory monitor is a caller-operated event intake loop, not a news crawler. A separate `sec-watch` command can check the latest EXE periodic filing with explicit network activation. Unknown send outcomes remain unknown and are not requeued automatically.

This is a single-user architecture. SQLite WAL supports bounded local readers and writers, not distributed workers across a shared network filesystem. No multi-tenant isolation, job queue, rate-limited provider fleet or tested public deployment is claimed.

## Reproducible research runs

Run bundles embed company/fact inputs, recorded planner decisions, cutoff, configuration, Python results and source-code hashes. They use canonical JSON and content-addressed exclusive storage. Repeating the same run is idempotent. Replay validates hashes and reexecutes recorded decisions without SEC or inference calls. Hashes detect changes, not source authenticity; matching code is required.

The default planner is scripted and explicitly labeled. Optional hosted tool calling uses a caller-chosen endpoint with validated arguments, no redirects, bounded response/steps and no accept/file/shell/send tool. Browser requests always use the offline planner. Real inference remains unverified.
