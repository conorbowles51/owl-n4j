"""
Financial Export Service — Generates PDF reports for financial transactions.
"""
from datetime import datetime


def generate_financial_pdf(transactions: list, case_name: str, filters_description: str = "") -> bytes:
    """Generate a financial transactions PDF report.
    
    Args:
        transactions: List of transaction dicts with keys: date, time, name, amount, 
                      financial_category, from_entity, to_entity, purpose, notes, 
                      amount_corrected, original_amount, correction_reason
        case_name: Name of the case for the header
        filters_description: Description of active filters applied
    
    Returns:
        PDF bytes
    """
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    
    total_count = len(transactions)
    total_value = sum(abs(float(t.get("amount") or 0)) for t in transactions)
    
    categories = {}
    for t in transactions:
        cat = t.get("financial_category") or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    
    category_summary = ", ".join(f"{cat}: {count}" for cat, count in sorted(categories.items()))
    
    corrected_rows = [t for t in transactions if t.get("amount_corrected")]
    
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
        
        rows_html += f"""
        <tr style="background: {bg};">
            <td style="padding: 6px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11px;">{t.get("date") or "-"}</td>
            <td style="padding: 6px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11px; {indent_style}">{name_prefix}{from_name}</td>
            <td style="padding: 6px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11px;">{to_name}</td>
            <td style="padding: 6px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11px; font-family: monospace; color: {amount_color}; text-align: right;">{amount_str}{corrected_marker}</td>
            <td style="padding: 6px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11px;">{t.get("financial_category") or "-"}</td>
            <td style="padding: 6px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11px; max-width: 200px; overflow: hidden; text-overflow: ellipsis;">{t.get("purpose") or t.get("notes") or "-"}</td>
        </tr>
        """
    
    footnote_html = ""
    if corrected_rows:
        footnote_html = """
        <div style="margin-top: 16px; padding: 10px 14px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; font-size: 10px; color: #92400e;">
            <strong>&#9998; Manually Corrected Amounts</strong> — Original values preserved on file for audit purposes.
        </div>
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
        </style>
    </head>
    <body>
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); color: white; padding: 20px 24px; border-radius: 8px; margin-bottom: 16px;">
            <div style="font-size: 20px; font-weight: 700; margin-bottom: 4px;">Financial Transaction Report</div>
            <div style="font-size: 13px; opacity: 0.85;">{case_name}</div>
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
            <div style="flex: 2; background: #f1f5f9; border-radius: 6px; padding: 12px 16px;">
                <div style="font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Categories</div>
                <div style="font-size: 12px; color: #334155; margin-top: 4px;">{category_summary or "None"}</div>
            </div>
        </div>
        
        {f'<div style="font-size: 11px; color: #64748b; margin-bottom: 12px;">Active filters: {filters_description}</div>' if filters_description else ''}
        
        <!-- Transaction Table -->
        <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
            <thead>
                <tr style="background: #1e3a5f; color: white;">
                    <th style="padding: 8px 10px; text-align: left; font-size: 11px; font-weight: 600;">Date</th>
                    <th style="padding: 8px 10px; text-align: left; font-size: 11px; font-weight: 600;">From</th>
                    <th style="padding: 8px 10px; text-align: left; font-size: 11px; font-weight: 600;">To</th>
                    <th style="padding: 8px 10px; text-align: right; font-size: 11px; font-weight: 600;">Amount</th>
                    <th style="padding: 8px 10px; text-align: left; font-size: 11px; font-weight: 600;">Category</th>
                    <th style="padding: 8px 10px; text-align: left; font-size: 11px; font-weight: 600;">Notes/Purpose</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        
        {footnote_html}
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
