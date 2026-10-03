# ThesisLedger

### Build your own investment research agent

ThesisLedger helps you understand how to research investments with an Agent and build your own research workbench. Use your knowledge of a business to frame questions and interpret its economics. Ask the Agent to organize evidence, challenge assumptions and run calculations, then revise your judgment using results you can check.

The documentation and executable workbench follow that collaboration: establishing a fact, turning a view into a testable assumption, reviewing a calculation and deciding what new information changes. Working through the research process explains why the tools are designed this way and how to use them well.

[中文](README.zh-CN.md) · [User guide](docs/USER_GUIDE.md) · [Research method](docs/METHODS.md) · [Verification](docs/VERIFICATION.md)

![Research workbench](docs/images/research-lab.png)

*The EXE illustration uses historical SEC filings and explicitly labeled teaching assumptions. It supplies no current quote or investment target.*

## Use your understanding to frame a specific question

You may already have a view: “Rising natural-gas demand will make this producer more valuable.” Your knowledge of the industry, competition and business can identify the questions that matter. How much saleable production can the company add? What price can it actually realize? How much capital will growth require? Those questions direct the Agent's evidence search.

Judgment has a place in research and needs an explanation. If you think the company has a cost advantage, ask the Agent to compare costs on a consistent basis and investigate the differences. Lower costs may reflect operating efficiency, asset mix or disclosure definitions. Your business understanding helps interpret the differences; the Agent's comparison subjects your initial view to scrutiny.

A useful research request might be:

> I think rising demand could improve this company's cash flow. Organize public evidence on saleable production, realized prices and incremental capital spending. Give original sources, periods and units, identify the strongest counterevidence, and explain what is missing. Once we check the key facts, we can discuss which assumptions belong in the model and what would make us revise this view.

You can give this request to your chosen coding or research agent. Share your reasoning and uncertainties so it can expand, check and challenge them. The calculation and review process then turns that conversation into a research record you can continue using.

## Verify a number in its original context

When an Agent supplies a number, open the original filing or company document and locate the relevant table, note and period. Confirm the company and business scope, then check units and definitions. “Production” may mean a quarterly total, annual total or daily average. “Profit” may include different adjustments. Comparisons and calculations depend on those definitions matching.

Reported revenue growth also needs explanation: did it come from prices, sales volumes or an acquisition? The revenue change is a reported fact. Attributing it to competitive advantage is an interpretation. Expecting that advantage to continue next year is a forecast assumption. Making those steps explicit lets evidence support the reasoning and assumptions receive their own review.

When sources conflict, preserve their definitions and provenance, then ask the Agent to help reconcile them. Check which information was available at the time as well. A later release can inform today's research but cannot establish what was known earlier. ThesisLedger preserves sources, periods, units and timing metadata to support these checks; you still need to verify the content against the original document.

## Connect the business story to shareholder value

Demand must become sales the company can deliver, and realized prices must turn those sales into revenue. Revenue then has to pay for operating costs, capital spending and working capital. That reveals how much cash growth leaves behind. Cash, debt and shares complete the discussion of value per share.

```text
Demand and competition → feasible operations → revenue → costs and reinvestment → cash flow → value per share
```

This chain explains why an attractive growth story can still need substantial research. More production may require more capital. Accounting profit may not yet have become cash. Financing may change existing shareholders' participation. A scenario needs to carry these relationships through together.

The workbench exposes intermediate calculations so you can follow an assumption to its consequences. Missing inputs, infeasible growth or unexplained funding requirements remain model gaps. Those gaps identify the next research question instead of turning unsupported precision into a conclusion. The [research method](docs/METHODS.md) describes the formulas and the scope of each business model.

## Make the Agent's reasoning inspectable

A research agent handles two kinds of work. Organizing evidence, noticing conflicts and proposing useful questions require interpretation. Calculating cash flows, checking constraints and reproducing a result require explicit inputs and rules. ThesisLedger connects the two: suggestions point to evidence, and calculations point back to their inputs.

This collaboration method can guide your use of an external coding or research agent. The built-in Agent demonstrates a narrower scope: it follows a fixed review plan using four allowlisted tools and produces source-linked suggestions from selected evidence. Its tool records, inputs and calculations are inspectable. Hosted LLM tool calling is an optional route that has not been verified live.

Model changes have their own review process. Inspect an exact candidate and its calculated result before accepting it. Saved runs support offline replay. Matching results establish reproducibility; the reliability of a source and the plausibility of an assumption still require research judgment.

You can carry these design choices into your own agent: define its inputs, calculations, suggestions and acceptance process, then leave enough evidence for the next research session to continue. The [research protocol](agents/RESEARCH_PROTOCOL.md) describes the full method; the [Agent guide](agents/START_HERE.md) supplies an opening request for a coding or research agent.

## Ask which step new information changes

Define observable reasons to revise a thesis while you are forming it. Demand may keep growing, but delayed expansion, unchanged realized prices or persistently higher capital spending could still require a different cash-flow view. Ask the Agent to look for that counterevidence, then use your business understanding to assess its significance.

