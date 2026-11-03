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
           "$": ("USD", "CAD", "AUD", "MXN", "NZD", "HKD", "SGD", "ARS", "CLP", "COP"), "¥": ("JPY", "CNY"),
           "Rs.": ("INR", "PKR", "LKR", "NPR"), "Rs": ("INR", "PKR", "LKR", "NPR"), "₨": ("INR", "PKR", "LKR", "NPR")}
_SYM = "|".join(re.escape(s) for s in sorted(SYMBOLS, key=len, reverse=True))
# a group is exactly three digits (never followed by a fourth); a number never continues a word, a mask or a date
_NUM = r"(?:\d{1,3}(?:[.,'’ ]\d{3}(?!\d))+(?:[.,]\d{1,2}(?!\d))?|\d+(?:[.,]\d{1,3}(?!\d))?)(?![0-9A-Za-z])"
_NUM_POST = r"(?<![\w*•/.,-])" + _NUM
_CODE = r"[A-Z]{3}"
# a symbol or code before the number is searched first, on its own: in "A/c XX1234 INR 500.00" the code belongs to
# the number after it, never to the account digits before it
AMOUNT_PRE = re.compile(r"(?:(?P<pre_sym>%s)\s?(?P<n1>%s)|(?P<pre_code>\b%s)\s?(?P<n2>%s))" % (_SYM, _NUM, _CODE, _NUM))
AMOUNT_POST = re.compile(r"(?:(?P<n3>%s)\s?(?P<post_sym>%s)|(?P<n4>%s)\s?(?P<post_code>%s\b))" % (_NUM_POST, _SYM,
                                                                                                    _NUM_POST, _CODE))
BALANCE_BEFORE = re.compile(r"(?i)(?:balance|bal\.?|avail(?:able)?|limit|credit line)\W{0,3}(?:is|of|:)?\W{0,3}$")
DUE_NOTICE = re.compile(r"(?i)\b(?:is due|due on|due date|minimum payment|payment reminder|statement is ready)\b")
# "debited from your A/c", "credited to card": the owner's own account, not the other side's
OWN_SIDE = re.compile(r"(?i)\b(?:debited|credited|withdrawn|charged|deducted|drawn)\s+(?:to|from)\W{1,3}(?:your\s)?"
                      r"(?:a/c|acct\.?|account|card)?\W{0,3}$")
COUNTERPARTY_REF = re.compile(r"(?i)\b(?:to|from|beneficiary|payee)\W{1,3}(?:your\s)?(?:a/c|acct\.?|account|card)?\W{0,3}$")
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


def amount_minor(number: str, currency: str | None, decimal_separator: str | None, group_separator=None):
    """(minor units or None, flag or None). A space between digit groups is read as grouping only when the
    institution says it groups with a space ("$40 711 Store" is not forty thousand)."""
    if " " in number and group_separator != " ":
        return None, "ambiguous_separator"
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
    code = _g(m, "pre_code") or _g(m, "post_code")
    if code:
        try:
            return get_currency(code).code, None
        except UnknownCurrencyError:
            return None, "currency_unknown"
    sym = _g(m, "pre_sym") or _g(m, "post_sym")
    options = SYMBOLS.get(sym, ())
    if len(options) == 1:
        return options[0], None
    listed = [c for c in ((institution or {}).get("currencies") or []) if c in options]
    if len(listed) == 1:
        return listed[0], None
    return None, "currency_unknown"


def _g(m, name):
    return m.groupdict().get(name)


def _is_amount(m, text) -> bool:
    if _g(m, "pre_code") or _g(m, "post_code"):
        code = _g(m, "pre_code") or _g(m, "post_code")
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


# a card number printed in groups of four ("4111 1111 1111 1234"): only whole groups of four, never a date or an
# amount that follows an ending ("ending 1234 12/05", "ending in 1234 2025-11-02")
_MORE_GROUPS = re.compile(r"(?:[ -]\d{4}){1,4}")
_ENDING_WORDS = re.compile(r"\b(?:end(?:s|ing)?|last)\b|xx|[*•]", re.I)


