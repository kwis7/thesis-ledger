import http.client
import json
import tempfile
import threading
import unittest

from thesisledger.engine import ResearchEngine
from thesisledger.server import make_server


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = ResearchEngine(self.temp.name)
        self.server = make_server(self.engine, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        data = json.dumps(body) if body is not None else None
        values = {'Content-Type': 'application/json'}
        values.update(headers or {})
        connection.request(method, path, data, values)
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def test_research_replay_review_and_accept_routes(self):
        code, _, body = self.request('GET', '/api/state')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['overview']['watched'], 3)
        code, _, body = self.request('POST', '/api/replay', {})
        self.assertEqual(code, 200)
        alert = json.loads(body)['state']['alerts'][0]
        self.assertEqual(self.request('GET', '/api/alerts/'+alert['id']+'/preview')[0], 200)
        self.assertEqual(self.request('POST', '/api/alerts/'+alert['id']+'/review', {'action': 'reviewed'})[0], 200)
        viewed = self.engine.company('ASTER')
        self.assertEqual(self.request('POST', '/api/company/ASTER/accept', {
            'event_id': viewed['candidate_event_id'], 'baseline_hash': viewed['candidate_baseline_hash'], 'candidate_hash': viewed['candidate_hash']})[0], 200)
        code, _, body = self.request('POST', '/api/research', {'symbol': 'ASTER'})
        report_id = json.loads(body)['report_id']
        self.assertEqual(self.request('GET', '/api/reports/'+report_id)[0], 200)
        self.assertEqual(self.request('GET', '/api/assistant-packet/ASTER')[0], 200)

    def test_exe_sandbox_agent_and_verified_run_routes(self):
        from thesisledger.cases import exe_company
        self.engine.import_company(exe_company())
        code, _, body = self.request("GET", "/api/company/EXE/lab")
        self.assertEqual(code, 200)
        baseline = json.loads(body)["baseline"]["base"]
        code, _, body = self.request("POST", "/api/company/EXE/lab", {"overrides": {"realized_price": 4}})
        self.assertEqual(code, 200)
        self.assertGreater(json.loads(body)["candidate"]["base"], baseline)
        self.assertEqual(self.engine.company("EXE")["assumptions"]["realized_price"], 3.5)
        code, _, body = self.request("POST", "/api/company/EXE/agent", {})
        self.assertEqual(code, 200)
        run_id = json.loads(body)["run_id"]
        self.assertEqual(self.request("GET", "/api/runs/"+run_id)[0], 200)
        code, _, body = self.request("POST", "/api/runs/"+run_id+"/replay", {})
        self.assertTrue(json.loads(body)["verified"])
        self.assertEqual(self.request("POST", "/api/company/EXE/agent", {"llm": True})[0], 400)
        self.assertEqual(self.request("POST", "/api/company/EXE/lab", {"overrides": {"realized_price": True}})[0], 400)
        self.assertEqual(len(self.engine.company("EXE")["history"]), 1)

    def test_unknown_requests_are_bounded(self):
        self.assertEqual(self.request('GET', '/api/company/UNKNOWN')[0], 400)
        self.assertEqual(self.request('GET', '/../store.py')[0], 404)
        self.assertEqual(self.request('GET', '/%2e%2e/engine.py')[0], 404)
        self.assertEqual(self.request('POST', '/api/settings', {'paused': 'yes'})[0], 400)
        self.assertEqual(self.request('POST', '/api/import', {'symbol': 'A'})[0], 400)

    def test_malformed_financial_objects_return_input_error(self):
        from thesisledger.cases import exe_company
        for key in ("financials", "assumptions", "balance_sheet_bridge"):
            company = exe_company()
            company[key] = None
            self.assertEqual(self.request("POST", "/api/import", company)[0], 400)
        self.assertFalse(any(company["symbol"] == "EXE" for company in self.engine.state()["companies"]))

    def test_cross_origin_write_and_host_rebinding_rejected(self):
        self.assertEqual(self.request('POST', '/api/replay', {}, {'Origin': 'https://other.invalid'})[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Host': 'other.invalid'})[0], 403)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'other.invalid'})[0], 403)
        self.assertEqual(len(self.engine.state()['events']), 0)

    def test_nonfinite_json_and_nonobject_body_rejected(self):
        self.assertEqual(self.request('POST', '/api/settings', {'value_change_threshold_pct': float('nan')})[0], 400)
        self.assertEqual(self.request('POST', '/api/replay', [1])[0], 400)

    def test_static_security_headers(self):
        code, headers, _ = self.request('GET', '/')
        self.assertEqual(code, 200)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_token_auth_and_nonloopback_policy(self):
        with self.assertRaises(ValueError):
            make_server(self.engine, host='0.0.0.0', port=0)
        authenticated = make_server(self.engine, port=0, token='test-token')
        thread = threading.Thread(target=authenticated.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        try:
            for authorization, expected in (('', 401), ('Bearer wrong', 401), ('Bearer test-token', 200)):
                connection = http.client.HTTPConnection('127.0.0.1', authenticated.server_port, timeout=5)
                connection.request('GET', '/api/state', headers={'Authorization': authorization})
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
                connection.close()
        finally:
            authenticated.shutdown()
            authenticated.server_close()
            thread.join(3)

    def test_explicit_https_proxy_origin_still_requires_authentication(self):
        with self.assertRaises(ValueError):
            make_server(self.engine, port=0, public_origin='https://desk.example.invalid')
        with self.assertRaises(ValueError):
            make_server(self.engine, port=0, token='test', public_origin='http://desk.example.invalid')
        server = make_server(self.engine, port=0, token='test', public_origin='https://desk.example.invalid')
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        try:
            for origin, expected in (('https://desk.example.invalid', 200), ('https://other.example.invalid', 403)):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                connection.request('POST', '/api/settings', '{}', {'Content-Type': 'application/json', 'Origin': origin, 'Authorization': 'Bearer test'})
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


if __name__ == '__main__':
    unittest.main()
