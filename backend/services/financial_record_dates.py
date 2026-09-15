"""Calendar dates recorded in financial evidence, without inferred parts."""

from datetime import date
import re


def financial_record_day(value):
    """Use the recorded calendar day without inventing missing date parts."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[T ](?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,9})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?)?', text):
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None



def validate_financial_date_range(start, end):
    for bound in (start, end):
        if bound and (len(bound) != 10 or financial_record_day(bound) is None):
            raise ValueError("Use complete valid dates in YYYY-MM-DD format.")
    if start and end and start > end:
        raise ValueError("The start date must be on or before the end date.")
