"""Immutable ledger snapshots, consistent history capture and downloadable reports."""
import hashlib
import json
from dataclasses import dataclass
from services.financial.ledger_summary import ledger_summary, LedgerSummaryError


@dataclass(frozen=True)
class LedgerSnapshot:
    content: str
    sha256: str
    byte_count: int


def capture_ledger_snapshot(session, *, case_id, account_id=None, start_date=None, end_date=None):
    result=ledger_summary(session,case_id=case_id,account_id=account_id,start_date=start_date,
        end_date=end_date,capture_readings=True)
    if not result['available']:
        raise LedgerSummaryError(result['reason'])
    document=dict(schema='loupe.financial.ledger_snapshot/1',ledger=result,
        export_ready=False,limitations=['Decision history has not been captured. This is an internal snapshot, not a completed export.',
            'Source digests are recorded ingestion digests; source bytes were not reverified for this snapshot.'])
    # No generation time in the content: equal captured inputs yield equal bytes.
    content=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    encoded=content.encode('utf-8')
    return LedgerSnapshot(content=content,sha256=hashlib.sha256(encoded).hexdigest(),byte_count=len(encoded))


MAX_EXPORT_DECISIONS = 10000
MAX_EXPORT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class LedgerExport:
    snapshot: LedgerSnapshot
    manifest: str
    source_files: tuple = ()
    source_files_requested: bool = False


def _capture_history(session, document, *, case_id):
    from uuid import UUID
    from sqlalchemy import select, and_, or_
    from postgres.models.financial import AdjudicationEvent
    from services.financial.decision_log import to_record, _machine_actor_email
    scopes = {name:set() for name in ('transaction','source_document','statement_period','evidence_file')}
    for reading in document['ledger']['readings']:
        row, source = reading['row'], reading['source']
        scopes['transaction'].add(UUID(row['key']))
        scopes['source_document'].add(UUID(source['id']))
        if row['statement_period_id']:scopes['statement_period'].add(UUID(row['statement_period_id']))
        if source['evidence_file_id']:scopes['evidence_file'].add(UUID(source['evidence_file_id']))
    predicates=[and_(AdjudicationEvent.subject_type==kind,AdjudicationEvent.subject_id.in_(ids))
        for kind,ids in scopes.items() if ids]
    events=[]
    if predicates:
        events=list(session.scalars(select(AdjudicationEvent).where(AdjudicationEvent.case_id==case_id,or_(*predicates))
            .order_by(AdjudicationEvent.subject_type,AdjudicationEvent.subject_id,AdjudicationEvent.subject_sequence)
            .limit(MAX_EXPORT_DECISIONS+1)))
    if len(events)>MAX_EXPORT_DECISIONS:
        raise LedgerSummaryError('Too many relevant decisions for a complete export; no truncated export was produced.')
    machine_email=_machine_actor_email()
    document['decisions']=[to_record(event,machine_email=machine_email).as_dict() for event in events]
    document['decision_scope']={kind:sorted(str(value) for value in ids) for kind,ids in scopes.items()}
    document['decision_order']='Per-subject sequence only; ordering across different subjects does not establish chronology.'
    document['ledger']['history_captured']=True
    document['export_ready']=True
    from services.financial.ledger_review_history import capture_pdf_review_history
    document['pdf_review_history']=capture_pdf_review_history(session,case_id=case_id,evidence_file_ids=scopes['evidence_file'])
    from services.financial.working_totals import working_totals_from_readings
    document['working_totals'] = working_totals_from_readings(document['ledger'])
    document['schema']='loupe.financial.ledger_snapshot/3'
    document['limitations']=[
        'Source digests are recorded ingestion digests; source bytes were not reverified for this snapshot.',
        'Decision history covers the captured rows and their source documents, statement periods and evidence files. It is not a complete case history.',
        'PDF review history covers all saved candidates for referenced source files, including other rows outside the ledger filters. Review history is context, not additional transactions.',
    ]
    return document


