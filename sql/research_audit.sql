-- Run against your own workspace SQLite database. All queries are read-only.
-- Accepted thesis version and the event that produced it.
SELECT symbol, version, reason, event_id, created_at, input_hash
FROM revisions ORDER BY symbol, version;

-- Unreviewed alerts, independently from external delivery state.
SELECT a.symbol, a.id, a.review_state, a.delivery_state,
       json_extract(a.payload, '$.verification') AS verification,
       json_extract(a.payload, '$.value_delta_pct') AS candidate_delta_pct,
       o.state AS outbox_state, o.attempted_at, o.delivered_at, o.error_code
FROM alerts a LEFT JOIN outbox o ON o.alert_id = a.id
WHERE a.review_state != 'reviewed' ORDER BY a.created_at;

-- Historical event deduplication and current review stage.
SELECT symbol, id, fingerprint, state, decision_ts, replay_count
FROM source_events ORDER BY decision_ts;

-- Frozen forecasts with later user-supplied observations.
SELECT symbol, revision_id, horizon, metric, predicted, frozen_at,
       observed, observed_at,
       CASE WHEN observed IS NOT NULL THEN observed - predicted END AS error
FROM forecasts ORDER BY symbol, revision_id, horizon;
