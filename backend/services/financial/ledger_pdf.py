"""Paginated report from captured ledger bytes, with no external resource access."""
import json
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES
MAX_PDF_READINGS = 2000
PDF_READINGS_REFUSAL = 'PDF reports support up to 2,000 captured readings. Narrow the export scope; no partial report was generated.'


def refuse_over_limit_scope(session, **scope):
    """One PDF holds up to MAX_PDF_READINGS captured readings: a scope counted past that is refused before any
    capture, in the render-time refusal's own words, so no caller pays a whole capture for a refusal a count
    already knows. A scope past the summary's own row limit is left to the capture, whose refusal names that
    larger bound; the render-time check still guards a scope that grows past the limit after this count."""
    from services.financial.ledger_summary import MAX_SUMMARY_ROWS, scope_reading_count
    count = scope_reading_count(session, **scope)
    if MAX_PDF_READINGS < count <= MAX_SUMMARY_ROWS:
        raise LedgerSummaryError(PDF_READINGS_REFUSAL)


def render_ledger_pdf(snapshot, html, *, part_words=None):
    """``part_words``: one numbered part of a larger report (numbered_report_parts), stated on its first page. A part
    is bounded by readings, so the 16 MiB allowance of a synchronous download does not apply to it."""
    if len(json.loads(snapshot.content)['ledger']['readings']) > MAX_PDF_READINGS:
        raise LedgerSummaryError(PDF_READINGS_REFUSAL)
    from weasyprint import HTML, CSS
    def deny_resource(url, *args, **kwargs):
        raise ValueError('Ledger PDF reports cannot load external or local resources.')
    if part_words:
        from html import escape
        html = html.replace('<h1>Loupe ledger report</h1>', '<h1>Loupe ledger report</h1><p><strong>' + escape(part_words) + '</strong></p>')
    html = html.replace('<h1>Loupe ledger report</h1>', '<h1>Loupe ledger report</h1><p>This PDF presents the captured readings, totals, decision reasons and reviewed statement controls. Full original values, source coordinates and machine-readable review chains are retained in the accompanying HTML and JSON files.</p>')
    marking = json.loads(snapshot.content).get('export_context',{}).get('privilege_marking','unmarked')
    label = {'unmarked':'No privilege marking selected','confidential':'Confidential','privileged_confidential':'Privileged and confidential'}.get(marking)
    if label is None:raise LedgerSummaryError('Unrecognized captured export marking.')
    styles = CSS(string='''
        @page { size: A4; margin: 18mm 16mm 20mm;
          @bottom-left { content: "Loupe · Captured ledger report"; font: 8pt sans-serif; color: #556; }
          @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt sans-serif; color: #556; }
        }
        body { font: 9pt sans-serif; line-height: 1.4; margin: 0; padding: 0; max-width: none; }
        h1 { font-size: 22pt; color: #a51b34; }
        h2 { font-size: 14pt; margin-top: 18pt; break-after: avoid; }
        h3, summary { break-after: avoid; }
        table { table-layout: fixed; font-size: 8pt; width: 100%; }
        td, th { padding: 5pt; overflow-wrap: anywhere; vertical-align: top; }
        th { background: #eef1f5; }
        thead { display: table-header-group; }
        tr { break-inside: avoid; }
        pre { font: 7pt monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
        details { display: none !important; }
        code { overflow-wrap: anywhere; }
        article { margin-top: 12pt; padding-top: 10pt; }
    ''')
    marking_style = CSS(string='@page { @bottom-left { content: "Loupe - ' + label + '"; font: 8pt sans-serif; color: #556; } }')
    content = HTML(string=html, url_fetcher=deny_resource).write_pdf(stylesheets=[styles,marking_style])
    if not part_words and len(content) > MAX_EXPORT_BYTES:
        raise LedgerSummaryError('PDF report exceeds 16 MiB. Narrow the scope; no partial PDF was generated.')
    return content


# Captured once for the whole report; part 1 carries them and every other part says so.
FIRST_PART_ONLY = ('investigation_notes', 'exhibit_assessment', 'pdf_review_history', 'case_financial_history')


def numbered_report_parts(snapshot):
    """Yield (number, of, document, words) covering every captured reading exactly once, in date order, at most
    MAX_PDF_READINGS each. The totals in every part are those of the whole scope; decisions go with their payments."""
    document = json.loads(snapshot.content)
    ledger = document['ledger']
    ordered = sorted(ledger['readings'], key=lambda reading: (reading['row']['ordering_date'], reading['row']['key']))
    chunks = [ordered[start:start + MAX_PDF_READINGS] for start in range(0, len(ordered), MAX_PDF_READINGS)] or [[]]
    decisions = {}
    for decision in document.get('decisions', []):
        decisions.setdefault(decision['subject_id'] if decision['subject_type'] == 'transaction' else None, []).append(decision)
    first = 1
    for number, chunk in enumerate(chunks, 1):
        keys = {reading['row']['key'] for reading in chunk}
        part = {**document, 'ledger': {**ledger, 'readings': chunk},
                'decisions': (decisions.get(None, []) if number == 1 else []) + [d for key in sorted(keys) for d in decisions.get(key, [])]}
        if number > 1:
            for name in FIRST_PART_ONLY:
                part.pop(name, None)
        last = first + len(chunk) - 1
        words = ('Part %d of %d: payments %s to %s of %s, in date order%s. All %d parts together cover every captured payment; '
                 'the totals in each part are those of the whole scope.%s') % (
            number, len(chunks), format(first, ','), format(last, ','), format(len(ordered), ','),
            ' (%s to %s)' % (chunk[0]['row']['ordering_date'], chunk[-1]['row']['ordering_date']) if chunk else '', len(chunks),
            '' if number == 1 else ' Notes, the exhibit assessment and review history are in part 1.')
        yield number, len(chunks), part, words
        first = last + 1