A new filing may support the thesis, add context or invalidate its most important assumption. Review returns to the original reasoning to locate the affected step. Repeated coverage of one announcement still represents one piece of evidence.

Monitoring therefore sends new filings into review alerts. After checking the contents, you can decide whether to propose a model update. SEC and the EXE company website keep separate source status; repeated verified filings are deduplicated, and source failures remain visible. A successful filing-list check does not establish that new financial figures have been reviewed.

The local workbench provides views for evidence, scenarios, alerts and history. The [self-hosting guide](docs/SELF_HOSTING.md) describes deployment to your own server and email configuration. Cloud operation and actual email delivery remain unverified.

## Preserve a prediction so you can learn from it

Revisiting a forecast six months later should let you ask which assumptions held, which missed and why. Rewriting the prediction after seeing the result makes those questions difficult to answer.

ThesisLedger preserves earlier model revisions and freezes forecasts when a model is accepted. After a forecast's horizon, you can supply an attributable observation and compare it with the prediction. The record helps you examine your judgment and distinguish missing information, reasoning errors and changing conditions.

The current project compares predictions with user-supplied observations. It does not implement a trading backtest or use investment returns to establish Agent quality. The [verification record](docs/VERIFICATION.md) separates computation, workflow checks and observed runtime behavior.

## Open the workbench

Download and extract this repository, or clone it. Open a terminal in the folder containing `run.py`. You need Python 3.10 or newer. The included illustration runs offline, with no dependency installation, data key or model account.

```sh
python3 run.py case EXE
```

The browser opens a local workbench. If it does not, visit `http://127.0.0.1:8765/#lab` and open **Research Lab**. The interface currently uses English.

Change **Realized price** from 3.5 to 4.0 USD/Mcfe. Follow its effect through revenue, cash costs and capital spending to FCFF and conditional value per share. Click **Run evidence review** to inspect three suggestions, their evidence and actual calculations. Use **Verify saved run** to check whether the recorded run reproduces.

Your sandbox stays separate from the accepted model. Existing model changes require explicit acceptance. Press Ctrl+C to stop the service; restart the same command to resume `.thesisledger/exe-case/`.

The illustration uses Expand Energy's [FY2024](https://www.sec.gov/Archives/edgar/data/895126/000089512625000021/exe-20241231.htm) and [FY2025](https://www.sec.gov/Archives/edgar/data/895126/000089512626000011/exe-20251231.htm) filings. It demonstrates how changing business boundaries, cash-flow definitions and a finite forecast affect research. Terminal value is zero, opening cash/debt is dated, and annual diluted EPS shares serve as a labeled proxy. Financing, dilution, hedging and other work needed for full investment valuation remain gaps. See the [case walkthrough](docs/EXE_CASE.md).

## Connect your own research and monitoring

Prepare a reviewed public or deliberately redacted company packet using the [input contract](docs/DATA_CONTRACT.md), then import it into a separate workspace. The [user guide](docs/USER_GUIDE.md#bring-your-own-research) shows the steps. Built-in models cover industrial businesses, recurring customer revenue and a bounded commodity-producer illustration; other businesses need an appropriate model adapter.

Keep the example workbench running. In another terminal, check EXE's official company website:

```sh
python3 run.py ir-watch EXE --once
```

Open **Monitor & Timeline** or **Alerts** and refresh the saved workspace. This company-site route currently supports EXE and reads filing-list metadata. To connect SEC, follow the [application declaration steps](docs/USER_GUIDE.md#declare-your-application-to-sec) to supply a truthful application identity and contact email. The guide also covers continuous checks, pause/resume and access failures.

The invented-company replay, `python3 run.py demo`, lets you practice conflicting evidence, source outages and model acceptance. See the [demo walkthrough](docs/QUICKSTART.md). Runtime workspaces and `.env` files are ignored. Known private fields are rejected, but free-form text still needs your review before sharing. The project executes no trades.

## Implementation and verification

The runtime uses Python's standard library, SQLite and plain browser JavaScript, with no third-party runtime dependencies. A saved research run contains selected inputs, cutoff, tool decisions, results, configuration and hashes. Offline replay checks the code version and calculated result.

```sh
python3 run.py benchmark
python3 run.py evaluate
```

The v0.2.2 [verification record](docs/VERIFICATION.md) reports 162 tests passed on Python 3.12 and 3.14, three UI controller checks and 19 fixed public-case benchmark checks. The benchmark covers 16 manually cross-checked facts from two EXE filings and three workflow guards. It does not measure unseen-company extraction, live LLM research quality or investment returns.

The EXE company-site adapter passed one live check and generated one review alert. SEC direct recovery remains unverified after a classified HTTP 403 refusal. Hosted LLM inference, cloud operation and actual SMTP delivery also remain unverified.

[Architecture](docs/ARCHITECTURE.md) · [Agent runtime](docs/AGENT_RUNTIME.md) · [Research method](docs/METHODS.md) · [Provenance](docs/PROVENANCE.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
