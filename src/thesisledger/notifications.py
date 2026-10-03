"""Local previews and a deliberately activated, fail-closed delivery worker."""

from __future__ import annotations

import smtplib
import socket
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Callable
from zoneinfo import ZoneInfo

from .store import Store, decode


class DeliveryFailed(Exception):
    """The message is known not to have been handed off."""


class DeliveryUnknown(Exception):
    """A hand-off may have occurred. Automatic retry could send a duplicate."""


def email_preview(store: Store, alert_id: str) -> dict:
    rows = store.rows("SELECT payload FROM alerts WHERE id=?", (alert_id,))
    if not rows:
        raise ValueError("Alert not found")
    alert = decode(rows[0]["payload"])
    lines = [alert["title"], "", alert["reason"], "",
             "Company: " + alert["symbol"], "Evidence date: " + alert["occurred_at"],
             "Verification: " + alert["verification"]]
    for change in alert.get("changes", []):
        lines.append(f"{change['parameter']}: {change.get('old')} -> {change.get('new')}")
    if alert.get("candidate_value") is not None:
        lines += [f"Baseline value: ${alert['baseline_value']:.2f}/share",
                  f"Candidate value: ${alert['candidate_value']:.2f}/share",
                  "Candidate assumptions need your review before acceptance."]
    else:
        lines.append("No supported numerical value update. Inspect evidence and definitions.")
    lines += ["Evidence IDs: " + ", ".join(alert.get("evidence_ids", [])), "",
              "Research only. Review evidence and the model in your workbench."]
    return {"subject": f"[ThesisLedger] {alert['symbol']}: {alert['title']}",
            "text": "\n".join(lines), "delivery_state": "preview_only"}


def quiet_now(settings: dict, at: datetime) -> bool:
    local = at.astimezone(ZoneInfo(settings.get("timezone", "UTC")))
    start, end = settings.get("quiet_start", "22:00"), settings.get("quiet_end", "07:00")
    if start == end:
        return False
    current = local.strftime("%H:%M")
    return start <= current < end if start < end else current >= start or current < end


def deliver_pending(store: Store, sender: Callable[[dict], str], *, confirmed: bool = False,
                    limit: int = 5, at: datetime | None = None) -> dict:
    if not confirmed:
        return {"state": "disabled", "reason": "Explicit delivery activation required", "attempted": 0}
    settings = store.metadata("settings", {})
    if store.metadata("mode") != "local_workspace" or not settings.get("email_enabled") or settings.get("paused"):
        return {"state": "disabled", "reason": "Live workspace email policy is disabled", "attempted": 0}
    stamp = at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError("Delivery clock must be timezone aware")
    stamp = stamp.astimezone(timezone.utc)
    if quiet_now(settings, stamp):
        return {"state": "quiet_hours", "attempted": 0}
    counts = {"attempted": 0, "provider_accepted": 0, "failed": 0, "unknown": 0, "suppressed": 0}
    for _ in range(max(0, min(limit, 20))):
        with store.connect(write=True) as connection:
            row = connection.execute("SELECT * FROM outbox WHERE state='pending' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                break
            alert_row = connection.execute("SELECT payload FROM alerts WHERE id=?", (row["alert_id"],)).fetchone()
            alert = decode(alert_row["payload"])
            occurred = datetime.fromisoformat(alert["occurred_at"].replace("Z", "+00:00"))
            if occurred > stamp or stamp - occurred > timedelta(hours=72):
                connection.execute("UPDATE outbox SET state='suppressed',error_code='stale_event' WHERE id=?", (row["id"],))
                counts["suppressed"] += 1
                continue
            changed = connection.execute("UPDATE outbox SET state='in_flight',attempted_at=? WHERE id=? AND state='pending'",
                                         (stamp.isoformat(), row["id"])).rowcount
            if not changed:
                continue
            outbox_id, alert_id = row["id"], row["alert_id"]
        counts["attempted"] += 1
        receipt = None
        try:
            receipt = sender(email_preview(store, alert_id))
            if not isinstance(receipt, str) or not receipt:
                raise DeliveryUnknown("Missing provider receipt")
            state, error = "provider_accepted", None
        except DeliveryFailed:
            state, error = "failed", "provider_rejected"
        except Exception:
            # Unknown send failures retain their ambiguity; do not reveal exception payloads.
            state, error = "unknown", "ambiguous_delivery"
        with store.connect(write=True) as connection:
            connection.execute("UPDATE outbox SET state=?,error_code=?,receipt=?,delivered_at=? WHERE id=? AND state='in_flight'",
                               (state, error, receipt, stamp.isoformat() if state == "provider_accepted" else None, outbox_id))
        counts[state] += 1
    return {"state": "partial" if counts["failed"] or counts["unknown"] else "complete", **counts}


def mark_interrupted_unknown(store: Store, before: datetime) -> int:
    """Operator-controlled reconciliation. An old in-flight message is never requeued."""
    if before.tzinfo is None:
        raise ValueError("Recovery cutoff must be timezone aware")
    before = before.astimezone(timezone.utc)
    with store.connect(write=True) as connection:
        return connection.execute("UPDATE outbox SET state='unknown',error_code='interrupted_delivery' "
                                  "WHERE state='in_flight' AND attempted_at<?", (before.isoformat(),)).rowcount


def smtp_sender(configuration: dict, factory=smtplib.SMTP_SSL) -> Callable[[dict], str]:
    required = ("host", "port", "user", "password", "recipient")
    if any(not configuration.get(key) for key in required):
        raise ValueError("SMTP host, port, user, password and recipient must be configured")
    def send(preview: dict) -> str:
        message = EmailMessage()
        message["From"] = configuration["user"]
        message["To"] = configuration["recipient"]
        message["Subject"] = preview["subject"]
        message.set_content(preview["text"])
        try:
            client = factory(configuration["host"], int(configuration["port"]),
                             timeout=20, context=ssl.create_default_context())
            client.login(configuration["user"], configuration["password"])
        except (smtplib.SMTPException, OSError, ValueError):
            raise DeliveryFailed("SMTP connection or authentication failed") from None
        try:
            refused = client.send_message(message)
            if refused:
                raise DeliveryFailed("Recipient rejected")
            # This proves relay acceptance, not delivery to a recipient's inbox.
            return "smtp-relay-accepted"
        except DeliveryFailed:
            raise
        except (smtplib.SMTPException, OSError, socket.timeout):
            raise DeliveryUnknown("SMTP result is ambiguous") from None
        finally:
            try:
                client.quit()
            except (smtplib.SMTPException, OSError):
                pass
    return send
