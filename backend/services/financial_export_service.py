"""Financial export rendering for PDF and printable HTML fallbacks.

The HTML is a pure function of the transactions, the case name and the filter
description.  Nothing about the machine or the moment enters it -- no clock, no
hostname, no path -- so two exports of an unchanged ledger under the same
filters are byte-identical, and a recipient can establish that the figures have
not moved by comparing a digest instead of reading both documents.

The generation time has not been discarded; it has been moved.  It lives in
``services.financial.export_manifest``, which records the act of exporting --
when, of what, by which version of the code -- separately from the document,
because the export is an event and the document is an exhibit.
"""

from html import escape
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from services.financial.export_manifest import manifest_for


def _esc(val: Any) -> str:
    if val is None:
        return "-"
    s = str(val).strip()
    return escape(s) if s else "-"


def _entity_name(entity: Any) -> str:
    if isinstance(entity, dict):
        return str(entity.get("name") or entity.get("key") or "").strip()
    if entity is None:
        return ""
    return str(entity).strip()


def _provenance_label(transaction: dict) -> str:
    source_type = transaction.get("evidence_source_type")
    source_file = transaction.get("source_filename")
    page = transaction.get("source_page")
    parts = []
    if source_type:
        parts.append(str(source_type).replace("_", " ").title())
    if source_file:
        parts.append(str(source_file))
    if page:
        parts.append(f"p.{page}")
    return " | ".join(parts) if parts else "Source not recorded"


def _group_transactions_for_export(transactions: list[dict]) -> list[dict]:
    """Order rows so children follow their parent, without losing any.

    Two properties matter and only one of them is about ordering.

    The first is that every row handed in comes out.  A row is dropped only
    when its ``key`` has already been emitted, which is the interleave doing
    its job -- a child reached through ``by_parent`` must not appear a second
    time in the sweep at the end.  Rows *without* a key are never suppressed,
    because a missing key is not evidence that two rows are the same row.  The
    earlier version deduplicated on ``tx.get("key")`` directly, so ``None``
    entered the seen set on the first keyless row and every subsequent keyless
    row vanished: three unkeyed transactions exported as one, with the count in
    the header agreeing with the truncated table and nothing anywhere saying a
    row had gone.  Production supplies keys from Neo4j, so this was latent
    rather than active -- but an exhibit that silently omits rows is the exact
    failure this package exists to make impossible, and it should not depend on
    a property of the upstream query staying true.

    The second is that the order is a function of the input alone.  No set is
    iterated to produce output, so two runs over equal input give equal output,
    which is what lets the rendered HTML be byte-identical.
    """
    by_parent: dict[str, list[dict]] = {}
    roots: list[dict] = []

    for tx in transactions:
        parent_key = tx.get("parent_transaction_key")
        if parent_key:
            by_parent.setdefault(parent_key, []).append(tx)
        else:
            roots.append(tx)

    ordered: list[dict] = []
    seen_keys: set[str] = set()
    emitted: set[int] = set()

    def take(tx: dict) -> bool:
        """Emit ``tx`` unless this row, or its key, has already been emitted."""
        if id(tx) in emitted:
            return False
        key = tx.get("key")
        if key is not None:
            if key in seen_keys:
                return False
            seen_keys.add(key)
        ordered.append(tx)
        emitted.add(id(tx))
        return True

    for tx in roots:
        if take(tx):
            for child in by_parent.get(tx.get("key"), []):
                take(child)

    # Anything the walk above could not reach: a child whose parent is absent
    # from this filtered slice, most often.  Tracked by identity rather than by
    # equality, because two rows that happen to carry identical values are two
    # rows -- a pair of matching cash withdrawals is ordinary, not a duplicate.
    for tx in transactions:
        take(tx)

    return ordered


def _record_amount(value):
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _currency_label(value):
    return str(value or '').strip().upper() or 'Currency not recorded'


def _amount_label(value, currency):
    amount = _record_amount(value)
    return f'{amount:,.2f} {_currency_label(currency)}' if amount is not None else 'Amount not recorded'


