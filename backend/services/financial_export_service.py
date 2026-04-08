"""
Financial export rendering for PDF and printable HTML fallbacks.
"""

from datetime import datetime
from html import escape
from typing import Any


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
    return " | ".join(parts) if parts else "Legacy"


def _group_transactions_for_export(transactions: list[dict]) -> list[dict]:
    by_parent: dict[str, list[dict]] = {}
    parent_keys = set()
    roots: list[dict] = []

    for tx in transactions:
        parent_key = tx.get("parent_transaction_key")
        if parent_key:
            by_parent.setdefault(parent_key, []).append(tx)
        else:
            roots.append(tx)
            if tx.get("is_parent"):
                parent_keys.add(tx.get("key"))

    ordered: list[dict] = []
    seen_keys: set[str] = set()

    for tx in roots:
        key = tx.get("key")
        if key in seen_keys:
            continue
        ordered.append(tx)
        seen_keys.add(key)
        for child in by_parent.get(key, []):
            child_key = child.get("key")
            if child_key in seen_keys:
                continue
            ordered.append(child)
            seen_keys.add(child_key)

    for tx in transactions:
        key = tx.get("key")
        if key not in seen_keys:
            ordered.append(tx)
            seen_keys.add(key)

    return ordered


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
                <td class="cell" style="text-align: right;">${float(row.get("totalAmount") or 0):,.2f}</td>
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
                        <th class="th" style="text-align: right;">Txns</th>
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
                        <th class="th" style="text-align: right;">Txns</th>
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
) -> str:
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    ordered_transactions = _group_transactions_for_export(transactions)
    total_count = len(ordered_transactions)
    total_value = sum(abs(float(t.get("amount") or 0)) for t in ordered_transactions)
    money_out = sum(
        abs(float(t.get("amount") or 0))
        for t in ordered_transactions
        if float(t.get("amount") or 0) >= 0
    )
    money_in = sum(
        abs(float(t.get("amount") or 0))
        for t in ordered_transactions
        if float(t.get("amount") or 0) < 0
    )

    categories: dict[str, int] = {}
    for t in ordered_transactions:
        cat = t.get("category") or t.get("financial_category") or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    category_summary = ", ".join(
        f"{cat}: {count}" for cat, count in sorted(categories.items())
    )

    rows_html = ""
    for i, t in enumerate(ordered_transactions):
        amount_val = float(t.get("amount") or 0)
        amount_color = "#dc2626" if amount_val >= 0 else "#16a34a"
        amount_str = f"${abs(amount_val):,.2f}"
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
        details_html = "<br>".join(details_parts) if details_parts else "-"

        rows_html += f"""
        <tr style="background: {background};">
            <td class="cell">{_esc(t.get("date"))}</td>
            <td class="cell{' parent-row' if t.get('is_parent') else ''}" style="padding-left: {'24px' if is_child else '8px'};">
                {'&#8627; ' if is_child else ''}{_esc(t.get("name"))}
            </td>
            <td class="cell">{_esc(_entity_name(t.get("from_entity")))}</td>
            <td class="cell">{_esc(_entity_name(t.get("to_entity")))}</td>
            <td class="cell" style="font-family: monospace; color: {amount_color}; text-align: right; white-space: nowrap;">
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
            Original values are preserved on file for audit purposes.
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
                    content: "Attorney-Client Privileged | Page " counter(page) " of " counter(pages);
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
                padding: 18px 22px;
                border-radius: 10px;
                margin-bottom: 16px;
            }}
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(5, minmax(0, 1fr));
                gap: 12px;
                margin-bottom: 14px;
            }}
            .summary-card {{
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px 14px;
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
            <div style="font-size: 20px; font-weight: 700; margin-bottom: 4px;">Financial Analysis Report</div>
            <div style="font-size: 13px; opacity: 0.86;">{_esc(case_name)}</div>
            <div style="font-size: 11px; opacity: 0.72; margin-top: 6px;">Generated: {now}</div>
            <div style="font-size: 10px; opacity: 0.65; margin-top: 2px;">ATTORNEY-CLIENT PRIVILEGED AND CONFIDENTIAL</div>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase;">Transactions</div>
                <div style="font-size: 19px; font-weight: 700;">{total_count}</div>
            </div>
            <div class="summary-card">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase;">Money Out</div>
                <div style="font-size: 18px; font-weight: 700; color: #dc2626;">${money_out:,.2f}</div>
            </div>
            <div class="summary-card">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase;">Money In</div>
                <div style="font-size: 18px; font-weight: 700; color: #16a34a;">${money_in:,.2f}</div>
            </div>
            <div class="summary-card">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase;">Total Value</div>
                <div style="font-size: 18px; font-weight: 700;">${total_value:,.2f}</div>
            </div>
            <div class="summary-card">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase;">Categories</div>
                <div style="font-size: 11px; margin-top: 4px;">{_esc(category_summary or "None")}</div>
            </div>
        </div>

        {f'<div class="filters">Active filters: {_esc(filters_description)}</div>' if filters_description else ''}

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
                    <th class="th" style="width: 14%;">Provenance</th>
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
) -> bytes:
    html = build_financial_export_html(
        transactions,
        case_name,
        filters_description=filters_description,
        entity_notes=entity_notes,
        entity_flow=entity_flow,
    )
    import weasyprint

    return weasyprint.HTML(string=html).write_pdf()


def render_financial_export(
    transactions: list[dict],
    case_name: str,
    filters_description: str = "",
    entity_notes: list[dict] | None = None,
    entity_flow: dict | None = None,
) -> dict:
    html = build_financial_export_html(
        transactions,
        case_name,
        filters_description=filters_description,
        entity_notes=entity_notes,
        entity_flow=entity_flow,
    )
    try:
        import weasyprint

        return {
            "content": weasyprint.HTML(string=html).write_pdf(),
            "media_type": "application/pdf",
            "extension": "pdf",
        }
    except Exception:
        return {
            "content": html.encode("utf-8"),
            "media_type": "text/html; charset=utf-8",
            "extension": "html",
        }
