"""Validate denominations and preserve printed numbers across minor-unit scales."""
from typing import Annotated
from pydantic import AfterValidator
from services.financial.money import get_currency, UnknownCurrencyError
from services.financial.pdf_candidates import PdfMappingError


def currency_code(value: str) -> str:
    try:
        return get_currency(value).code
    except UnknownCurrencyError as exc:
        raise ValueError('Choose a supported three-letter currency code.') from exc


CurrencyCode = Annotated[str, AfterValidator(currency_code)]


def rescale_minor(value, before, after):
    """Relabel the same major-unit amount, exactly; never round or exchange."""
    if value is None:
        return None
    original = int(value)
    difference = get_currency(after).exponent - get_currency(before).exponent
    if difference < 0:
        divisor = 10 ** -difference
        if original % divisor:
            raise PdfMappingError(f'An amount has more decimal places than {after} supports. No changes were saved. Check the printed amount before changing currency.', 422)
        result = original // divisor
    else:
        result = original * 10 ** difference
    if not -9223372036854775807 <= result <= 9223372036854775807:
        raise PdfMappingError('An amount would exceed the supported range in the selected currency. No changes were saved.', 422)
    return str(result) if isinstance(value, str) else result
