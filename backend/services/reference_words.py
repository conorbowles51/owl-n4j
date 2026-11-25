"""Words that point at a person or body without naming one: pronouns, kin and role words ('She', 'Mother',
'Plaintiff', 'The Court', 'Lic', 'Unknown Victim').

Entity extraction stored such words as aliases (a Person in case 5eeaa265 had the alias
'She'), and the Similar entities scan, which pairs people by alias, then paired two different people at 100 %
whenever a second record was named by the same word. Measured on the live graphs, 25 Nov 2026: this rule takes 112 of
the 1,314 alias suggestions away and leaves 1,202, and the 21 merges people made that an alias
pair suggests are all still suggested.

A bare pronoun names no one and is never an alias. A role word can name one person within a case ('Mommy' on a
Person merged by a person with the record 'Mommy' in 0e4fb172) but not several ('The Court' as an alias of
three different judges in 042cfaee), so the scan pairs on a role word only when two records carry it.

A text is a reference word when every word in it, after a leading article or possessive ('the', 'my', 'su'), is in
the lists below, or it is 'unknown' with role words ('Unknown Male'), or bracketed '[Unknown]'. A word that names
someone ('Ana Ruiz's mother', 'Suspect 4', 'Juror No. 313', 'Licenciado Ortega') is not one.

The evidence engine imports this module too (the backend is on its path), so extraction and the scan agree.
"""
from __future__ import annotations

import re
import unicodedata

_LEADING = frozenset({
    "the", "a", "an", "my", "your", "his", "her", "their", "our", "this", "that",
    "el", "la", "los", "las", "un", "una", "mi", "tu", "su", "sus", "mis", "tus",
})

_PRONOUNS = frozenset({
    "he", "she", "him", "her", "his", "hers", "they", "them", "their", "theirs", "i", "me", "you", "we", "us", "it",
    "himself", "herself", "themselves", "ella", "el", "ellos", "ellas", "usted", "yo",
})

_ROLES = frozenset({
    # kin and relations
    "mother", "mom", "mum", "mommy", "father", "dad", "daddy", "son", "daughter", "brother", "sister", "wife",
    "husband", "uncle", "aunt", "cousin", "grandmother", "grandfather", "grandma", "grandpa", "child", "minor",
    "babe", "girlfriend", "boyfriend", "friend", "partner", "spouse", "parent", "parents",
    "madre", "mama", "padre", "papa", "hijo", "hija", "hermano", "hermana", "esposa", "esposo", "tio", "tia",
    "primo", "prima", "abuela", "abuelo", "novia", "novio", "amigo", "amiga", "comadre", "compadre", "tocayo",
    # roles in a case or a business
    "victim", "witness", "plaintiff", "defendant", "respondent", "petitioner", "suspect", "subject", "subj",
    "accused", "complainant", "court", "clerk", "judge", "magistrate", "juror", "jury", "prosecutor", "prosecution",
    "police", "officer", "detective", "agent", "investigator", "lab", "laboratory", "law", "enforcement",
    "doctor", "lawyer", "attorney", "counsel", "boss", "owner", "manager", "employee", "customer", "client",
    "company", "person", "individual", "male", "female", "man", "woman", "recipient", "sender", "caller",
    "contact", "participant", "party", "first", "second", "third", "user", "unknown", "unidentified",
    "lic", "licenciado", "licenciada", "jefe", "jefa", "patron", "conta", "contador", "contadora", "senor",
    "senora", "victima", "testigo", "sospechoso", "abogado", "abogada",
    # the possessive 's of "Victim's Mother" after punctuation is folded away
    "s",
})

_ALL = _PRONOUNS | _ROLES


def _words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^0-9a-z]+", " ", folded).split()


def _capital_name(text: str | None, words: list[str]) -> bool:
    """'US' and 'IT' in capitals are the United States and a department, not 'us' and 'it'."""
    return words in (["us"], ["it"]) and (text or "").strip().isupper()


def reference_key(text: str | None) -> str:
    """The words of a pronoun or role word, leading article left out ('The Court' and 'COURT' give 'court');
    '' for a text that names someone."""
    words = _words(text or "")
    if _capital_name(text, words):
        return ""
    if words and words[0] in _LEADING and len(words) > 1:
        words = words[1:]
    return " ".join(words) if words and all(word in _ALL for word in words) else ""


def is_reference_word(text: str | None) -> bool:
    """True when ``text`` points at someone without naming them ('She', 'The Court', 'Unknown Victim')."""
    return bool(reference_key(text))


def is_pronoun(text: str | None) -> bool:
    """True for a bare pronoun ('She', 'him', 'ella'): it names no one, in any document."""
    words = _words(text or "")
    return len(words) == 1 and words[0] in _PRONOUNS and not _capital_name(text, words)


def drop_pronouns(aliases) -> list:
    """The aliases, in order, without bare pronouns. Role words stay: 'Mommy' on a Person is how a document
    names her, and a person merged her with the record 'Mommy' (case 0e4fb172)."""
    return [alias for alias in aliases if not is_pronoun(alias if isinstance(alias, str) else str(alias))]
