"""Readable index derived from captured review inputs, without combining their scopes."""
import json
from html import escape
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.money import Money


def render_review_package_report(*, case_id, scenarios, supports, preparation=None, ledger=None, measurement=None):
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
        parts += ['<li><a href="ledger/original-export.zip">Original ledger export</a> — open this ZIP separately for its captured report and any selected original source files.</li>']
    for i in range(len(scenarios)):
        prefix=f'scenarios/{i+1:02d}/'
        parts += ['<li>Scenario '+str(i+1)+': <a href="'+prefix+'scenario.json">original scenario</a>, <a href="'+prefix+'replay.json">recalculation check</a>, <a href="'+prefix+'expert-support.json">methods, versions and support index</a>.</li>']
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
        parts += ['<h2>Attached ledger and case history</h2>',table(['Captured item','Count or scope'],[
            ['Included ledger readings',ledger['ledger'].get('included_rows')],['Excluded ledger readings',ledger['ledger'].get('excluded_rows')],
            ['Wider case history','Attached' if history is not None else 'Not selected'],
            ['Case custody reports',len(custody['events']) if custody is not None else 'Not captured'],
            ['Case financial decisions',len(history['decisions']) if history is not None and 'decisions' in history else 'Not captured'],
            ['Recorded audit events',audit['verification']['event_count'] if audit else 'Not captured']]),
            '<p>These counts describe the attached capture. They are not a completeness finding or the current live case state.</p>']
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
            '<p>Conditional cash results under each selected method. Asset/resale allocations are separate interpretations retained in the scenario; do not add them to these cash amounts.</p>']
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
