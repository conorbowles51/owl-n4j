"""Locate split card descriptions without changing the extracted source cells."""
from services.financial.locators import Locator, LocatorError


def has_unmapped_card_amount(cells, headers):
    """Flag a measured payment line when one of its expected cells is lost."""
    if len(cells) < 2:
        return False
    try:
        amount = Locator.from_json(headers['Amount']['locator']).rectangle
        description = Locator.from_json(headers['Description']['locator']).rectangle
        boxes = [Locator.from_json(cell['locator']).rectangle for cell in cells]
    except (LocatorError, ValueError, TypeError, KeyError):
        return False
    if any(box is None for box in [amount, description, *boxes]):
        return False
    if len({(b.page_number, b.page_width, b.page_height) for b in [amount, description, *boxes]}) != 1:
        return False
    if min(b.y0 for b in boxes) <= max(amount.y1, description.y1) or max(b.y0 for b in boxes) >= min(b.y1 for b in boxes):
        return False
    tolerance = amount.page_width // 100
    return (any(abs(b.x1 - amount.x1) <= tolerance and b.x0 > description.x1 for b in boxes)
            and any(abs(b.x0 - description.x0) <= tolerance for b in boxes))


def card_row_columns(cells, headers):
    """Use exact columns, or measured positions for an over-split row.

    A description can be extracted as several cells. Its amount must still be
    the single cell aligned with the right edge of the printed Amount header.
    No numeric-looking description fragment is used as an amount by guessing.
    """
    by_column = {cell['column_index']: cell for cell in cells}
    if len(by_column) != len(cells):
        return None
    if len(cells) == len(headers):
        if not all(cell['column_index'] in by_column for cell in headers.values()):
            return None
        result = {name: by_column[cell['column_index']] for name, cell in headers.items()}
        return result, [result['Description']]
    if len(cells) < len(headers):
        return None

    try:
        header_boxes = {name: Locator.from_json(cell['locator']).rectangle for name, cell in headers.items()}
        boxes = [Locator.from_json(cell['locator']).rectangle for cell in cells]
    except (LocatorError, ValueError, TypeError, KeyError):
        return None
    all_boxes = [*header_boxes.values(), *boxes]
    if any(box is None for box in all_boxes):
        return None
    if len({(box.page_number, box.page_width, box.page_height) for box in all_boxes}) != 1:
        return None
    ordered = sorted(header_boxes, key=lambda name: header_boxes[name].x0)
    expected = ['Date', 'Description', 'Amount'] if 'Date' in headers else ['Trans Date', 'Post Date', 'Description', 'Amount']
    if ordered != expected:
        return None
    tolerance = header_boxes['Amount'].page_width // 100
    # These statements sometimes place an advertisement beside the table.
    # Keep it in source_cells, but do not join text beyond Amount into a payment.
    table_cells = [(cell, box) for cell, box in zip(cells, boxes)
                   if box.x0 <= header_boxes['Amount'].x1 + tolerance]
    table_boxes = [box for _, box in table_cells]
    if not table_boxes or max(box.y0 for box in table_boxes) >= min(box.y1 for box in table_boxes):
        return None
    if min(box.y0 for box in table_boxes) < max(box.y1 for box in header_boxes.values()):
        return None
    result = {}
    date_columns = set()
    for name in expected[:-2]:
        column = headers[name]['column_index']
        if column not in by_column:
            return None
        index = next(i for i, cell in enumerate(cells) if cell['column_index'] == column)
        if abs(boxes[index].x0 - header_boxes[name].x0) > tolerance:
            return None
        result[name] = cells[index]
        date_columns.add(column)
    remaining = [(cell, box) for cell, box in table_cells if cell['column_index'] not in date_columns]
    amounts = [(cell, box) for cell, box in remaining
               if abs(box.x1 - header_boxes['Amount'].x1) <= tolerance
               and box.x0 > header_boxes['Description'].x1]
    if len(amounts) != 1:
        return None
    amount, amount_box = amounts[0]
    description = sorted([(cell, box) for cell, box in remaining if cell is not amount], key=lambda pair: pair[1].x0)
    if not description or abs(description[0][1].x0 - header_boxes['Description'].x0) > tolerance:
        return None
    if any(not cell['expected_text'].strip() or box.x1 >= amount_box.x0 for cell, box in description):
        return None
    if any(left[1].x1 > right[1].x0 for left, right in zip(description, description[1:])):
        return None
    result.update(Description=description[0][0], Amount=amount)
    return result, [cell for cell, _ in description]
