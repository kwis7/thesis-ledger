"""Synthetic evidence episodes and explicit, bounded model-update proposals."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def fingerprint(event: dict[str, Any]) -> str:
    # Source identity, publication time and changed facts survive different headlines.
    canonical = {
        "symbol": event.get("symbol"), "source_document": event.get("source_document"),
        "published_at": event.get("published_at"),
        "changes": [{"parameter": item.get("parameter"), "new": item.get("new")} for item in event.get("changes", [])],
        "evidence_ids": sorted(event.get("evidence_ids", [])), "kind": event.get("kind"),
    }
    if event.get("kind") == "baseline_refresh":
        canonical["proposed_company"] = event.get("proposed_company")
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, allow_nan=False).encode()).hexdigest()


def replay_events() -> list[dict[str, Any]]:
    return [
        {
            "id": "aster-qualification-delay", "symbol": "ASTER", "kind": "driver_change",
            "title": "Customer qualification is taking longer",
            "summary": "The synthetic quarterly update lowers qualified utilization. Demand has not disappeared, but the ramp takes longer and cash conversion changes.",
            "source": "Synthetic quarterly operating update", "source_document": "aster-q2-qualification",
            "published_at": "2026-07-15T14:00:00+00:00", "decision_ts": "2026-07-15T16:00:00+00:00",
            "verified": True, "evidence_ids": ["ASTER-EVENT-01"],
            "changes": [{"parameter": "qualified_utilization", "new": 0.66,
                         "reason": "Only customer-qualified productive capacity can become recognized shipments."}],
            "evidence": [{"id": "ASTER-EVENT-01", "title": "Qualified utilization update", "source": "Synthetic fixture", "source_type": "synthetic", "url": "fixture://aster/qualification-update", "published_at": "2026-07-15T14:00:00+00:00", "retrieved_at": "2026-07-15T15:00:00+00:00", "usable_at": "2026-07-15T15:00:00+00:00", "period": "2026-Q2", "unit": "ratio", "currency": "USD", "locator": "Operating update / qualification table", "content": "Qualified utilization is 0.66 in the fictional scenario.", "classification": "confirmed_fact", "verified": True}],
        },
        {
            "id": "beacon-conflicting-retention", "symbol": "BCN", "kind": "ambiguous_evidence",
            "title": "Two retention reports need reconciliation",
            "summary": "A synthetic customer survey and a company update use different retention definitions. No numerical assumption should change until the definitions reconcile.",
            "source": "Synthetic conflicting-source exercise", "source_document": "beacon-retention-conflict",
            "published_at": "2026-07-16T14:00:00+00:00", "decision_ts": "2026-07-16T16:00:00+00:00",
            "verified": False, "evidence_ids": ["BCN-EVENT-01"], "changes": [],
            "evidence": [{"id": "BCN-EVENT-01", "title": "Retention definitions conflict", "source": "Synthetic fixture", "source_type": "synthetic", "url": "fixture://beacon/retention-conflict", "published_at": "2026-07-16T14:00:00+00:00", "retrieved_at": "2026-07-16T15:00:00+00:00", "usable_at": "2026-07-16T15:00:00+00:00", "period": "2026-Q2", "unit": "ratio", "currency": "USD", "locator": "Synthetic reconciliation exercise", "content": "Gross logo retention and net dollar retention are not equivalent.", "classification": "data_gap", "verified": False}],
        },
        {
            "id": "aster-source-unavailable", "symbol": "ASTER", "kind": "source_failure",
            "title": "An expected evidence source is unavailable",
            "summary": "The synthetic source outage preserves the last dated model and visibly degrades monitoring coverage. No fresh-data claim is made.",
            "source": "Synthetic source-health exercise", "source_document": "aster-source-health",
            "published_at": "2026-07-17T14:00:00+00:00", "decision_ts": "2026-07-17T16:00:00+00:00",
            "verified": True, "evidence_ids": [], "changes": [], "evidence": [],
        },
        {
            "id": "aster-source-recovered", "symbol": "ASTER", "kind": "source_recovered",
            "title": "Evidence coverage has recovered",
            "summary": "The source-health exercise is resolved. The existing financial assumptions remain unchanged until supported new company evidence arrives.",
            "source": "Synthetic source-health exercise", "source_document": "aster-source-recovery",
            "published_at": "2026-07-18T14:00:00+00:00", "decision_ts": "2026-07-18T16:00:00+00:00",
            "verified": True, "evidence_ids": [], "changes": [], "evidence": [],
        },
    ]
