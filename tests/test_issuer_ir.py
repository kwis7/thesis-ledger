"""Official issuer fallback boundaries; no provider requests or notifications."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from thesisledger import issuer_ir as ir, sec
from thesisledger.cases import exe_company
from thesisledger.engine import ResearchEngine
from thesisledger.ir_monitor import check_exe_ir
from thesisledger.sec_monitor import check_exe_filings

ROOT=Path(__file__).resolve().parents[1]
ANNUAL=(ROOT/'examples/ir/annual-excerpt.html').read_text()
QUARTERLY=(ROOT/'examples/ir/quarterly-excerpt.html').read_text()
CUTOFF='2026-10-03T05:00:00Z'
LATEST='0000895126-26-000047'


class IssuerParserTests(unittest.TestCase):
    def test_real_excerpt_filters_ars_and_preserves_unknown_report_period(self):
        rows=ir.parse_exe_filings(ANNUAL,CUTOFF)
        self.assertEqual(rows[0]['form'],'10-K')
        self.assertEqual(rows[0]['accessionNumber'],'0000895126-26-000011')
        self.assertTrue(any(row['form']=='10-K/A' for row in rows))
        latest=ir.parse_exe_filings(QUARTERLY,CUTOFF)[0]
        self.assertEqual(latest['accessionNumber'],LATEST)
        self.assertEqual(latest['filingDate'],'2026-07-28')
        self.assertIsNone(latest['reportDate'])

    def test_wrong_issuer_or_lost_table_is_not_success(self):
        for value in (QUARTERLY.replace('Expand Energy','Other Company'), QUARTERLY.replace(ir.DATE_CELL,'wrong').replace(ir.FORM_CELL,'wrong'), '<html>Access denied</html>'):
            with self.assertRaises(ir.IRError):ir.parse_exe_filings(value,CUTOFF)

    def test_form_path_and_foreign_links_reject(self):
        for value in ('https://evil.test/sec-filings/sec-filing/10-q/'+LATEST,
                      '//evil.test/sec-filings/sec-filing/10-q/'+LATEST,
                      '/sec-filings/sec-filing/10-k/'+LATEST,
                      '/sec-filings/sec-filing/10-q/'+LATEST+'?private=1'):
            html=QUARTERLY.replace('/sec-filings/sec-filing/10-q/'+LATEST,value)
            with self.assertRaises(ir.IRError):ir.parse_exe_filings(html,CUTOFF)

    def test_malformed_date_timestamp_and_accession_reject(self):
        for html in (QUARTERLY.replace('Jul 28, 2026','Jul 32, 2026'),QUARTERLY.replace('2026-07-28T04:00:00Z','2026-07-29T04:00:00Z'),QUARTERLY.replace('2026-07-28T04:00:00Z','2026-07-28broken'),QUARTERLY.replace(LATEST,'bad-accession'),QUARTERLY.replace(LATEST,LATEST.replace('-26-','-25-'))):
            with self.assertRaises(ir.IRError):ir.parse_exe_filings(html,CUTOFF)

    def test_date_only_metadata_obeys_next_eastern_midnight(self):
        early=ir.parse_exe_filings(QUARTERLY,'2026-07-29T03:59:59Z')
        late=ir.parse_exe_filings(QUARTERLY,sec.public_available_at('2026-07-28'))
        self.assertNotIn(LATEST,[row['accessionNumber'] for row in early])
        self.assertEqual(late[0]['accessionNumber'],LATEST)

    def test_conflicting_duplicate_rejects_and_equal_duplicate_collapses(self):
        row=QUARTERLY.split('<tr>',1)[1].split('</tr>',1)[0]
        equal=QUARTERLY.replace('</tbody>','<tr>'+row+'</tr></tbody>')
        self.assertEqual(len(ir.parse_exe_filings(equal,CUTOFF)),len(ir.parse_exe_filings(QUARTERLY,CUTOFF)))
        changed=row.replace('Jul 28, 2026','Jul 29, 2026').replace('2026-07-28T04:00:00Z','2026-07-29T04:00:00Z')
        with self.assertRaises(ir.IRError):ir.parse_exe_filings(QUARTERLY.replace('</tbody>','<tr>'+changed+'</tr></tbody>'),CUTOFF)

    def test_unbounded_html_and_rows_reject(self):
        with self.assertRaises(ir.IRError):ir.parse_exe_filings('x'*(ir.MAX_IR_BYTES+1),CUTOFF)
        with patch.object(ir,'MAX_ROWS',1),self.assertRaises(ir.IRError):ir.parse_exe_filings(QUARTERLY,CUTOFF)

    def test_nested_table_cannot_supply_official_filing_cells(self):
        nested=QUARTERLY.replace('<tbody>', '<tbody><tr><td><table><tbody>', 1).replace('</tbody>', '</tbody></table></td></tr></tbody>', 1)
        with self.assertRaises(ir.IRError):ir.parse_exe_filings(nested,CUTOFF)


class IssuerCollectorTests(unittest.TestCase):
    def fake(self,url):
        text='User-agent: *\nAllow: /\n' if url==ir.IR_ROBOTS else ANNUAL if url==ir.IR_URLS[0] else QUARTERLY
        raw=text.encode();return text,raw,{'url':url,'retrieved_at':'2026-10-03T04:31:00+00:00','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'http_status':200,'headers':{}}

    def test_three_fixed_requests_hashes_and_correct_raw_extensions(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(ir,'_fetch',side_effect=self.fake) as fetch,patch.object(ir.time,'sleep'):
            result=ir.collect_exe_filings(directory,CUTOFF)
            self.assertEqual([call.args[0] for call in fetch.call_args_list],[ir.IR_ROBOTS,*ir.IR_URLS])
            self.assertEqual(result['filings'][0]['accessionNumber'],LATEST)
            self.assertEqual(result['sources'][0]['cache_path'][-4:],'.txt')
            for source in result['sources']:
                self.assertEqual(hashlib.sha256(Path(source['cache_path']).read_bytes()).hexdigest(),source['sha256'])
            self.assertTrue(result['sources'][1]['cache_path'].endswith('.html'))

    def test_robots_refusal_and_unvalidated_policy_stop_before_listing(self):
        for robots in ('User-agent: *\nDisallow: /financial-information/\n','<html>Forbidden</html>'):
            def refused(url):
                text,raw,metadata=self.fake(url);return robots,robots.encode(),metadata
            with tempfile.TemporaryDirectory() as directory,patch.object(ir,'_fetch',side_effect=refused) as fetch:
                with self.assertRaises(ir.IRError):ir.collect_exe_filings(directory,CUTOFF)
                self.assertEqual(fetch.call_count,1)

    def test_crawl_delay_honored_and_long_policy_stops(self):
        for delay in (3,70):
            def delayed(url):
                text,raw,metadata=self.fake(url)
                if url==ir.IR_ROBOTS:text=f'User-agent: *\nCrawl-delay: {delay}\nAllow: /\n';raw=text.encode();metadata['sha256']=hashlib.sha256(raw).hexdigest()
                return text,raw,metadata
            with tempfile.TemporaryDirectory() as directory,patch.object(ir,'_fetch',side_effect=delayed),patch.object(ir.time,'sleep') as sleep:
                if delay>60:
                    with self.assertRaises(ir.IRError):ir.collect_exe_filings(directory,CUTOFF)
                    sleep.assert_not_called()
                else:
                    ir.collect_exe_filings(directory,CUTOFF)
                    self.assertEqual([call.args[0] for call in sleep.call_args_list],[3,3])

    def test_budget_includes_html_without_pruning(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(ir,'_fetch',side_effect=self.fake),patch.object(ir.time,'sleep'),patch.object(sec,'MAX_CACHE_BYTES',10):
            keep=Path(directory)/'sec-old.html';keep.write_bytes(b'x'*9)
            with self.assertRaises(ir.IRError):ir.collect_exe_filings(directory,CUTOFF)
            self.assertEqual(keep.read_bytes(),b'x'*9)

    def test_redirect_and_non_allowlisted_endpoints_stop(self):
        with patch.object(ir.request,'build_opener') as opener:
            for url in ('http://127.0.0.1','https://investors.expandenergy.com.evil.test/robots.txt',ir.IR_LISTING):
                with self.assertRaises(ir.IRError):ir._fetch(url)
            opener.assert_not_called()
        with self.assertRaises(ir.IRError):ir._NoRedirect().redirect_request(None,None,302,'redirect',{},'https://evil.test/')

    def test_transport_errors_do_not_echo_arbitrary_text(self):
        failure=HTTPError(ir.IR_ROBOTS,403,'private-contact',{},io.BytesIO(b'private-contact'))
        with patch.object(ir.request,'build_opener') as opener:
            opener.return_value.open.side_effect=failure
            with self.assertRaises(ir.IRError) as caught:ir._fetch(ir.IR_ROBOTS)
            self.assertNotIn('private-contact',str(caught.exception))

    def test_response_type_byte_limit_and_encoding_fail_closed(self):
        class Response:
            status=200
            def __init__(self,media,raw):self.headers={'Content-Type':media};self.raw=raw
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,bound):return self.raw[:bound]
        with patch.object(ir.request,'build_opener') as opener:
            for media,raw in [('application/json',b'{}'),('text/html',b'\xff'),('text/html',b'x'*5)]:
                opener.return_value.open.return_value=Response(media,raw)
                with patch.object(ir,'MAX_IR_BYTES',4),self.assertRaises(ir.IRError):ir._fetch(ir.IR_URLS[0])


class IssuerMonitorTests(unittest.TestCase):
    def engine(self,path):
        engine=ResearchEngine(path,demo=False);engine.import_company(exe_company());return engine

    def snapshot(self,*args):
        return {'issuer':{'cik':'0000895126'},'provider':'issuer_ir','as_of':datetime.now(timezone.utc).isoformat(),'filings':ir.parse_exe_filings(QUARTERLY,CUTOFF),'sources':[],'scope':'bounded official metadata'}

    def sec_failed(self,*args):raise sec.SECError('HTTP 403 private-contact',reason_code='undeclared_automated_tool')

    def test_live_alternative_semantics_preserve_sec_failure_and_model(self):
        with tempfile.TemporaryDirectory() as path:
            engine=self.engine(path)
            with self.assertRaises(sec.SECError):check_exe_filings(engine,'app contact',collector=self.sec_failed)
            before=engine.company('EXE');sec_status=deepcopy(engine.store.metadata('sec_monitor'))
            self.assertEqual(check_exe_ir(engine,collector=self.snapshot)['alerts_created'],1)
            self.assertEqual(check_exe_ir(engine,collector=self.snapshot)['alerts_created'],0)
            after=engine.company('EXE')
            self.assertEqual(engine.store.metadata('sec_monitor'),sec_status)
            self.assertEqual(engine.state()['meta']['ir_monitor']['status'],'available')
            self.assertEqual(after['data_status'],'stale')
            for key in ('financials','assumptions','history','forecast_cohorts','valuation'):self.assertEqual(after[key],before[key])
            self.assertEqual(len(engine.state()['alerts']),2)
            self.assertIsNone(engine.state()['meta']['ir_monitor']['latest_filing']['reportDate'])

    def test_cross_provider_accession_dedup_both_directions(self):
        for first in ('ir','sec'):
            with tempfile.TemporaryDirectory() as path:
                engine=self.engine(path)
                def official(*args):
                    snap=self.snapshot();snap['issuer']['tickers']=['EXE']
                    for row in snap['filings']:row['reportDate']='2026-06-30'
                    return snap
                checks={'ir':lambda:check_exe_ir(engine,collector=self.snapshot),'sec':lambda:check_exe_filings(engine,'app contact',collector=official)}
                self.assertEqual(checks[first]() ['alerts_created'],1)
                self.assertEqual(checks['sec' if first=='ir' else 'ir']()['alerts_created'],0)
                self.assertEqual(len(engine.state()['alerts']),1)

    def test_unverified_prior_event_does_not_suppress_official_discovery(self):
        for provider in ('ir','sec'):
            with tempfile.TemporaryDirectory() as path:
                engine=self.engine(path);now=datetime.now(timezone.utc).isoformat()
                engine.ingest_event({'id':'sec-'+LATEST.replace('-',''),'symbol':'EXE','kind':'review_due',
                    'title':'Unverified filing mention','source_document':LATEST,'published_at':now,
                    'decision_ts':now,'verified':False,'evidence':[],'evidence_ids':[],'changes':[]})
                def official(*args):
                    snap=self.snapshot();snap['issuer']['tickers']=['EXE']
                    for row in snap['filings']:row['reportDate']='2026-06-30'
                    return snap
                check=(lambda:check_exe_ir(engine,collector=self.snapshot)) if provider=='ir' else (lambda:check_exe_filings(engine,'app contact',collector=official))
                self.assertEqual(check()['alerts_created'],1)
                self.assertEqual(check()['alerts_created'],0)
                self.assertEqual(len(engine.state()['alerts']),2)
                events=engine.store.rows("SELECT payload FROM source_events WHERE id=?",('official-filing-'+LATEST.replace('-',''),))
                self.assertEqual(json.loads(events[0]['payload'])['verification'],'verified')

    def test_controlled_failure_diagnostics_preserve_status_without_private_text(self):
        with tempfile.TemporaryDirectory() as path:
            engine=self.engine(path)
            def failed(*args):raise ir.IRError('private-contact',reason_code='http_error',http_status=403)
            with self.assertRaises(ir.IRError) as caught:check_exe_ir(engine,collector=failed)
            self.assertIn('HTTP 403',str(caught.exception))
            status=engine.store.metadata('ir_monitor')
            self.assertEqual(status['error_code'],'http_error');self.assertEqual(status['http_status'],403)
            self.assertNotIn('private-contact',json.dumps(engine.state()))

    def test_paused_does_not_call_collector(self):
        with tempfile.TemporaryDirectory() as path:
            engine=self.engine(path);engine.update_settings({'paused':True})
            with patch('thesisledger.ir_monitor.collect_exe_filings'):
                def forbidden(*args):raise AssertionError('No network while paused')
                self.assertEqual(check_exe_ir(engine,collector=forbidden)['status'],'paused')
            self.assertIsNone(engine.store.metadata('ir_monitor'))

    def test_outage_deduplicates_and_recovery_is_quiet_and_separate(self):
        with tempfile.TemporaryDirectory() as path:
            engine=self.engine(path)
            def failed(*args):raise ir.IRError('private-contact failed')
            for unused in range(2):
                with self.assertRaises(ir.IRError):check_exe_ir(engine,collector=failed)
            self.assertEqual(len(engine.state()['alerts']),1)
            self.assertNotIn('private-contact',json.dumps(engine.state()))
            def known(*args):
                snap=self.snapshot();snap['filings']=ir.parse_exe_filings(ANNUAL,CUTOFF);return snap
            check_exe_ir(engine,collector=known)
            self.assertEqual(len(engine.state()['alerts']),1)
            self.assertEqual(engine.store.metadata('ir_monitor')['status'],'available')
            self.assertIsNone(engine.store.metadata('sec_monitor'))
            with self.assertRaises(ir.IRError):check_exe_ir(engine,collector=failed)
            self.assertEqual(len(engine.state()['alerts']),2)

    def test_empty_validated_source_remains_gap(self):
        with tempfile.TemporaryDirectory() as path:
            engine=self.engine(path)
            def empty(*args):
                snap=self.snapshot();snap['filings']=[];return snap
            self.assertEqual(check_exe_ir(engine,collector=empty)['status'],'data_gap')
            self.assertIsNone(engine.store.metadata('ir_monitor')['last_success_at'])
            self.assertEqual(len(engine.state()['alerts']),0)


class SECRecoveryTests(unittest.TestCase):
    def test_undeclared_error_is_classified_without_storing_body(self):
        raw=b'<title>Undeclared Automated Tool</title>private-contact'
        failure=HTTPError('https://data.sec.gov/submissions/CIK0000895126.json',403,'private-contact',{},io.BytesIO(raw))
        with patch.object(sec.request,'build_opener') as opener:
            opener.return_value.open.side_effect=failure
            with self.assertRaises(sec.SECError) as caught:sec._fetch_json(failure.url,'app private-contact')
            self.assertEqual(caught.exception.reason_code,'undeclared_automated_tool')
            self.assertNotIn('private-contact',str(caught.exception))

    def test_metadata_monitor_uses_only_submissions(self):
        data=json.loads((ROOT/'examples/sec/submissions-excerpt.json').read_text());raw=json.dumps(data).encode()
        with tempfile.TemporaryDirectory() as path,patch.object(sec,'_fetch_json',return_value=(data,raw,{'url':'https://data.sec.gov/submissions/CIK0000895126.json','retrieved_at':'2026-10-03T02:45:00Z','http_status':200,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'headers':{}})) as fetch:
            sec.collect_submissions('895126',path,'Research app public contact')
            self.assertEqual(fetch.call_count,1)
            self.assertIn('/submissions/',fetch.call_args.args[0])


if __name__=='__main__':unittest.main()
