"""
Financial Export Service — Generates PDF reports for financial transactions.

Designed for print-friendly output suitable for attorney-client meetings
where laptops and internet are unavailable (e.g., jail visits).
Includes transaction table, entity flow tables, category chart, volume
timeline, and entity notes appendix — all filtered to match the current view.
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
    inflow_entities: list = None,
    outflow_entities: list = None,
) -> str:
    """Generate a financial transactions report as printable HTML.

    Args:
        transactions: List of filtered transaction dicts
        case_name: Name of the case for the header
        filters_description: Description of active filters applied
        entity_notes: Optional list of dicts {name, type, notes, summary}
        from_entities: List of {name, count, total} for sender entities
        to_entities: List of {name, count, total} for recipient entities
        selected_from_keys: Set of selected sender entity keys (or None)
        selected_to_keys: Set of selected recipient entity keys (or None)
        category_counts: Dict of category -> transaction count
        category_amounts: Dict of category -> total amount
        volume_timeline: List of (month_key, amount) tuples sorted by date
        has_entity_selection: Whether entity filters are active
        total_inflows: Directional inflows relative to selected entities
        total_outflows: Directional outflows relative to selected entities
        inflow_entities: List of {name, amount} for entities on inflow side (entity mode only)
        outflow_entities: List of {name, amount} for entities on outflow side (entity mode only)

    Returns:
        HTML string
    """
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    total_count = len(transactions)
    total_value = sum(abs(float(t.get("amount") or 0)) for t in transactions)

    categories_summary = {}
    for t in transactions:
        cat = t.get("category") or "Uncategorized"
        categories_summary[cat] = categories_summary.get(cat, 0) + 1
    category_summary_text = ", ".join(f"{cat}: {count}" for cat, count in sorted(categories_summary.items()))

    corrected_rows = [t for t in transactions if t.get("amount_corrected")]

    # ── Volume Timeline Chart (pure HTML/CSS bars) ──
    volume_chart_html = ""
    if volume_timeline and len(volume_timeline) > 0:
        max_vol = max((v for _, v in volume_timeline), default=1)
        bars_html = ""
        for month_key, amount in volume_timeline:
            pct = _bar_width(amount, max_vol)
            label = month_key  # YYYY-MM
            bars_html += f"""
            <div style="display: flex; align-items: center; margin-bottom: 3px;">
                <div style="width: 55px; font-size: 9px; color: #64748b; text-align: right; padding-right: 8px; flex-shrink: 0;">{_esc(label)}</div>
                <div style="flex: 1; background: #f1f5f9; border-radius: 3px; overflow: hidden; height: 16px;">
                    <div style="width: {pct:.1f}%; background: linear-gradient(90deg, #3b82f6, #1d4ed8); height: 100%; border-radius: 3px;"></div>
                </div>
                <div style="width: 70px; font-size: 9px; color: #334155; text-align: right; padding-left: 6px; flex-shrink: 0;">{_fmt_amount(amount)}</div>
            </div>
            """
        volume_chart_html = f"""
        <div style="flex: 1; min-width: 0;">
            <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; font-weight: 600;">Volume Over Time (Monthly)</div>
            {bars_html}
        </div>
        """

    # ── Category Breakdown Chart (horizontal bars) ──
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
            <div style="display: flex; align-items: center; margin-bottom: 3px;">
                <div style="width: 90px; font-size: 9px; color: #334155; text-align: right; padding-right: 8px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{_esc(cat)}">{_esc(cat)}</div>
                <div style="flex: 1; background: #f1f5f9; border-radius: 3px; overflow: hidden; height: 16px;">
                    <div style="width: {pct:.1f}%; background: {color}; height: 100%; border-radius: 3px;"></div>
                </div>
                <div style="width: 80px; font-size: 9px; color: #334155; text-align: right; padding-left: 6px; flex-shrink: 0;">{_fmt_amount(amt)} ({count})</div>
            </div>
            """
        category_chart_html = f"""
        <div style="flex: 1; min-width: 0;">
            <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; font-weight: 600;">Category Breakdown</div>
            {cat_bars}
        </div>
        """

    charts_section_html = ""
    if volume_chart_html or category_chart_html:
        charts_section_html = f"""
        <div style="display: flex; gap: 24px; margin-bottom: 16px; padding: 14px 16px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px;">
            {volume_chart_html}
            {category_chart_html}
        </div>
        """

    # ── Entity Flow Tables ──
    def _entity_table_html(title, entities, selected_keys, accent_color):
        if not entities:
            return ""
        max_total = max((e["total"] for e in entities), default=1)
        rows = ""
        for e in entities:
            name = _esc(e["name"])
            is_selected = selected_keys and e.get("name") and any(
                k == e.get("key", e["name"]) for k in selected_keys
            ) if selected_keys else False
            bg = "#eff6ff" if is_selected else ""
            bg_style = f"background: {bg};" if bg else ""
            bar_pct = _bar_width(e["total"], max_total)
            rows += f"""
            <tr style="{bg_style}">
                <td style="padding: 4px 8px; font-size: 10px; border-bottom: 1px solid #e2e8f0; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{name}">
                    {'<strong>' if is_selected else ''}{name}{'</strong>' if is_selected else ''}
                </td>
                <td style="padding: 4px 6px; font-size: 10px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #64748b;">{e['count']}</td>
                <td style="padding: 4px 8px; font-size: 10px; border-bottom: 1px solid #e2e8f0; width: 40%;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <div style="flex: 1; background: #f1f5f9; border-radius: 2px; height: 10px; overflow: hidden;">
                            <div style="width: {bar_pct:.1f}%; background: {accent_color}; height: 100%; border-radius: 2px;"></div>
                        </div>
                        <span style="font-size: 9px; color: #334155; white-space: nowrap;">{_fmt_amount(e['total'])}</span>
                    </div>
                </td>
            </tr>
            """
        return f"""
        <div style="flex: 1; min-width: 0;">
            <div style="font-size: 10px; font-weight: 600; color: {accent_color}; margin-bottom: 6px;">{title} ({len(entities)})</div>
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 4px; overflow: hidden;">
                <thead>
                    <tr style="background: #f8fafc;">
                        <th style="padding: 4px 8px; font-size: 9px; text-align: left; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Entity</th>
                        <th style="padding: 4px 6px; font-size: 9px; text-align: right; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Txns</th>
                        <th style="padding: 4px 8px; font-size: 9px; text-align: left; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Amount</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """

    entity_flow_html = ""
    if from_entities or to_entities:
        from_html = _entity_table_html("Senders (From)", from_entities or [], selected_from_keys, "#ef4444")
        to_html = _entity_table_html("Recipients (To)", to_entities or [], selected_to_keys, "#22c55e")
        entity_flow_html = f"""
        <div style="display: flex; gap: 16px; margin-bottom: 16px;">
            {from_html}
            {to_html}
        </div>
        """

    # ── Transaction Rows ──
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

        is_child = t.get("parent_transaction_key")
        is_parent = t.get("is_parent")

        # Visual grouping: parent rows get a subtle bold treatment,
        # child rows get a tinted background + left border to show nesting
        if is_child:
            bg = "#eef2ff"  # light indigo tint for child rows
            border_left = "border-left: 3px solid #818cf8;"  # indigo accent bar
        elif is_parent:
            bg = "#f1f5f9"  # slightly stronger slate for parent header
            border_left = ""
        else:
            bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
            border_left = ""

        name_prefix = "&#8627; " if is_child else ""
        indent_style = "padding-left: 24px;" if is_child else ""
        parent_weight = "font-weight: 600;" if is_parent else ""

        tx_name = _esc(t.get("name"))

        purpose = t.get("purpose") or t.get("notes") or ""
        summary = t.get("summary") or ""
        details_parts = []
        if purpose:
            details_parts.append(_esc(purpose))
        if summary and summary != purpose:
            details_parts.append(f'<span style="color: #6366f1; font-style: italic;">[AI] {_esc(summary)}</span>')
        details_html = "<br>".join(details_parts) if details_parts else "-"

        ref_id = _esc(t.get("ref_id") or "-")
        rows_html += f"""
        <tr style="background: {bg}; {border_left}">
            <td class="cell" style="font-family: monospace; font-size: 9px; letter-spacing: 0.5px; color: #475569;">{ref_id}</td>
            <td class="cell">{_esc(t.get("date"))}</td>
            <td class="cell" style="{indent_style} {parent_weight}">{name_prefix}{_esc(tx_name)}</td>
            <td class="cell">{_esc(from_name)}</td>
            <td class="cell">{_esc(to_name)}</td>
            <td class="cell" style="font-family: monospace; color: {amount_color}; text-align: right; white-space: nowrap;">{amount_str}{corrected_marker}</td>
            <td class="cell">{_esc(t.get("category"))}</td>
            <td class="cell">{_esc(t.get("source_document") or "-")}</td>
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

    # ── Entity Notes Appendix ──
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

    # ── Summary Cards — context-aware like frontend ──
    net_flow = total_inflows - total_outflows
    net_color = "#16a34a" if net_flow >= 0 else "#dc2626"
    net_bg = "#dcfce7" if net_flow >= 0 else "#fef2f2"

    if has_entity_selection:
        summary_cards_html = f"""
        <div style="display: flex; gap: 12px; margin-bottom: 16px;">
            <div style="flex: 1; background: #dcfce7; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #16a34a; text-transform: uppercase; letter-spacing: 0.5px;">Inflows</div>
                <div style="font-size: 18px; font-weight: 700; color: #16a34a;">${total_inflows:,.2f}</div>
            </div>
            <div style="flex: 1; background: #fef2f2; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #dc2626; text-transform: uppercase; letter-spacing: 0.5px;">Outflows</div>
                <div style="font-size: 18px; font-weight: 700; color: #dc2626;">${total_outflows:,.2f}</div>
            </div>
            <div style="flex: 1; background: {net_bg}; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: {net_color}; text-transform: uppercase; letter-spacing: 0.5px;">Net Flow</div>
                <div style="font-size: 18px; font-weight: 700; color: {net_color};">${net_flow:,.2f}</div>
            </div>
            <div style="flex: 1; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Transactions</div>
                <div style="font-size: 20px; font-weight: 700; color: #0f172a;">{total_count}</div>
            </div>
        </div>
        """
    else:
        # Compute unique entities for overview mode
        entity_keys_set = set()
        for t in transactions:
            if isinstance(t.get("from_entity"), dict) and t["from_entity"].get("key"):
                entity_keys_set.add(t["from_entity"]["key"])
            elif isinstance(t.get("from_entity"), dict) and t["from_entity"].get("name"):
                entity_keys_set.add(t["from_entity"]["name"])
            if isinstance(t.get("to_entity"), dict) and t["to_entity"].get("key"):
                entity_keys_set.add(t["to_entity"]["key"])
            elif isinstance(t.get("to_entity"), dict) and t["to_entity"].get("name"):
                entity_keys_set.add(t["to_entity"]["name"])
        avg_amount = (total_value / total_count) if total_count > 0 else 0

        summary_cards_html = f"""
        <div style="display: flex; gap: 12px; margin-bottom: 16px;">
            <div style="flex: 1; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Total Volume</div>
                <div style="font-size: 20px; font-weight: 700; color: #0f172a;">${total_value:,.2f}</div>
            </div>
            <div style="flex: 1; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Transactions</div>
                <div style="font-size: 20px; font-weight: 700; color: #0f172a;">{total_count}</div>
            </div>
            <div style="flex: 1; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Unique Entities</div>
                <div style="font-size: 20px; font-weight: 700; color: #0f172a;">{len(entity_keys_set)}</div>
            </div>
            <div style="flex: 1; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Avg Transaction</div>
                <div style="font-size: 20px; font-weight: 700; color: #0f172a;">${avg_amount:,.2f}</div>
            </div>
            <div style="flex: 2; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Categories</div>
                <div style="font-size: 11px; color: #334155; margin-top: 4px;">{category_summary_text or "None"}</div>
            </div>
        </div>
        """

    # ── Inflow vs Outflow comparison bar — always visible when there's flow data ──
    flow_comparison_html = ""
    if total_inflows > 0 or total_outflows > 0:
        flow_total = total_inflows + total_outflows
        in_pct = (total_inflows / flow_total * 100) if flow_total > 0 else 50
        out_pct = 100 - in_pct
        hint_html = ""
        if not has_entity_selection and total_outflows == 0:
            hint_html = '<span style="font-size: 9px; color: #94a3b8; font-style: italic; margin-left: 8px;">Select entities for directional flow analysis</span>'
        # Build the bar sections — only include sections with width > 0
        bar_sections = ""
        if in_pct > 0:
            bar_sections += f"""<div style="width: {in_pct:.1f}%; background: linear-gradient(90deg, #22c55e, #16a34a); display: flex; align-items: center; justify-content: center;">
                    <span style="font-size: 10px; font-weight: 600; color: white;">{_fmt_amount(total_inflows)}</span>
                </div>"""
        if out_pct > 0:
            bar_sections += f"""<div style="width: {out_pct:.1f}%; background: linear-gradient(90deg, #ef4444, #dc2626); display: flex; align-items: center; justify-content: center;">
                    <span style="font-size: 10px; font-weight: 600; color: white;">{_fmt_amount(total_outflows)}</span>
                </div>"""
        # Entity breakdown lists — only when entities are selected
        entity_breakdown_html = ""
        if has_entity_selection and (inflow_entities or outflow_entities):
            inflow_list_html = ""
            if inflow_entities:
                inflow_items = ""
                for e in inflow_entities[:5]:
                    inflow_items += f'<div style="display: flex; justify-content: space-between; font-size: 9px; margin-bottom: 2px;"><span style="color: #475569; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 8px;">{_esc(e["name"])}</span><span style="color: #16a34a; font-weight: 600; white-space: nowrap;">{_fmt_amount(e["amount"])}</span></div>'
                if len(inflow_entities) > 5:
                    inflow_items += f'<div style="font-size: 8px; color: #94a3b8;">+{len(inflow_entities) - 5} more</div>'
                inflow_list_html = f"""
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 9px; color: #16a34a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">Inflow From</div>
                    {inflow_items}
                </div>
                """
            outflow_list_html = ""
            if outflow_entities:
                outflow_items = ""
                for e in outflow_entities[:5]:
                    outflow_items += f'<div style="display: flex; justify-content: space-between; font-size: 9px; margin-bottom: 2px;"><span style="color: #475569; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 8px;">{_esc(e["name"])}</span><span style="color: #dc2626; font-weight: 600; white-space: nowrap;">{_fmt_amount(e["amount"])}</span></div>'
                if len(outflow_entities) > 5:
                    outflow_items += f'<div style="font-size: 8px; color: #94a3b8;">+{len(outflow_entities) - 5} more</div>'
                outflow_list_html = f"""
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 9px; color: #dc2626; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">Outflow To</div>
                    {outflow_items}
                </div>
                """
            entity_breakdown_html = f"""
            <div style="display: flex; gap: 16px; margin-top: 10px; padding-top: 8px; border-top: 1px solid #e2e8f0;">
                {inflow_list_html}
                {outflow_list_html}
            </div>
            """

        flow_comparison_html = f"""
        <div style="margin-bottom: 16px; padding: 14px 16px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px;">
            <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; font-weight: 600;">Inflow vs Outflow{hint_html}</div>
            <div style="display: flex; height: 28px; border-radius: 6px; overflow: hidden; margin-bottom: 8px;">
                {bar_sections}
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 10px;">
                <div style="color: #16a34a;">&#9650; Inflows ({in_pct:.0f}%)</div>
                <div style="color: #64748b; font-weight: 600;">Net: <span style="color: {net_color};">${net_flow:,.2f}</span></div>
                <div style="color: #dc2626;">&#9660; Outflows ({out_pct:.0f}%)</div>
            </div>
            {entity_breakdown_html}
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Financial Report — {_esc(case_name)}</title>
        <style>
            @page {{
                size: A4 landscape;
                margin: 1.5cm;
            }}
            @media print {{
                body {{ padding: 0; margin: 0; }}
                .no-print {{ display: none !important; }}
                thead {{ display: table-header-group; }}
                tr {{ page-break-inside: avoid; }}
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                color: #1e293b;
                margin: 0;
                padding: 24px;
                background: #f1f5f9;
            }}
            .report-wrap {{
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                padding: 32px;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            @media print {{
                body {{ background: white; padding: 0; }}
                .report-wrap {{ box-shadow: none; padding: 0; border-radius: 0; max-width: none; }}
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
            .print-btn {{
                position: fixed;
                bottom: 24px;
                right: 24px;
                background: #1e3a5f;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
                z-index: 999;
            }}
            .print-btn:hover {{ background: #0f172a; }}
        </style>
    </head>
    <body>
        <button class="print-btn no-print" onclick="window.print()">&#128438; Print / Save as PDF</button>
        <div class="report-wrap">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); color: white; padding: 20px 24px; border-radius: 8px; margin-bottom: 16px;">
            <div style="font-size: 20px; font-weight: 700; margin-bottom: 4px;">Financial Transaction Report</div>
            <div style="font-size: 13px; opacity: 0.85;">{_esc(case_name)}</div>
            <div style="font-size: 11px; opacity: 0.7; margin-top: 6px;">Generated: {now}</div>
            <div style="font-size: 10px; opacity: 0.6; margin-top: 2px;">ATTORNEY-CLIENT PRIVILEGED AND CONFIDENTIAL</div>
        </div>

        <!-- Summary Cards -->
        {summary_cards_html}

        {f'<div style="font-size: 11px; color: #64748b; margin-bottom: 12px; padding: 8px 12px; background: #f8fafc; border-radius: 4px; border-left: 3px solid #3b82f6;">Active filters: {_esc(filters_description)}</div>' if filters_description else ''}

        <!-- Inflow vs Outflow -->
        {flow_comparison_html}

        <!-- Charts -->
        {charts_section_html}

        <!-- Entity Flow Tables -->
        {entity_flow_html}

        <!-- Transaction Table -->
        <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
            <thead>
                <tr style="background: #1e3a5f; color: white;">
                    <th class="th" style="width: 6%;">Ref</th>
                    <th class="th" style="width: 7%;">Date</th>
                    <th class="th" style="width: 13%;">Name</th>
                    <th class="th" style="width: 11%;">From</th>
                    <th class="th" style="width: 11%;">To</th>
                    <th class="th" style="text-align: right; width: 8%;">Amount</th>
                    <th class="th" style="width: 9%;">Category</th>
                    <th class="th" style="width: 8%;">Source</th>
                    <th class="th" style="width: 27%;">Details / AI Summary</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        {footnote_html}

        {entity_notes_html}
        </div>
    </body>
    </html>
    """

    return html


def render_pdf(html: str) -> bytes:
    """Convert HTML string to PDF bytes using WeasyPrint."""
    import weasyprint
    return weasyprint.HTML(string=html).write_pdf()
