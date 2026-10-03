import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from thesisledger.engine import ResearchEngine
from thesisledger.events import replay_events
from thesisledger.fixtures import build_demo_companies
from thesisledger.store import decode, encode
from thesisledger.cli import scan_events
from thesisledger.reports import digest_report


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = ResearchEngine(self.temp.name)

    def accept(self):
        company = self.engine.company('ASTER')
        return self.engine.accept_assumptions('ASTER', company['candidate_event_id'], company['candidate_baseline_hash'], company['candidate_hash'])

    def test_baseline_has_no_alert_or_certification(self):
        state = self.engine.state()
        self.assertEqual(state['overview']['watched'], 3)
        self.assertEqual(state['alerts'], [])
        self.assertTrue(state['meta']['synthetic'])
        self.assertEqual(self.engine.company('HBR')['valuation']['state'], 'unavailable')

    def test_candidate_review_and_accept_are_separate(self):
        baseline = self.engine.company('ASTER')
        result = self.engine.replay()
        alert = result['state']['alerts'][0]
        self.assertLess(alert['value_delta_pct'], -20)
        self.engine.review_alert(alert['id'], 'reviewed')
        self.assertEqual(self.engine.company('ASTER')['assumptions'], baseline['assumptions'])
        candidate = self.engine.company('ASTER')['candidate_valuation']['base']
        self.accept()
        updated = self.engine.company('ASTER')
        self.assertAlmostEqual(candidate, updated['valuation']['base'])
        self.assertEqual(len(updated['history']), 2)
        self.assertEqual(len(updated['forecast_cohorts']), 10)
        self.assertEqual(updated['history'][1]['company']['assumptions'], baseline['assumptions'])
        recovered = ResearchEngine(self.temp.name, demo=False)
        self.assertEqual(recovered.company('ASTER')['assumptions'], updated['assumptions'])
        self.assertEqual(recovered.store.metadata('mode'), 'synthetic_replay')
        with self.assertRaises(ValueError):
            recovered.accept_assumptions('ASTER', 'expired', 'expired', 'expired')

    def test_fingerprint_ignores_reworded_headline_and_new_id(self):
        event = replay_events()[0]
        self.engine.ingest_event(event)
        self.accept()
        event['id'] = 'same-evidence-new-headline'
        event['title'] = 'A differently worded headline'
        result = self.engine.ingest_event(event)
        self.assertTrue(result['duplicate'])
        self.assertEqual(len(result['state']['alerts']), 1)

    def test_future_evidence_rejected_without_partial_persistence(self):
        event = replay_events()[0]
        event['evidence'][0]['usable_at'] = '2026-07-16T17:00:00+00:00'
        with self.assertRaises(ValueError):
            self.engine.ingest_event(event)
        self.assertEqual(self.engine.state()['events'], [])
        self.assertEqual(self.engine.state()['alerts'], [])

    def test_ambiguous_definitions_do_not_change_model(self):
        base = self.engine.company('BCN')['valuation']['base']
        result = self.engine.ingest_event(replay_events()[1])
        self.assertEqual(result['state']['alerts'][0]['verification'], 'needs_verification')
        self.assertIsNone(result['state']['alerts'][0]['candidate_value'])
        self.assertEqual(self.engine.company('BCN')['valuation']['base'], base)
        with self.assertRaises(ValueError):
            self.engine.accept_assumptions('BCN', 'unverified', 'unverified', 'unverified')

    def test_minor_change_does_not_create_alert(self):
        event = replay_events()[0]
        event['changes'][0]['new'] = 0.7599
        result = self.engine.ingest_event(event)
        self.assertEqual(result['alerts_created'], 0)
        self.assertEqual(self.engine.company('ASTER')['thesis_status'], 'unchanged')

    def test_pause_does_not_consume_event(self):
        self.engine.update_settings({'paused': True})
        self.assertEqual(self.engine.replay()['status'], 'paused')
        self.assertEqual(self.engine.state()['events'], [])
        self.engine.update_settings({'paused': False})
        self.assertEqual(self.engine.replay()['alerts_created'], 1)

    def test_source_failure_and_recovery_preserve_dated_value(self):
        value = self.engine.company('ASTER')['valuation']['base']
        result = self.engine.ingest_event(replay_events()[2])
        self.assertEqual(result['state']['overview']['status'], 'data_pending')
        self.assertEqual(self.engine.company('ASTER')['valuation']['base'], value)
        result = self.engine.ingest_event(replay_events()[3])
        self.assertEqual(result['state']['overview']['data_gaps'], 0)
        self.assertEqual(result['alerts_created'], 0)

    def test_local_workspace_import_rejects_private_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            packet = build_demo_companies()[0]
            packet['nested'] = {'account_number': 'invented-for-test'}
            with self.assertRaises(ValueError):
                engine.import_company(packet)
            self.assertEqual(engine.state()['companies'], [])
            packet.pop('nested')
            engine.import_company(packet)
            with self.assertRaises(ValueError):
                engine.import_company(packet)

    def test_malformed_research_text_rejected_before_persistence(self):
        invalid_fields = [
            (('thesis',), 'malformed synthetic thesis'),
            (('thesis',), None),
            (('thesis', 'statement'), {}),
            (('thesis', 'drivers'), 'not a list'),
            (('thesis', 'drivers'), [None]),
            (('thesis', 'drivers'), [{'evidence_ids': 'not a list'}]),
            (('thesis', 'drivers'), [{'evidence_ids': [7]}]),
            (('thesis', 'counterevidence'), None),
            (('thesis', 'counterevidence'), [7]),
            (('thesis', 'falsifiers'), {}),
            (('description',), ['not text']),
            (('name',), None),
        ]
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            for path, value in invalid_fields:
                with self.subTest(path=path, value=value):
                    packet = build_demo_companies()[0]
                    target = packet
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = value
                    with self.assertRaises(ValueError):
                        engine.import_company(packet)
                    for table in ('companies', 'revisions', 'forecasts', 'reports'):
                        count = engine.store.rows(f'SELECT COUNT(*) AS total FROM {table}')[0]['total']
                        self.assertEqual(count, 0, table)
            engine.import_company(build_demo_companies()[0])
            report = engine.research('ASTER')
            self.assertIn('Operating assumptions', engine.report(report['report_id'])['markdown'])

    def test_missing_optional_thesis_details_remain_visible_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchEngine(directory, demo=False)
            packet = build_demo_companies()[0]
            packet['thesis'] = {'next_review': {'condition': 'Review the next public filing'}}
            engine.import_company(packet)
            report = engine.research('ASTER')
            self.assertIn('Thesis not recorded', engine.report(report['report_id'])['markdown'])

    def test_unmonitored_company_records_evidence_without_alert(self):
        self.engine.update_watchlist('ASTER', 'observe', False)
        result = self.engine.replay()
        self.assertEqual(result['alerts_created'], 0)
        self.assertEqual(len(result['state']['events']), 1)

    def test_settings_reject_invalid_values(self):
        for patch in ({'quiet_start': '24:00'}, {'timezone': 'unknown/zone'}, {'cooldown_hours': -1},
                      {'value_change_threshold_pct': float('nan')}, {'paused': 'false'}, {'unknown': 1}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.engine.update_settings(patch)

    def test_research_and_allowlisted_agent_packet(self):
        result = self.engine.research('ASTER')
        report = self.engine.report(result['report_id'])
        self.assertIn('Synthetic example', report['markdown'])
        self.assertIn('Free cash flow', report['markdown'])
        self.assertEqual(report['status'], 'bounded_research')
        self.engine.research('ASTER')
        self.assertEqual(len(self.engine.reports()['items']), 1)
        packet = self.engine.assistant_packet('ASTER')
        self.assertTrue(packet['research_only'])
        self.assertNotIn('settings', packet)
        self.assertNotIn('workspace', packet)

    def test_directory_monitor_is_idempotent_and_keeps_failures(self):
        directory = Path(self.temp.name) / 'incoming'
        directory.mkdir()
        (directory / 'a.json').write_text(encode(replay_events()[0]))
        (directory / 'bad.json').write_text('{bad')
        first = scan_events(self.engine, directory)
        second = scan_events(self.engine, directory)
        self.assertEqual(first['rejected'], 1)
        self.assertEqual(second['files'][0]['status'], 'duplicate')
        self.assertEqual(len(self.engine.state()['alerts']), 1)
        self.assertTrue((directory / 'bad.json').exists())

    def test_replay_last_checked_does_not_regress(self):
        self.engine.ingest_event(replay_events()[2])
        before = self.engine.state()['overview']['last_checked']
        self.engine.ingest_event(replay_events()[0])
        self.assertEqual(self.engine.state()['overview']['last_checked'], before)

    def test_source_health_cannot_regress(self):
        self.engine.ingest_event(replay_events()[3])
        result = self.engine.ingest_event(replay_events()[2])
        self.assertEqual(self.engine.company('ASTER')['data_status'], 'fresh')
        self.assertEqual(result['alerts_created'], 0)

    def test_verification_requires_boolean_and_referenced_sources(self):
        event = replay_events()[0]
        event['verified'] = 'false'
        with self.assertRaises(ValueError):
            self.engine.ingest_event(event)
        event['verified'] = True
        event['evidence_ids'] = []
        result = self.engine.ingest_event(event)
        self.assertEqual(result['state']['alerts'][0]['verification'], 'needs_verification')
        self.assertIsNone(self.engine.company('ASTER')['candidate_valuation'])

    def test_future_events_and_technical_bars_rejected(self):
        event = replay_events()[3]
        event['decision_ts'] = '2035-01-01T16:00:00+00:00'
        event['published_at'] = '2035-01-01T14:00:00+00:00'
        with self.assertRaises(ValueError):
            self.engine.ingest_event(event)
        packet = build_demo_companies()[0]
        packet['symbol'] = 'NEW'
        packet['prices'].append({'date': '2035-01-01', 'close': 33, 'volume': 300})
        with self.assertRaises(ValueError):
            self.engine.import_company(packet)

    def test_accept_requires_exact_reviewed_proposal(self):
        self.engine.ingest_event(replay_events()[0])
        viewed = self.engine.company('ASTER')
        newer = replay_events()[0]
        newer['id'] = 'aster-newer-proposal'
        newer['source_document'] = 'aster-q2-revision'
        newer['decision_ts'] = '2026-07-15T17:00:00+00:00'
        newer['changes'][0]['new'] = 0.70
        self.engine.ingest_event(newer)
        with self.assertRaises(ValueError):
            self.engine.accept_assumptions('ASTER', viewed['candidate_event_id'], viewed['candidate_baseline_hash'], viewed['candidate_hash'])
        self.assertEqual(self.engine.company('ASTER')['assumptions']['qualified_utilization'], 0.76)

    def test_concurrent_imports_create_one_baseline(self):
        from concurrent.futures import ThreadPoolExecutor
        packet = build_demo_companies()[0]
        packet['symbol'] = 'NEW'
        def attempt(_):
            try:
                self.engine.import_company(copy.deepcopy(packet))
                return 'inserted'
            except ValueError:
                return 'rejected'
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(attempt, range(4)))
        self.assertEqual(outcomes.count('inserted'), 1)
        self.assertEqual(len(self.engine.company('NEW')['history']), 1)

    def test_reused_id_with_different_facts_is_rejected(self):
        self.engine.replay()
        event = replay_events()[0]
        event['changes'][0]['new'] = 0.70
        with self.assertRaises(ValueError):
            self.engine.ingest_event(event)

    def test_digest_distinguishes_recent_and_overdue_open_items(self):
        for event in replay_events():
            self.engine.ingest_event(event)
        daily = digest_report(self.engine.state())
        weekly = digest_report(self.engine.state(), period='weekly')
        self.assertEqual(len(daily['items']), 0)
        self.assertEqual(len(daily['overdue_items']), 3)
        self.assertEqual(len(weekly['items']), 3)
        self.assertEqual(weekly['overdue_items'], [])

    def test_forecast_observations_require_elapsed_horizon(self):
        cohort = self.engine.company('ASTER')['forecast_cohorts'][0]
        with self.assertRaises(ValueError):
            self.engine.forecast_observation(cohort['id'], 100, datetime.now(timezone.utc).isoformat())
        with self.assertRaises(ValueError):
            self.engine.forecast_observation(cohort['id'], 100, '2035-01-01T00:00:00+00:00')

    def test_utc_offsets_order_candidates_by_instant(self):
        self.engine.replay()
        later = replay_events()[0]
        later['id'] = 'aster-offset-proposal'
        later['source_document'] = 'aster-offset-source'
        later['decision_ts'] = '2026-07-15T12:00:00-05:00'
        later['changes'][0]['new'] = 0.70
        self.engine.ingest_event(later)
        self.assertEqual(self.engine.company('ASTER')['candidate_event_id'], later['id'])
        self.assertEqual(self.engine.company('ASTER')['candidate_changes'][0]['new'], 0.70)

    def test_unverified_source_recovery_preserves_gap(self):
        self.engine.ingest_event(replay_events()[2])
        event = replay_events()[3]
        event['verified'] = False
        result = self.engine.ingest_event(event)
        self.assertEqual(self.engine.company('ASTER')['data_status'], 'stale')
        self.assertEqual(result['state']['overview']['data_gaps'], 1)
        self.assertEqual(result['alerts_created'], 1)

    def test_elapsed_forecast_observation_preserves_prediction(self):
        cohort = self.engine.company('ASTER')['forecast_cohorts'][0]
        with self.engine.store.connect(write=True) as connection:
            connection.execute("UPDATE forecasts SET frozen_at='2024-01-01T00:00:00+00:00',horizon='2025-01-01' WHERE id=?", (cohort['id'],))
        result = self.engine.forecast_observation(cohort['id'], cohort['predicted']*0.9, '2025-01-02T00:00:00+00:00')
        self.assertAlmostEqual(result['error_pct'], -10)
        self.assertEqual(self.engine.store.rows('SELECT predicted FROM forecasts WHERE id=?', (cohort['id'],))[0]['predicted'], cohort['predicted'])
        with self.assertRaises(ValueError):
            self.engine.forecast_observation(cohort['id'], 999, '2025-01-03T00:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
