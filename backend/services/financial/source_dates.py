"""Conservative numeric and English named-month date proposals. Never infer locale, year or OCR repairs."""
import re
from datetime import date


_MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july",
                "august", "september", "october", "november", "december")
_MONTHS = {label: number for number, name in enumerate(_MONTH_NAMES, 1)
           for label in (name, name[:3])}
_MONTHS["sept"] = 9


def _named_parts(text):
    # Explicit English month tokens only. No locale, fuzzy spelling or OCR repair.
    day_first = re.fullmatch(r"([0-9]{1,2})[ \t]+([A-Za-z]+)\.?(?:[ \t]+([0-9]{4}|[0-9]{2}))?", text)
    month_first = re.fullmatch(r"([A-Za-z]+)\.?[ \t]+([0-9]{1,2})(?:(?:,[ \t]*|[ \t]+)([0-9]{4}|[0-9]{2}))?", text)
    if day_first:
        day, month, year = day_first.groups()
        order = "day-month-year"
    elif month_first:
        month, day, year = month_first.groups()
        order = "month-day-year"
    else:
        return None
    if month.lower() not in _MONTHS:
        return None
    return int(day), _MONTHS[month.lower()], year, order


def assess_date_text(raw, origin):
    text = raw.strip()
    proposals = []
    status = "unsupported"
    explanation = "This format was not interpreted. Review the original date and its context."
    iso = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", text)
    numeric = re.fullmatch(r"([0-9]{1,2})([/.-])([0-9]{1,2})(?:\2([0-9]{4}|[0-9]{2}))?", text)
    if iso:
        try:
            value = date(*(int(v) for v in iso.groups()))
            proposals = [dict(iso_date=value.isoformat(), order="year-month-day")]
            status = "unambiguous_format"
            explanation = "One valid ISO calendar reading. This does not verify the source glyphs or date role."
        except ValueError:
            status = "invalid_calendar_date"
            explanation = "The printed ISO-shaped value is not a valid calendar date. No repair was guessed."
    elif (named := _named_parts(text)) is not None:
        day, month, year, order = named
        try:
            # Test possible month/day only when the printed full year is absent.
            value = date(int(year) if year and len(year) == 4 else 2000, month, day)
        except ValueError:
            status = "invalid_calendar_date"
            explanation = "The named-month reading is not a valid calendar date. No repair was guessed."
        else:
            if year and len(year) == 4:
                proposals = [dict(order=order, iso_date=value.isoformat())]
                status = "unambiguous_format"
                explanation = "One calendar reading with an explicit English month name. This does not verify the source glyphs or date role."
            else:
                proposals = [dict(order=order, month=month, day=day)]
                status = "missing_year" if not year else "ambiguous_century"
                explanation = "A complete four-digit year is required from source context. No current year or century was assumed; leap-day validity may depend on that year."
    elif numeric:
        left, _, right, year = numeric.groups()
        # A leap year is used only to test whether a month/day can ever exist.
        # It is never emitted or supplied as a proposed source year.
        calendar_year = int(year) if year and len(year) == 4 else 2000
        for order, day, month in (("day-month-year", int(left), int(right)),
                                  ("month-day-year", int(right), int(left))):
            try:
                value = date(calendar_year, month, day)
            except ValueError:
                continue
            proposals.append(dict(order=order, **({"iso_date": value.isoformat()}
                if year and len(year) == 4 else {"month": month, "day": day})))
        if not proposals:
            status = "invalid_calendar_date"
            explanation = "Neither numeric date order produces a valid calendar date. No repair was guessed."
        elif not year or len(year) == 2:
            status = "missing_year" if not year else "ambiguous_century"
            explanation = "A complete four-digit year is required from source context. No current year or century was assumed; leap-day validity may depend on that year."
        elif len({p["iso_date"] for p in proposals}) > 1:
            status = "ambiguous_order"
            explanation = "Both day-first and month-first readings are valid. Source context must establish the date order."
        else:
            status = "unambiguous_format"
            explanation = "One calendar date fits the supported numeric orders. This does not verify the source glyphs or date role."
    return dict(raw=raw, origin=origin, status=status, proposals=proposals,
        requires_source_review=True, explanation=explanation,
        glyph_limitation=("Digital text still requires source/context review." if origin == "digital_text_layer"
            else "Recognised or unknown glyphs may be wrong even when a calendar reading is valid."))
