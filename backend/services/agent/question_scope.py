"""What a question names, so the answer stays on it (AG-02: "references data the user didn't ask about").

``build`` reads the question against the case's accounts and returns the people, accounts, identifiers and dates it
names, ranked: an account the question names by number or id first, then accounts of a person it names. ``block``
turns that into the focus lines both the agent's planning prompt and its final-answer prompt carry, with the rule
to answer only that and offer anything else as one "Also found:" line.

Decision (rule 2): the scope ranks and focuses; it never removes a row from what the model reads. A broad question
("go through the financials" about Erica Hopper) needs accounts it does not name (her grandfather's), so cutting rows
by name would lose evidence. Reverse with a replay showing trimmed results keep every fact and citation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_ACCOUNT_REF = re.compile(r"account:(" + _UUID + ")", re.I)
_DIGITS = re.compile(r"(?<![\w-])\d[\d ]{2,}\d(?![\w-])")
_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|"
           "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b|\b\d{1,2} (?:" + _MONTHS + r")\.? \d{4}\b|\b(?:" + _MONTHS
                   + r")\.? (?:\d{1,2},? )?\d{4}\b|\b(?:19|20)\d{2}\b", re.I)
# Two to five capitalised words: a name the case may not hold as an account holder.
_NAME = re.compile(r"\b(?:[A-Z][a-zA-Z'À-ſ.-]+|[A-Z]{2,})(?:\s+(?:de|del|la|van|von|[A-Z][a-zA-Z'À-ſ.-]+"
                   r"|[A-Z]{2,})){1,4}\b")
_NOT_NAMES = frozenset({"which", "what", "who", "how", "does", "did", "is", "are", "the", "this", "can", "could",
                        "please", "show", "list", "give", "tell", "find", "where", "when", "why", "here", "in", "on"})
_WORD = re.compile(r"[a-zà-ſ]+")


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


@dataclass
class Scope:
    names: list[str] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)  # ranked
    identifiers: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.names or self.accounts or self.identifiers or self.dates)


def _holder_named(holder: str, question_words: set[str]) -> bool:
    """A holder ("ERICA HOPPER / LASHIKA -HOPPER") is named when, for one of its people, the first and last word of
    the name are both in the question."""
    for person in re.split(r"\s*/\s*|\s+&\s+|\s+and\s+", holder or ""):
        words = [w for w in _words(person) if len(w) > 1]
        if len(words) >= 2 and words[0] in question_words and words[-1] in question_words:
            return True
    return False


def build(question: str, accounts: Iterable[dict[str, Any]] = ()) -> Scope:
    """``accounts``: the case's accounts as dicts with id, holder, institution, identifier (as printed or digits)."""
    text = question or ""
    scope = Scope()
    for match in _NAME.finditer(text):
        words = match.group(0).split()
        while words and words[0].lower() in _NOT_NAMES:
            words = words[1:]
        if len(words) >= 2 and match.group(0) not in scope.names:
            scope.names.append(" ".join(words))
    refs = {m.group(1).lower() for m in _ACCOUNT_REF.finditer(text)}
    digit_runs = [re.sub(r"\D", "", m.group(0)) for m in _DIGITS.finditer(text)]
    scope.identifiers = [d for d in dict.fromkeys(digit_runs)
                         if len(d) >= 4 and not (len(d) == 4 and d[:2] in ("19", "20"))]
    scope.dates = list(dict.fromkeys(m.group(0) for m in _DATE.finditer(text)))
    question_words = set(_words(text))
    by_number, by_holder = [], []
    for account in accounts:
        account_id = str(account.get("id") or "").lower()
        digits = re.sub(r"\D", "", str(account.get("identifier") or ""))
        if account_id in refs or (len(digits) >= 4 and any(digits.endswith(d) or d.endswith(digits)
                                                            for d in scope.identifiers)):
            by_number.append(account)
        elif _holder_named(str(account.get("holder") or ""), question_words):
            by_holder.append(account)
    scope.accounts = by_number + by_holder
    if not scope.names:
        for account in by_holder:
            for person in re.split(r"\s*/\s*|\s+&\s+|\s+and\s+", str(account.get("holder") or "")):
                if _holder_named(person, question_words) and person.strip() not in scope.names:
                    scope.names.append(person.strip())
    return scope


STAY_ON_THE_QUESTION = (
    "Stay on the question. Answer what was asked, first, in one to three sentences. Then give the evidence for that "
    "answer with its citations. Then give only the limits that change the answer. Leave out accounts, people, totals, "
    "checks, proposals and caveats the question did not ask about, even when a tool returned them or a rule below "
    "asks for them in other answers. Where a person must still settle something the answer rests on, end with "
    "'Open questions:', one line each. When something the question did not ask about matters to it, add one line "
    "at the end that starts 'Also found:'. Never drop the citation of a fact you state. Write as an investigator "
    "reporting findings, not as a system describing the checks it ran."
)

MAX_FOCUS_ACCOUNTS = 12


def _account_line(account: dict[str, Any]) -> str:
    parts = [str(account.get(k)).strip() for k in ("holder", "institution", "identifier") if account.get(k)]
    return " · ".join(parts) or str(account.get("id"))


def block(scope: Scope) -> str:
    """The focus lines for the prompts; empty when the question names nothing the case holds."""
    lines = [STAY_ON_THE_QUESTION]
    if scope.empty:
        return "\n".join(lines)
    lines.append("What the question names (answer about these first):")
    if scope.names:
        lines.append("- People or companies: " + "; ".join(scope.names))
    if scope.accounts:
        shown = scope.accounts[:MAX_FOCUS_ACCOUNTS]
        more = len(scope.accounts) - len(shown)
        lines.append("- Case accounts it concerns: " + "; ".join(_account_line(a) for a in shown)
                     + (f"; and {more} more of the same holders" if more > 0 else ""))
    if scope.identifiers:
        lines.append("- Numbers: " + ", ".join(scope.identifiers))
    if scope.dates:
        lines.append("- Dates: " + ", ".join(scope.dates))
    return "\n".join(lines)


def case_accounts(session, case_id) -> list[dict[str, Any]]:
    """The case's accounts for ``build`` (one read; a failure gives none, never stops a run)."""
    import uuid
    from sqlalchemy import select
    from postgres.models.financial import FinancialAccount as A
    case = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
    rows = session.execute(select(A.id, A.holder_name, A.institution_name, A.identifier_as_printed,
                                  A.identifier_normalised).where(A.case_id == case)).all()
    return [dict(id=str(r[0]), holder=r[1], institution=r[2], identifier=r[3] or r[4]) for r in rows]


def focus_for(session, case_id, question: str) -> str:
    """The focus block for one question; the stay-on-the-question rule alone when the case cannot be read."""
    import logging
    try:
        with session.begin_nested():  # a savepoint: a failed read never undoes the run's own unsaved rows
            accounts = case_accounts(session, case_id)
    except Exception:  # noqa: BLE001 - focus helps the answer; it never stops a run
        logging.getLogger(__name__).warning("Question scope: case accounts could not be read", exc_info=True)
        accounts = []
    return block(build(question, accounts))