def capture_ledger_export(engine, *, case_id, account_id=None, start_date=None, end_date=None, generated_at=None, include_source_files=False, resolve_path=None):
    """Own a fresh PostgreSQL repeatable-read read-only transaction for both reads."""
    from datetime import datetime, timezone
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session
    from services.financial.version import code_version
    if not isinstance(engine,Engine) or engine.dialect.name!='postgresql':
        raise LedgerSummaryError('Consistent ledger export requires a fresh PostgreSQL engine connection.')
    if include_source_files and not callable(resolve_path):
        raise LedgerSummaryError('Source file export requires a registered path resolver.')
    source_files = ()
    generated_at=generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise LedgerSummaryError('Export generation time must carry a timezone.')
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            with Session(bind=connection,autoflush=False) as session:
                snapshot=capture_ledger_snapshot(session,case_id=case_id,account_id=account_id,start_date=start_date,end_date=end_date)
                document=_capture_history(session,json.loads(snapshot.content),case_id=case_id)
                if include_source_files:
                    from services.financial.export_sources import capture_export_sources
                    source_files = capture_export_sources(session,document,case_id=case_id,resolve_path=resolve_path)
                content=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    encoded=content.encode('utf-8')
    if len(encoded)>MAX_EXPORT_BYTES:
        raise LedgerSummaryError('Export exceeds 16 MiB; narrow the scope. No partial export was produced.')
    snapshot=LedgerSnapshot(content,hashlib.sha256(encoded).hexdigest(),len(encoded))
    manifest=dict(schema='loupe.financial.ledger_export_manifest/1',digest_covers='ledger_snapshot_json_utf8',
        document_sha256=snapshot.sha256,byte_count=snapshot.byte_count,
        generated_at=generated_at.astimezone(timezone.utc).isoformat(),case_id=str(case_id),
        code_version=code_version(),snapshot_schema=document['schema'],
        pdf_candidate_review_count=len(document['pdf_review_history']['reviews']),
        pdf_candidate_count=len(document['pdf_review_history']['candidates']),
        pdf_finalization_count=len(document['pdf_review_history']['finalizations']),
        decision_count=len(document['decisions']),included_rows=document['ledger']['included_rows'],
        excluded_rows=document['ledger']['excluded_rows'])
    return LedgerExport(snapshot,json.dumps(manifest,sort_keys=True,separators=(',',':')), source_files, include_source_files)


