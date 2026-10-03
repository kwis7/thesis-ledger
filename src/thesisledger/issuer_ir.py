"""Explicit, bounded EXE issuer-site filing discovery, separate from SEC JSON."""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib import error, request, robotparser
from urllib.parse import urljoin, urlsplit

from . import __version__
from .sec import SECError, _cache_snapshot, _cutoff, public_available_at

IR_ORIGIN = 'https://investors.expandenergy.com'
IR_LISTING = IR_ORIGIN+'/financial-information/sec-filings'
IR_ROBOTS = IR_ORIGIN+'/robots.txt'
IR_URLS = (IR_LISTING+'?field_nir_sec_form_group_target_id=471',
           IR_LISTING+'?field_nir_sec_form_group_target_id=496')
MAX_IR_BYTES = 2*1024*1024
MAX_ROWS = 200
IR_USER_AGENT = f'ThesisLedger/{__version__} public research https://github.com/kwis7'
DATE_CELL = 'view-field-nir-sec-date-filed-table-column'
FORM_CELL = 'view-field-nir-sec-form-table-column'
FORMS = {'10-K': '10-k', '10-K/A': '10-ka', '10-Q': '10-q', '10-Q/A': '10-qa'}


class IRError(ValueError):
    """Issuer metadata could not be safely acquired or validated."""

    def __init__(self, message, *, reason_code='validation_failed', http_status=None):
        super().__init__(message)
        self.reason_code = reason_code
        self.http_status = http_status


def failure_diagnostic(exc):
    """Persist only controlled reasons, never arbitrary exception or response text."""
    reasons = {
        'redirect_refused': 'The issuer redirected a fixed endpoint; review its configuration.',
        'network_failed': 'The issuer request failed at the network or timeout boundary.',
        'response_too_large': 'The issuer response exceeded the 2 MiB bound.',
        'content_type': 'The issuer endpoint returned an unexpected content type.',
        'encoding': 'The issuer response was not valid UTF-8.',
        'robots_invalid': 'The issuer robots policy could not be validated.',
        'robots_denied': 'The issuer robots policy disallowed the configured listing.',
        'robots_rate': 'The issuer crawl rate requires operator review.',
        'cache_failed': 'The issuer snapshot cache was invalid or exceeded its budget.',
        'validation_failed': 'Official issuer collection stopped or could not be validated.',
    }
    code = getattr(exc, 'reason_code', None)
    status = getattr(exc, 'http_status', None)
    if code == 'http_error' and type(status) is int and 100 <= status <= 599:
        return code, f'The official issuer request failed (HTTP {status}).', status
    code = code if code in reasons else 'validation_failed'
    return code, reasons[code], None


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IRError('Issuer redirect refused; review the official source configuration', reason_code='redirect_refused')


def _fetch(url):
    if url not in (IR_ROBOTS, *IR_URLS):
        raise IRError('Only the fixed official issuer listing and robots endpoints may be fetched')
    try:
        req = request.Request(url, headers={'User-Agent':IR_USER_AGENT, 'Accept':'text/html,text/plain', 'Accept-Encoding':'identity'})
        with request.build_opener(_NoRedirect()).open(req, timeout=30) as response:
            if response.status != 200:
                raise IRError('Issuer request did not return HTTP 200', reason_code='http_error', http_status=response.status)
            raw = response.read(MAX_IR_BYTES+1)
            if len(raw) > MAX_IR_BYTES:
                raise IRError('Issuer response exceeds the 2 MiB limit', reason_code='response_too_large')
            media = response.headers.get('Content-Type', '').split(';',1)[0].strip().lower()
            if media != ('text/plain' if url == IR_ROBOTS else 'text/html'):
                raise IRError('Issuer response has an unexpected content type', reason_code='content_type')
            metadata = {'url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat(),
                'http_status':200, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest(),
                'headers':{'Content-Type':media}}
    except error.HTTPError as exc:
        status = exc.code;exc.close()
        raise IRError(f'Issuer request failed (HTTP {status}); no automatic retry', reason_code='http_error', http_status=status) from None
    except (error.URLError, TimeoutError, OSError):
        raise IRError('Issuer request failed (network/timeout); no automatic retry', reason_code='network_failed') from None
    try:
        return raw.decode('utf-8'), raw, metadata
    except UnicodeDecodeError:
        raise IRError('Issuer response is not valid UTF-8', reason_code='encoding') from None


