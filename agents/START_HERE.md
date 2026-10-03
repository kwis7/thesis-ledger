# Build your own investment secretary

Start the demo with `python3 run.py demo`, then use an agent of your choice to study this checkout. No plugin installation or model account is required by the deterministic workbench.

Copy this opening request into your agent:

> Read `agents/RESEARCH_PROTOCOL.md`, `docs/DATA_CONTRACT.md` and `docs/METHODS.md`. Help me build a sourced investment research workspace using only public or explicitly redacted inputs. Begin by identifying the company, its operating model and the decisive question. Explain your evidence gaps. Use this repository's deterministic valuation outputs; propose sourced changes for review. Keep the work local unless I explicitly authorize a specific external action.

The agent can help you retrieve permitted public documents, identify accounting periods, organize a thesis, challenge assumptions and prepare a company JSON file for import. You decide which tools and public sources it can use. It should not invent full-company coverage, quietly substitute source vintages or move personal files into the project.

Import the reviewed company JSON using the format in `examples/companies/`, run `serve`, and export an agent packet with `packet SYMBOL`. The export includes the thesis, evidence, assumptions, calculated model and useful questions for reviewing research and preparing events. It cannot be reimported or passed directly to the numerical model because it omits the complete financial and price inputs. It contains no workspace settings or account model. Nested text still needs your review before sharing.

For a new document, ask the agent to produce an event following the contract: source context, dates, classification and explicitly supported parameter changes. Ingest it manually first and inspect the result. Continuous directory monitoring is useful after the collector's outputs are reliable. Unknown facts should remain gaps and reviewed model choices should remain labelled assumptions.

v0.2 also supplies a bounded four-tool Agent runtime with an offline planner and optional hosted tool calling. Start with `case EXE`, then `agent EXE --workspace .thesisledger/exe-case`. Hosted use requires an explicit endpoint/model and sends the reviewed selected packet to that provider; it has not been verified live. See [runtime configuration](../docs/AGENT_RUNTIME.md). External coding agents can still use the portable protocol and structured packets.