def ledger_export_archive(export, *, include_pdf=False):
    """Package canonical bytes without reserializing the captured content."""
    import io
    import zipfile
    report = render_ledger_report(export.snapshot)
    report_bytes = report.encode('utf-8')
    manifest = json.loads(export.manifest)
    manifest['report'] = dict(filename='ledger-report.html', sha256=hashlib.sha256(report_bytes).hexdigest(),
        byte_count=len(report_bytes), derived_from_sha256=export.snapshot.sha256)
    pdf = None
    if include_pdf:
        from services.financial.ledger_pdf import render_ledger_pdf
        pdf = render_ledger_pdf(export.snapshot, report)
        manifest['pdf_report'] = dict(filename='ledger-report.pdf', sha256=hashlib.sha256(pdf).hexdigest(),
            byte_count=len(pdf), derived_from_sha256=export.snapshot.sha256)
    if export.source_files_requested:
        manifest['source_files'] = [{key:value for key,value in item.items() if key != 'content'} for item in export.source_files]
        manifest['source_files_verified_against_ingestion'] = True
        manifest['source_files_scope'] = 'Complete original files referenced by captured rows; files may contain pages or information outside the ledger filters.'
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,content in (('ledger-snapshot.json',export.snapshot.content),('manifest.json',json.dumps(manifest,sort_keys=True,separators=(',',':'))), ('ledger-report.html',report)):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,content.encode('utf-8'))
        if pdf is not None:
            info = zipfile.ZipInfo('ledger-report.pdf', date_time=(1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, pdf)
        for item in export.source_files:
            info=zipfile.ZipInfo(item['archive_path'],date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,item['content'])
    return stream.getvalue()


def render_ledger_report(snapshot):
    """Render only immutable captured content; never consult live data or execute evidence."""
    from html import escape

    document = json.loads(snapshot.content)
    ledger = document['ledger']

    def text(value):
        return escape('Not recorded' if value is None else str(value), quote=True)

    def details(label, value):
        return '<details><summary>' + text(label) + '</summary><pre>' + text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)) + '</pre></details>'

    def money_display(value, currency):
        from services.financial.money import Money, MoneyError
        import re
        if not isinstance(value, str) or not re.fullmatch(r"-?(0|[1-9][0-9]*)", value):
            return str(value) + ' minor units (unscaled: invalid stored integer)'
        try:
            amount = Money(int(value), currency)
            historical = ' (historical currency)' if amount.currency_info.is_historical else ''
            return amount.format() + historical + ' [' + value + ' minor units]'
        except (MoneyError, ValueError, TypeError):
            return value + ' minor units (unscaled: unsupported currency)'

    def table(headers, rows):
        return '<table><thead><tr>' + ''.join('<th>' + text(h) + '</th>' for h in headers) + (
            '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + text(v) + '</td>' for v in row)
            + '</tr>' for row in rows) + '</tbody></table>')

    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Loupe ledger report</title><style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}',
        'table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #aaa;padding:.5rem;text-align:left;overflow-wrap:anywhere}',
        'pre{white-space:pre-wrap;overflow-wrap:anywhere}article{border-top:1px solid #aaa;margin-top:1rem;padding-top:1rem}',
        '@media print{details>*{display:block}thead{display:table-header-group}body{max-width:none}}</style></head><body>',
        '<h1>Loupe ledger report</h1><p>Captured account postings and recorded decisions.</p>',
        '<h2>Scope and interpretation</h2>',
        table(['Case', 'Account', 'Ordering dates, inclusive'], [[ledger['case_id'],
            ledger['account_id'] or 'All accounts', (ledger['start_date'] or 'Unbounded') + ' to ' + (ledger['end_date'] or 'Unbounded')]]),
        '<p>' + text(ledger['limitation']) + '</p>',
        '<p>Amounts show currency units with their exact integer minor units in brackets. '
        'Unsupported values remain explicitly unscaled. No exchange-rate conversion or transfer matching is applied.</p>',
        '<p>Included rows: ' + text(ledger['included_rows']) + '; excluded rows: ' + text(ledger['excluded_rows']) + '.</p>',
        '<h2>Verified totals by currency</h2>',
        table(['Currency', 'Rows', 'Credits', 'Debits', 'Net postings'],
              [[c['currency'], c['rows'], money_display(c['credits_minor'], c['currency']), money_display(c['debits_minor'], c['currency']), money_display(c['net_minor'], c['currency'])] for c in ledger['currencies']]),
        '<h2>Limitations</h2><ul>' + ''.join('<li>' + text(v) + '</li>' for v in document['limitations']) + '</ul>']
    working = document.get('working_totals')
    if working is not None:
        parts += ['<h2>Working totals — including readings outside verified totals</h2>',
            '<p>' + text(working['limitation']) + '</p>',
            '<p>' + text(working['included_rows']) + ' current rows; ' + text(working['outside_verified_rows']) + ' outside verified totals.</p>',
            table(['Currency', 'Rows', 'Credits', 'Debits', 'Net postings'],
                [[g['currency'], g['rows'], money_display(g['credits_minor'],g['currency']), money_display(g['debits_minor'],g['currency']), money_display(g['net_minor'],g['currency'])] for g in working['currencies']])]
    parts += ['<h2>Captured readings</h2><p>Readings excluded from verified totals are retained for review. Current admitted P3 readings can enter the separate working totals. Displayed by ordering date; same-day display order does not establish bank sequence.</p>']
    for reading in sorted(ledger['readings'], key=lambda value:(value['row']['ordering_date'],value['row']['key'])):
        row = reading['row']
        parts += ['<article><h3>Reading ' + text(row.get('ref_id') or row['key']) + '</h3>',
            table(['Included in verified totals', 'Ordering date', 'Description', 'Direction', 'Currency', 'Amount (exact minor units in brackets)'],
                  [['Yes' if reading['included'] else 'No: ' + {'proof_class_not_included':'Outside verified proof classes', 'superseded':'Superseded reading', 'quarantined':'Held for review', 'rejected':'Rejected reading', 'source_not_admitted':'Source is not admitted'}.get(reading['exclusion_reason'],str(reading['exclusion_reason'])),
                    row['ordering_date'] + (' (statement end; ordering only, transaction date unknown)' if row.get('ordering_date_context') == 'statement_end_ordering_only' else ''), row['description'], row['direction'], row['currency'], money_display(row['amount_minor'], row['currency'])]]),
            '<p>Source document: ' + text(reading['source']['id']) + '; PDF page: ' + text((row.get('locator') or {}).get('page')) + '. Recorded ingestion SHA-256: <code>' + text(reading['source'].get('sha256_at_ingestion')) + '</code>.</p>',
            details('Source reference and recorded ingestion digest', reading['source']),
            details('Original captured row, dates and source locator', row),
            details('Preserved transaction provenance', reading['provenance']), '</article>']
    parts += ['<h2>Relevant recorded decisions</h2>', '<p>' + text(document.get('decision_order', 'Decision history has not been captured.')) + '</p>']
    for decision in document.get('decisions', []):
        parts += ['<article><h3>' + text(decision['decision']) + '</h3>',
            table(['Subject', 'Sequence', 'Recorded at', 'Actor', 'Reason'], [[
                decision['subject_type'] + ': ' + decision['subject_id'], decision['subject_sequence'],
                decision['recorded_at'], decision['actor_name'] or decision['actor_email'], decision['reason']]]),
            details('Decision reference, original values and changed values', decision), '</article>']
    history=document.get('pdf_review_history')
    if history is not None:
        parts += ['<h2>PDF reading review history</h2><p>' + text(history['scope']) + '</p>']
        parts += [table(['Saved candidates','Review decisions','Finalizations'], [[len(history['candidates']),len(history['reviews']),len(history['finalizations'])]])]
        for state in history['review_states']:
            parts += ['<article><h3>Candidate ' + text(state['candidate_id']) + '</h3>']
            for event in state['history']:
                parts += [table(['Sequence','Status','Reason','Actor'], [[event['sequence'],event['status'],event['reason'],event['actor'].get('name') or event['actor'].get('email')]]),details('Reviewed values and recorded decision',event)]
            parts += ['</article>']
        for finalization in history['finalizations']:
            scopes = finalization['snapshot'].get('manifest', {}).get('statement_scopes', [])
            for scope in scopes:
                parts += ['<article><h3>Reviewed statement controls</h3>',
                    '<p>Retained at finalization. These are selected-row review observations, not a complete-statement certification or a fresh balance check.</p>',
                    table(['Account', 'Currency', 'Balance convention', 'Assigned rows'], [[scope['account_id'], scope['currency'],
                        'Amounts owed (converted to negative ledger balances)' if scope['balance_convention'] == 'liability_owed' else 'Money held in account',
                        len(scope['candidate_ids'])]])]
                controls = []
                for role in ('start', 'end', 'opening', 'closing', 'credits_total', 'debits_total'):
                    control = scope['bound_controls'].get(role)
                    if control is None:
                        controls.append([{'credits_total': 'Total money in', 'debits_total': 'Total money out'}.get(role, role.capitalize()), 'Unknown — not supplied', '—', '—'])
                    else:
                        value = control['value'] if role in ('start', 'end') else money_display(control['amount_minor'], scope['currency'])
                        controls.append([{'credits_total': 'Total money in', 'debits_total': 'Total money out'}.get(role, role.capitalize()), value, control['source']['expected_text'], control['source']['page_number']])
                parts += [table(['Control', 'Reviewed printed value', 'Original source text', 'PDF page'], controls),
                    '<p>Review reason: ' + text(scope['reason']) + '</p>',
                    details('Control source locations and selected candidate references', scope), '</article>']
        parts += [details('Original PDF mappings and cells, review chain and finalization receipts',history)]
    parts += ['<h2>Verification</h2><p>This report is derived only from the bundled ledger-snapshot.json. '
        'Its SHA-256 is <code>' + text(snapshot.sha256) + '</code>; its UTF-8 size is ' + text(snapshot.byte_count) +
        ' bytes. The manifest separately identifies the report bytes.</p></body></html>']
    result = ''.join(parts)
    if len(result.encode('utf-8')) > MAX_EXPORT_BYTES:
        raise LedgerSummaryError('Readable report exceeds 16 MiB; narrow the scope. No partial report was produced.')
    return result
