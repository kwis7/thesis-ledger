"""Operator-started EXE SEC periodic-filing checks, with local review alerts."""
from datetime import datetime, timezone
import re

from .engine import digest
from .sec import SECError, collect_submissions
from .store import decode


def _previous(connection):
    row = connection.execute("SELECT value FROM metadata WHERE key='sec_monitor'").fetchone()
    return decode(row["value"], {}) if row else {}


def _health_event(engine, kind, at, summary):
    identity = "sec-health-"+digest({"kind": kind, "at": at})[:24]
    return engine.ingest_event({"id": identity, "symbol": "EXE", "kind": kind,
        "title": "SEC collection unavailable" if kind == "source_failure" else "SEC collection restored",
        "summary": summary, "source": "SEC collector status", "source_document": identity,
        "published_at": at, "decision_ts": at, "verified": True,
        "evidence": [], "evidence_ids": [], "changes": []})


def _failed(engine, exc):
    # Never persist arbitrary exception text or the operator's User-Agent/contact.
    match = re.search(r"\bHTTP ([0-9]{3})\b", str(exc))
    code = "http_"+match[1] if match else "collection_failed"
    reason = ("SEC request failed (HTTP "+match[1]+")." if match else "SEC collection could not be validated.")
    diagnostic = getattr(exc, 'reason_code', None)
    if diagnostic == 'undeclared_automated_tool':
        reason += ' SEC reported an undeclared automated tool. Review the declared application identity and public contact against SEC guidance.'
    at = datetime.now(timezone.utc).isoformat()
    with engine.store.connect(write=True) as connection:
        previous = _previous(connection)
        started = previous.get("failure_started_at") or at
        first_reason = previous.get("first_failure_reason") or reason
        engine.store.set_metadata(connection, "sec_monitor", {
            "status": "unavailable", "checked_at": at, "error_code": code, "reason": reason,
            "diagnostic": diagnostic if diagnostic in {'undeclared_automated_tool', 'rate_threshold', 'access_denied'} else None,
            "failure_started_at": started, "first_failure_reason": first_reason,
            "last_success_at": previous.get("last_success_at")})
    _health_event(engine, "source_failure", started,
        first_reason+" The check stopped. Saved filings and financial assumptions are unchanged; verify the application identity/contact and network access before starting another check.")
    raise SECError(reason+" Collection stopped; no automatic retry. See Monitor & timeline for saved status.") from None


def check_exe_filings(engine, user_agent, *, collector=collect_submissions):
    """Check once; preserve a visible, deduplicated outage and stop on failure."""
    company = engine.company("EXE")
    if company.get("case_id") != "exe-sec-2024-2025":
        raise ValueError("This first SEC monitor requires the isolated EXE public case")
    if engine.store.metadata("settings", {}).get("paused"):
        return {"status": "paused", "alerts_created": 0, "reason": "Resume monitoring before a network check"}
    try:
        snapshot = collector("0000895126", engine.store.workspace / "sec", user_agent)
        if "EXE" not in snapshot["issuer"].get("tickers", []):
            raise SECError("Collected SEC issuer does not match EXE")
    except SECError as exc:
        _failed(engine, exc)
    result = _process_snapshot(engine, company, snapshot)
    at = datetime.now(timezone.utc).isoformat()
    success = result["status"] not in {"data_gap", "paused"}
    with engine.store.connect(write=True) as connection:
        previous = _previous(connection)
        engine.store.set_metadata(connection, "sec_monitor", {
            "status": "available" if success else result["status"], "checked_at": at,
            "last_success_at": at if success else previous.get("last_success_at"),
            "reason": "Latest periodic-filing metadata checked; report contents still require review." if success else result.get("reason", "Check was paused"),
            "failure_started_at": None if success else previous.get("failure_started_at"),
            "first_failure_reason": None if success else previous.get("first_failure_reason")})
    if success and previous.get("failure_started_at"):
        _health_event(engine, "source_recovered", at,
            "A validated SEC response is available again. Financial contents have not been mapped or accepted; the saved model is unchanged.")
    return result


def known_accessions(engine, company):
    """One review per accession, including discovery by another official source."""
    from .cases import exe_facts
    known = {row['accessionNumber'] for row in exe_facts()['filings']}
    known.update(item.get('accession') for item in company['evidence'] if item.get('accession'))
    known.update(row['accession'] for row in engine.store.rows(
        "SELECT json_extract(payload,'$.source_document') AS accession FROM source_events WHERE symbol=? AND json_extract(payload,'$.kind')='review_due' AND json_extract(payload,'$.verification')='verified'", ('EXE',))
        if isinstance(row['accession'], str) and re.fullmatch(r'[0-9]{10}-[0-9]{2}-[0-9]{6}', row['accession']))
    return known


def _process_snapshot(engine, company, snapshot):
    filings = [row for row in snapshot["filings"] if row["form"] in {"10-K", "10-K/A", "10-Q", "10-Q/A"}]
    if not filings:
        return {"status": "data_gap", "reason": "No eligible periodic filing in the SEC recent window", "alerts_created": 0}
    latest = max(filings, key=lambda row: (row["filingDate"], row["accessionNumber"]))
    known = known_accessions(engine, company)
    if latest["accessionNumber"] in known or latest["reportDate"] < company["financials"]["period_end"]:
        return {"status": "unchanged", "alerts_created": 0, "accession": latest["accessionNumber"]}
    accn = latest["accessionNumber"]
    evidence_id = "official-filing-"+accn.replace("-", "")
    url = latest.get("source_url", latest.get("url"))
    published = latest["available_at"]
    acquired = snapshot["as_of"]
    evidence = {"id": evidence_id, "title": f"EXE {latest['form']} filing metadata", "source": "SEC EDGAR submissions",
        "source_type": "regulatory_filing", "url": url, "published_at": published, "retrieved_at": acquired,
        "usable_at": acquired, "period": latest["reportDate"], "unit": "filing metadata", "currency": "USD",
        "locator": accn+" / SEC submissions recent", "content": f"SEC lists {latest['form']}, accession {accn}, filed {latest['filingDate']}, period {latest['reportDate']}. Financial contents have not been mapped to forecast assumptions.",
        "classification": "confirmed_fact", "verified": True}
    result = engine.ingest_event({"id": evidence_id, "symbol": "EXE", "kind": "review_due",
        "title": f"New EXE {latest['form']} needs a financial review", "summary": "A later periodic filing is available. Reconcile its operating facts and financial bridge before proposing a model refresh.",
        "source": "SEC EDGAR submissions", "source_document": accn, "published_at": published,
        "decision_ts": acquired, "verified": True, "evidence": [evidence], "evidence_ids": [evidence_id], "changes": []})
    return {"status": result["status"], "alerts_created": result.get("alerts_created", 0), "accession": accn,
            "source_url": url, "scope": "Latest eligible periodic filing only; report contents require review"}
