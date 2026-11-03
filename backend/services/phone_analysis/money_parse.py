"""A phone text read as a money reading (docs/cellebrite/05 section 4.3.2). Pure and deterministic.

``parse(text, *, institution=None, phone_country=None)`` returns a ``MoneyReading`` or ``None`` when the text states
no amount. A reading with a defect is still produced, with its flags (flag, don't refuse): ``ambiguous_separator``
(the amount is not converted), ``currency_unknown``, ``direction_unknown``, ``several_amounts``. Integer arithmetic only;
minor units from the currency's exponent (``services.financial.money``).

Separators: a number whose final separator has exactly two digits after it is a decimal reading (a group always has
three); a number with two different separators reads the final one as the decimal; one kind of separator repeated
is grouping. Otherwise (``1,234``) the institution's ``decimal_separator`` decides, and with none the amount is
``ambiguous_separator``.

Currency: an ISO code beside the number; else a symbol naming one currency (``€``, ``£``, ``US$``); a symbol several
currencies use (``$``) takes the institution's one currency of that symbol, else ``currency_unknown``.

Account or card reference: ``services.financial.account_mentions.mentions`` (labelled references) and the endings an
alert prints ("ending in 1234", "x1234", "*1234"). Four or fewer visible digits is ``partial``; a partial reference
never becomes an account identifier (``account_identity``), it binds and leads only.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from services.financial.money import UnknownCurrencyError, get_currency

GENERIC = "generic"
# "credit card" and "debit card" name a card, not a direction: the bare words are not cues
DEBIT_CUES = ("purchase", "purchased", "payment", "paid", "withdrawal", "withdrawn", "sent", "charged", "debited",
              "spent", "transfer to", "transferred to", "atm")
CREDIT_CUES = ("deposit", "deposited", "received", "credited", "refund", "refunded", "transfer from",
               "transferred from", "direct deposit")
SYMBOLS = {"€": ("EUR",), "£": ("GBP",), "₹": ("INR",), "₱": ("PHP",), "₦": ("NGN",), "₩": ("KRW",), "₪": ("ILS",),
           "US$": ("USD",), "C$": ("CAD",), "CA$": ("CAD",), "A$": ("AUD",), "AU$": ("AUD",), "MX$": ("MXN",),
           "NZ$": ("NZD",), "HK$": ("HKD",), "S$": ("SGD",), "R$": ("BRL",),
           "$": ("USD", "CAD", "AUD", "MXN", "NZD", "HKD", "SGD", "ARS", "CLP", "COP"), "¥": ("JPY", "CNY")}
_SYM = "|".join(re.escape(s) for s in sorted(SYMBOLS, key=len, reverse=True))
_NUM = r"\d{1,3}(?:[.,\u00a0 '’]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,3})?"
_CODE = r"[A-Z]{3}"
AMOUNT = re.compile(
    r"(?:(?P<pre_sym>%s)\s?(?P<n1>%s)|(?P<pre_code>\b%s)\s?(?P<n2>%s)|(?P<n3>%s)\s?(?P<post_sym>%s)|(?P<n4>%s)\s?"
    r"(?P<post_code>%s\b))" % (_SYM, _NUM, _CODE, _NUM, _NUM, _SYM, _NUM, _CODE))
ENDING = re.compile(r"(?i)\b(?:ending(?:\s+in)?|ends\s+in|last\s+(?:4|four)(?:\s+digits)?)\s*:?\s*[x*•]*(?P<e>\d{4})\b"
                    r"|(?<![A-Za-z0-9])[x*•]{1,12}\s?(?P<d>\d{4})\b")
STATED_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|"
                         r"nov|dec)[a-z]*\.? \d{1,2}(?:, ?\d{4})?)\b", re.I)


@dataclass
class MoneyReading:
    amount_minor: int | None
    currency: str | None
    direction: str | None          # debit | credit | None
    account_ref: str | None        # as printed ("ending 1234")
    account_digits: str | None     # the visible digits ("1234")
    account_partial: bool
    counterparty_text: str | None
    stated_date: str | None
    template: str
    amount_text: str
    flags: list = field(default_factory=list)
    spans: list = field(default_factory=list)   # [(start, end, role)] into the original text

    @property
    def testable(self) -> bool:
        return self.amount_minor is not None and self.currency is not None

    def as_dict(self) -> dict:
        return {"amount_minor": self.amount_minor, "currency": self.currency, "direction": self.direction,
                "account_ref": self.account_ref, "account_digits": self.account_digits,
                "account_partial": self.account_partial, "counterparty_text": self.counterparty_text,
                "stated_date": self.stated_date, "template": self.template, "amount_text": self.amount_text,
                "flags": list(self.flags), "spans": [list(s) for s in self.spans]}


def normalise(text: str):
    """(normalised, offsets): NFKC with whitespace collapsed; ``offsets[i]`` is the original index of normalised
    character ``i`` (one more entry for the end)."""
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(text or ""):
        n = unicodedata.normalize("NFKC", ch)
        for c in n:
            if c.isspace():
                if prev_space:
                    continue
                c, prev_space = " ", True
            else:
                prev_space = False
            out.append(c)
            idx.append(i)
    idx.append(len(text or ""))
    return "".join(out), idx


def _span(offsets, s, e):
    return offsets[s], offsets[e - 1] + 1 if e > s else offsets[s]


def amount_minor(number: str, currency: str | None, decimal_separator: str | None):
    """(minor units or None, flag or None)."""
    digits_only = re.sub(r"[\u00a0 '’]", "", number)
    seps = [(m.start(), m.group()) for m in re.finditer(r"[.,]", digits_only)]
    exponent = None
    if currency:
        try:
            exponent = get_currency(currency).exponent
        except UnknownCurrencyError:
            exponent = None
    if not seps:
        whole, frac = digits_only, ""
    else:
        kinds = {s for _, s in seps}
        last_at, last = seps[-1]
        after = digits_only[last_at + 1:]
        if len(kinds) == 2:
            decimal = last
        elif len(seps) > 1:
            decimal = None                       # one kind repeated: grouping only
        elif len(after) in (1, 2):
            decimal = last                       # a group has three digits
        elif decimal_separator in (".", ","):
            # the institution's decimal mark: the same mark is a decimal, the other one groups thousands
            decimal = last if last == decimal_separator else None
        else:
            return None, "ambiguous_separator"
        if decimal is None:
            whole, frac = re.sub(r"[.,]", "", digits_only), ""
        else:
            at = digits_only.rfind(decimal)
            if digits_only.count(decimal) > 1:
                return None, "ambiguous_separator"
            whole = re.sub(r"[.,]", "", digits_only[:at])
            frac = digits_only[at + 1:]
            grouping = digits_only[:at]
            if re.search(r"[.,]", grouping) and not re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", grouping):
                return None, "ambiguous_separator"
    if exponent is None:
        exponent = 2
    if len(frac) > exponent:
        return None, "ambiguous_separator"
    return int(whole or "0") * 10 ** exponent + int((frac + "0" * exponent)[:exponent] or "0"), None


def _currency(m, text, institution) -> tuple:
    code = m.group("pre_code") or m.group("post_code")
    if code:
        try:
            return get_currency(code).code, None
        except UnknownCurrencyError:
            return None, "currency_unknown"
    sym = m.group("pre_sym") or m.group("post_sym")
    options = SYMBOLS.get(sym, ())
    if len(options) == 1:
        return options[0], None
    listed = [c for c in ((institution or {}).get("currencies") or []) if c in options]
    if len(listed) == 1:
        return listed[0], None
    return None, "currency_unknown"


def _is_amount(m, text) -> bool:
    if m.group("pre_code") or m.group("post_code"):
        code = m.group("pre_code") or m.group("post_code")
        try:
            get_currency(code)
        except UnknownCurrencyError:
            return False
    return True


def _direction(lower: str, template: dict | None):
    debit = (template or {}).get("debit_cues") or DEBIT_CUES
    credit = (template or {}).get("credit_cues") or CREDIT_CUES

    def has(words):
        return any(re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(w), lower) for w in words)
    d, c = has(debit), has(credit)
    if d and not c:
        return "debit"
    if c and not d:
        return "credit"
    return None


def _reference(norm: str):
    from services.financial.account_mentions import mentions
    for ref in mentions(norm):
        digits = re.sub(r"\D", "", ref["normalised"])
        if len(digits) >= 4:
            return ref["printed"], digits, bool(ref["partial"]) or len(digits) <= 4, (ref["start"], ref["end"])
    m = ENDING.search(norm)
    if m:
        d = m.group("d") or m.group("e")
        return m.group().strip(), d, True, (m.start(), m.end())
    return None


def parse(text: str, *, institution: dict | None = None, phone_country: str | None = None,
          template: dict | None = None) -> MoneyReading | None:
    """``institution``: a directory entry (its ``currencies`` and ``decimal_separator``); ``template``: the entry's
    template for this channel when the entry is reviewed, else ``None`` (``template = generic``)."""
    norm, offsets = normalise(text)
    found = [m for m in AMOUNT.finditer(norm) if _is_amount(m, norm)]
    if not found:
        return None
    m = found[0]
    flags = []
    if len(found) > 1:
        flags.append("several_amounts")
    number = next(m.group(g) for g in ("n1", "n2", "n3", "n4") if m.group(g))
    currency, cflag = _currency(m, norm, institution)
    if cflag:
        flags.append(cflag)
    minor, aflag = amount_minor(number, currency, (institution or {}).get("decimal_separator"))
    if aflag:
        flags.append(aflag)
    lower = norm.casefold()
    direction = _direction(lower, template)
    if direction is None:
        flags.append("direction_unknown")
    spans = [(*_span(offsets, m.start(), m.end()), "amount")]
    ref = _reference(norm)
    account_ref = digits = None
    partial = False
    if ref:
        account_ref, digits, partial, (rs, re_) = ref
        spans.append((*_span(offsets, rs, re_), "account_ref"))
    counterparty = None
    pattern = (template or {}).get("counterparty_pattern")
    if pattern:
        cm = re.search(pattern, norm)
        if cm and cm.groupdict().get("payee"):
            counterparty = cm.group("payee").strip()
            spans.append((*_span(offsets, cm.start("payee"), cm.end("payee")), "counterparty"))
    sd = STATED_DATE.search(norm)
    return MoneyReading(amount_minor=minor, currency=currency, direction=direction, account_ref=account_ref,
                        account_digits=digits, account_partial=partial, counterparty_text=counterparty,
                        stated_date=sd.group() if sd else None, template=(template or {}).get("name") or (
                            "template" if template else GENERIC),
                        amount_text=text[spans[0][0]:spans[0][1]], flags=flags, spans=spans)
