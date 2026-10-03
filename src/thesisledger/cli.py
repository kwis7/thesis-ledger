"""Zero-dependency local research and explicitly activated delivery commands."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import unittest
import webbrowser

from .engine import ResearchEngine, aware
from .events import replay_events
from .fixtures import build_demo_companies
from .notifications import deliver_pending, mark_interrupted_unknown, smtp_sender
from .reports import digest_report
from .server import make_server
from .store import encode

PROJECT = Path(__file__).resolve().parents[2]


def read_json(path: str | Path) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024:
        raise ValueError("Use a regular JSON research file smaller than 512 KiB")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    if not isinstance(value, dict):
        raise ValueError("A JSON object is required")
    return value


def write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def scan_events(engine: ResearchEngine, directory: Path) -> dict:
    if not directory.is_dir():
        raise ValueError("Create a directory containing public-source event JSON files")
    results = []
    for path in sorted(directory.glob("*.json")):
        try:
            result = engine.ingest_event(read_json(path))
            results.append({"file": path.name, "status": result["status"], "alerts_created": result.get("alerts_created", 0)})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            results.append({"file": path.name, "status": "rejected", "reason": type(exc).__name__})
    return {"files": results, "rejected": sum(item["status"] == "rejected" for item in results)}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="ThesisLedger: your investment research workbench")
    sub = command.add_subparsers(dest="command", required=True)
    for name in ("demo", "serve", "case"):
        p = sub.add_parser(name, help="Open synthetic replay" if name == "demo" else "Serve a sourced local workspace")
        p.add_argument("--workspace", default=f".thesisledger/{'demo' if name == 'demo' else 'exe-case' if name == 'case' else 'workspace'}")
        if name == "case":
            p.add_argument("symbol", choices=("EXE",))
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--no-open", action="store_true")
        p.add_argument("--public-origin", help="Exact trusted HTTPS browser origin behind your private proxy")
    for name in ("init", "import", "research", "packet", "ingest", "monitor", "digest", "observe", "deliver", "reconcile", "baseline", "agent"):
        p = sub.add_parser(name)
        p.add_argument("--workspace", default=".thesisledger/workspace")
        if name in {"import", "ingest", "baseline"}:
            p.add_argument("file")
        if name in {"research", "packet", "agent"}:
            p.add_argument("symbol")
            p.add_argument("--output", type=Path)
        if name == "agent":
            p.add_argument("--llm", action="store_true", help="Explicit external model call using selected public research inputs")
            p.add_argument("--endpoint", help="Chat Completions HTTPS endpoint or local loopback HTTP endpoint")
            p.add_argument("--model", help="Model identifier; required for --llm")
        if name == "init":
            p.add_argument("--demo", action="store_true")
        if name == "monitor":
            p.add_argument("--events-dir", type=Path, required=True)
            p.add_argument("--once", action="store_true")
            p.add_argument("--interval", type=int, default=60)
        if name == "digest":
            p.add_argument("--period", choices=("daily", "weekly"), default="daily")
        if name == "observe":
            p.add_argument("cohort_id")
            p.add_argument("value", type=float)
            p.add_argument("--observed-at", required=True)
        if name == "deliver":
            p.add_argument("--confirm-send", action="store_true", help="Explicitly activate real email sending")
            p.add_argument("--limit", type=int, default=5)
        if name == "reconcile":
            p.add_argument("--before", required=True, help="Mark interrupted in-flight attempts unknown; never requeue")
    p = sub.add_parser("sec", help="Explicit public SEC snapshot collection; no model or automatic acceptance")
    p.add_argument("cik")
    p.add_argument("--cache-dir", type=Path, default=Path(".thesisledger/sec"))
    p.add_argument("--user-agent", required=True, help="SEC-compliant app identity and operator contact")
    p.add_argument("--cutoff", help="ISO date or aware timestamp for public-availability filtering")
    p = sub.add_parser("sec-watch", help="Operator-started EXE periodic-filing monitor; local alerts only")
    p.add_argument("symbol", choices=("EXE",))
    p.add_argument("--workspace", default=".thesisledger/exe-case")
    p.add_argument("--user-agent", required=True)
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=int, default=900)
    p = sub.add_parser('ir-watch', help='Explicit EXE official-issuer alternative; keeps SEC status separate')
    p.add_argument('symbol', choices=('EXE',))
    p.add_argument('--workspace', default='.thesisledger/exe-case')
    p.add_argument('--once', action='store_true')
    p.add_argument('--interval', type=int, default=900)
    p = sub.add_parser("verify-run", help="Verify and replay a saved research bundle offline")
    p.add_argument("file", type=Path)
    p = sub.add_parser("benchmark", help="Evaluate public EXE extraction and repeatable research offline")
    p.add_argument("--output", type=Path)
    p = sub.add_parser("samples", help="Write invented example packets; never overwrite files")
    p.add_argument("--output", type=Path, default=Path("examples"))
    sub.add_parser("evaluate", help="Run reproducible numerical, evidence and workflow checks")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "evaluate":
            if not (PROJECT / "tests").is_dir():
                raise ValueError("Evaluation requires the source checkout with its tests directory")
            suite = unittest.defaultTestLoader.discover(str(PROJECT / "tests"))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            print(encode({"checks": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "passed": result.wasSuccessful(), "scope": "local deterministic evaluation; no real-market alpha claim"}))
            return 0 if result.wasSuccessful() else 1
        if args.command == "samples":
            for company in build_demo_companies():
                write_new(args.output / "companies" / (company["symbol"].lower()+".json"), json.dumps(company, indent=2)+"\n")
            for event in replay_events():
                write_new(args.output / "events" / (event["id"]+".json"), json.dumps(event, indent=2)+"\n")
            print("Invented examples written. No market or account data was accessed.")
            return 0
        if args.command == "sec":
            from .sec import collect_company, select_facts
            snapshot = collect_company(args.cik, args.cache_dir, args.user_agent, args.cutoff)
            annuals = [row for row in snapshot["filings"] if row["form"] == "10-K"][:2]
            facts = [fact for filing in annuals for fact in select_facts(snapshot["companyfacts"], snapshot["cutoff"], accession=filing["accessionNumber"])]
            print(encode({"issuer": snapshot["issuer"], "cutoff": snapshot["cutoff"], "sources": snapshot["sources"], "filings": snapshot["filings"], "selected_fact_count": len(facts), "limitations": snapshot["limitations"]}))
            return 0
        if args.command == "verify-run":
            from .agent import replay_run
            replayed = replay_run(args.file)
            print(encode({"verified": True, "output_hash": replayed["manifest"]["output_sha256"]}))
            return 0
        if args.command == "benchmark":
            from .evaluation import evaluate_public_case
            result = evaluate_public_case()
            if args.output:
                write_new(args.output, json.dumps(result, indent=2)+"\n")
            print(encode(result))
            return 0 if result["passed"] else 1
        engine = ResearchEngine(args.workspace, demo=args.command == "demo" or (args.command == "init" and args.demo))
        if args.command == "case":
            from .cases import exe_company
            if engine.store.metadata("mode") != "local_workspace":
                raise ValueError("Choose an unused sourced workspace for the public EXE case")
            rows = engine.store.rows("SELECT payload FROM companies WHERE symbol='EXE'")
            if not rows:
                engine.import_company(exe_company())
            elif json.loads(rows[0]["payload"]).get("case_id") != "exe-sec-2024-2025":
                raise ValueError("An existing EXE baseline belongs to your research; choose a separate case workspace")
        if args.command in {"demo", "serve", "case"}:
            if args.command == "demo" and engine.store.metadata("mode") != "synthetic_replay":
                raise ValueError("This directory holds a sourced workspace. Choose a new demo directory.")
            server = make_server(engine, host=args.host, port=args.port, token=os.environ.get("THESISLEDGER_API_TOKEN"), public_origin=args.public_origin)
            address = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{server.server_port}"
            print(f"ThesisLedger {engine.store.metadata('mode')}: {address}", flush=True)
            print("Research remains on this machine. Press Ctrl+C to stop.", flush=True)
            if not args.no_open:
                webbrowser.open(address+"/#lab" if args.command == "case" else address)
            try:
                server.serve_forever(poll_interval=0.25)
            finally:
                server.server_close()
            return 0
        if args.command == "init":
            result = {"mode": engine.store.metadata("mode"), "workspace": str(Path(args.workspace)), "companies": len(engine.state()["companies"])}
        elif args.command in {"sec-watch", "ir-watch"}:
            from .sec_monitor import check_exe_filings
            from .ir_monitor import check_exe_ir
            if args.interval < 60:
                raise ValueError("Official-source monitoring uses an interval of at least 60 seconds")
            while True:
                result = check_exe_filings(engine, args.user_agent) if args.command == 'sec-watch' else check_exe_ir(engine)
                if args.once or result.get("alerts_created"):
                    print(encode(result), flush=True)
                if args.once:
                    return 0
                time.sleep(args.interval)
        elif args.command == "baseline":
            result = engine.propose_baseline(read_json(args.file))
        elif args.command == "agent":
            planner = None
            if args.llm:
                from .agent import ChatCompletionsPlanner
                if not args.endpoint or not args.model:
                    raise ValueError("--llm requires an explicit endpoint and model; selected research inputs will be sent there")
                planner = ChatCompletionsPlanner(args.endpoint, args.model, api_key=os.environ.get("THESISLEDGER_LLM_API_KEY"))
            result = engine.run_agent(args.symbol.upper(), planner)
            if args.output:
                write_new(args.output, json.dumps(result, indent=2)+"\n")
        elif args.command == "import":
            result = engine.import_company(read_json(args.file))
        elif args.command == "ingest":
            result = engine.ingest_event(read_json(args.file))
        elif args.command in {"research", "packet"}:
            symbol = args.symbol.upper()
            if args.command == "research":
                result = engine.research(symbol)
                text = engine.report(result["report_id"])["markdown"]
            else:
                result = engine.assistant_packet(symbol)
                text = json.dumps(result, indent=2)+"\n"
            if args.output:
                write_new(args.output, text)
                print(f"Saved {args.output}")
            else:
                print(text)
            return 0
        elif args.command == "monitor":
            if args.interval < 10:
                raise ValueError("Use an interval of at least 10 seconds")
            while True:
                result = scan_events(engine, args.events_dir)
                # In continuous mode stay quiet while files have no new actionable evidence.
                if args.once or any(item.get("alerts_created") or item["status"] == "rejected" for item in result["files"]):
                    print(encode(result), flush=True)
                if args.once:
                    return 1 if result["rejected"] else 0
                time.sleep(args.interval)
        elif args.command == "digest":
            result = digest_report(engine.state(), period=args.period)
        elif args.command == "observe":
            result = engine.forecast_observation(args.cohort_id, args.value, args.observed_at)
        elif args.command == "reconcile":
            result = {"marked_unknown": mark_interrupted_unknown(engine.store, aware(args.before))}
        elif args.command == "deliver":
            if not args.confirm_send:
                result = {"state": "disabled", "attempted": 0, "reason": "Use --confirm-send only when you intend to send real email"}
            else:
                if engine.store.metadata("mode") != "local_workspace":
                    raise ValueError("Synthetic replay never sends external email")
                configuration = {key: os.environ.get("THESISLEDGER_SMTP_"+key.upper()) for key in ("host", "port", "user", "password", "recipient")}
                result = deliver_pending(engine.store, smtp_sender(configuration), confirmed=True, limit=args.limit)
        print(encode({key: value for key, value in result.items() if key != "state" or not isinstance(value, dict)}))
        return 0
    except KeyboardInterrupt:
        print("Stopped. Saved research remains in the workspace.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Never display raw SMTP errors or environmental credential values.
        message = "Delivery configuration is missing or invalid" if args.command == "deliver" else str(exc)
        print("Cannot complete: "+message, file=sys.stderr)
        return 2
