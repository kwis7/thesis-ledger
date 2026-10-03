"""Issuer-site monitoring with status separate from SEC availability."""
from datetime import datetime, timezone
from .engine import digest
from .issuer_ir import IRError, IR_LISTING, collect_exe_filings, failure_diagnostic
from .sec_monitor import known_accessions
from .store import decode


def check_exe_ir(engine, *, collector=collect_exe_filings):
    company=engine.company('EXE')
    if company.get('case_id')!='exe-sec-2024-2025':raise ValueError('Issuer monitor requires the isolated EXE public case')
    if engine.store.metadata('settings',{}).get('paused'):
        return {'status':'paused','alerts_created':0,'reason':'Resume monitoring before an issuer check'}
    try:
        snapshot=collector(engine.store.workspace/'ir')
        if snapshot.get('issuer',{}).get('cik')!='0000895126' or snapshot.get('provider')!='issuer_ir':
            raise IRError('Issuer collector identity did not match EXE')
    except IRError as exc:
        code, reason, http_status = failure_diagnostic(exc)
        at=datetime.now(timezone.utc).isoformat()
        with engine.store.connect(write=True) as connection:
            previous=_previous(connection);started=previous.get('failure_started_at') or at
            status={'status':'unavailable','checked_at':at,'last_success_at':previous.get('last_success_at'),
                'failure_started_at':started,'error_code':code,'http_status':http_status,
                'reason':reason+' No automatic retry.', 'source_url':IR_LISTING}
            engine.store.set_metadata(connection,'ir_monitor',status)
        identity='ir-outage-'+digest(started)[:24]
        engine.ingest_event({'id':identity,'symbol':'EXE','kind':'review_due','source_status':True,
            'title':'Official issuer filing check unavailable','summary':status['reason'], 'source':'EXE issuer collector status',
            'source_document':identity,'published_at':started,'decision_ts':started,'verified':True,'evidence':[],'evidence_ids':[],'changes':[]})
        raise IRError(status['reason']+' See saved issuer status in the workbench.') from None
    filings=snapshot['filings'];latest=filings[0] if filings else None
    result={'status':'data_gap' if latest is None else 'unchanged','alerts_created':0,'provider':'issuer_ir','scope':snapshot['scope']}
    if latest and latest['accessionNumber'] not in known_accessions(engine,company):
        accn=latest['accessionNumber'];identity='official-filing-'+accn.replace('-','');acquired=snapshot['as_of']
        evidence={'id':identity,'title':f"EXE {latest['form']} issuer listing",'source':'Expand Energy official investor website',
            'source_type':'issuer_ir','url':latest['source_url'],'published_at':latest['available_at'],'retrieved_at':acquired,
            'usable_at':acquired,'period':'Report period not established','unit':'filing metadata','currency':'USD',
            'locator':accn+' / official annual and quarterly listing pages','content':f"The issuer website lists {latest['form']}, accession {accn}, filed {latest['filingDate']}. Report period and financial contents have not been mapped. This check does not establish SEC API recovery.",
            'classification':'confirmed_fact','verified':True}
        saved=engine.ingest_event({'id':identity,'symbol':'EXE','kind':'review_due',
            'title':f"EXE {latest['form']} listed by its issuer needs review",'summary':'An unreviewed periodic filing is listed on the official company website. Verify its report period and financial bridge before changing the model.',
            'source':'Expand Energy official investor website','source_document':accn,'published_at':latest['available_at'],
            'decision_ts':acquired,'verified':True,'evidence':[evidence],'evidence_ids':[identity],'changes':[]})
        result.update(status=saved['status'],alerts_created=saved.get('alerts_created',0))
    at=datetime.now(timezone.utc).isoformat();success=latest is not None
    with engine.store.connect(write=True) as connection:
        previous=_previous(connection)
        status={'status':'available' if success else 'data_gap','checked_at':at,
            'last_success_at':at if success else previous.get('last_success_at'),
            'failure_started_at':None if success else previous.get('failure_started_at'),
            'reason':'Official issuer periodic metadata checked. Report periods and financial contents require review.' if success else 'No eligible periodic metadata in the bounded issuer pages.',
            'source_url':IR_LISTING,'latest_filing':latest,
            'sources':[{key:source[key] for key in ('url','retrieved_at','sha256','bytes')} for source in snapshot.get('sources',[])]}
        engine.store.set_metadata(connection,'ir_monitor',status)
    return dict(result,accession=latest['accessionNumber'] if latest else None,source_url=latest['source_url'] if latest else IR_LISTING)


def _previous(connection):
    row=connection.execute("SELECT value FROM metadata WHERE key='ir_monitor'").fetchone()
    return decode(row['value'],{}) if row else {}
