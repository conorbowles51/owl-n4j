"""Read credit-card account-summary balances from their measured cells."""
import re

from services.financial.locators import Locator, LocatorError
from services.financial.statement_import_proposal import exact_amount


def _rectangle(cell, page):
    try:
        rectangle = Locator.from_json(cell['locator']).rectangle
        return rectangle if rectangle and rectangle.page_number == page else None
    except (LocatorError, ValueError, TypeError, KeyError):
        return None


def balance_control(role, label, value, currency):
    """Keep the printed cell separate from the reviewed amount owed."""
    fields = dict(description=f'{role.title()} Balance',
                  balance_column=str(value['column_index']),
                  balance_label_column=str(label['column_index']),
                  balance_convention='liability_owed')
    issues = []
    try:
        raw = re.sub(r'^=\s*', '', value['expected_text'].strip())
        sign = -1 if raw.startswith('-') else 1
        raw = re.sub(r'^[+-]\s*', '', raw)
        amount = int(exact_amount(raw, currency)) * sign
        if not -9223372036854775807 <= amount <= 9223372036854775807:
            raise ValueError('This balance exceeds the supported range.')
        fields['balance'] = str(amount)
    except ValueError:
        issues.append(f'Check the {role} amount owed against the highlighted account-summary value.')
    return dict(fields=fields, issues=issues, excluded=True, kind='balance')


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
        result[index] = balance_control(role, label, value, currency)
    return result, warning if len(closings) != 1 else []


def merrick_summary_balances(source, currency):
    """Use the left activity box, bounded by the adjacent payment-information box.

    Both boxes repeat New Balance. The coupon above and payment illustrations
    to the right must not provide the activity summary's control amounts.
    OCR can read a box border as | or [; ignoring it does not repair text.
    """
    measured = [(row['row_index'], cell, _rectangle(cell, source['page_number']))
                for row in source['rows'] for cell in row['cells']]
    headings = {name: [(cell, box) for _, cell, box in measured
                       if cell['expected_text'].strip(' |[]') == name]
                for name in ('Summary of Account Activity', 'Payment Information')}
    warning = ['Check the previous and new balances in Summary of Account Activity. Their positions or values could not be read clearly.']
    if not headings['Summary of Account Activity']:
        return {}, warning
    if any(len(items) != 1 or items[0][1] is None for items in headings.values()):
        return {}, warning
    left, right = (headings[name][0][1] for name in headings)
    if (left.page_width != right.page_width or left.page_height != right.page_height
            or right.x0 <= left.x1 or min(left.y1, right.y1) <= max(left.y0, right.y0)):
        return {}, warning
    tolerance = left.page_width // 50
    pairs = {'Previous Balance': [], 'New Balance': []}
    labels = {'Previous Balance': [], 'New Balance': []}
    for index, cell, box in measured:
        label = cell['expected_text'].strip()
        if (label not in pairs or box is None
                or (box.page_width, box.page_height) != (left.page_width, left.page_height)
                or not left.x0 - tolerance <= box.x0 < box.x1 < right.x0
                or not left.y1 <= box.y0 <= left.y1 + left.page_height // 5):
            continue
        labels[label].append(box)
        neighbours = [(value, value_box) for row_index, value, value_box in measured
                      if row_index == index and value_box is not None
                      and (value_box.page_width, value_box.page_height) == (left.page_width, left.page_height)
                      and box.x1 <= value_box.x0 < value_box.x1 < right.x0
                      and min(box.y1, value_box.y1) > max(box.y0, value_box.y0)]
        # Exactly one value prevents treating a detached minus as a positive
        # amount, or choosing one of two readings. Leave those for review.
        if len(neighbours) == 1:
            value, value_box = neighbours[0]
            pairs[label].append((index, cell, box, value, value_box))
    openings = [pair for pair in pairs['Previous Balance']
                if pair[2].y0 <= left.y1 + left.page_height // 20]
    if len(openings) != 1 or len(labels['Previous Balance']) != 1:
        return {}, warning
    opening = openings[0]
    closings = [pair for pair in pairs['New Balance']
               if pair[2].y0 >= opening[2].y1
               and abs(pair[2].x0 - opening[2].x0) <= tolerance
               and abs(pair[4].x1 - opening[4].x1) <= tolerance]
    if len(labels['New Balance']) != 1:
        closings = []
    controls = {}
    for role, candidates in (('opening', openings), ('closing', closings)):
        if len(candidates) == 1:
            index, label, _, value, _ = candidates[0]
            controls[index] = balance_control(role, label, value, currency)
            # This statement layout prints a dollar marker on summary values.
            # OCR can turn $1,234.56 into the valid-looking number 31,234.56.
            # Never strip a leading digit to "repair" it, or silently accept it.
            if not re.match(r'^(?:[+-]\s*)?(?:\$|USD\b)', value['expected_text'].strip()):
                controls[index]['fields'].pop('balance', None)
                controls[index]['issues'] = [f'Check the {role} amount owed in the PDF. The dollar sign was not read and may have become an extra digit.']
    return controls, [] if len(closings) == 1 else warning
