"""Read numeric amounts in other evidence without manufacturing missing digits."""

from decimal import Decimal, InvalidOperation
import math
import re


def recorded_amount(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    parenthesized = text.startswith("(") and text.endswith(")")
    if parenthesized:
        text = text[1:-1].strip()
    # Accept plain decimals and correctly grouped thousands, with an optional
    # recorded currency prefix/suffix. Arbitrary letters, ranges and ambiguous
    # decimal commas need a source review instead of destructive stripping.
    match = re.fullmatch(r'([+-]?)\s*(?:[$€£]|[A-Z]{3}\s+)?\s*([+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+))(?:\s+[A-Z]{3})?', text)
    if not match or (match[1] and match[2].startswith(('+', '-'))):
        return None
    try:
        exact = Decimal(match[1] + match[2].replace(',', ''))
        if parenthesized:
            if exact < 0 or match[1] or match[2].startswith(("+", "-")):
                return None
            exact = -exact
        numeric = float(exact)
    except (ValueError, InvalidOperation, OverflowError):
        return None
    if (not exact.is_finite() or not math.isfinite(numeric)
            or exact.normalize().as_tuple().exponent < -2
            or abs(exact * 100) > 9007199254740991
            or Decimal(str(numeric)) != exact):
        return None
    return numeric


def recorded_amount_text(value):
    return None if value is None else str(value)
