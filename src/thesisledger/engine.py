"""Research, evidence replay, proposed updates and an auditable local alert inbox."""

from __future__ import annotations

import copy
import hashlib
import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .events import fingerprint, replay_events
from .fixtures import build_demo_companies
from .store import Store, decode, encode
from .valuation import technical_summary, validate_evidence, value_company


BASELINE_TS = "2026-07-01T16:00:00+00:00"
DEFAULT_SETTINGS = {
    "name": "My research desk", "language": "en", "cooldown_hours": 24,
    "quiet_start": "22:00", "quiet_end": "07:00", "digest_enabled": True,
    "paused": False, "timezone": "UTC", "email_enabled": False,
    "value_change_threshold_pct": 5.0,
}
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,11}$")
SENSITIVE_KEYS = {"account", "account_id", "account_number", "holdings", "transactions",
                  "cost_basis", "password", "api_key", "token", "cookie", "private_key",
                  "email", "phone", "address", "ssn"}
ALLOWED_PARAMETERS = {
    "industrial": {"qualified_utilization", "unit_price_growth", "qualified_capacity_growth", "discount_rate"},
    "recurring": {"retention", "new_customers", "service_cost_ratio", "discount_rate"},
    "commodity": {"annual_production", "realized_price", "cash_cost", "annual_capex", "discount_rate", "reserve_life_years"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def aware(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("A timezone-aware timestamp is required")
    return result


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


def check_public_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Research object keys must be text")
            if key.lower() in SENSITIVE_KEYS:
                raise ValueError("The research packet contains a private or credential field")
            check_public_fields(item)
    elif isinstance(value, list):
        for item in value:
            check_public_fields(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite numeric inputs are not accepted")


class ResearchEngine:
    def __init__(self, workspace: str | Path, *, demo: bool = True):
        self.store = Store(workspace)
        with self.store.connect(write=True) as connection:
            exists = connection.execute("SELECT value FROM metadata WHERE key='mode'").fetchone()
            if exists is None:
                mode = "synthetic_replay" if demo else "local_workspace"
                self.store.set_metadata(connection, "mode", mode)
                self.store.set_metadata(connection, "settings", DEFAULT_SETTINGS)
                self.store.set_metadata(connection, "as_of", BASELINE_TS if demo else now_iso())
                self.store.set_metadata(connection, "updated_at", now_iso())
                if demo:
                    for company in build_demo_companies():
                        self._insert_company(connection, company, "Initial synthetic baseline", None)
                    self.store.activity(connection, "baseline", "Research baseline ready. No alerts generated.", BASELINE_TS)

    def _insert_company(self, connection: sqlite3.Connection, company: dict, reason: str,
                        event_id: str | None) -> str:
        symbol = company["symbol"]
        valuation = value_company(company)
        connection.execute(
            "INSERT INTO companies(symbol,payload) VALUES(?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET payload=excluded.payload, thesis_status='updated'",
            (symbol, encode(company)),
        )
        version = connection.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM revisions WHERE symbol=?", (symbol,)
        ).fetchone()[0]
        revision_id = f"{symbol.lower()}-v{version}"
        created_at = now_iso()
        connection.execute(
            "INSERT INTO revisions VALUES(?,?,?,?,?,?,?,?,?)",
            (revision_id, symbol, version, encode(company), encode(valuation), reason,
             event_id, created_at, digest(company)),
        )
        # Preserve old cohorts. No later refresh overwrites their predicted values.
        for scenario in valuation.get("scenarios", []):
            if str(scenario.get("name", "")).lower() == "base":
                for index, row in enumerate(scenario.get("forecast", [])):
                    if row.get("revenue") is not None:
                        anchor = aware(company["as_of"])
                        try:
                            end = anchor.replace(year=anchor.year + index + 1)
                        except ValueError:
                            end = anchor.replace(year=anchor.year + index + 1, day=28)
                        connection.execute(
                            "INSERT INTO forecasts(id,symbol,revision_id,horizon,metric,predicted,frozen_at) "
                            "VALUES(?,?,?,?,?,?,?)",
                            (f"{revision_id}-revenue-{index+1}", symbol, revision_id,
                             end.date().isoformat(), "revenue", row["revenue"], created_at),
                        )
        return revision_id

    def _company(self, symbol: str) -> dict:
        rows = self.store.rows("SELECT * FROM companies WHERE symbol=?", (symbol,))
        if not rows:
            raise ValueError("Company is not in this workspace. Import a sourced research packet first.")
        row = rows[0]
        company = decode(row["payload"])
        company["valuation"] = value_company(company)
        company["synthetic"] = bool(company.get("evidence")) and all(item.get("source_type") == "synthetic" for item in company["evidence"])
        company["technical"] = technical_summary(company.get("prices", []), company["as_of"])
        company.update(watch_tier=row["tier"], watched=bool(row["watched"]),
                       thesis_status=row["thesis_status"], data_status=row["data_status"], currency="USD")
        events = self.store.rows("SELECT * FROM source_events WHERE symbol=? ORDER BY decision_ts DESC", (symbol,))
        latest_candidate = next((decode(item["payload"]) for item in events
                                 if decode(item["payload"]).get("candidate_valuation")
                                 and decode(item["payload"]).get("baseline_hash") == digest(decode(row["payload"]))), None)
        company["candidate_valuation"] = latest_candidate.get("candidate_valuation") if latest_candidate else None
        company["candidate_changes"] = latest_candidate.get("changes", []) if latest_candidate else []
        company["candidate_event_id"] = latest_candidate["id"] if latest_candidate else None
        company["candidate_baseline_hash"] = latest_candidate["baseline_hash"] if latest_candidate else None
        company["candidate_hash"] = digest(latest_candidate["candidate_valuation"]) if latest_candidate else None
        company["latest_change"] = decode(events[0]["payload"]) if events else None
        company["history"] = [dict(item, company=decode(item["company_json"]), valuation=decode(item["valuation_json"]))
                              for item in self.store.rows("SELECT * FROM revisions WHERE symbol=? ORDER BY version DESC", (symbol,))]
        for item in company["history"]:
            item.pop("company_json", None)
            item.pop("valuation_json", None)
        company["forecast_cohorts"] = self.store.rows("SELECT * FROM forecasts WHERE symbol=? ORDER BY frozen_at,id", (symbol,))
        return company

    def company(self, symbol: str) -> dict:
        return self._company(symbol.upper())

    def state(self) -> dict:
        settings = self.store.metadata("settings", DEFAULT_SETTINGS)
        companies = [self._company(row["symbol"]) for row in self.store.rows("SELECT symbol FROM companies ORDER BY symbol")]
        alerts = [dict(decode(row["payload"]), review_state=row["review_state"], delivery_state=row["delivery_state"])
                  for row in self.store.rows("SELECT * FROM alerts ORDER BY created_at DESC,rowid DESC")]
        events = [dict(decode(row["payload"]), state=row["state"], replay_count=row["replay_count"])
                  for row in self.store.rows("SELECT * FROM source_events ORDER BY decision_ts DESC")]
        watched = [item for item in companies if item["watched"]]
        gaps = sum(item["data_status"] != "fresh" for item in watched)
        review = sum(item["thesis_status"] == "review_required" for item in watched)
        available = replay_events() if self.store.metadata("mode") == "synthetic_replay" else []
        seen = {item["id"] for item in events}
        next_event = next((item["id"] for item in available if item["id"] not in seen), None)
        return {
            "meta": {"version": __version__, "mode": self.store.metadata("mode"),
                     "as_of": self.store.metadata("as_of"), "updated_at": self.store.metadata("updated_at"),
                     "synthetic": self.store.metadata("mode") == "synthetic_replay", "paused": settings["paused"],
                     "sec_monitor": self.store.metadata("sec_monitor"), "ir_monitor": self.store.metadata("ir_monitor")},
            "overview": {"status": "data_pending" if gaps else "review_required" if review else "stable",
                         "watched": len(watched), "unread_alerts": sum(item["review_state"] == "new" for item in alerts),
                         "review_required": review, "data_gaps": gaps,
                         "last_checked": self.store.metadata("last_checked", self.store.metadata("as_of"))},
            "companies": companies, "alerts": alerts, "events": events,
            "activity": self.store.rows("SELECT * FROM activity ORDER BY id DESC LIMIT 60"), "settings": settings,
            "replay": {"available_events": [{"id": item["id"], "title": item["title"], "symbol": item["symbol"]} for item in available],
                       "next_event_id": next_event, "last_event_id": self.store.metadata("last_event_id")},
            "delivery": {"channel": "local_inbox", "external_enabled": settings["email_enabled"],
                         "outbox": self.store.rows("SELECT state,COUNT(*) AS count FROM outbox GROUP BY state")},
        }

    def replay(self, event_id: str | None = None) -> dict:
        if self.store.metadata("mode") != "synthetic_replay":
            raise ValueError("Replay is available only in the clearly labelled synthetic demo.")
        if event_id is None:
            event_id = self.state()["replay"]["next_event_id"]
        event = next((item for item in replay_events() if item["id"] == event_id), None)
        if event is None:
            return {"status": "complete", "message": "All sample updates have been replayed.", "state": self.state()}
        return self.ingest_event(event)

    def ingest_event(self, original: dict) -> dict:
        check_public_fields(original)
        event = copy.deepcopy(original)
        required = ("id", "symbol", "kind", "title", "published_at", "decision_ts", "source_document")
        if any(not event.get(key) for key in required):
            raise ValueError("An event needs identity, source, publication and decision timestamps")
        if event["kind"] not in {"driver_change", "ambiguous_evidence", "source_failure", "source_recovered", "review_due", "baseline_refresh"}:
            raise ValueError("Unsupported event kind")
        if len(event["id"]) > 100 or not SYMBOL.fullmatch(event["symbol"]):
            raise ValueError("Invalid event identity")
        published, decision = aware(event["published_at"]), aware(event["decision_ts"])
        if published > decision:
            raise ValueError("Future evidence cannot be used at the decision cutoff")
        if decision > datetime.now(timezone.utc):
            raise ValueError("An event decision cutoff cannot be in the future")
        event["published_at"] = published.astimezone(timezone.utc).isoformat()
        event["decision_ts"] = decision.astimezone(timezone.utc).isoformat()
        if not isinstance(event.get("verified"), bool):
            raise ValueError("Event verification must be a literal boolean")
        initial_fingerprint = fingerprint(event)
        duplicate_id = None
        with self.store.connect(write=True) as connection:
            existing = connection.execute("SELECT id,fingerprint FROM source_events WHERE fingerprint=? OR id=?", (initial_fingerprint, event["id"])).fetchone()
            if existing:
                if existing["fingerprint"] != initial_fingerprint:
                    raise ValueError("This event ID was already used for different source evidence")
                duplicate_id = existing["id"]
                connection.execute("UPDATE source_events SET replay_count=replay_count+1 WHERE id=?", (duplicate_id,))
        if duplicate_id:
            return {"status": "duplicate", "duplicate": True, "event_id": duplicate_id, "alerts_created": 0,
                    "message": "Already processed. No duplicate alert.", "state": self.state()}
        settings = self.store.metadata("settings", DEFAULT_SETTINGS)
        if settings["paused"]:
            return {"status": "paused", "message": "Monitoring is paused. No event was consumed.", "state": self.state()}
        base_company = self.company(event["symbol"])
        base_payload = decode(self.store.rows("SELECT payload FROM companies WHERE symbol=?", (event["symbol"],))[0]["payload"])
        if decision < aware(base_payload["as_of"]):
            raise ValueError("An update cannot move the thesis baseline backwards in time")
        errors = []
        for evidence in event.get("evidence", []):
            errors.extend(validate_evidence(evidence, event["decision_ts"]))
        if errors and event.get("verified"):
            raise ValueError("Evidence validation failed: " + "; ".join(errors[:5]))
        event["evidence_errors"] = errors
        event["baseline_hash"] = digest(base_payload)
        event["candidate_valuation"] = None
        event["changes"] = list(event.get("changes", []))
        verified = event.get("verified") is True and not errors
        if event["kind"] == "baseline_refresh":
            proposed_payload = self._validate_company(event.get("proposed_company"))
            identity = digest(proposed_payload)
            if (event.get("verified") is not True or event["source_document"] != identity
                    or event["id"] != "baseline-"+identity[:24]
                    or event.get("evidence") != proposed_payload["evidence"]
                    or sorted(event.get("evidence_ids", [])) != sorted(item["id"] for item in proposed_payload["evidence"])):
                raise ValueError("Use a verified canonical financial refresh prepared from its complete sourced packet")
            if proposed_payload["symbol"] != event["symbol"] or proposed_payload["as_of"] != event["decision_ts"]:
                raise ValueError("Financial refresh identity/cutoff must match its event")
            candidate = value_company(proposed_payload)
            if candidate["state"] != "available":
                raise ValueError("Financial refresh requires a supported, validated model")
            event["candidate_valuation"] = candidate
            verified = True
        if event["kind"] == "driver_change":
            if not event["changes"]:
                raise ValueError("A driver proposal must contain at least one explicit change")
            references = event.get("evidence_ids", [])
            sources = {item["id"]: item for item in event.get("evidence", [])}
            if not references or not set(references).issubset(sources) or any(
                sources[key].get("verified") is not True or sources[key].get("classification") not in {"confirmed_fact", "model_assumption"}
                for key in references if key in sources
            ):
                verified = False
            assumptions = dict(base_payload["assumptions"])
            for change in event["changes"]:
                parameter = change.get("parameter")
                if parameter not in ALLOWED_PARAMETERS.get(base_payload["archetype"], set()):
                    raise ValueError("This driver has no supported model mapping; keep it as ambiguous evidence")
                value = change.get("new")
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    raise ValueError("Driver update must be finite numeric input")
                change["old"] = assumptions.get(parameter)
                assumptions[parameter] = value
            if verified:
                proposed_payload = copy.deepcopy(base_payload)
                proposed_payload["as_of"] = event["decision_ts"]
                if proposed_payload.get("archetype") == "commodity" and proposed_payload.get("balance_sheet_bridge", {}).get("method") == "hold_last_reported":
                    proposed_payload["balance_sheet_bridge"]["as_of"] = event["decision_ts"]
                proposed_payload["evidence"] += event.get("evidence", [])
                candidate = value_company(proposed_payload, assumptions)
                if candidate["state"] == "available":
                    event["candidate_valuation"] = candidate
                else:
                    event["model_gap"] = candidate.get("data_gaps", ["Model update is infeasible"])
        event["verification"] = "verified" if verified else "needs_verification"
        event_hash = fingerprint(event)
        created_at = now_iso()
        baseline_value = base_company["valuation"].get("base")
        proposed_value = (event.get("candidate_valuation") or {}).get("base")
        value_change = abs((proposed_value-baseline_value)/baseline_value*100) if baseline_value not in (None, 0) and proposed_value is not None else None
        material = event["kind"] != "driver_change" or not verified or proposed_value is None or (value_change is not None and value_change >= settings["value_change_threshold_pct"])
        event["material"] = material
        duplicate = False
        alert_created = False
        with self.store.connect(write=True) as connection:
            existing = connection.execute("SELECT id,fingerprint FROM source_events WHERE fingerprint=? OR id=?", (event_hash, event["id"])).fetchone()
            if existing:
                if existing["fingerprint"] != event_hash:
                    raise ValueError("This event ID was already used for different source evidence")
                connection.execute("UPDATE source_events SET replay_count=replay_count+1 WHERE id=?", (existing["id"],))
                duplicate = True
            else:
                current_payload = decode(connection.execute("SELECT payload FROM companies WHERE symbol=?", (event["symbol"],)).fetchone()[0])
                if digest(current_payload) != event["baseline_hash"]:
                    raise ValueError("The baseline changed while checking evidence. Refresh and retry.")
                superseded_health = False
                if event["kind"] in {"source_failure", "source_recovered"}:
                    health = connection.execute("SELECT decision_ts FROM source_events WHERE symbol=? AND (json_extract(payload,'$.kind')='source_failure' OR (json_extract(payload,'$.kind')='source_recovered' AND json_extract(payload,'$.verification')='verified')) ORDER BY decision_ts DESC LIMIT 1", (event["symbol"],)).fetchone()
                    superseded_health = bool(health and aware(health["decision_ts"]) > decision)
                    if superseded_health:
                        material = False
                        event["material"] = False
                state = "coverage_degraded" if event["kind"] == "source_failure" else "coverage_restored" if event["kind"] == "source_recovered" else "review_required" if material else "no_material_change"
                if superseded_health:
                    state = "superseded_health_observation"
                elif event["kind"] == "source_recovered" and not verified:
                    state = "coverage_recovery_unverified"
                connection.execute("INSERT INTO source_events(id,fingerprint,symbol,payload,state,decision_ts,created_at) VALUES(?,?,?,?,?,?,?)",
                                   (event["id"], event_hash, event["symbol"], encode(event), state, event["decision_ts"], created_at))
                watched = connection.execute("SELECT watched FROM companies WHERE symbol=?", (event["symbol"],)).fetchone()[0]
                if event["kind"] in {"source_failure", "source_recovered"} and not superseded_health and (event["kind"] == "source_failure" or verified):
                    connection.execute("UPDATE companies SET data_status=? WHERE symbol=?",
                                       ("stale" if event["kind"] == "source_failure" else "fresh", event["symbol"]))
                elif material:
                    connection.execute("UPDATE companies SET thesis_status='review_required' WHERE symbol=?", (event["symbol"],))
                # Local inbox receives research-relevant changes. Cooldown controls repeated external nudges.
                if watched and material and (event["kind"] != "source_recovered" or not verified):
                    base = base_company["valuation"].get("base")
                    candidate_value = (event.get("candidate_valuation") or {}).get("base")
                    delta = (candidate_value - base) / abs(base) * 100 if base not in (None, 0) and candidate_value is not None else None
                    alert = {"id": "alert-" + event_hash[:16], "event_id": event["id"], "symbol": event["symbol"],
                             "title": event["title"], "reason": event.get("summary", "Evidence needs your review"),
                             "severity": "high" if event.get("candidate_valuation") else "medium",
                             "occurred_at": event["published_at"], "verification": event["verification"],
                             "evidence_ids": event.get("evidence_ids", []), "changes": event["changes"],
                             "baseline_value": base, "candidate_value": candidate_value, "value_delta_pct": delta,
                             "review_state": "new", "delivery_state": "delivered_local",
                             "model_gap": event.get("model_gap", []), "external_delivery": "not_enabled"}
                    connection.execute("INSERT INTO alerts(id,event_id,symbol,payload,created_at) VALUES(?,?,?,?,?)",
                                       (alert["id"], event["id"], event["symbol"], encode(alert), created_at))
                    alert_created = True
                    if settings["email_enabled"] and self.store.metadata("mode") == "local_workspace":
                        last = connection.execute("SELECT outbox.created_at FROM outbox JOIN alerts ON alerts.id=outbox.alert_id WHERE alerts.symbol=? ORDER BY outbox.created_at DESC LIMIT 1", (event["symbol"],)).fetchone()
                        cooldown = last and datetime.now(timezone.utc) < aware(last["created_at"]) + timedelta(hours=settings["cooldown_hours"])
                        if not cooldown:
                            connection.execute("INSERT INTO outbox(id,alert_id,channel,created_at) VALUES(?,?,?,?)",
                                               ("mail-" + event_hash[:16], alert["id"], "email", created_at))
                self.store.activity(connection, "evidence", event["title"], event["decision_ts"], event["symbol"])
            current = self.store.metadata("as_of")
            if aware(event["decision_ts"]) > aware(current):
                self.store.set_metadata(connection, "as_of", event["decision_ts"])
            self.store.set_metadata(connection, "last_event_id", event["id"])
            previous_check = self.store.metadata("last_checked", BASELINE_TS)
            self.store.set_metadata(connection, "last_checked", max(aware(previous_check), decision).isoformat())
            self.store.set_metadata(connection, "updated_at", created_at)
        return {"status": "duplicate" if duplicate else "processed", "duplicate": duplicate,
                "event_id": event["id"], "alerts_created": int(alert_created),
                "message": "Already processed. No duplicate alert." if duplicate else "Evidence checked. Review any proposed assumption change before accepting it.",
                "state": self.state()}

    def review_alert(self, alert_id: str, action: str) -> dict:
        if action not in {"reviewed", "deferred"}:
            raise ValueError("Choose reviewed or deferred")
        with self.store.connect(write=True) as connection:
            row = connection.execute("SELECT symbol FROM alerts WHERE id=?", (alert_id,)).fetchone()
            if not row:
                raise ValueError("Alert not found")
            connection.execute("UPDATE alerts SET review_state=? WHERE id=?", (action, alert_id))
            self.store.activity(connection, "review", "Alert marked " + action + ". Financial assumptions were not changed.", now_iso(), row["symbol"])
        return {"status": "success", "message": "Review recorded. Accepting a model change is a separate action.", "state": self.state()}

    def accept_assumptions(self, symbol: str, event_id: str, baseline_hash: str, candidate_hash: str) -> dict:
        company = self.company(symbol)
        if (company["candidate_event_id"] != event_id or company["candidate_baseline_hash"] != baseline_hash
                or company["candidate_hash"] != candidate_hash):
            raise ValueError("The reviewed candidate changed. Refresh and review the current proposal.")
        event = next((decode(row["payload"]) for row in self.store.rows("SELECT payload FROM source_events WHERE symbol=? ORDER BY decision_ts DESC", (symbol,))
                      if decode(row["payload"]).get("candidate_valuation") and decode(row["payload"]).get("baseline_hash") == digest(decode(self.store.rows("SELECT payload FROM companies WHERE symbol=?", (symbol,))[0]["payload"]))), None)
        if event is None or event["verification"] != "verified":
            raise ValueError("No verified, current-baseline model update is available")
        payload = decode(self.store.rows("SELECT payload FROM companies WHERE symbol=?", (symbol,))[0]["payload"])
        if event["kind"] == "baseline_refresh":
            payload = copy.deepcopy(event["proposed_company"])
        for change in event["changes"] if event["kind"] != "baseline_refresh" else []:
            payload["assumptions"][change["parameter"]] = change["new"]
            for driver in payload["thesis"].get("drivers", []):
                if driver.get("id") == change["parameter"]:
                    driver["value"] = change["new"]
                    driver["evidence_ids"] = event["evidence_ids"]
        if event["kind"] != "baseline_refresh":
            payload["evidence"] += event.get("evidence", [])
        payload["as_of"] = event["decision_ts"]
        if payload.get("archetype") == "commodity" and payload.get("balance_sheet_bridge", {}).get("method") == "hold_last_reported":
            payload["balance_sheet_bridge"]["as_of"] = event["decision_ts"]
        with self.store.connect(write=True) as connection:
            # A concurrent acceptance cannot accept against an obsolete baseline.
            current = decode(connection.execute("SELECT payload FROM companies WHERE symbol=?", (symbol,)).fetchone()[0])
            if digest(current) != event["baseline_hash"]:
                raise ValueError("Baseline changed. Refresh and inspect the new candidate.")
            latest = connection.execute("SELECT id FROM source_events WHERE symbol=? AND json_extract(payload,'$.candidate_valuation') IS NOT NULL AND json_extract(payload,'$.baseline_hash')=? ORDER BY decision_ts DESC LIMIT 1", (symbol, baseline_hash)).fetchone()
            if not latest or latest["id"] != event_id:
                raise ValueError("A new candidate arrived. Review it before accepting a change.")
            locked_row = connection.execute("SELECT payload,fingerprint FROM source_events WHERE id=?", (event_id,)).fetchone()
            locked_event = decode(locked_row["payload"])
            if fingerprint(locked_event) != locked_row["fingerprint"] or digest(locked_event) != digest(event):
                raise ValueError("The saved proposal changed. Prepare and review a new candidate.")
            if event["kind"] == "baseline_refresh" and (digest(payload) != event["source_document"] or event["id"] != "baseline-"+digest(payload)[:24]):
                raise ValueError("Financial refresh packet integrity failed")
            if digest(value_company(payload)) != candidate_hash:
                raise ValueError("Recomputed proposal differs from the reviewed calculation")
            reason = "Reviewed and accepted financial baseline refresh" if event["kind"] == "baseline_refresh" else "Reviewed and accepted operating-assumption update"
            self._insert_company(connection, payload, reason, event["id"])
            connection.execute("UPDATE source_events SET state='accepted' WHERE id=?", (event["id"],))
            connection.execute("UPDATE alerts SET review_state='reviewed' WHERE event_id=?", (event["id"],))
            self.store.activity(connection, "thesis_update", "Revised assumptions accepted. The previous thesis and forecasts remain preserved.", now_iso(), symbol)
        return {"status": "success", "message": "New thesis version saved; prior baseline preserved.", "state": self.state()}

    def update_settings(self, patch: dict) -> dict:
        settings = self.store.metadata("settings", DEFAULT_SETTINGS)
        if set(patch) - set(DEFAULT_SETTINGS):
            raise ValueError("Unknown workspace setting")
        settings.update(patch)
        if not isinstance(settings["name"], str) or not 1 <= len(settings["name"]) <= 80:
            raise ValueError("Workspace name must contain 1 to 80 characters")
        if settings["language"] not in {"en", "zh-CN"}:
            raise ValueError("Supported preference: en or zh-CN. UI is currently English.")
        if not isinstance(settings["cooldown_hours"], (int, float)) or not 0 <= settings["cooldown_hours"] <= 720:
            raise ValueError("Cooldown must be between 0 and 720 hours")
        if not isinstance(settings["value_change_threshold_pct"], (int, float)) or not 0 <= settings["value_change_threshold_pct"] <= 100:
            raise ValueError("Value materiality threshold must be between 0 and 100 percent")
        for key in ("paused", "digest_enabled", "email_enabled"):
            if not isinstance(settings[key], bool):
                raise ValueError("Toggle settings must be booleans")
        for key in ("quiet_start", "quiet_end"):
            if not isinstance(settings[key], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", settings[key]):
                raise ValueError("Quiet hours use HH:MM")
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(settings["timezone"])
        except (ZoneInfoNotFoundError, TypeError):
            raise ValueError("Use a valid IANA timezone") from None
        with self.store.connect(write=True) as connection:
            self.store.set_metadata(connection, "settings", settings)
            self.store.activity(connection, "settings", "Workspace preferences updated", now_iso())
        return {"status": "success", "message": "Workspace preferences saved. External email remains separately configured and never sends from this page.", "state": self.state()}

    def update_watchlist(self, symbol: str, tier: str, watched: bool) -> dict:
        if tier not in {"focused", "observe", "discover"} or not isinstance(watched, bool):
            raise ValueError("Choose a supported tier and boolean monitoring state")
        self.company(symbol)
        with self.store.connect(write=True) as connection:
            connection.execute("UPDATE companies SET tier=?,watched=? WHERE symbol=?", (tier, int(watched), symbol))
        return {"status": "success", "message": "Monitoring preference saved", "state": self.state()}

    def _validate_company(self, packet: dict) -> dict:
        if not isinstance(packet, dict):
            raise ValueError("Company packet must be a JSON object")
        check_public_fields(packet)
        packet = copy.deepcopy(packet)
        required = {"symbol", "name", "archetype", "as_of", "financials", "assumptions", "evidence", "thesis"}
        if required - set(packet):
            raise ValueError("Company packet is missing required model, thesis or evidence fields")
        for key in ("financials", "assumptions"):
            if not isinstance(packet[key], dict):
                raise ValueError(f"Company {key} must be an object")
        if packet["archetype"] == "commodity" and not isinstance(packet.get("balance_sheet_bridge"), dict):
            raise ValueError("Commodity balance_sheet_bridge must be an object")
        for key in ("symbol", "name", "archetype", "as_of"):
            if not isinstance(packet[key], str) or not packet[key].strip():
                raise ValueError(f"Company {key} must be nonempty text")
        if not SYMBOL.fullmatch(packet["symbol"]):
            raise ValueError("Invalid security symbol")
        if "description" in packet and not isinstance(packet["description"], str):
            raise ValueError("Company description must be text")
        thesis = packet["thesis"]
        if not isinstance(thesis, dict):
            raise ValueError("Company thesis must be an object")
        if "statement" in thesis and not isinstance(thesis["statement"], str):
            raise ValueError("Thesis statement must be text")
        for key in ("counterevidence", "falsifiers"):
            items = thesis.get(key, [])
            if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                raise ValueError(f"Thesis {key} must be a list of text entries")
        drivers = thesis.get("drivers", [])
        if not isinstance(drivers, list) or any(not isinstance(driver, dict) for driver in drivers):
            raise ValueError("Thesis drivers must be a list of objects")
        for driver in drivers:
            references = driver.get("evidence_ids", [])
            if not isinstance(references, list) or any(not isinstance(item, str) for item in references):
                raise ValueError("Driver evidence_ids must be a list of text identifiers")
        if not isinstance(packet["evidence"], list) or not packet["evidence"]:
            raise ValueError("An imported baseline needs attributable source evidence")
        if aware(packet["as_of"]) > datetime.now(timezone.utc):
            raise ValueError("A live workspace cannot import a future baseline")
        packet["as_of"] = aware(packet["as_of"]).astimezone(timezone.utc).isoformat()
        if packet.get("prices"):
            technical = technical_summary(packet["prices"], packet["as_of"])
            if technical["state"] == "unavailable":
                raise ValueError("Price-bar validation failed: " + "; ".join(technical.get("notes", [])))
        errors = [error for evidence in packet["evidence"] for error in validate_evidence(evidence, packet["as_of"])]
        if errors:
            raise ValueError("Baseline evidence validation failed: " + "; ".join(errors[:5]))
        return packet

    def propose_baseline(self, packet: dict) -> dict:
        packet = self._validate_company(packet)
        previous = decode(self.store.rows("SELECT payload FROM companies WHERE symbol=?", (packet["symbol"],))[0]["payload"]) if self.store.rows("SELECT payload FROM companies WHERE symbol=?", (packet["symbol"],)) else None
        if previous is None:
            raise ValueError("Import a first baseline before proposing a financial refresh")
        if aware(packet["as_of"]) < aware(previous["as_of"]):
            raise ValueError("Financial refresh cannot move the research cutoff backwards")
        changes = [{"parameter": "financials."+key, "old": previous["financials"].get(key), "new": value}
                   for key, value in packet["financials"].items()
                   if isinstance(value, (int, float)) and not isinstance(value, bool) and previous["financials"].get(key) != value]
        event_id = "baseline-"+digest(packet)[:24]
        return self.ingest_event({"id": event_id, "symbol": packet["symbol"], "kind": "baseline_refresh",
            "title": "Review a complete financial baseline refresh", "summary": "A new sourced packet needs explicit acceptance; previous revisions stay available.",
            "source": "Reviewed supplied research packet", "source_document": digest(packet),
            "published_at": max(item["published_at"] for item in packet["evidence"]), "decision_ts": packet["as_of"],
            "verified": True, "evidence": packet["evidence"], "evidence_ids": [item["id"] for item in packet["evidence"]],
            "changes": changes, "proposed_company": packet})

    def import_company(self, packet: dict) -> dict:
        packet = self._validate_company(packet)
        with self.store.connect(write=True) as connection:
            if connection.execute("SELECT symbol FROM companies WHERE symbol=?", (packet["symbol"],)).fetchone():
                raise ValueError("Company already exists. Ingest an evidence update instead of replacing its history.")
            self._insert_company(connection, packet, "Imported sourced research baseline", None)
            self.store.activity(connection, "import", "Public research packet imported", now_iso(), packet["symbol"])
        return {"status": "success", "message": "Baseline imported with its evidence and model inputs", "state": self.state()}

    def lab(self, symbol: str, overrides: dict | None = None) -> dict:
        from .lab import research_lab
        payload = decode(self.store.rows("SELECT payload FROM companies WHERE symbol=?", (symbol,))[0]["payload"]) if self.store.rows("SELECT payload FROM companies WHERE symbol=?", (symbol,)) else None
        if payload is None:
            raise ValueError("Import a supported company before opening the Research Lab")
        facts = []
        if payload.get("case_id") == "exe-sec-2024-2025":
            from .cases import exe_facts
            facts = [dict(row, url=row.get("source_url")) for row in exe_facts()["facts"]]
        return research_lab(payload, facts, overrides)

    def run_agent(self, symbol: str, planner=None) -> dict:
        from .agent import run_agent, save_run
        rows = self.store.rows("SELECT payload FROM companies WHERE symbol=?", (symbol,))
        if not rows:
            raise ValueError("Company is not in this workspace")
        company = decode(rows[0]["payload"])
        from .cases import exe_agent_inputs, exe_review_event
        filings = exe_agent_inputs() if company.get("case_id") == "exe-sec-2024-2025" else {"facts": []}
        run = run_agent(company, filings, planner=planner)
        saved = save_run(run, self.store.workspace / "runs")
        if company.get("case_id") == "exe-sec-2024-2025":
            self.ingest_event(exe_review_event(company))
        output = run["output"]
        return dict(output, run_id=saved.stem, planner_mode=run["manifest"].get("planner_mode", "offline"), manifest=run["manifest"])

    def runs(self) -> dict:
        from .agent import MAX_BUNDLE_BYTES, _verify
        directory = self.store.workspace / "runs"
        items = []
        skipped = 0
        if directory.is_dir() and not directory.is_symlink():
            for path in sorted(directory.glob("run-*.json"))[-100:]:
                try:
                    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES:
                        raise ValueError("Invalid saved research file")
                    bundle = decode(path.read_text(encoding="utf-8"))
                    _verify(bundle)
                    manifest = bundle["manifest"]
                    if path.stem != "run-"+manifest["bundle_sha256"]:
                        raise ValueError("Saved run filename does not match its bundle")
                except (OSError, ValueError, KeyError, TypeError):
                    skipped += 1
                    continue
                items.append({"run_id": path.stem, "symbol": manifest.get("symbol", bundle.get("inputs", {}).get("company", {}).get("symbol")),
                              "cutoff": manifest.get("cutoff"), "planner_mode": manifest.get("planner_mode"), "output_hash": manifest.get("output_hash")})
        return {"runs": items, "skipped": skipped}

    def run_bundle(self, run_id: str) -> dict:
        from .agent import MAX_BUNDLE_BYTES, _verify
        if not re.fullmatch(r"run-[a-f0-9]{12,64}", run_id):
            raise ValueError("Invalid research run identity")
        path = self.store.workspace / "runs" / (run_id+".json")
        if path.parent.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES:
            raise ValueError("Research run not found")
        bundle = decode(path.read_text(encoding="utf-8"))
        _verify(bundle)
        if path.stem != "run-"+bundle["manifest"]["bundle_sha256"]:
            raise ValueError("Saved run filename does not match its bundle")
        return bundle

    def replay_run(self, run_id: str) -> dict:
        from .agent import replay_run
        result = replay_run(self.run_bundle(run_id))
        return {"verified": True, "run_id": run_id, "output_hash": result["manifest"]["output_sha256"]}

    def research(self, symbol: str) -> dict:
        from .reports import render_report
        company = self.company(symbol)
        created_at = now_iso()
        snapshot_identity = {key: company.get(key) for key in ("symbol", "as_of", "financials", "assumptions", "thesis", "evidence", "prices", "price", "price_as_of", "data_status")}
        snapshot_identity["report_format"] = 1
        report_id = f"{symbol.lower()}-{digest(snapshot_identity)[:12]}"
        markdown = render_report(company, self.store.metadata("mode"))
        status = "bounded_research" if company["valuation"]["state"] == "available" else "valuation_unavailable"
        with self.store.connect(write=True) as connection:
            connection.execute("INSERT OR IGNORE INTO reports VALUES(?,?,?,?,?,?,?)",
                               (report_id, symbol, company["name"] + " research brief", markdown, encode(company), status, created_at))
            self.store.activity(connection, "report", "Research brief saved with linked sources and calculations", created_at, symbol)
        return {"status": "success", "report_id": report_id, "message": "Bounded research brief saved. Full-coverage certification is not claimed.", "state": self.state()}

    def reports(self) -> dict:
        rows = self.store.rows("SELECT id,symbol,title,status,created_at FROM reports ORDER BY created_at DESC")
        return {"items": [dict(row, url="/api/reports/" + row["id"]) for row in rows]}

    def report(self, report_id: str) -> dict:
        rows = self.store.rows("SELECT * FROM reports WHERE id=?", (report_id,))
        if not rows:
            raise ValueError("Research brief not found")
        result = rows[0]
        result["snapshot"] = decode(result.pop("snapshot_json"))
        return result

    def forecast_observation(self, cohort_id: str, observed: float, observed_at: str) -> dict:
        if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed):
            raise ValueError("Observation must be finite")
        stamp = aware(observed_at)
        if stamp > datetime.now(timezone.utc):
            raise ValueError("An observation cannot be recorded from the future")
        with self.store.connect(write=True) as connection:
            row = connection.execute("SELECT * FROM forecasts WHERE id=?", (cohort_id,)).fetchone()
            if not row or row["observed"] is not None:
                raise ValueError("Unknown or already evaluated forecast cohort")
            if stamp < aware(row["frozen_at"]):
                raise ValueError("An observation cannot precede the frozen prediction")
            horizon_end = aware(row["horizon"] + "T00:00:00+00:00")
            if stamp < horizon_end:
                raise ValueError("The forecast horizon has not ended")
            connection.execute("UPDATE forecasts SET observed=?,observed_at=? WHERE id=?", (observed, stamp.astimezone(timezone.utc).isoformat(), cohort_id))
        return {"predicted": row["predicted"], "observed": observed, "error": observed-row["predicted"],
                "error_pct": (observed-row["predicted"])/abs(row["predicted"])*100 if row["predicted"] else None}

    def assistant_packet(self, symbol: str) -> dict:
        company = self.company(symbol)
        # Allowlisted research fields. No workspace settings, account fields or raw runtime state.
        return {"type": "thesisledger_research_packet/v1", "research_only": True,
                "human_decision": "pending", "synthetic": company["synthetic"],
                "identity": {key: company.get(key) for key in ("symbol", "name", "sector", "archetype", "as_of")},
                "thesis": company["thesis"], "evidence": company["evidence"], "assumptions": company["assumptions"],
                "valuation": company["valuation"], "technical": company["technical"],
                "questions": ["Which decisive assumption has the weakest evidence?", "What could invalidate this thesis?", "Is growth paying for required capital and dilution?"]}
