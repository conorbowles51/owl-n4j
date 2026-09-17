"""Recognise complete information pages without hiding mixed payment pages."""
import re


def capital_information_kind(rows):
    texts = [cell['expected_text'].strip() for row in rows for cell in row['cells']]
    content = ' '.join(texts).lower()
    # A familiar notice beside a transaction table must not suppress that table.
    if any(text.lower() in ('date', 'trans date', 'transaction date', 'post date',
                           'transactions', 'account summary', 'fees', 'interest charged')
           for text in texts):
        return None
    if any(re.search(r'(?i)account ending in|mastercard ending in', text) for text in texts):
        return None
    for row in rows:
        cells = row['cells']
        if (len(cells) >= 2 and re.match(r'^(?:\d{1,4}[/-]\d{1,2}|[A-Za-z]{3}\.?\s+\d{1,2})', cells[0]['expected_text'])
                and any(re.search(r'\d[,.]\d{2}\b', c['expected_text']) for c in cells[1:])):
            return None
    if all(phrase in content for phrase in ('how can i avoid paying interest charges?',
                                           'how can i close my account?', 'billing rights summary')):
        return 'card_terms'
    if 'capital one' not in content and 'capitalone.com' not in content:
        return None
    if (all(phrase in content for phrase in ('do with your personal information?',
                                             'financial companies choose how they share',
                                             'to limit our'))
            or all(phrase in content for phrase in ('who is providing this',
                                                    'protect your personal information',
                                                    'computer safeguards and secured files'))):
        return 'privacy_notice'
    if all(phrase in content for phrase in ('your billing cycle end date',
                                            'your payment due date will stay the same',
                                            'starting with your next statement')):
        return 'billing_notice'
    if all(phrase in content for phrase in ('referfriendsnow', 'earn a bonus', 'refer')):
        return 'advertisement'
    return None
