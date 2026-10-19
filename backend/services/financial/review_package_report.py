"""Readable index derived from captured review inputs, without combining their scopes."""
import json
from html import escape
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.money import Money


def render_review_package_report(*, case_id, scenarios, supports, preparation=None, ledger=None, measurement=None, ledger_support_attached=False, ledger_support=None, scenario_reports=False):
    def text(value): return escape('Not recorded' if value is None else str(value), quote=True)
    def table(headers, rows):
        return '<table><thead><tr>'+''.join('<th>'+text(v)+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join(
            '<tr>'+''.join('<td data-label="'+text(headers[i])+'">'+text(v)+'</td>' for i,v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table>'
    def money(amount, currency):
        return Money(int(amount), currency).format()+' ['+str(amount)+' minor units]'
    preparation = preparation or {}
    marking = {'unmarked':'No privilege marking selected','confidential':'Confidential',
        'privileged_confidential':'Privileged and confidential'}.get(preparation.get('privilege_marking','unmarked'))
    if marking is None: raise LedgerSummaryError('Unsupported review package marking.')
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Loupe review package</title>',
        '<style>body{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}table{border-collapse:collapse;width:100%;table-layout:fixed;margin:1rem 0}td,th{border:1px solid #aab;padding:.5rem;text-align:left;overflow-wrap:anywhere}th{background:#eef1f5}code,p,li{overflow-wrap:anywhere}h1{color:#a51b34}@media screen and (max-width:600px){table,tbody,tr,td{display:block;width:auto}thead{display:none}tr{border:1px solid #aab;margin:1rem 0}td{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem;border:0;border-bottom:1px solid #dde}td:before{content:attr(data-label);font-weight:600}}@media print{thead{display:table-header-group}h2,h3{break-after:avoid}tr{break-inside:avoid}}</style></head><body>',
        '<h1>Financial review package</h1><p>'+text(marking)+'</p>',
        '<p>Case: '+text(case_id)+'. Prepared: '+text(preparation.get('generated_at'))+'.</p>',
        '<p>Prepared by: '+text((preparation.get('generated_by') or {}).get('name'))+' ('+text((preparation.get('generated_by') or {}).get('email'))+').</p>',
        '<p>Each enclosed capture keeps its own date, filters, source readings and marking. The outer marking does not relabel the originals. This report does not combine their totals.</p>',
        '<h2>Contents</h2><ul><li><a href="manifest.json">File inventory and SHA-256 hashes</a></li>']
    if ledger is not None:
        parts += ['<li><a href="ledger/original-export.zip">Original ledger export</a>: open this ZIP separately for its captured report and any selected original source files.</li>']
        if ledger_support_attached:
            parts += ['<li><a href="ledger/captured-expert-support.json">Saved ledger methods, versions and decision references</a>: an unchanged copy from the ledger export. Its capture date and scope remain separate from the selected scenarios.</li>']
    for i in range(len(scenarios)):
        prefix=f'scenarios/{i+1:02d}/'
        parts += ['<li>Scenario '+str(i+1)+': <a href="'+prefix+'scenario.json">original scenario</a>, <a href="'+prefix+'replay.json">recalculation check</a>, <a href="'+prefix+'expert-support.json">methods, versions and support index</a>.</li>']
        if scenario_reports:
            parts += ['<li><a href="'+prefix+'report.html">Read calculation '+str(i+1)+'</a>: saved reasons, transfer steps, results under each method, asset purchases, resales and payment references.</li>']
    if measurement is not None:
        parts += ['<li><a href="validation/measurements.json">Extraction measurements</a> and <a href="validation/corpus.json">measured corpus</a>.</li>']
    parts += ['</ul><h2>Material still requiring review</h2><ul>',
        '<li>Scenario assumptions and the applicability of selected tracing methods require investigator review. Matching recalculation does not verify the assumptions.</li>',
        '<li>Recorded custody reports and decisions cannot reconstruct unrecorded earlier events or establish document authenticity.</li>',
        '<li>Recorded component versions are scoped to the supplied captures. A complete historical runtime is not inferred.</li>',
        '<li>This is generated preparation support, not an expert opinion or signature.</li></ul>']
    if ledger is None:
        parts += ['<h2>Ledger and case history</h2><p>No separate ledger export was attached. Scenario snapshots remain available in their original files.</p>']
    else:
        history=ledger.get('case_financial_history')
        custody=(history or {}).get('custody_reports')
        audit=(history or {}).get('audit_chain')
        imports=(ledger.get('processing_provenance') or {}).get('statement_import_history')
        working = ledger.get('working_totals') if ledger_support is not None else None
        reading_counts = ([['Transactions in investigation totals', working.get('included_rows')],
            ['Transactions outside investigation totals', working.get('excluded_rows')],
            ['Transactions in separately verified totals', ledger['ledger'].get('included_rows')]] if working is not None else [
            ['Included ledger readings', ledger['ledger'].get('included_rows')],
            ['Excluded ledger readings', ledger['ledger'].get('excluded_rows')]])
        parts += ['<h2>Attached ledger and case history</h2>',table(['Captured item','Count or scope'],[
            *reading_counts,
            ['Wider case history','Attached' if history is not None else 'Not selected'],
            ['Statement import confirmations',len(imports) if imports is not None else 'Not captured'],
            ['Case custody reports',len(custody['events']) if custody is not None else 'Not captured'],
            ['Case financial decisions',len(history['decisions']) if history is not None and 'decisions' in history else 'Not captured'],
            ['Recorded audit events',audit['verification']['event_count'] if audit else 'Not captured']]),
            '<p>These counts describe the attached capture. They are not a completeness finding or the current live case state.</p>']
        if working is not None:
            parts += ['<h3>Saved investigation totals</h3>',
                '<p>These totals include imported transactions awaiting further verification. The separately verified totals use the narrower review category recorded at export. Currency totals are kept separate.</p>',
                table(['Currency', 'Transactions', 'Credits', 'Debits', 'Credits minus debits'], [
                    [group['currency'], group['rows'], Money(int(group['credits_minor']), group['currency']).format(),
                     Money(int(group['debits_minor']), group['currency']).format(), Money(int(group['net_minor']), group['currency']).format()]
                    for group in working.get('currencies', [])])]
            if working.get('has_credit_card_readings'):
                parts += ['<p>For credit-card transactions, debits increase the amount owed and credits reduce it. Credits minus debits is the change from these transactions, not a statement balance.</p>']
    if ledger_support is not None:
        versions = ledger_support.get('versions') or {}
        decisions = ledger_support.get('human_decisions') or {}
        sources = ledger_support.get('source_records') or {}
        processing = sources.get('processing_records') or {}
        filenames = {item['id']: item.get('original_filename') for item in processing.get('evidence_registrations', [])}
        source_names = {item['id']: filenames.get(item.get('evidence_file_id'))
                        for item in sources.get('sources', [])}
        def source_name(identifier):
            return source_names.get(identifier) or identifier
        parts += ['<h2>Saved ledger processing and review</h2>',
            '<p>These records come from the attached ledger export. They describe its saved readings, not a new extraction or the current case. '
            'The <a href="ledger/captured-expert-support.json">complete saved support record</a> is retained unchanged.</p>',
            table(['Saved item', 'Recorded value'], [
                ['Export code version', versions.get('export_code_version')],
                ['Statement import confirmations', decisions.get('statement_import_confirmations')],
                ['Financial decisions', decisions.get('recorded_decisions')],
                ['PDF reviews', decisions.get('pdf_reviews')]])]
        parsers = versions.get('source_parsers')
        if parsers:
            parts += [table(['Statement file', 'Statement reader', 'Reader version'], [
                [source_name(row.get('source_document_id')), row.get('parser_name'), row.get('parser_version')] for row in parsers])]
        records = versions.get('statement_pdf_processing_records')
        if records:
            rows = []
            for record in records:
                content = (record.get('manifest') or {}).get('content') or {}
                ocr = content.get('tesseract') or {}
                rows.append([source_name(record.get('source_document_id')), record.get('page_number'),
                    content.get('recorded_at'), content.get('python_version'),
                    (content.get('packages') or {}).get('PyMuPDF'),
                    'Not used' if ocr.get('status') == 'not_used' else ocr.get('version')])
            parts += [table(['Statement file', 'Page', 'Processed at', 'Python', 'PDF reader', 'OCR engine'], rows)]
        else:
            parts += ['<p>No statement PDF processing records were saved in this support file.</p>']
        case_custody = sources.get('case_custody_reports')
        source_custody = sources.get('source_custody_reports')
        if case_custody is not None:
            events = case_custody.get('events', [])
            scope = 'All custody reports included in the saved case-history capture.'
        elif source_custody is not None:
            events = [event for source in source_custody for event in source.get('events', [])]
            scope = 'Custody reports for the sources selected in the saved ledger export.'
        else:
            events = None
            scope = 'Custody reports were not captured in this saved support file.'
        parts += ['<h3>Reported source custody</h3><p>'+text(scope)+'</p>']
        if events:
            for event in events:
                report = event.get('report') or {}
                actor = event.get('actor') or {}
                parts += [table(['Recorded item', 'Value'], [
                    ['Source file', filenames.get(event.get('evidence_file_id')) or event.get('evidence_file_id')], ['Report ID', event.get('id')],
                    ['Event', report.get('event_kind')], ['Reported event time', report.get('occurred_at')],
                    ['Recorded by', actor.get('name')], ['Recorded at', event.get('recorded_at')],
                    ['Provided by', report.get('from_person_or_organisation')], ['Received by', report.get('received_by')],
                    ['Acquisition method', report.get('acquisition_method')], ['Native file', report.get('native_file_status')],
                    ['Certification file', report.get('certification_file_id')], ['Corrects report', report.get('corrects_event_id')],
                    ['Explanation', report.get('reason')]])]
        elif events is not None:
            parts += ['<p>No custody reports were recorded in this captured scope.</p>']
        parts += ['<p>Reported event times and recording times are separate. Corrections retain the earlier report. Missing history remains unknown.</p>']
    parts += ['<h2>Extraction measurements</h2>']
    if measurement is None:
        parts += ['<p>No extraction measurements were attached. Software test counts are not extraction accuracy.</p>']
    else:
        parts += ['<p>Label status: <strong>'+text(measurement['label_status'])+'</strong>. Corpus '+text(measurement['corpus_id'])+', version '+text(measurement['corpus_version'])+'.</p>',
            '<p>Measurements apply to the supplied corpus and recorded extractor versions. Case equivalence, reviewer independence and representativeness are not established by this package.</p>']
        def fraction(value):
            return str(value['numerator'])+' / '+str(value['denominator']) if value['status']=='available' else 'Unavailable (no denominator)'
        parts += [table(['Layer','Extractor versions','Documents','Correct rows / nominated rows','Found rows / reference rows','Errors surviving gate'],[
            [layer['extraction_layer'],', '.join(layer['extractor_versions']),layer['documents'],fraction(layer['row_precision']),fraction(layer['row_recall']),fraction(layer['errors_surviving_gate'])] for layer in measurement['layers']])]
    for i,(scenario,support) in enumerate(zip(scenarios,supports),1):
        inputs=scenario['inputs'];results=scenario.get('comparison',{}).get('results',scenario.get('results',{}))
        parts += ['<h2>Scenario '+str(i)+'</h2>',
            '<p>Period: '+text(inputs.get('start_date'))+' to '+text(inputs.get('end_date'))+'. Snapshot SHA-256: <code>'+text(support['derived_from_sha256'])+'</code>.</p>',
            '<p>Captured export code version: '+text(support['versions']['export_code_version'])+'.</p>',
            '<p>Statement import confirmations: '+text(support['human_decisions'].get('statement_import_confirmations'))+'. Original extraction and confirmed changes are identified in this scenario’s support index.</p>',
            '<p>Conditional cash results under each selected method. Asset/resale allocations are separate interpretations retained in the scenario; do not add them to these cash amounts.</p>']
        processing_records = support['versions'].get('statement_pdf_processing_records')
        if processing_records:
            parts += ['<h3>Recorded statement processing</h3>', table(
                ['Source document', 'Page', 'Recorded at', 'Python', 'PDF reader', 'OCR engine'], [
                    [record['source_document_id'], record['page_number'],
                     (record.get('manifest') or {}).get('content', {}).get('recorded_at'),
                     (record.get('manifest') or {}).get('content', {}).get('python_version'),
                     (record.get('manifest') or {}).get('content', {}).get('packages', {}).get('PyMuPDF'),
                     ((record.get('manifest') or {}).get('content', {}).get('tesseract') or {}).get('version')
                     if ((record.get('manifest') or {}).get('content', {}).get('tesseract') or {}).get('status') != 'not_used' else 'Not used']
                    for record in processing_records]),
                '<p>Versions describe the saved extraction, not the computer opening this report. Missing historical records remain not recorded. The support index retains the settings and component hashes where captured.</p>']
        rows=[]
        for method,result in results.items():
            if 'claims' in result:
                for claim,amounts in result['claims'].items():
                    currency=inputs['currency'];rows.append([method.replace('_',' '),claim,currency,
                        money(amounts['root_attributed_minor'],currency),money(amounts['reported_remaining_minor'],currency),
                        money(amounts['withdrawn_without_selected_transfer_minor'],currency)])
            else:
                for claim,amounts in result['outcomes'].items():
                    currency=result['currency'];rows.append([method.replace('_',' '),claim,currency,
                        money(amounts['deposited']['minor_units'],currency),money(amounts['surviving']['minor_units'],currency),
                        money(amounts['withdrawn']['minor_units'],currency)])
        parts += [table(['Selected method','Claim','Currency','Attributed deposit','Reported remaining cash','Withdrawn outside selected transfers'],rows),
            '<h3>Captured limitations</h3><ul>'+''.join('<li>'+text(v)+'</li>' for v in scenario['limitations'])+'</ul>']
    parts += ['<h2>Checking this package</h2><p>The manifest hashes this report and every enclosed file. Use Loupe’s saved-package verifier to check all bytes and recalculate the selected scenarios. Retain the original ZIP and any independently recorded digest. The report does not prove authorship or evidence truth.</p></body></html>']
    html=''.join(parts).replace('</head>', '<style>@page{size:A4;margin:18mm 16mm 20mm;@bottom-left{content:"Loupe - '+marking+'";font:8pt sans-serif}@bottom-right{content:"Page " counter(page);font:8pt sans-serif}}</style></head>')
    result=html.encode('utf-8')
    if len(result)>16*1024*1024: raise LedgerSummaryError('Readable package report exceeds 16 MiB.')
    return result
