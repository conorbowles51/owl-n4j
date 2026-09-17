"""Recognise complete information pages without hiding mixed payment pages."""
import re


def andrews_information_kind(rows):
    texts = [cell['expected_text'].strip() for row in rows for cell in row['cells']]
    content = ' '.join(texts).lower()
    if 'andrews' not in content:
        return None
    # Check every table on the physical page before classifying a form.
    if any(re.sub(r'\s+', '', text).lower() == 'accountstatement'
           or text.lower() in ('transaction date', 'transactions', 'amount')
           or re.search(r'(?i)previous\s*balance|ending\s*balance', text) for text in texts):
        return None
    if any(re.match(r'(?i)^\S{4,10}\s+(?:ID|Withdrawal|Deposit|Recurring)\b', ' '.join(c['expected_text'] for c in row['cells']))
           or (len(row['cells']) >= 2
               and re.match(r'^\d{1,4}[/-]\d{1,2}', row['cells'][0]['expected_text'])
               and any(re.search(r'\d[,.]\d{2}\b', c['expected_text']) for c in row['cells'][1:])) for row in rows):
        return None
    if ('andrews federal credit union' in content
            and 'membership application and signature card' in content
            and ('section 1 - minor information' in content or 'section 4 - beneficiaries' in content)):
        return 'account_application'
    if (all(text in content for text in ('andrews federal credit union', 'guaranty and indemnification agreement', 'recitals'))
            or all(text in content for text in ('right to proceed directly against the guarantor', 'waiver', 'amendments', 'severability'))):
        return 'account_agreement'
    return None


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


def merrick_information_kind(rows):
    """Recognise supporting paperwork without clearing payment-history pages."""
    texts = [cell['expected_text'].strip() for row in rows for cell in row['cells']]
    content = ' '.join(texts).lower().replace('’', "'")
    # Apply these checks across every table on the physical page. Account
    # summaries and payment lists must retain their separate review path.
    if any(phrase in content for phrase in ('transactions, payments and credits',
            'payment history', 'summary of account activity')):
        return None
    if any(text.lower() in ('trans date', 'transaction date', 'item description',
                            'amount', 'from account', 'previous balance', 'new balance') for text in texts):
        return None
    for row in rows:
        cells = row['cells']
        if (len(cells) >= 2
                and re.match(r'^(?:\d{1,4}[/-]\d{1,2}|[A-Za-z]{3}\.?\s+\d{1,2})', cells[0]['expected_text'])
                and any(re.search(r'\d[,.]\d{2}\b', c['expected_text']) for c in cells[1:])):
            return None
    branded = 'merrick bank' in content or 'merrickbank.com' in content
    if branded and all(phrase in content for phrase in (
            'in response to the request received', 'copies of the monthly billing statements',
            'copies of the payments made on the account')):
        return 'records_cover_letter'
    if branded and all(phrase in content for phrase in ('original application information', 'applicant', 'auth user')):
        return 'account_application'
    if all(phrase in content for phrase in ('app info', 'app received date', 'solicitation number',
                                          'applicant signature', 'original app employment')):
        return 'account_application'
    if branded and all(phrase in content for phrase in ('cardholder news', 'cardholder center', 'enroll')):
        return 'cardholder_notice'
    if branded and all(phrase in content for phrase in ('interest charge calculation',
            'your annual percentage rate (apr)', 'type of balance', 'purchases', 'cash advances')):
        return 'interest_calculation'
    if branded and all(phrase in content for phrase in ("state's attorney's subpoena",
            'obtaining documents', 'certification from custodian of records')):
        return 'records_request'
    if all(phrase in content for phrase in ('any surveillance video and pictures of access',
            'all account reviews from', 'correspondences to or from the account holder', 'not just received')):
        return 'records_request'
    if all(phrase in content for phrase in ('certificate of service', "state's attorney's subpoena",
                                          'postage prepaid', 'financial institutions')):
        return 'records_request_service'
    if branded and all(phrase in content for phrase in ('certification of custodian of records',
            'or other qualified individual', 'true and correct copies')):
        return 'records_certification'
    return None
