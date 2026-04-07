"""
Financial Export Service — Generates PDF reports for financial transactions.

Designed for print-friendly output suitable for attorney-client meetings
where laptops and internet are unavailable (e.g., jail visits).

Renders to a real PDF via WeasyPrint, with proper page breaks, repeating
table headers, and a compact layout. Falls back to printable HTML if
WeasyPrint isn't available.

Per user feedback (Apr 2026):
  - Show two clear numbers: Money Out (positive amounts) and Money In (negative).
  - Drop confusing directional inflow/outflow visualisations.
  - From/To tables only show entities present in the filtered view.
  - Generate native PDF (server-side) instead of browser-print HTML.
"""
from datetime import datetime
from html import escape


def _esc(val):
    """Safely escape a value for HTML, returning '-' for empty/None."""
    if val is None:
        return "-"
    s = str(val).strip()
    return escape(s) if s else "-"


def _fmt_amount(val):
    """Format a number as $X,XXX.XX."""
    try:
        v = float(val)
        return f"${v:,.2f}"
    except (TypeError, ValueError):
        return "-"


def _bar_width(value, max_value):
    """Calculate bar width percentage for inline chart."""
    if not max_value or max_value == 0:
        return 0
    return min(100, max(2, (value / max_value) * 100))


# Palette for categories in the export
EXPORT_CATEGORY_COLORS = [
    "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6",
    "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
    "#06b6d4", "#e11d48", "#10b981", "#a855f7", "#78716c",
]


