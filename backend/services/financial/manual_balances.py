"""Explicit, page-cited balances entered when extraction missed a control."""
from services.financial.pdf_candidates import PdfMappingError


def manual_balance(row, proposal):
    role = next((role for role in ('opening', 'closing') if row['id'] == f'manual:{role}-balance'), None)
    if role is None:
        return None
    from services.financial.summary_pages import balance_pages
    # Its pages, and its summary page before them, where a card prints its previous and new balance (summary_pages).
    pages = balance_pages(proposal)
    if not row['excluded'] or row.get('manual_page') not in pages:
        raise PdfMappingError('A statement balance must stay outside transactions and cite a page of this statement.', 422)
    return dict(id=row['id'], kind='balance', excluded=True, issues=[], page_number=row['manual_page'],
        table_index=None, row_index=None, source_cells=[], manual_balance=True,
        fields=dict(description=f'{role.title()} Balance', balance=row.get('balance_minor')))
