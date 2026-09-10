"""Paginated report from captured ledger bytes, with no external resource access."""
import json
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES
MAX_PDF_READINGS = 2000


def render_ledger_pdf(snapshot, html):
    if len(json.loads(snapshot.content)['ledger']['readings']) > MAX_PDF_READINGS:
        raise LedgerSummaryError('PDF reports support up to 2,000 captured readings. Narrow the export scope; no partial report was generated.')
    from weasyprint import HTML, CSS
    def deny_resource(url, *args, **kwargs):
        raise ValueError('Ledger PDF reports cannot load external or local resources.')
    html = html.replace('<h1>Loupe ledger report</h1>', '<h1>Loupe ledger report</h1><p>This PDF presents the captured readings, totals, decision reasons and reviewed statement controls. Full original values, source coordinates and machine-readable review chains are retained in the accompanying HTML and JSON files.</p>')
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
    content = HTML(string=html, url_fetcher=deny_resource).write_pdf(stylesheets=[styles])
    if len(content) > MAX_EXPORT_BYTES:
        raise LedgerSummaryError('PDF report exceeds 16 MiB. Narrow the scope; no partial PDF was generated.')
    return content
