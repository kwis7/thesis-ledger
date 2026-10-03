# Your first research loop

For the real EXE case, run `python3 run.py case EXE` and follow [the EXE walkthrough](EXE_CASE.md). Research Lab connects public historical facts, an operating sandbox, offline review and saved-run verification.

## Invented-company replay

Run `python3 run.py demo` from the checkout. Your browser opens a local research desk with invented inputs. The app keeps its state when you restart.

1. Open **Company Research**, select **Aster Systems**, and read the thesis, qualified capacity and utilization assumptions. Inspect the five-year cash-flow bridge and the source dates. Compare its dated price with the scenario range and conditional reverse requirement.
2. Return to **Today**, then click **Replay next update**. The invented update lowers qualified utilization from 0.76 to 0.66. The model recomputes a candidate value using the event cutoff and the added evidence. The accepted baseline stays unchanged.
3. Open the alert. Inspect the actual new source content, then open the company desk and **Compare revised assumptions**. Compare the old and new drivers and values. **Mark reviewed** records attention; **Accept revised assumptions** creates a new version. The event and hashes pin the exact proposal you inspected.
4. In **Monitor & Timeline**, use **Replay same event** or **Replay selected event**. It creates no second alert. Continue replay to see conflicting retention definitions, a source outage and recovery. Conflicting definitions need reconciliation and do not fabricate a numerical update.
5. Generate a research brief. Find it in **Research Library**. Return to the company history to compare saved thesis versions and frozen forecast cohorts.
6. In **My Workspace**, change the materiality threshold, quiet hours or monitoring preference. Pause monitoring and attempt a replay: no event is consumed. Email preview stays local; enabling queue eligibility does not send a message.

To start a new demo without deleting your work:

```sh
python3 run.py demo --workspace .thesisledger/another-demo --port 8766
```

To practice your own workspace, run `init`, import a public/redacted company JSON file, then `serve`. The sample files remain synthetic when imported. On later visits, run `serve` to resume. To repeat the imports, choose an unused workspace path and pass the same `--workspace` path to every command; an existing company cannot be replaced by import.

The `packet SYMBOL` export helps an agent review the saved research and prepare evidence events. It is not an import file or a direct numerical-model input. Review its contents before sharing them with an agent; use [the agent guide](../agents/START_HERE.md).

## CLI reference

```sh
python3 run.py --help
python3 run.py init --workspace .thesisledger/workspace
python3 run.py import examples/companies/aster.json
python3 run.py import examples/companies/bcn.json
python3 run.py ingest examples/events/aster-qualification-delay.json
python3 run.py research ASTER --output .thesisledger/aster-brief.md
python3 run.py packet ASTER --output .thesisledger/aster-agent.json
python3 run.py digest --period weekly
python3 run.py monitor --events-dir examples/events --once
python3 run.py evaluate
```

Workspace flags can select an isolated practice directory. Export commands refuse to overwrite an existing file. `samples --output DIRECTORY` writes invented examples only into new filenames.