class _Table(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title=False;self.title_text=[];self.row=None;self.cell=None;self.rows=[];self.header_seen=False
        self.table_depth=0;self.table_count=0

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='title':self.title=True
        if tag=='table':
            if self.table_depth:raise IRError('Nested tables are not valid issuer filing rows')
            elif {'nirtable','views-table','views-view-table'}.issubset(set(attrs.get('class','').split())):
                self.table_depth=1;self.table_count+=1
        if tag=='tr' and self.table_depth==1:self.row={'date':[], 'form':[], 'links':[], 'timestamps':[]}
        if self.row is not None and tag=='td':
            self.cell = 'date' if attrs.get('headers')==DATE_CELL else 'form' if attrs.get('headers')==FORM_CELL else None
            self.header_seen |= self.cell is not None
        if self.row is not None and self.cell=='form' and tag=='a':self.row['links'].append(attrs.get('href',''))
        if self.row is not None and self.cell=='date' and tag=='time':self.row['timestamps'].append(attrs.get('datetime',''))

    def handle_data(self, data):
        if self.title:self.title_text.append(data)
        if self.row is not None and self.cell is not None:self.row[self.cell].append(data)

    def handle_endtag(self, tag):
        if tag=='title':self.title=False
        if tag=='td':self.cell=None
        if tag=='tr' and self.row is not None:
            if any(self.row['form']):self.rows.append(self.row)
            if len(self.rows)>MAX_ROWS:raise IRError('Issuer listing exceeds the bounded row count')
            self.row=None;self.cell=None
        if tag=='table' and self.table_depth:
            self.table_depth-=1
            if not self.table_depth:self.row=None;self.cell=None


def parse_exe_filings(html, cutoff):
    """Read only validated periodic filing rows; report periods remain unknown."""
    if not isinstance(html,str) or len(html.encode('utf-8'))>MAX_IR_BYTES:
        raise IRError('Use a bounded HTML issuer listing')
    parser=_Table();parser.feed(html);parser.close()
    title=' '.join(''.join(parser.title_text).split())
    if title!='SEC Filings - Expand Energy Corporation' or not parser.header_seen or parser.table_count!=1 or parser.table_depth:
        raise IRError('Official issuer identity or filing table structure was not found')
    limit=_cutoff(cutoff);found={}
    for row in parser.rows:
        form=' '.join(''.join(row['form']).split())
        if form not in FORMS:continue
        date_text=' '.join(''.join(row['date']).split())
        match=re.fullmatch(r'([A-Z][a-z]{2}) ([0-9]{1,2}), ([0-9]{4})',date_text)
        if not match:raise IRError('Periodic filing row has no unambiguous filing date')
        months=('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
        try:
            filed=datetime(int(match[3]),months.index(match[1])+1,int(match[2])).date().isoformat()
        except ValueError:raise IRError('Periodic filing date is invalid') from None
        if len(row['timestamps'])!=1 or row['timestamps'][0][:10]!=filed:
            raise IRError('Visible filing date and timestamp disagree')
        try:
            _cutoff(row['timestamps'][0])
        except SECError:
            raise IRError('Issuer filing timestamp is invalid or lacks a timezone') from None
        if len(row['links'])!=1:raise IRError('Periodic filing row needs one form link')
        url=urljoin(IR_ORIGIN,row['links'][0]);parts=urlsplit(url)
        expected=r'/sec-filings/sec-filing/'+FORMS[form]+r'/([0-9]{10}-[0-9]{2}-[0-9]{6})'
        accession=re.fullmatch(expected,parts.path)
        if (parts.scheme!='https' or parts.netloc!='investors.expandenergy.com' or parts.query or parts.fragment or not accession):
            raise IRError('Periodic form link does not match the official issuer path')
        if int(accession[1].split('-')[1]) != int(filed[:4])%100:
            raise IRError('Accession year and issuer-listed filing year disagree')
        record={'accessionNumber':accession[1], 'filingDate':filed, 'form':form,
            'reportDate':None, 'available_at':public_available_at(filed), 'source_url':url,
            'availability_basis':'Conservative next Eastern midnight from issuer-listed filing date; issuer publication time is unknown'}
        prior=found.get(accession[1])
        if prior and prior!=record:raise IRError('Conflicting issuer rows for one accession')
        found[accession[1]]=record
    return sorted((row for row in found.values() if _cutoff(row['available_at'])<=limit),
                  key=lambda row:(row['filingDate'],row['accessionNumber']),reverse=True)


def collect_exe_filings(cache_dir, cutoff=None):
    """Three opt-in GETs, robots first; no SEC calls, credentials or full reports."""
    limit=_cutoff(cutoff) if cutoff is not None else datetime.now(timezone.utc)
    robots, raw, metadata=_fetch(IR_ROBOTS)
    if 'user-agent:' not in robots.lower() or '<html' in robots.lower():
        raise IRError('Issuer robots policy could not be validated', reason_code='robots_invalid')
    policy=robotparser.RobotFileParser();policy.parse(robots.splitlines())
    if any(not policy.can_fetch(IR_USER_AGENT,url) for url in IR_URLS):
        raise IRError('Issuer robots policy disallows the configured listing', reason_code='robots_denied')
    delay=policy.crawl_delay(IR_USER_AGENT) or 1
    rate=policy.request_rate(IR_USER_AGENT)
    if rate:
        if rate.requests<=0:raise IRError('Issuer request-rate policy requires operator review', reason_code='robots_rate')
        delay=max(delay, rate.seconds/rate.requests)
    if not isinstance(delay,(int,float)) or delay>60:raise IRError('Issuer crawl delay requires operator review', reason_code='robots_rate')
    sources=[_cache(cache_dir,'ir-robots',raw,metadata,'.txt')]
    records={}
    for group,url in zip(('annual','quarterly'),IR_URLS):
        time.sleep(max(1,delay))
        html,raw,metadata=_fetch(url)
        selected=parse_exe_filings(html,limit)
        for row in selected:
            prior=records.get(row['accessionNumber'])
            if prior and prior!=row:raise IRError('Conflicting issuer listing groups')
            records[row['accessionNumber']]=row
        sources.append(_cache(cache_dir,'ir-'+group,raw,metadata,'.html'))
    return {'issuer':{'name':'Expand Energy Corporation','cik':'0000895126','tickers':['EXE']},
        'provider':'issuer_ir', 'sources':sources, 'as_of':max(row['retrieved_at'] for row in sources),
        'cutoff':limit.isoformat(), 'filings':sorted(records.values(),key=lambda row:(row['filingDate'],row['accessionNumber']),reverse=True),
        'scope':'Latest periodic metadata in the first annual and quarterly issuer listing pages; report periods and contents are not mapped'}


def _cache(directory, kind, raw, metadata, suffix):
    try:
        return _cache_snapshot(Path(directory),'0000895126',kind,raw,metadata,suffix=suffix)
    except (SECError, OSError):
        raise IRError('Issuer snapshot cache could not be validated or would exceed its budget', reason_code='cache_failed') from None
