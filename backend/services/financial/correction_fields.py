"""Validate source-field corrections without changing stored observations."""
from datetime import date
import re

DATE_FIELDS = frozenset(('transaction_date', 'posted_date', 'value_date', 'effective_date'))
TEXT_FIELDS = frozenset(('description', 'counterparty_raw', 'bank_reference', 'transaction_type'))
ALLOWED_FIELDS = DATE_FIELDS | TEXT_FIELDS | {'running_balance_minor'}


def correction_fields(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict) or set(raw) - ALLOWED_FIELDS:
        raise ValueError('Only printed transaction dates, text and balance can be corrected here.')
    result = {}
    for key, value in raw.items():
        if value is None:
            result[key] = None
        elif key in DATE_FIELDS:
            if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError('Dates must use YYYY-MM-DD or be empty.')
            result[key] = date.fromisoformat(value)
        elif key in TEXT_FIELDS:
            if not isinstance(value, str) or len(value) > 4000 or '\x00' in value:
                raise ValueError('Corrected text must contain at most 4,000 characters and no null character.')
            result[key] = value
        else:
            if not isinstance(value, str) or not re.fullmatch(r'-?(0|[1-9][0-9]{0,18})', value):
                raise ValueError('The balance must be an exact integer in minor units or empty.')
            result[key] = int(value)
            if not -9223372036854775808 <= result[key] <= 9223372036854775807:
                raise ValueError('The balance is outside the ledger range.')
    return result


def json_fields(fields):
    return {key: value.isoformat() if isinstance(value, date) else
            str(value) if key == 'running_balance_minor' and value is not None else value
            for key, value in fields.items()}