def generate_financial_pdf(
    transactions: list,
    case_name: str,
    filters_description: str = "",
    entity_notes: list = None,
    from_entities: list = None,
    to_entities: list = None,
    selected_from_keys: set = None,
    selected_to_keys: set = None,
    category_counts: dict = None,
    category_amounts: dict = None,
    volume_timeline: list = None,
    has_entity_selection: bool = False,
    total_inflows: float = 0.0,
    total_outflows: float = 0.0,
    inflow_entities: list = None,   # kept for back-compat, ignored
    outflow_entities: list = None,  # kept for back-compat, ignored
) -> str:
    """Generate a financial transactions report as print-friendly HTML.

    Sign convention (matches frontend):
      total_outflows = sum of abs(amount) for positive amounts → "Money Out"
      total_inflows  = sum of abs(amount) for negative amounts → "Money In"
    """
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    total_count = len(transactions)
    total_value = total_outflows + total_inflows  # all money flowing, in either direction
    net_flow = total_inflows - total_outflows  # negative if more spent than received
    net_color = "#16a34a" if net_flow >= 0 else "#dc2626"

    categories_summary = {}
    for t in transactions:
        cat = t.get("category") or "Uncategorized"
        categories_summary[cat] = categories_summary.get(cat, 0) + 1

    corrected_rows = [t for t in transactions if t.get("amount_corrected")]

    # ── Volume Timeline Chart (pure HTML/CSS bars) ──
    volume_chart_html = ""
    if volume_timeline and len(volume_timeline) > 0:
        max_vol = max((v for _, v in volume_timeline), default=1)
        bars_html = ""
        for month_key, amount in volume_timeline:
            pct = _bar_width(amount, max_vol)
            bars_html += f"""
            <div class="chart-row">
                <div class="chart-label">{_esc(month_key)}</div>
                <div class="chart-track"><div class="chart-bar" style="width: {pct:.1f}%; background: linear-gradient(90deg, #3b82f6, #1d4ed8);"></div></div>
                <div class="chart-value">{_fmt_amount(amount)}</div>
            </div>
            """
        volume_chart_html = f"""
        <div class="chart-block">
            <div class="chart-title">Volume Over Time (Monthly)</div>
            {bars_html}
        </div>
        """

    # ── Category Breakdown Chart ──
    category_chart_html = ""
    if category_amounts and len(category_amounts) > 0:
        max_cat_amt = max(category_amounts.values(), default=1)
        sorted_cats = sorted(category_amounts.items(), key=lambda x: x[1], reverse=True)
        cat_bars = ""
        for idx, (cat, amt) in enumerate(sorted_cats):
            color = EXPORT_CATEGORY_COLORS[idx % len(EXPORT_CATEGORY_COLORS)]
            count = (category_counts or {}).get(cat, 0)
            pct = _bar_width(amt, max_cat_amt)
            cat_bars += f"""
            <div class="chart-row">
                <div class="chart-label" title="{_esc(cat)}">{_esc(cat)}</div>
                <div class="chart-track"><div class="chart-bar" style="width: {pct:.1f}%; background: {color};"></div></div>
                <div class="chart-value">{_fmt_amount(amt)} ({count})</div>
            </div>
            """
        category_chart_html = f"""
        <div class="chart-block">
            <div class="chart-title">Category Breakdown</div>
            {cat_bars}
        </div>
        """

    charts_section_html = ""
    if volume_chart_html or category_chart_html:
        charts_section_html = f"""
        <div class="section-charts">
            {volume_chart_html}
            {category_chart_html}
        </div>
        """

    # ── Entity Flow Tables ──
    def _entity_table_html(title, entities, accent_color):
        if not entities:
            return ""
        max_total = max((e["total"] for e in entities), default=1)
        rows = ""
        for e in entities:
            name = _esc(e["name"])
            bar_pct = _bar_width(e["total"], max_total)
            rows += f"""
            <tr>
                <td class="ent-name" title="{name}">{name}</td>
                <td class="ent-count">{e['count']}</td>
                <td class="ent-bar">
                    <div class="ent-bar-track"><div class="ent-bar-fill" style="width: {bar_pct:.1f}%; background: {accent_color};"></div></div>
                </td>
                <td class="ent-amt">{_fmt_amount(e['total'])}</td>
            </tr>
            """
        return f"""
        <div class="entity-block">
            <div class="entity-title" style="color: {accent_color};">{title} ({len(entities)})</div>
            <table class="entity-table">
                <thead>
                    <tr>
                        <th>Entity</th>
                        <th>Txns</th>
                        <th>Distribution</th>
                        <th>Amount</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """

    entity_flow_html = ""
    if from_entities or to_entities:
        from_html = _entity_table_html("Senders (From)", from_entities or [], "#dc2626")
        to_html = _entity_table_html("Recipients (To)", to_entities or [], "#16a34a")
        entity_flow_html = f"""
        <div class="section-entities">
            {from_html}
            {to_html}
        </div>
        """

    # ── Summary Cards — Money Out / Money In / Transactions / Net ──
    summary_cards_html = f"""
    <div class="summary-grid">
        <div class="summary-card card-out">
            <div class="summary-label">Money Out</div>
            <div class="summary-sub">Positive transactions</div>
            <div class="summary-value">{_fmt_amount(total_outflows)}</div>
        </div>
        <div class="summary-card card-in">
            <div class="summary-label">Money In</div>
            <div class="summary-sub">Negative transactions</div>
            <div class="summary-value">{_fmt_amount(total_inflows)}</div>
        </div>
        <div class="summary-card card-net" style="border-color: {net_color}33;">
            <div class="summary-label" style="color: {net_color};">Net</div>
            <div class="summary-sub">In − Out</div>
            <div class="summary-value" style="color: {net_color};">{_fmt_amount(net_flow)}</div>
        </div>
        <div class="summary-card card-count">
            <div class="summary-label">Transactions</div>
            <div class="summary-sub">{'Filtered' if has_entity_selection else 'Total'}</div>
            <div class="summary-value">{total_count:,}</div>
        </div>
    </div>
    """

    # ── Transaction Rows ──
    rows_html = ""
    for i, t in enumerate(transactions):
        amount_val = float(t.get("amount") or 0)
        amount_color = "#dc2626" if amount_val >= 0 else "#16a34a"
        abs_amount = abs(amount_val)
        amount_str = f"${abs_amount:,.2f}" if amount_val >= 0 else f"-${abs_amount:,.2f}"

        corrected_marker = ""
        if t.get("amount_corrected"):
            corrected_marker = ' <span style="color: #d97706;" title="Manually corrected">&#9998;</span>'

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

        is_child = t.get("parent_transaction_key")
        is_parent = t.get("is_parent")

        row_class = "txn-row"
        if is_child:
            row_class += " txn-child"
        elif is_parent:
            row_class += " txn-parent"
        elif i % 2 == 0:
            row_class += " txn-alt"

        name_prefix = "&#8627; " if is_child else ""

        tx_name = _esc(t.get("name"))

        purpose = t.get("purpose") or t.get("notes") or ""
        summary = t.get("summary") or ""
        details_parts = []
        if purpose:
            details_parts.append(_esc(purpose))
        if summary and summary != purpose:
            details_parts.append(f'<span class="ai-summary">[AI] {_esc(summary)}</span>')
        details_html = "<br>".join(details_parts) if details_parts else "-"

        ref_id = _esc(t.get("ref_id") or "-")
        rows_html += f"""
        <tr class="{row_class}">
            <td class="cell ref">{ref_id}</td>
            <td class="cell">{_esc(t.get("date"))}</td>
            <td class="cell name-cell">{name_prefix}{_esc(tx_name)}</td>
            <td class="cell">{_esc(from_name)}</td>
            <td class="cell">{_esc(to_name)}</td>
            <td class="cell amt" style="color: {amount_color};">{amount_str}{corrected_marker}</td>
            <td class="cell">{_esc(t.get("category"))}</td>
            <td class="cell">{_esc(t.get("source_document") or "-")}</td>
            <td class="cell details">{details_html}</td>
        </tr>
        """

    footnote_html = ""
    if corrected_rows:
        footnote_html = """
        <div class="footnote">
            <strong>&#9998; Manually Corrected Amounts</strong> — Original values preserved on file for audit purposes.
        </div>
        """

    # ── Entity Notes Appendix ──
    entity_notes_html = ""
    if entity_notes:
        notes_with_content = [e for e in entity_notes if e.get("notes") or e.get("summary")]
        if notes_with_content:
            entity_rows = ""
            for i, e in enumerate(notes_with_content):
                row_class = "txn-alt" if i % 2 == 0 else ""
                name = _esc(e.get("name"))
                etype = _esc(e.get("type"))
                enotes = _esc(e.get("notes")) if e.get("notes") else ""
                esummary = e.get("summary") or ""

                details = []
                if enotes and enotes != "-":
                    details.append(enotes)
                if esummary:
                    details.append(f'<span class="ai-summary">[AI] {_esc(esummary)}</span>')
                details_str = "<br>".join(details) if details else "-"

                entity_rows += f"""
                <tr class="{row_class}">
                    <td class="cell" style="font-weight: 600;">{name}</td>
                    <td class="cell">{etype}</td>
                    <td class="cell details">{details_str}</td>
                </tr>
                """

            entity_notes_html = f"""
            <div class="page-break"></div>
            <div class="section-header">
                <div class="section-title">Entity Notes &amp; Summaries</div>
                <div class="section-sub">{len(notes_with_content)} entities with notes or AI summaries</div>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th style="width: 22%;">Entity Name</th>
                        <th style="width: 12%;">Type</th>
                        <th style="width: 66%;">Notes / AI Summary</th>
                    </tr>
                </thead>
                <tbody>
                    {entity_rows}
                </tbody>
            </table>
            """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Financial Report — {_esc(case_name)}</title>
    <style>
        @page {{
            size: A4 landscape;
            margin: 1.2cm 1cm 1.4cm 1cm;
            @bottom-center {{
                content: "Page " counter(page) " of " counter(pages);
                font-size: 8pt;
                color: #64748b;
                font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
            }}
            @bottom-left {{
                content: "{_esc(case_name)} — Financial Report";
                font-size: 8pt;
                color: #94a3b8;
                font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
            }}
            @bottom-right {{
                content: "ATTORNEY-CLIENT PRIVILEGED";
                font-size: 7pt;
                color: #94a3b8;
                font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
            }}
        }}

        * {{ box-sizing: border-box; }}

        html, body {{
            font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
            color: #1e293b;
            margin: 0;
            padding: 0;
            font-size: 9pt;
            line-height: 1.35;
        }}

        /* ── HEADER ── */
        .report-header {{
            background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
            color: white;
            padding: 14px 20px;
            border-radius: 6px;
            margin-bottom: 12px;
        }}
        .report-title {{ font-size: 16pt; font-weight: 700; margin-bottom: 2px; }}
        .report-case {{ font-size: 10pt; opacity: 0.9; }}
        .report-meta {{ font-size: 8pt; opacity: 0.7; margin-top: 4px; }}

        /* ── SUMMARY CARDS ── */
        .summary-grid {{
            display: table;
            width: 100%;
            border-collapse: separate;
            border-spacing: 8px 0;
            margin-bottom: 12px;
            margin-left: -8px;
            margin-right: -8px;
        }}
        .summary-card {{
            display: table-cell;
            width: 25%;
            padding: 10px 12px;
            border-radius: 6px;
            border: 1px solid #e2e8f0;
            vertical-align: top;
        }}
        .summary-label {{
            font-size: 9pt;
            font-weight: 600;
            color: #334155;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }}
        .summary-sub {{ font-size: 7pt; color: #94a3b8; margin-top: 1px; }}
        .summary-value {{ font-size: 16pt; font-weight: 700; color: #0f172a; margin-top: 4px; }}
        .card-out {{ background: #fef2f2; border-color: #fecaca; }}
        .card-out .summary-label, .card-out .summary-value {{ color: #dc2626; }}
        .card-in {{ background: #dcfce7; border-color: #bbf7d0; }}
        .card-in .summary-label, .card-in .summary-value {{ color: #16a34a; }}
        .card-net {{ background: #f8fafc; }}
        .card-count {{ background: #eff6ff; border-color: #bfdbfe; }}
        .card-count .summary-label, .card-count .summary-value {{ color: #1d4ed8; }}

        /* ── FILTER BANNER ── */
        .filter-banner {{
            font-size: 8pt;
            color: #475569;
            margin-bottom: 10px;
            padding: 6px 10px;
            background: #f8fafc;
            border-left: 3px solid #3b82f6;
            border-radius: 3px;
        }}

        /* ── CHARTS ── */
        .section-charts {{
            display: table;
            width: 100%;
            border-collapse: separate;
            border-spacing: 12px 0;
            margin: 0 -12px 12px -12px;
            page-break-inside: avoid;
        }}
        .chart-block {{
            display: table-cell;
            width: 50%;
            padding: 10px 12px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            vertical-align: top;
        }}
        .chart-title {{
            font-size: 8pt;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            margin-bottom: 6px;
            font-weight: 600;
        }}
        .chart-row {{ display: table; width: 100%; margin-bottom: 2px; }}
        .chart-label {{
            display: table-cell;
            width: 70px;
            font-size: 7pt;
            color: #64748b;
            text-align: right;
            padding-right: 6px;
            vertical-align: middle;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .chart-track {{
            display: table-cell;
            background: #f1f5f9;
            border-radius: 2px;
            overflow: hidden;
            height: 12px;
            vertical-align: middle;
        }}
        .chart-bar {{ height: 12px; border-radius: 2px; }}
        .chart-value {{
            display: table-cell;
            width: 80px;
            font-size: 7pt;
            color: #334155;
            text-align: right;
            padding-left: 6px;
            vertical-align: middle;
            white-space: nowrap;
        }}

        /* ── ENTITY FLOW ── */
        .section-entities {{
            display: table;
            width: 100%;
            border-collapse: separate;
            border-spacing: 12px 0;
            margin: 0 -12px 12px -12px;
            page-break-inside: avoid;
        }}
        .entity-block {{
            display: table-cell;
            width: 50%;
            vertical-align: top;
        }}
        .entity-title {{
            font-size: 8pt;
            font-weight: 700;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }}
        .entity-table {{
            width: 100%;
            border-collapse: collapse;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
        }}
        .entity-table th {{
            background: #f8fafc;
            font-size: 7pt;
            text-align: left;
            color: #64748b;
            font-weight: 600;
            padding: 4px 6px;
            border-bottom: 1px solid #e2e8f0;
        }}
        .entity-table td {{
            font-size: 7.5pt;
            padding: 3px 6px;
            border-bottom: 1px solid #f1f5f9;
        }}
        .ent-name {{
            max-width: 140px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .ent-count {{ width: 30px; text-align: right; color: #64748b; }}
        .ent-bar {{ width: 35%; }}
        .ent-bar-track {{ background: #f1f5f9; border-radius: 2px; height: 8px; overflow: hidden; }}
        .ent-bar-fill {{ height: 8px; border-radius: 2px; }}
        .ent-amt {{ width: 70px; text-align: right; font-weight: 600; color: #334155; }}

        /* ── DATA TABLE (transactions / notes appendix) ── */
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            border: 1px solid #cbd5e1;
        }}
        .data-table thead {{
            display: table-header-group;  /* repeat on every page */
        }}
        .data-table thead th {{
            background: #1e3a5f;
            color: white;
            padding: 6px 7px;
            text-align: left;
            font-size: 8pt;
            font-weight: 600;
            border-right: 1px solid #2d4a6f;
        }}
        .data-table tbody tr {{
            page-break-inside: avoid;  /* don't split a row across pages */
        }}
        .cell {{
            padding: 4px 7px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 7.5pt;
            vertical-align: top;
            line-height: 1.35;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        .cell.ref {{ font-family: "SF Mono", "Menlo", monospace; font-size: 7pt; color: #475569; letter-spacing: 0.3px; }}
        .cell.amt {{ font-family: "SF Mono", "Menlo", monospace; text-align: right; white-space: nowrap; }}
        .cell.details {{ max-width: 220px; }}
        .ai-summary {{ color: #6366f1; font-style: italic; }}

        .txn-alt {{ background: #f8fafc; }}
        .txn-parent {{ background: #f1f5f9; font-weight: 600; }}
        .txn-child {{ background: #eef2ff; border-left: 3px solid #818cf8; }}
        .txn-child .name-cell {{ padding-left: 18px; }}

        /* ── SECTION HEADERS (e.g. Notes appendix) ── */
        .section-header {{
            background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
            color: white;
            padding: 12px 18px;
            border-radius: 6px;
            margin-bottom: 10px;
        }}
        .section-title {{ font-size: 14pt; font-weight: 700; }}
        .section-sub {{ font-size: 9pt; opacity: 0.8; margin-top: 2px; }}

        /* ── FOOTNOTE ── */
        .footnote {{
            margin-top: 12px;
            padding: 8px 12px;
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-radius: 4px;
            font-size: 8pt;
            color: #92400e;
            page-break-inside: avoid;
        }}

        /* ── PAGE BREAKS ── */
        .page-break {{ page-break-before: always; }}

        /* Avoid orphaning section headers */
        h1, h2, h3, .section-header, .section-charts, .section-entities, .summary-grid {{
            page-break-after: avoid;
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <div class="report-title">Financial Transaction Report</div>
        <div class="report-case">{_esc(case_name)}</div>
        <div class="report-meta">Generated: {now} &nbsp;·&nbsp; ATTORNEY-CLIENT PRIVILEGED AND CONFIDENTIAL</div>
    </div>

    {summary_cards_html}

    {f'<div class="filter-banner">Active filters: {_esc(filters_description)}</div>' if filters_description else ''}

    {charts_section_html}

    {entity_flow_html}

    <table class="data-table">
        <thead>
            <tr>
                <th style="width: 6%;">Ref</th>
                <th style="width: 7%;">Date</th>
                <th style="width: 13%;">Name</th>
                <th style="width: 11%;">From</th>
                <th style="width: 11%;">To</th>
                <th style="width: 8%; text-align: right;">Amount</th>
                <th style="width: 9%;">Category</th>
                <th style="width: 8%;">Source</th>
                <th style="width: 27%;">Details / AI Summary</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    {footnote_html}

    {entity_notes_html}
</body>
</html>"""

    return html


def render_pdf(html: str) -> bytes:
    """Convert HTML string to PDF bytes using WeasyPrint."""
    import weasyprint
    return weasyprint.HTML(string=html).write_pdf()
