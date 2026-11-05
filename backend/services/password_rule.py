"""What a new password must be, on every path that sets one. Existing passwords keep working: login never reads this."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

MINIMUM_LENGTH = 12
# bcrypt refuses anything longer.
MAXIMUM_BYTES = 72
MINIMUM_DIFFERENT_CHARACTERS = 5
_LIST = Path(__file__).with_name("common_passwords.txt")
_SEQUENCES = ("abcdefghijklmnopqrstuvwxyz", "01234567890", "qwertyuiopasdfghjklzxcvbnm")
_LOOK_ALIKES = str.maketrans("@$!0134578", "asioleastb")
_WORDS = re.compile(r"[a-z0-9]+")
_ENDS = re.compile(r"^[^a-z]+|[^a-z]+$")
TOO_COMMON = "This password is too common or too easy to guess. Choose something longer and less predictable."


@lru_cache(maxsize=1)
def _common() -> tuple[frozenset[str], frozenset[str]]:
    whole, words = set(), set()
    for line in _LIST.read_text(encoding="utf-8").splitlines():
        if line.startswith("="):
            whole.add(line[1:])
        elif line.startswith("~"):
            words.add(line[1:])
    return frozenset(whole), frozenset(words)


def _repeats(text: str) -> bool:
    return any(len(text) % size == 0 and text == text[:size] * (len(text) // size)
               for size in range(1, len(text) // 2 + 1))


def _in_sequence(text: str) -> bool:
    return any(text in line or text in line[::-1] for line in _SEQUENCES) or (
        len(text) >= 8 and any(text in line * 3 or text in (line * 3)[::-1] for line in _SEQUENCES))


def _personal_parts(email: str | None, name: str | None) -> list[str]:
    """Each word of the name and of the email's local part, and each of those run together."""
    found = []
    for text in ((email or "").lower().split("@")[0], (name or "").lower()):
        words = _WORDS.findall(text)
        found += [*words, "".join(words)]
    return [part for part in found if len(part) >= 4]


def refusal(password: str, *, email: str | None = None, name: str | None = None) -> str | None:
    """A plain reason, or None. The password itself is never in the reason."""
    if len(password) < MINIMUM_LENGTH:
        return f"Use a password of at least {MINIMUM_LENGTH} characters."
    if len(password.encode("utf-8")) > MAXIMUM_BYTES:
        return f"Use a password of at most {MAXIMUM_BYTES} bytes (about {MAXIMUM_BYTES} plain letters)."
    lowered = password.lower()
    whole, words = _common()
    if lowered in whole or _repeats(lowered) or _in_sequence(lowered):
        return TOO_COMMON
    if len(set(lowered)) < MINIMUM_DIFFERENT_CHARACTERS or len(set(_WORDS.findall(lowered))) == 1 < len(_WORDS.findall(lowered)):
        return TOO_COMMON
    # What is left once digits and symbols at the ends go, then with look-alikes (p@ssw0rd) read as letters.
    bare = _ENDS.sub("", lowered)
    core = bare.translate(_LOOK_ALIKES)
    readings = {bare, core, bare.replace("1", "i").translate(_LOOK_ALIKES)}  # 1 stands for l or i
    if readings & words or core in whole or _repeats(core or lowered):
        return TOO_COMMON
    joined = re.sub(r"[^a-z0-9]", "", bare)
    if lowered == (email or "").lower() or any(joined == part or core == part for part in _personal_parts(email, name)):
        return "Do not use your own name or email as the password."
    return None


def require_acceptable(password: str, *, email: str | None = None, name: str | None = None) -> None:
    reason = refusal(password, email=email, name=name)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
