"""
Financial Export Service — Generates PDF reports for financial transactions.

Designed for print-friendly output suitable for attorney-client meetings
where laptops and internet are unavailable (e.g., jail visits).
"""
from datetime import datetime
from html import escape


def _esc(val):
    """Safely escape a value for HTML, returning '-' for empty/None."""
    if val is None:
        return "-"
    s = str(val).strip()
    return escape(s) if s else "-"


def generate_financial_pdf(
    transactions: list,
    case_name: str,
    filters_description: str = "",
    entity_notes: list = None,
) -> bytes:
    """Generate a financial transactions PDF report.

    Args:
        transactions: List of transaction dicts with keys: date, time, name, amount,
                      financial_category, from_entity, to_entity, purpose, notes,
                      summary, amount_corrected, original_amount, correction_reason
        case_name: Name of the case for the header
        filters_description: Description of active filters applied
        entity_notes: Optional list of dicts {name, type, notes, summary} for entity
                      notes appendix

    Returns:
        PDF bytes
    """
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    total_count = len(transactions)
    total_value = sum(abs(float(t.get("amount") or 0)) for t in transactions)

    # Net inflows / outflows
    total_in = sum(float(t.get("amount") or 0) for t in transactions if float(t.get("amount") or 0) > 0)
    total_out = sum(abs(float(t.get("amount") or 0)) for t in transactions if float(t.get("amount") or 0) < 0)

    categories = {}
    for t in transactions:
        cat = t.get("financial_category") or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1

    category_summary = ", ".join(f"{cat}: {count}" for cat, count in sorted(categories.items()))

    corrected_rows = [t for t in transactions if t.get("amount_corrected")]

    # Build transaction rows
    rows_html = ""
    for i, t in enumerate(transactions):
        amount_val = float(t.get("amount") or 0)
        amount_color = "#16a34a" if amount_val >= 0 else "#dc2626"
        abs_amount = abs(amount_val)
        amount_str = f"${abs_amount:,.2f}" if amount_val >= 0 else f"-${abs_amount:,.2f}"

        corrected_marker = ""
        if t.get("amount_corrected"):
            corrected_marker = ' <span style="color: #d97706; font-size: 10px;" title="Manually corrected">&#9998;</span>'

        from_name = ""
        if isinstance(t.get("from_entity"), dict):
            from_name = t["from_entity"].get("name", "")
        elif isinstance(t.get("from_entity"), str):
            from_name = t["from_entity"]

        to_name = ""
        if isinstance(t.get("to_entity"), dict):
            to_name = t["to_entity"].get("name", "")
        elif isinstance(t.get("to_entity"), str):
            to_name = t["to_entity"]

        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"

        is_child = t.get("parent_transaction_key")
        name_prefix = "&#8627; " if is_child else ""
        indent_style = "padding-left: 24px;" if is_child else ""

        # Transaction name / description
        tx_name = _esc(t.get("name"))

        # Notes/Purpose + AI Summary combined
        purpose = t.get("purpose") or t.get("notes") or ""
        summary = t.get("summary") or ""
        details_parts = []
        if purpose:
            details_parts.append(_esc(purpose))
        if summary and summary != purpose:
            details_parts.append(f'<span style="color: #6366f1; font-style: italic;">[AI] {_esc(summary)}</span>')
        details_html = "<br>".join(details_parts) if details_parts else "-"

        rows_html += f"""
        <tr style="background: {bg};">
            <td class="cell">{_esc(t.get("date"))}</td>
            <td class="cell" style="{indent_style}">{name_prefix}{_esc(tx_name)}</td>
            <td class="cell">{_esc(from_name)}</td>
            <td class="cell">{_esc(to_name)}</td>
            <td class="cell" style="font-family: monospace; color: {amount_color}; text-align: right; white-space: nowrap;">{amount_str}{corrected_marker}</td>
            <td class="cell">{_esc(t.get("financial_category"))}</td>
            <td class="cell details">{details_html}</td>
        </tr>
        """

    footnote_html = ""
    if corrected_rows:
        footnote_html = """
        <div style="margin-top: 16px; padding: 10px 14px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; font-size: 10px; color: #92400e;">
            <strong>&#9998; Manually Corrected Amounts</strong> — Original values preserved on file for audit purposes.
        </div>
        """

    # Entity notes appendix
    entity_notes_html = ""
    if entity_notes:
        notes_with_content = [e for e in entity_notes if e.get("notes") or e.get("summary")]
        if notes_with_content:
            entity_rows = ""
            for i, e in enumerate(notes_with_content):
                bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
                name = _esc(e.get("name"))
                etype = _esc(e.get("type"))
                enotes = _esc(e.get("notes")) if e.get("notes") else ""
                esummary = e.get("summary") or ""

                details = []
                if enotes and enotes != "-":
                    details.append(enotes)
                if esummary:
                    details.append(f'<span style="color: #6366f1; font-style: italic;">[AI] {_esc(esummary)}</span>')
                details_str = "<br>".join(details) if details else "-"

                entity_rows += f"""
                <tr style="background: {bg};">
                    <td class="cell" style="font-weight: 600;">{name}</td>
                    <td class="cell">{etype}</td>
                    <td class="cell details">{details_str}</td>
                </tr>
                """

            entity_notes_html = f"""
            <div style="page-break-before: always;"></div>
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); color: white; padding: 16px 24px; border-radius: 8px; margin-bottom: 16px; margin-top: 24px;">
                <div style="font-size: 16px; font-weight: 700;">Entity Notes &amp; Summaries</div>
                <div style="font-size: 11px; opacity: 0.7; margin-top: 4px;">{len(notes_with_content)} entities with notes or AI summaries</div>
            </div>
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
                <thead>
                    <tr style="background: #1e3a5f; color: white;">
                        <th class="th" style="width: 20%;">Entity Name</th>
                        <th class="th" style="width: 10%;">Type</th>
                        <th class="th" style="width: 70%;">Notes / AI Summary</th>
                    </tr>
                </thead>
                <tbody>
                    {entity_rows}
                </tbody>
            </table>
            """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: A4 landscape;
                margin: 1.5cm;
                @bottom-center {{
                    content: "Attorney-Client Privileged — Page " counter(page) " of " counter(pages);
                    font-size: 9px;
                    color: #64748b;
                }}
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                color: #1e293b;
                margin: 0;
                padding: 0;
            }}
            .cell {{
                padding: 5px 8px;
                border-bottom: 1px solid #e2e8f0;
                font-size: 10px;
                vertical-align: top;
            }}
            .details {{
                max-width: 260px;
                word-wrap: break-word;
                overflow-wrap: break-word;
                line-height: 1.4;
            }}
            .th {{
                padding: 7px 8px;
                text-align: left;
                font-size: 10px;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); color: white; padding: 20px 24px; border-radius: 8px; margin-bottom: 16px;">
            <div style="font-size: 20px; font-weight: 700; margin-bottom: 4px;">Financial Transaction Report</div>
            <div style="font-size: 13px; opacity: 0.85;">{_esc(case_name)}</div>
            <div style="font-size: 11px; opacity: 0.7; margin-top: 6px;">Generated: {now}</div>
            <div style="font-size: 10px; opacity: 0.6; margin-top: 2px;">ATTORNEY-CLIENT PRIVILEGED AND CONFIDENTIAL</div>
        </div>

        <!-- Summary -->
        <div style="display: flex; gap: 12px; margin-bottom: 16px;">
            <div style="flex: 1; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Transactions</div>
                <div style="font-size: 20px; font-weight: 700; color: #0f172a;">{total_count}</div>
            </div>
            <div style="flex: 1; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Total Value</div>
                <div style="font-size: 20px; font-weight: 700; color: #0f172a;">${total_value:,.2f}</div>
            </div>
            <div style="flex: 1; background: #dcfce7; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #16a34a; text-transform: uppercase; letter-spacing: 0.5px;">Inflows</div>
                <div style="font-size: 16px; font-weight: 700; color: #16a34a;">${total_in:,.2f}</div>
            </div>
            <div style="flex: 1; background: #fef2f2; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #dc2626; text-transform: uppercase; letter-spacing: 0.5px;">Outflows</div>
                <div style="font-size: 16px; font-weight: 700; color: #dc2626;">-${total_out:,.2f}</div>
            </div>
            <div style="flex: 2; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Categories</div>
                <div style="font-size: 11px; color: #334155; margin-top: 4px;">{category_summary or "None"}</div>
            </div>
        </div>

        {f'<div style="font-size: 11px; color: #64748b; margin-bottom: 12px; padding: 8px 12px; background: #f8fafc; border-radius: 4px; border-left: 3px solid #3b82f6;">Active filters: {_esc(filters_description)}</div>' if filters_description else ''}

        <!-- Transaction Table -->
        <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
            <thead>
                <tr style="background: #1e3a5f; color: white;">
                    <th class="th" style="width: 8%;">Date</th>
                    <th class="th" style="width: 14%;">Name</th>
                    <th class="th" style="width: 12%;">From</th>
                    <th class="th" style="width: 12%;">To</th>
                    <th class="th" style="text-align: right; width: 9%;">Amount</th>
                    <th class="th" style="width: 10%;">Category</th>
                    <th class="th" style="width: 35%;">Details / AI Summary</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        {footnote_html}

        {entity_notes_html}
    </body>
    </html>
    """

    try:
        import weasyprint
    except ImportError:
        raise RuntimeError(
            "WeasyPrint is not installed. Install it with: pip install weasyprint "
            "(requires system dependencies: Cairo, Pango, GDK-PixBuf)"
        )
    return weasyprint.HTML(string=html).write_pdf()
