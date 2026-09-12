"""Read Capital One's account-summary balances from their measured cells."""
import re

from services.financial.locators import Locator, LocatorError
from services.financial.statement_import_proposal import exact_amount


def _rectangle(cell, page):
    try:
        rectangle = Locator.from_json(cell['locator']).rectangle
        return rectangle if rectangle and rectangle.page_number == page else None
    except (LocatorError, ValueError, TypeError, KeyError):
        return None


def summary_balances(source, currency):
    """Require a summary heading and aligned label/value pairs on the same page.

    Column indexes vary across extracted rows. Geometry, immediate adjacency and
    the Previous Balance anchor distinguish this summary from payment coupons.
    Unreadable or ambiguous controls stay unresolved, never default to zero.
    """
    headings = []
    pairs = {'Previous Balance': [], 'New Balance': []}
    for row in source['rows']:
        measured = [(cell, _rectangle(cell, source['page_number'])) for cell in row['cells']
                    if cell['expected_text'].strip()]
        for cell, rect in measured:
            label = cell['expected_text'].strip()
            if label == 'Account Summary':
                headings.append(rect)
            if label not in pairs or rect is None:
                continue
            right = [(other, box) for other, box in measured if box is not None
                     and box.page_width == rect.page_width and box.page_height == rect.page_height
                     and box.x0 >= rect.x1 and min(box.y1, rect.y1) > max(box.y0, rect.y0)]
            right.sort(key=lambda pair: pair[1].x0)
            if not right:
                continue
            value, box = right[0]
            # The immediate neighbour must be an amount, not another label.
            if not re.match(r'^(?:=\s*)?(?:[+-]\s*)?(?:\$|USD\b|\(?\d)', value['expected_text'].strip()):
                continue
            pairs[label].append((row['row_index'], cell, rect, value, box))
    if not headings:
        return {}, []
    warning = ['The opening and closing amounts owed could not be identified clearly in the account summary. Check them against the PDF.']
    if len(headings) != 1 or headings[0] is None:
        return {}, warning
    heading = headings[0]
    openings = [pair for pair in pairs['Previous Balance']
                if heading.page_width == pair[2].page_width
                and heading.page_height == pair[2].page_height
                and heading.y1 <= pair[2].y0 <= heading.y1 + heading.page_height // 8
                and pair[2].x0 <= (heading.x0 + heading.x1) // 2 <= pair[4].x1]
    if len(openings) != 1:
        return {}, warning
    opening = openings[0]
    closings = [pair for pair in pairs['New Balance']
               if opening[2].y1 <= pair[2].y0 <= opening[2].y1 + heading.page_height // 3
               and abs(pair[2].x0 - opening[2].x0) <= heading.page_width // 50
               and abs(pair[4].x1 - opening[4].x1) <= heading.page_width // 50]
    result = {}
    for role, candidates in (('opening', openings), ('closing', closings)):
        if len(candidates) != 1:
            continue
        index, label, _, value, _ = candidates[0]
        fields = dict(description=f'{role.title()} Balance',
                      balance_column=str(value['column_index']),
                      balance_label_column=str(label['column_index']),
                      balance_convention='liability_owed')
        issues = []
        try:
            raw = re.sub(r'^=\s*', '', value['expected_text'].strip())
            # Preserve a minus printed before a currency symbol, including a
            # credit balance. Negation must also fit the ledger's signed range.
            sign = -1 if raw.startswith('-') else 1
            raw = re.sub(r'^[+-]\s*', '', raw)
            amount = int(exact_amount(raw, currency)) * sign
            if not -9223372036854775807 <= amount <= 9223372036854775807:
                raise ValueError('This balance exceeds the supported range.')
            fields['balance'] = str(amount)
        except ValueError:
            issues.append(f'Check the {role} amount owed against the highlighted account-summary value.')
        result[index] = dict(fields=fields, issues=issues, excluded=True, kind='balance')
    return result, warning if len(closings) != 1 else []
