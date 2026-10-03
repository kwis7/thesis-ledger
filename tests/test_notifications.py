from datetime import datetime, timedelta, timezone
import tempfile
import unittest

from thesisledger.engine import ResearchEngine
from thesisledger.events import replay_events
from thesisledger.fixtures import build_demo_companies
from thesisledger.notifications import (DeliveryFailed, deliver_pending, email_preview,
                                        mark_interrupted_unknown, quiet_now, smtp_sender)


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = ResearchEngine(self.temp.name, demo=False)
        self.engine.import_company(build_demo_companies()[0])
        self.engine.update_settings({'email_enabled': True})
        self.engine.ingest_event(replay_events()[0])
        self.clock = datetime(2026, 7, 15, 16, tzinfo=timezone.utc)

    def test_preview_and_default_worker_never_send(self):
        calls = []
        alert = self.engine.state()['alerts'][0]
        self.assertEqual(email_preview(self.engine.store, alert['id'])['delivery_state'], 'preview_only')
        result = deliver_pending(self.engine.store, lambda packet: calls.append(packet), at=self.clock)
        self.assertEqual(result['attempted'], 0)
        self.assertEqual(calls, [])

    def test_mock_relay_acceptance_is_not_inbox_delivery(self):
        calls = []
        def sender(packet):
            calls.append(packet)
            return 'mock-receipt'
        result = deliver_pending(self.engine.store, sender, confirmed=True, at=self.clock)
        self.assertEqual(result['provider_accepted'], 1)
        again = deliver_pending(self.engine.store, sender, confirmed=True, at=self.clock)
        self.assertEqual(again['attempted'], 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.engine.store.rows('SELECT state FROM outbox')[0]['state'], 'provider_accepted')

    def test_unknown_send_is_not_retried_and_error_payload_is_not_stored(self):
        def sender(packet):
            raise TimeoutError('secret-like-payload-never-store')
        result = deliver_pending(self.engine.store, sender, confirmed=True, at=self.clock)
        self.assertEqual(result['unknown'], 1)
        self.assertEqual(deliver_pending(self.engine.store, sender, confirmed=True, at=self.clock)['attempted'], 0)
        row = self.engine.store.rows('SELECT * FROM outbox')[0]
        self.assertEqual(row['error_code'], 'ambiguous_delivery')
        self.assertNotIn('secret-like', str(row))

    def test_known_rejection_and_stale_event(self):
        def sender(packet):
            raise DeliveryFailed('known rejection')
        self.assertEqual(deliver_pending(self.engine.store, sender, confirmed=True, at=self.clock)['failed'], 1)
        with self.engine.store.connect(write=True) as connection:
            connection.execute("UPDATE outbox SET state='pending'")
        result = deliver_pending(self.engine.store, sender, confirmed=True, at=self.clock+timedelta(days=4))
        self.assertEqual(result['suppressed'], 1)
        self.assertEqual(result['attempted'], 0)

    def test_quiet_hours_use_timezone_and_wrap_midnight(self):
        settings = {'timezone': 'America/Chicago', 'quiet_start': '22:00', 'quiet_end': '07:00'}
        self.assertTrue(quiet_now(settings, datetime(2026, 7, 16, 5, tzinfo=timezone.utc)))
        self.assertFalse(quiet_now(settings, self.clock))
        result = deliver_pending(self.engine.store, lambda _: self.fail('must stay quiet'), confirmed=True,
                                 at=datetime(2026, 7, 15, 23, tzinfo=timezone.utc))
        self.assertEqual(result['state'], 'quiet_hours')

    def test_interrupted_claim_stays_unknown(self):
        with self.engine.store.connect(write=True) as connection:
            connection.execute("UPDATE outbox SET state='in_flight',attempted_at=?", (self.clock.isoformat(),))
        self.assertEqual(mark_interrupted_unknown(self.engine.store, self.clock+timedelta(minutes=5)), 1)
        self.assertEqual(deliver_pending(self.engine.store, lambda _: self.fail('must not retry'), confirmed=True, at=self.clock)['attempted'], 0)

    def test_demo_never_queues_external_email(self):
        with tempfile.TemporaryDirectory() as directory:
            demo = ResearchEngine(directory)
            demo.update_settings({'email_enabled': True})
            demo.replay()
            self.assertEqual(demo.store.rows('SELECT * FROM outbox'), [])
            self.assertEqual(deliver_pending(demo.store, lambda _: self.fail('must not send'), confirmed=True, at=self.clock)['attempted'], 0)

    def test_smtp_adapter_with_mock_transport(self):
        calls = []
        class MockSMTP:
            def __init__(self, host, port, **kwargs):
                calls.append('connect')
            def login(self, user, password):
                calls.append('login')
            def send_message(self, message):
                calls.append('send')
                return {}
            def quit(self):
                calls.append('quit')
        sender = smtp_sender(dict(host='mock.invalid', port=465, user='sender@example.invalid', password='mock', recipient='reader@example.invalid'), factory=MockSMTP)
        self.assertEqual(sender({'subject': 'test', 'text': 'synthetic'}), 'smtp-relay-accepted')
        self.assertEqual(calls, ['connect', 'login', 'send', 'quit'])

    def test_reconcile_cutoff_with_offset_compares_utc_instants(self):
        with self.engine.store.connect(write=True) as connection:
            connection.execute("UPDATE outbox SET state='in_flight',attempted_at='2026-07-15T18:00:00+00:00'")
        self.assertEqual(mark_interrupted_unknown(self.engine.store, datetime.fromisoformat('2026-07-15T14:00:00-05:00')), 1)


if __name__ == '__main__':
    unittest.main()