def _reference(norm: str):
    """(printed, digits, partial, span, counterparty): the account or card the text names. A number printed in groups
    ("4111 1111 1111 1234") is read whole. A reference after "to" or "from" is the other side's account
    (``counterparty``), never the phone owner's, so it never binds."""
    from services.financial.account_mentions import mentions
    for ref in mentions(norm):
        digits = re.sub(r"\D", "", ref["normalised"])
        if len(digits) < 4:
            continue
        end = ref["end"]
        # an ending ("ending 1234", "last 4", "XX1234", "*1234") is never extended into a longer number
        ending_form = _ENDING_WORDS.search(norm[max(0, ref["start"] - 16):ref["end"]])
        more = _MORE_GROUPS.match(norm, end) if len(digits) == 4 and not ending_form else None
        # the groups are read whole or not at all: a match that stops before another digit or letter is a number of
        # another shape, and a shorter card number would name the wrong ending
        if more and re.match(r"[\w]|[ -]\d", norm[more.end():more.end() + 2]):
            more = None
        if more and "*" not in ref["normalised"] and 12 <= len(digits) + len(re.sub(r"\D", "", more.group())) <= 19:
            digits += re.sub(r"\D", "", more.group())
            end = more.end()
        before = norm[max(0, ref["start"] - 30):ref["start"]]
        other = bool(COUNTERPARTY_REF.search(before)) and not OWN_SIDE.search(before)
        return norm[ref["start"]:end].strip(), digits, bool(ref["partial"]) or len(digits) <= 4, \
            (ref["start"], end), other
    m = ENDING.search(norm)
    if m:
        d = m.group("d") or m.group("e")
        return m.group().strip(), d, True, (m.start(), m.end()), False
    return None


def parse(text: str, *, institution: dict | None = None, phone_country: str | None = None,
          template: dict | None = None) -> MoneyReading | None:
    """``institution``: a directory entry (its ``currencies`` and ``decimal_separator``); ``template``: the entry's
    template for this channel when the entry is reviewed, else ``None`` (``template = generic``)."""
    norm, offsets = normalise(text)
    pre = [m for m in AMOUNT_PRE.finditer(norm) if _is_amount(m, norm)]
    taken = [(m.start(), m.end()) for m in pre]
    post = [m for m in AMOUNT_POST.finditer(norm) if _is_amount(m, norm) and
            not any(a < m.end() and m.start() < b for a, b in taken)]
    found = sorted(pre + post, key=lambda m: m.start())
    if not found:
        return None
    flags = []
    # a balance or limit is not the payment: the first amount not introduced as one is read
    plain = [m for m in found if not BALANCE_BEFORE.search(norm[max(0, m.start() - 30):m.start()])]
    if len(plain) < len(found):
        flags.append("balance_mentioned")
    m = (plain or found)[0]
    if len({x.group() for x in found}) > 1:
        flags.append("several_amounts")
    number = next(_g(m, g) for g in ("n1", "n2", "n3", "n4") if _g(m, g))
    currency, cflag = _currency(m, norm, institution)
    if cflag:
        flags.append(cflag)
    minor, aflag = amount_minor(number, currency, (institution or {}).get("decimal_separator"),
                                (institution or {}).get("group_separator"))
    if aflag:
        flags.append(aflag)
    lower = norm.casefold()
    direction = _direction(lower, template)
    if DUE_NOTICE.search(norm):
        direction = None  # "your credit card payment is due": a reminder, not a payment
        flags.append("payment_due_notice")
    if direction is None:
        flags.append("direction_unknown")
    spans = [(*_span(offsets, m.start(), m.end()), "amount")]
    ref = _reference(norm)
    account_ref = digits = counterparty_ref = None
    partial = False
    if ref:
        printed, refdigits, refpartial, (rs, re_), other = ref
        if other:
            counterparty_ref = refdigits[-4:]
            flags.append("other_side_account")
            spans.append((*_span(offsets, rs, re_), "counterparty_account"))
        else:
            account_ref, digits, partial = printed, refdigits, refpartial
            spans.append((*_span(offsets, rs, re_), "account_ref"))
    counterparty = None
    pattern = (template or {}).get("counterparty_pattern")
    if pattern:
        cm = re.search(pattern, norm)
        if cm and cm.groupdict().get("payee"):
            counterparty = cm.group("payee").strip()
            spans.append((*_span(offsets, cm.start("payee"), cm.end("payee")), "counterparty"))
    sd = STATED_DATE.search(norm)
    if counterparty_ref and not counterparty:
        counterparty = "account ending %s" % counterparty_ref
    return MoneyReading(amount_minor=minor, currency=currency, direction=direction, account_ref=account_ref,
                        account_digits=digits, account_partial=partial, counterparty_text=counterparty,
                        stated_date=sd.group() if sd else None, template=(template or {}).get("name") or (
                            "template" if template else GENERIC),
                        amount_text=text[spans[0][0]:spans[0][1]], flags=flags, spans=spans)