def _currency_summary(transactions):
    groups = {}
    for row in transactions:
        currency = _currency_label(row.get('currency'))
        group = groups.setdefault(currency, dict(count=0, positive=Decimal(0), negative=Decimal(0), missing=0))
        group['count'] += 1
        amount = _record_amount(row.get('amount'))
        if amount is None:
            group['missing'] += 1
        elif amount >= 0:
            group['positive'] += amount
        else:
            group['negative'] += amount
    rows = []
    for currency, group in sorted(groups.items()):
        can_total = bool(re.fullmatch(r'[A-Z]{3}', currency)) and not group['missing']
        cells = [f'{group[k]:,.2f}' if can_total else 'Not totalled' for k in ('positive', 'negative')]
        net = f"{group['positive'] + group['negative']:,.2f}" if can_total else 'Not totalled'
        rows.append(f'<tr><td class="cell">{_esc(currency)}</td><td class="cell">{group["count"]}</td>'
                    + ''.join(f'<td class="cell" style="text-align:right">{v}</td>' for v in [*cells, net]) + '</tr>')
    return '<table class="report-table"><thead><tr><th class="th">Currency</th><th class="th">Records</th><th class="th">Positive amounts</th><th class="th">Negative amounts</th><th class="th">Sum of amounts</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'


def _render_entity_flow_section(entity_flow: dict | None) -> str:
    if not entity_flow:
        return ""

    senders = entity_flow.get("senders") or []
    beneficiaries = entity_flow.get("beneficiaries") or []
    if not senders and not beneficiaries:
        return ""

    def render_rows(rows: list[dict]) -> str:
        if not rows:
            return '<tr><td class="cell" colspan="3">No entities in current view.</td></tr>'
        return "".join(
            f"""
            <tr>
                <td class="cell">{_esc(row.get("name"))}</td>
                <td class="cell" style="text-align: right;">{int(row.get("count") or 0)}</td>
                <td class="cell" style="text-align: right;">{_esc(_amount_label(row.get("totalAmount"), row.get("currency"))) if row.get("currency") else "Not totalled"}</td>
            </tr>
            """
            for row in rows[:10]
        )

    return f"""
    <div class="analysis-grid">
        <div class="panel">
            <div class="panel-title">Senders</div>
            <table class="compact-table">
                <thead>
                    <tr>
                        <th class="th">Entity</th>
                        <th class="th" style="text-align: right;">Records</th>
                        <th class="th" style="text-align: right;">Amount</th>
                    </tr>
                </thead>
                <tbody>{render_rows(senders)}</tbody>
            </table>
        </div>
        <div class="panel">
            <div class="panel-title">Beneficiaries</div>
            <table class="compact-table">
                <thead>
                    <tr>
                        <th class="th">Entity</th>
                        <th class="th" style="text-align: right;">Records</th>
                        <th class="th" style="text-align: right;">Amount</th>
                    </tr>
                </thead>
                <tbody>{render_rows(beneficiaries)}</tbody>
            </table>
        </div>
    </div>
    """


