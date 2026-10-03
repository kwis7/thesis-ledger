# From a company story to a testable investment thesis

The central method is a causal chain: industry economics and competitive position shape operating drivers; those drivers must convert into recognized revenue, cash and common equity value. A positive demand story alone does not establish attractive value per share.

## Define the company before defining the model

Confirm issuer identity, listing, share class, currency, fiscal period and financial units. Define the customer, product, payment mechanism, competitive advantage and bottleneck. Separate industry demand from the portion the company can serve and monetize. Contracts, management targets, policy support and total addressable markets require an attributable conversion bridge before becoming forecast revenue.

The public code supports industrial and recurring models plus a bounded commodity-producer illustration. Selecting an unsupported archetype records a gap rather than choosing a generic fallback.

| Research question | Industrial capacity model | Recurring customer model |
| --- | --- | --- |
| What can grow? | Installed capacity, customer-qualified capacity and qualified utilization | Existing customers retained and feasible new-customer additions |
| What creates sales? | Qualified units produced and sold, multiplied by unit price | Retained plus acquired customers, multiplied by annual revenue per customer |
| What restricts growth? | Qualification cannot exceed installed capacity; utilization cannot exceed its feasible range | Additions cannot exceed onboarding capacity; retention definition must reconcile |
| What consumes cash? | Variable/fixed cost, maintenance and expansion capital, working capital | Service cost, fixed cost, customer acquisition, platform capital, maintenance and working capital |
| What challenges the story? | Qualification delays, yield, pricing and capital productivity | Churn, definitions of retention, acquisition productivity and service margins |

The producer illustration and its separate annual-date/balance constraints are documented in [the EXE case](EXE_CASE.md). Read the precise formulas in `src/thesisledger/valuation.py` and `commodity.py`; intermediate rows remain visible in the API and company workbench.

## Build the cash and ownership bridge

Each scenario calculates revenue, operating cost, depreciation, operating profit, taxes and reinvestment. Free cash flow to the firm is:

```text
FCFF = EBIT - cash tax + depreciation - maintenance capex
       - growth capex - change in net working capital
```

For industrial and recurring models, five forward annual FCFF values are discounted. Terminal reinvestment reflects terminal growth and return on invested capital. The terminal state therefore pays for assumed continuing growth. Common equity value reconciles enterprise value, debt, minority interest, available cash and diluted common shares.

The funding diagnostic compares a cumulative unlevered cash deficit with available opening cash. A path requiring unidentified financing returns unavailable. It is a screening diagnostic, not a complete liquidity or solvency model. Debt service, refinancing, trapped cash, future financing and future dilution need dedicated inputs and are outside the current engine. Starting diluted shares, debt and minority claims remain explicit. Preferred stock and other complex claims require a separate adapter.

The Bear/Base/Bull cases change connected operating assumptions. The exit-multiple cross-check shares the forecast and is labelled as dependent on shared assumptions; it is not independent confirmation of value. A conditional reverse solution holds other assumptions fixed, solves one driver, and feeds that result back into the same forward model. One price cannot identify every business assumption.

## Keep evidence and judgment distinct

Each source carries publication, retrieval and usable timestamps, period, unit, currency and locator. The engine requires timezone-aware metadata and excludes evidence unavailable at the decision cutoff. Industrial/recurring annual financial periods must be plausible and no more than 31 days before the model cutoff. The commodity illustration instead requires an explicit forward-rate basis and dated hold-last-reported bridge, with annual history at most 450 days old; it does not certify current balances. Older annual data needs an interim bridge, which this version does not manufacture.

Use explicit classifications:

- `confirmed_fact`: an attributable supplied fact with verification recorded.
- `interpretation`: a reading of facts that can be challenged.
- `model_assumption`: an explicit forecast choice.
- `counterevidence`: information that challenges the thesis.
- `data_gap`: an unresolved definition or missing input.

Metadata validation is not source authentication or proof that content is true. Evidence must still be checked against the original document. A currently retrieved historical filing cannot establish that a research run actually possessed it at that historical time.

A numerical update needs explicit supported parameter changes, nonempty referenced evidence and literal verification flags. Events with uncertain definitions generate review needs rather than changing an assumption. Proposed updates keep an input hash, evidence and candidate calculation. Acceptance requires the exact event and hashes shown to the reviewer; a newly arriving proposal invalidates the old acceptance action.

## Define what would change your mind

Record a thesis statement, decisive drivers, contrary evidence, observable falsifiers and next-review conditions. Ask which assumption is least supported and which uncertainty could change the decision. Avoid increasing confidence merely because many headlines repeat the same announcement.

The current materiality rule tests the absolute percentage change in the candidate base value against a user threshold. Source outages, definition conflicts and unsupported model updates remain visible even without a numerical change. An unavailable model is a research gap, not a trade signal. Ranking companies, counting duplicate news and detecting keywords do not establish investment quality.

## Add technical context and learn from dated forecasts

Technical conditions are separate from business quality and valuation. Current indicators are descriptive MA20/60/200, Wilder RSI14 and maximum close-to-close drawdown. Full warm-up is required. Future bars fail closed when a research cutoff is supplied. Date-only bars do not prove same-day intraday availability; corporate-action adjustments and exchange calendars require external provenance.

Each accepted model freezes forecast cohorts and preserves earlier versions. Later observations cannot overwrite predictions, precede the freeze, precede the horizon or come from the future. The resulting error is a transparent comparison with a user-supplied observation. The current repository does not run a trading backtest, estimate alpha or claim portfolio returns.

## Extend by a concrete bottleneck

The research checklist is reusable beyond the current models: commodity producers still need complete realized-price/netback and reserve replacement bridges; utilities need rate-base and allowed-return inputs; regulated financial businesses need capital and regulatory models. Add an archetype only with explicit accounting, financing constraints, evidence mapping and invariant tests. Until then, preserve unavailable outputs and useful research questions.