def build_financial_export_html(
    transactions: list[dict],
    case_name: str,
    filters_description: str = "",
    entity_notes: list[dict] | None = None,
    entity_flow: dict | None = None,
    dataset_mode: str = "transactions",
) -> str:
    ordered_transactions = _group_transactions_for_export(transactions)
    total_count = len(ordered_transactions)
    report_title = 'Other financial records' if dataset_mode == 'intelligence' else 'Financial records report'
    currency_summary = _currency_summary(ordered_transactions)

    categories: dict[str, int] = {}
    for t in ordered_transactions:
        cat = t.get("category") or t.get("financial_category") or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    category_summary = ", ".join(
        f"{cat}: {count}" for cat, count in sorted(categories.items())
    )

    rows_html = ""
    for i, t in enumerate(ordered_transactions):
        amount_color = "#0f172a"
        amount_str = _esc(_amount_label(t.get("amount"), t.get("currency")))
        corrected_marker = ""
        if t.get("amount_corrected"):
            corrected_marker = (
                ' <span style="color: #d97706; font-size: 10px;" '
                'title="Manually corrected">&#9998;</span>'
            )

        background = "#f8fafc" if i % 2 == 0 else "#ffffff"
        is_child = bool(t.get("parent_transaction_key"))
        if is_child:
            background = "#eef2ff"
        elif t.get("is_parent"):
            background = "#f1f5f9"

        purpose = t.get("purpose") or t.get("notes") or ""
        summary = t.get("summary") or ""
        details_parts = []
        if purpose:
            details_parts.append(_esc(purpose))
        if summary and summary != purpose:
            details_parts.append(
                f'<span style="color: #475569; font-style: italic;">[AI] {_esc(summary)}</span>'
            )
        if t.get('amount_corrected'):
            details_parts.append('Original amount: ' + _esc(_amount_label(t.get('original_amount'), t.get('currency'))))
            details_parts.append('Latest correction: ' + _esc(t.get('correction_reason') or 'Explanation not recorded'))
        details_html = "<br>".join(details_parts) if details_parts else "-"

        rows_html += f"""
        <tr style="background: {background};">
            <td class="cell">{_esc(t.get("date"))}</td>
            <td class="cell{' parent-row' if t.get('is_parent') else ''}" style="padding-left: {'24px' if is_child else '8px'};">
                {'&#8627; ' if is_child else ''}{_esc(t.get("name"))}<br><small>Record: {_esc(t.get("key"))}</small>
            </td>
            <td class="cell">{_esc(_entity_name(t.get("from_entity")))}</td>
            <td class="cell">{_esc(_entity_name(t.get("to_entity")))}</td>
            <td class="cell" style="font-family: monospace; color: {amount_color}; text-align: right;">
                {amount_str}{corrected_marker}
            </td>
            <td class="cell">{_esc(t.get("category") or t.get("financial_category") or "Uncategorized")}</td>
            <td class="cell">{_esc(_provenance_label(t))}</td>
            <td class="cell details">{details_html}</td>
        </tr>
        """

    footnote_html = ""
    if any(t.get("amount_corrected") for t in ordered_transactions):
        footnote_html = """
        <div class="callout warning">
            <strong>&#9998; Manually Corrected Amounts</strong>
            Original amounts and the latest correction explanations appear beside the corrected records.
        </div>
        """

    entity_notes_html = ""
    if entity_notes:
        rows = []
        for entry in entity_notes:
            if not entry.get("notes") and not entry.get("summary"):
                continue
            details = []
            if entry.get("notes"):
                details.append(_esc(entry.get("notes")))
            if entry.get("summary"):
                details.append(
                    f'<span style="color: #475569; font-style: italic;">[AI] {_esc(entry.get("summary"))}</span>'
                )
            rows.append(
                f"""
                <tr>
                    <td class="cell" style="font-weight: 600;">{_esc(entry.get("name"))}</td>
                    <td class="cell">{_esc(entry.get("type"))}</td>
                    <td class="cell details">{'<br>'.join(details) if details else '-'}</td>
                </tr>
                """
            )
        if rows:
            entity_notes_html = f"""
            <div style="page-break-before: always;"></div>
            <div class="section-title">Entity Notes &amp; Summaries</div>
            <table class="report-table">
                <thead>
                    <tr>
                        <th class="th" style="width: 25%;">Entity Name</th>
                        <th class="th" style="width: 15%;">Type</th>
                        <th class="th">Notes / AI Summary</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
            """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: A4 landscape;
                margin: 1.2cm;
                @bottom-center {{
                    content: "Financial records | Page " counter(page) " of " counter(pages);
                    font-size: 9px;
                    color: #64748b;
                }}
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                color: #1e293b;
                margin: 0;
                padding: 0;
            }}
            thead {{ display: table-header-group; }}
            tr {{ page-break-inside: avoid; }}
            .hero {{
                background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
                color: white;
                padding: 14px 18px;
                border-radius: 10px;
                margin-bottom: 16px;
            }}
            .report-note {{ font-size: 11px; line-height: 1.35; margin: 8px 0; }}
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 12px;
                margin-bottom: 14px;
            }}
            .summary-card {{
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 9px 12px;
            }}
            .analysis-grid {{
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 12px;
                margin-bottom: 16px;
            }}
            .panel {{
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                overflow: hidden;
            }}
            .panel-title, .section-title {{
                font-size: 14px;
                font-weight: 700;
                margin-bottom: 8px;
                color: #0f172a;
            }}
            .panel-title {{
                margin: 0;
                padding: 10px 12px;
                background: #f8fafc;
                border-bottom: 1px solid #e2e8f0;
            }}
            .report-table, .compact-table {{
                width: 100%;
                border-collapse: collapse;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                overflow: hidden;
            }}
            .compact-table {{
                border: none;
            }}
            .cell {{
                padding: 6px 8px;
                border-bottom: 1px solid #e2e8f0;
                font-size: 10px;
                vertical-align: top;
            }}
            .details {{
                line-height: 1.45;
                max-width: 280px;
                overflow-wrap: break-word;
            }}
            .th {{
                padding: 7px 8px;
                text-align: left;
                font-size: 10px;
                font-weight: 600;
                background: #1e3a5f;
                color: white;
            }}
            .callout {{
                margin-top: 14px;
                padding: 10px 14px;
                border-radius: 8px;
                font-size: 10px;
            }}
            .warning {{
                background: #fffbeb;
                border: 1px solid #fde68a;
                color: #92400e;
            }}
            .filters {{
                font-size: 11px;
                color: #475569;
                margin-bottom: 14px;
                padding: 8px 12px;
                background: #f8fafc;
                border-left: 3px solid #3b82f6;
                border-radius: 4px;
            }}
            .parent-row {{
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="hero">
            <div style="font-size: 20px; font-weight: 700; margin-bottom: 4px;">{report_title}</div>
            <div style="font-size: 13px; opacity: 0.86;">{_esc(case_name)}</div>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase;">Records</div>
                <div style="font-size: 19px; font-weight: 700;">{total_count}</div>
            </div>
            <div class="summary-card">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase;">Categories</div>
                <div style="font-size: 11px; margin-top: 4px;">{_esc(category_summary or "None")}</div>
            </div>
        </div>

        {f'<div class="filters">Active filters: {_esc(filters_description)}</div>' if filters_description else ''}

        <p class="report-note">These amounts are recorded in the selected evidence. Positive and negative signs are retained. A sign alone does not identify money paid in or out.</p>
        {currency_summary}
        <p class="report-note">Different currencies remain separate. Missing currencies or amounts are not totalled. These sums are not account balances.</p>
        {_render_entity_flow_section(entity_flow)}

        <table class="report-table">
            <thead>
                <tr>
                    <th class="th" style="width: 8%;">Date</th>
                    <th class="th" style="width: 16%;">Name</th>
                    <th class="th" style="width: 12%;">Sender</th>
                    <th class="th" style="width: 12%;">Beneficiary</th>
                    <th class="th" style="width: 9%; text-align: right;">Amount</th>
                    <th class="th" style="width: 10%;">Category</th>
                    <th class="th" style="width: 14%;">Original source</th>
                    <th class="th">Details / AI Summary</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>

        {footnote_html}
        {entity_notes_html}
    </body>
    </html>
    """


def generate_financial_pdf(
    transactions: list[dict],
    case_name: str,
    filters_description: str = "",
    entity_notes: list[dict] | None = None,
    entity_flow: dict | None = None,
    dataset_mode: str = "transactions",
) -> bytes:
    html = build_financial_export_html(
        transactions,
        case_name,
        filters_description=filters_description,
        entity_notes=entity_notes,
        entity_flow=entity_flow,
        dataset_mode=dataset_mode,
    )
    import weasyprint

    return weasyprint.HTML(string=html).write_pdf()


def render_financial_export(
    transactions: list[dict],
    case_name: str,
    filters_description: str = "",
    entity_notes: list[dict] | None = None,
    entity_flow: dict | None = None,
    dataset_mode: str = "transactions",
) -> dict:
    """Render the export, and describe the act of rendering it.

    The returned ``manifest`` is the record a recipient checks against.  It is
    returned rather than persisted here because this function does not know
    whether it is serving a download, a preview or a replay, and only the
    caller does; persisting every preview would fill the record with acts that
    never reached anybody.

    Note what the manifest's digest covers: the HTML, always, even when the
    ``content`` handed back is a PDF.  The HTML is what this code determines;
    the PDF adds a creation date and a document id of weasyprint's own, so its
    bytes differ run to run for reasons that say nothing about the figures.
    ``manifest.digest_covers`` states this, so a recipient handed a PDF is not
    left to discover by experiment that hashing it disagrees.
    """
    html = build_financial_export_html(
        transactions,
        case_name,
        filters_description=filters_description,
        entity_notes=entity_notes,
        entity_flow=entity_flow,
        dataset_mode=dataset_mode,
    )
    manifest = manifest_for(
        html,
        case_name=case_name,
        filters_description=filters_description,
        # The count of rows *in the document*, which is what the manifest
        # describes -- not the count handed in.  The two differ when the input
        # carries the same key twice, and a manifest asserting a number the
        # document's own header contradicts would be worse than no number.
        transaction_count=len(_group_transactions_for_export(transactions)),
    )
    try:
        import weasyprint

        return {
            "content": weasyprint.HTML(string=html).write_pdf(),
            "media_type": "application/pdf",
            "extension": "pdf",
            "manifest": manifest,
        }
    except Exception:
        return {
            "content": html.encode("utf-8"),
            "media_type": "text/html; charset=utf-8",
            "extension": "html",
            "manifest": manifest,
        }
