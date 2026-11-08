"""Production numbers (Bates numbers) on evidence: what a file was given, what it arrived with, and where a number goes.

Three kinds, never merged:

- **assigned**: issued by a numbered set of this case. Once issued a number is never issued again (see below).
- **received**: what a disclosure called the file, as a person typed, imported or confirmed it.
- **suggested**: read from the file name by rule, worked out each time and never stored. It stays suggested until a
  person confirms it, and every surface says so.

A set's ``next_number`` only moves up, under a row lock. Withdrawing a range or removing its file leaves the issued
row in place, so the numbers stay spent. A purged file leaves its name and hash on the row.

A number goes to a page only when the range has exactly one number per page of the file. A range whose size differs
from the page count is a conflict shown to the reader, and it opens the file with no page, never a guessed page.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.production_numbers import ProductionAssignment, ProductionSet, ProductionStampedCopy, ReceivedNumber

MAX_FILES_PER_ASSIGN = 5000
MAX_IMPORT_ROWS = 20000
MAX_SEARCH_HITS = 200
PAGE_CHECK_HITS = 20  # a search opens at most this many files to count their pages for a suggested range
MAX_CONFLICTS_SHOWN = 10
MAX_DIGITS = 18  # fits the BigInteger columns
_MAX_NAME_SPAN = 100_000  # a file name's range wider than this is two numbers side by side, not a page range
_CAMERA_PREFIXES = {"IMG", "VID", "PTT", "AUD", "DSC", "DSCN", "DCIM", "PXL", "MOV", "MVI", "WA", "STK", "PIC", "PHOTO",
                    "SCAN", "DOC", "FILE", "CDR", "PTM", "SAM", "GOPR", "RPReplay".upper()}

KIND_ASSIGNED, KIND_RECEIVED, KIND_SUGGESTED = "assigned", "received", "suggested"
SUGGESTED_WORDS = "Suggested from the file name · not confirmed"
NO_PAGES_WORDS = "One number for the whole file: this file has no pages to number."
PAGE_NOT_CERTAIN = "This range does not have one number per page of the file, so the page is not given."


class ProductionNumberError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


# ---- reading numbers ------------------------------------------------------------------------------------------------

_NUMBER = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _.\-]*?)?[ _.\-]*(\d+)\s*$")
_RANGE_TEXT = re.compile(r"^\s*(.*?\d)\s*(?:-|–|—|\bto\b)\s*([A-Za-z]*[ _.\-]*\d+)\s*$", re.IGNORECASE)
_PREFIX = re.compile(r"^[A-Za-z](?:[A-Za-z0-9 _.\-]{0,30}[A-Za-z _.\-])?$")
_LEADING_RANGE = re.compile(r"^(\d{5,10})\s*-\s*(\d{5,10})(?=[\s_.])")
_PREFIXED_RANGE = re.compile(r"(?<![A-Za-z0-9])(?P<first>(?P<head>[A-Za-z]{2,10})[-_ ]?(?P<low>\d{4,10}))\s*-\s*"
                             r"(?P<last>(?P=head)[-_ ]?(?P<high>\d{4,10}))(?![A-Za-z0-9])", re.IGNORECASE)
_WHOLE_NAME_NUMBER = re.compile(r"^([A-Z]{2,10})([-_]?)(\d{5,10})$")


def prefix_key(prefix: str | None) -> str:
    """A prefix as numbers compare: upper case, letters and digits only, so OWL-1 and owl 1 are the same number."""
    return re.sub(r"[^A-Z0-9]", "", (prefix or "").upper())


@dataclass(frozen=True)
class Number:
    key: str
    value: int
    width: int
    text: str


def parse_number(text: str | None) -> Number | None:
    """A number as a person writes it: OWL000012, OWL-12, 001765. None when it is not one."""
    match = _NUMBER.match(text or "")
    if not match or len(match.group(2)) > MAX_DIGITS:
        return None
    return Number(prefix_key(match.group(1)), int(match.group(2)), len(match.group(2)), (text or "").strip())


def parse_range(first: str | None, last: str | None = None) -> tuple[Number, Number]:
    """Both ends of a range, or a refusal in words. One end alone is a range of one."""
    if last is None or not last.strip():
        split = _RANGE_TEXT.match(first or "")
        first, last = (split.group(1), split.group(2)) if split else (first, first)
    low, high = parse_number(first), parse_number(last)
    if low is None or high is None:
        raise ProductionNumberError("That is not a number. Write it as a prefix and digits, for example OWL000012.")
    if high.key and not low.key:
        raise ProductionNumberError("The two ends of the range have different prefixes.")
    if not high.key and low.key:  # "OWL000012-000020": the prefix is written once
        high = Number(low.key, high.value, high.width, high.text)
    if low.key != high.key:
        raise ProductionNumberError("The two ends of the range have different prefixes.")
    if high.value < low.value:
        raise ProductionNumberError("The range ends before it starts.")
    return low, high


def format_number(prefix: str, value: int, padding: int) -> str:
    return f"{prefix}{value:0{padding}d}"


def range_text(first: str, last: str) -> str:
    return first if first == last else f"{first}-{last}"


def _looks_like_date(digits: str) -> bool:
    if len(digits) != 8:
        return False
    try:
        return 1900 <= int(digits[:4]) <= 2100 and bool(date(int(digits[:4]), int(digits[4:6]), int(digits[6:8])))
    except ValueError:
        return False


def _plausible(low: str, high: str) -> bool:
    return (len(low) == len(high) and int(low) <= int(high) <= int(low) + _MAX_NAME_SPAN
            and not (_looks_like_date(low) or _looks_like_date(high)))


def suggestions_from_name(name: str | None) -> list[dict[str, Any]]:
    """The ranges a file name states, by rule. Each is a suggestion for a person, never a value.

    Three shapes occur in the productions held: ``001765-001895 Statements.pdf`` (a range at the start of the name),
    ``SWA000001-SWA000010`` (the same prefix on both ends, anywhere) and ``USA-261411.pdf`` (a capital prefix and a
    number as the whole name). Names that only resemble them are left alone: WhatsApp and camera names, index numbers
    (widths differ), date pairs, and ranges too wide to be pages.
    """
    name = (name or "").strip()
    if not name or name.startswith("._"):
        return []
    found: list[tuple[str, str, str]] = []  # key, first text, last text
    leading = _LEADING_RANGE.match(name)
    if leading and _plausible(leading.group(1), leading.group(2)):
        found.append(("", leading.group(1), leading.group(2)))
    for match in _PREFIXED_RANGE.finditer(name):
        if _plausible(match["low"], match["high"]) and match["head"].upper() not in _CAMERA_PREFIXES:
            found.append((prefix_key(match["head"]), match["first"], match["last"]))
    stem = name.rsplit(".", 1)[0]
    whole = _WHOLE_NAME_NUMBER.match(stem)
    if whole and whole.group(1) not in _CAMERA_PREFIXES and not _looks_like_date(whole.group(3)):
        found.append((prefix_key(whole.group(1)), stem, stem))
    out, seen = [], set()
    for key, low_text, high_text in found:
        low, high = parse_number(low_text), parse_number(high_text)
        if low is None or high is None or (key, low.value, high.value) in seen:
            continue
        seen.add((key, low.value, high.value))
        out.append(dict(prefix_key=key, first_number=low.value, last_number=high.value, first_text=low_text,
                        last_text=high_text, text=range_text(low_text, high_text), kind=KIND_SUGGESTED,
                        status="suggested", source="file_name", label=SUGGESTED_WORDS))
    return out


def page_of(first: int, last: int, page_count: int | None, value: int) -> int | None:
    """The page ``value`` stands for, only when the range has one number per page; else None (never a guess)."""
    if page_count is None or last - first + 1 != page_count or not first <= value <= last:
        return None
    return value - first + 1


# ---- the files ------------------------------------------------------------------------------------------------------

def _copy_root() -> Path:
    from config import EVIDENCE_DATA_ROOT
    return Path(os.environ.get("LOUPE_PRODUCTION_COPY_DIR") or Path(EVIDENCE_DATA_ROOT) / "production-copies")


def _resolve(file: EvidenceFile | None = None, stored_path: str | None = None) -> Path | None:
    from config import EVIDENCE_DATA_ROOT
    from services.evidence_file_check import resolve_stored_path
    return resolve_stored_path(file.stored_path if file is not None else stored_path, EVIDENCE_DATA_ROOT)


def count_pages(file: EvidenceFile | None = None, *, stored_path: str | None = None) -> int | None:
    """Pages counted from the file itself. None for anything with no pages to number (media, spreadsheets, an
    unreadable or missing file)."""
    from services.evidence_page_text import _pdf_pages
    return _pdf_pages(_resolve(file, stored_path))


def _visible_files(session, case_id, ids: Iterable[Any] | None = None):
    from services.financial.source_lineage import visible_evidence_condition
    query = select(EvidenceFile).where(EvidenceFile.case_id == case_id, EvidenceFile.deleted_at.is_(None),
                                       visible_evidence_condition())
    if ids is None:
        return session.scalars(query).all()
    wanted, out = list(ids), []
    for start in range(0, len(wanted), 1000):
        out.extend(session.scalars(query.where(EvidenceFile.id.in_(wanted[start:start + 1000]))).all())
    return out


def _user_name(user) -> str | None:
    return (getattr(user, "name", None) or getattr(user, "email", None)) if user is not None else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- numbered sets --------------------------------------------------------------------------------------------------

def set_view(row: ProductionSet) -> dict[str, Any]:
    return dict(id=str(row.id), case_id=str(row.case_id), name=row.name, prefix=row.prefix, start_number=row.start_number,
                padding=row.padding, next_number=row.next_number,
                next_text=format_number(row.prefix, row.next_number, row.padding),
                created_at=row.created_at.isoformat() if row.created_at else None)


def create_set(session, case_id, *, name: str, prefix: str, start: int = 1, padding: int = 6, user=None) -> ProductionSet:
    name, prefix = (name or "").strip(), (prefix or "").strip()
    if not name or len(name) > 120:
        raise ProductionNumberError("A set needs a name of up to 120 characters.")
    if not _PREFIX.match(prefix):
        raise ProductionNumberError("A prefix starts with a letter, has up to 32 characters and does not end in a digit.")
    if start < 0 or not 1 <= padding <= 12:
        raise ProductionNumberError("The start cannot be negative and padding is 1 to 12 digits.")
    key = prefix_key(prefix)
    if session.scalar(select(ProductionSet.id).where(ProductionSet.case_id == case_id, ProductionSet.prefix_key == key)):
        raise ProductionNumberError(f"This case already has a set with the prefix {prefix}: its numbers would repeat.", 409)
    row = ProductionSet(id=uuid.uuid4(), case_id=case_id, name=name, prefix=prefix, prefix_key=key, start_number=start,
                        padding=padding, next_number=start, created_by_user_id=getattr(user, "id", None))
    session.add(row)
    session.flush()
    return row


def list_sets(session, case_id) -> list[ProductionSet]:
    return session.scalars(select(ProductionSet).where(ProductionSet.case_id == case_id).order_by(
        ProductionSet.created_at, ProductionSet.id)).all()


def _locked_set(session, case_id, set_id) -> ProductionSet:
    row = session.scalar(select(ProductionSet).where(ProductionSet.id == set_id, ProductionSet.case_id == case_id)
                         .with_for_update())
    if row is None:
        raise ProductionNumberError("That numbered set is not in this case.", 404)
    return row


def assign(session, case_id, set_id, file_ids: list[Any], *, level: str = "page", user=None) -> dict[str, Any]:
    """Issue numbers to files, in the order given. A file already numbered in this set keeps its range and is reported;
    a file with no pages gets one number and the result says so. Nothing is left out without a reason."""
    if level not in ("page", "file"):
        raise ProductionNumberError("Numbers are issued per page or per file.")
    if len(file_ids) > MAX_FILES_PER_ASSIGN:
        raise ProductionNumberError(f"{len(file_ids)} files is more than one request can number "
                                    f"({MAX_FILES_PER_ASSIGN}). Number them in smaller groups.")
    wanted = list(dict.fromkeys(uuid.UUID(str(value)) for value in file_ids))
    number_set = _locked_set(session, case_id, set_id)  # held to the commit: two requests cannot issue the same number
    files = {row.id: row for row in _visible_files(session, case_id, wanted)}
    live = {row.evidence_file_id: row for row in session.scalars(select(ProductionAssignment).where(
        ProductionAssignment.set_id == number_set.id, ProductionAssignment.withdrawn_at.is_(None)))}
    issued, skipped = [], []
    for file_id in wanted:
        file = files.get(file_id)
        if file is None:
            skipped.append(dict(evidence_file_id=str(file_id), reason="This file is not in the case."))
            continue
        if file_id in live:
            held = live[file_id]
            skipped.append(dict(evidence_file_id=str(file_id), file_name=file.original_filename,
                                reason="Already numbered in this set: " + _assignment_text(held, number_set) + "."))
            continue
        pages = count_pages(file)
        by_page = level == "page" and bool(pages)
        count = pages if by_page else 1
        first = number_set.next_number
        number_set.next_number = first + count
        row = ProductionAssignment(
            id=uuid.uuid4(), case_id=case_id, set_id=number_set.id, evidence_file_id=file.id,
            file_name=file.original_filename, file_sha256=file.sha256, level="page" if by_page else "file",
            page_count=pages, first_number=first, last_number=first + count - 1,
            assigned_by_user_id=getattr(user, "id", None))
        session.add(row)
        issued.append(dict(_assignment_view(row, number_set), note=None if pages or level == "file" else NO_PAGES_WORDS))
    session.flush()
    return dict(issued=issued, skipped=skipped, next_text=format_number(number_set.prefix, number_set.next_number,
                                                                        number_set.padding))


def withdraw_assignment(session, case_id, assignment_id, *, reason: str, user=None) -> ProductionAssignment:
    """The range stops being shown as the file's number and stays recorded. Its numbers are spent."""
    row = session.get(ProductionAssignment, assignment_id)
    if row is None or row.case_id != case_id:
        raise ProductionNumberError("That number is not in this case.", 404)
    if row.withdrawn_at is not None:
        raise ProductionNumberError("That number is already withdrawn.", 409)
    if not (reason or "").strip():
        raise ProductionNumberError("Say why the number is withdrawn; the reason stays with the range.")
    row.withdrawn_at, row.withdrawn_by_user_id, row.withdrawn_reason = _now(), getattr(user, "id", None), reason.strip()
    session.flush()
    return row


def _assignment_text(row: ProductionAssignment, number_set: ProductionSet) -> str:
    return range_text(format_number(number_set.prefix, row.first_number, number_set.padding),
                      format_number(number_set.prefix, row.last_number, number_set.padding))


def _assignment_view(row: ProductionAssignment, number_set: ProductionSet) -> dict[str, Any]:
    return dict(id=str(row.id), kind=KIND_ASSIGNED, set_id=str(row.set_id), set_name=number_set.name,
                evidence_file_id=str(row.evidence_file_id) if row.evidence_file_id else None, file_name=row.file_name,
                file_sha256=row.file_sha256, level=row.level, page_count=row.page_count,
                first_number=row.first_number, last_number=row.last_number, prefix_key=number_set.prefix_key,
                text=_assignment_text(row, number_set), withdrawn=row.withdrawn_at is not None,
                withdrawn_reason=row.withdrawn_reason, note=NO_PAGES_WORDS if row.level == "file" and not row.page_count else None)


# ---- received numbers -----------------------------------------------------------------------------------------------

_SOURCE_WORDS = {"person": "entered by", "import": "imported by", "file_name": "read from the file name, confirmed by"}


def _received_label(row: ReceivedNumber) -> str:
    who = row.decided_by_name or "a person"
    if row.status == "rejected":
        return f"Suggestion rejected by {who}"
    return f"Received, {_SOURCE_WORDS.get(row.source, 'recorded by')} {who}"


def received_view(row: ReceivedNumber) -> dict[str, Any]:
    return dict(id=str(row.id), kind=KIND_RECEIVED, evidence_file_id=str(row.evidence_file_id), prefix_key=row.prefix_key,
                first_number=row.first_number, last_number=row.last_number, first_text=row.first_text,
                last_text=row.last_text, text=range_text(row.first_text, row.last_text), source=row.source,
                status=row.status, page_count=row.page_count, label=_received_label(row),
                withdrawn=row.withdrawn_at is not None, note=row.note)


def _case_file(session, case_id, file_id) -> EvidenceFile:
    found = _visible_files(session, case_id, [uuid.UUID(str(file_id))])
    if not found:
        raise ProductionNumberError("That file is not in this case.", 404)
    return found[0]


def _add_received(session, case_id, file: EvidenceFile, low: Number, high: Number, *, source: str, status: str, user,
                  page_count: int | None = None, note: str | None = None) -> ReceivedNumber:
    if session.scalar(select(ReceivedNumber.id).where(
            ReceivedNumber.evidence_file_id == file.id, ReceivedNumber.first_text == low.text,
            ReceivedNumber.last_text == high.text, ReceivedNumber.status != "withdrawn")):
        raise ProductionNumberError(f"{range_text(low.text, high.text)} is already recorded for this file.", 409)
    row = ReceivedNumber(id=uuid.uuid4(), case_id=case_id, evidence_file_id=file.id, prefix_key=low.key,
                         first_number=low.value, last_number=high.value, first_text=low.text, last_text=high.text,
                         source=source, status=status, page_count=page_count, decided_by_user_id=getattr(user, "id", None),
                         decided_by_name=_user_name(user), note=note)
    session.add(row)
    session.flush()
    return row


def enter_received(session, case_id, file_id, *, first: str, last: str | None = None, user=None) -> ReceivedNumber:
    """A person types the range the file arrived with. It never replaces anything on the file."""
    file = _case_file(session, case_id, file_id)
    low, high = parse_range(first, last)
    return _add_received(session, case_id, file, low, high, source="person", status="confirmed", user=user,
                         page_count=count_pages(file))


def _suggestion(file: EvidenceFile, first_text: str, last_text: str) -> dict[str, Any]:
    for item in suggestions_from_name(file.original_filename):
        if (item["first_text"], item["last_text"]) == (first_text, last_text):
            return item
    raise ProductionNumberError("The name of this file does not suggest that range.", 409)


def decide_suggestion(session, case_id, file_id, *, first_text: str, last_text: str, confirm: bool, user=None) -> ReceivedNumber:
    """A person's answer to a suggestion: confirmed it becomes a received number under their name; rejected it stops
    being suggested. Only this path turns a suggestion into a value."""
    file = _case_file(session, case_id, file_id)
    item = _suggestion(file, first_text, last_text)
    low, high = (Number(item["prefix_key"], item["first_number"], 0, first_text),
                 Number(item["prefix_key"], item["last_number"], 0, last_text))
    return _add_received(session, case_id, file, low, high, source="file_name",
                         status="confirmed" if confirm else "rejected", user=user,
                         page_count=count_pages(file) if confirm else None)


def withdraw_received(session, case_id, row_id, *, user=None, note: str | None = None) -> ReceivedNumber:
    """Take back a received number or a rejection. The row stays visible; a withdrawn rejection is suggested again."""
    row = session.get(ReceivedNumber, row_id)
    if row is None or row.case_id != case_id:
        raise ProductionNumberError("That number is not in this case.", 404)
    if row.status == "withdrawn":
        raise ProductionNumberError("That number is already withdrawn.", 409)
    row.status, row.withdrawn_at, row.withdrawn_by_user_id = "withdrawn", _now(), getattr(user, "id", None)
    row.note = (note or "").strip() or row.note
    session.flush()
    return row


def import_received(session, case_id, content: str, *, user=None) -> dict[str, Any]:
    """A person's list of file name, first number, last number (a heading row is optional). Every line either lands or
    comes back with its reason: a name no file has, or several files share, is never matched by guessing."""
    lines = list(csv.reader(io.StringIO(content or "")))
    lines = [(at, line) for at, line in enumerate(lines, start=1) if any(cell.strip() for cell in line)]
    if len(lines) > MAX_IMPORT_ROWS:
        raise ProductionNumberError(f"{len(lines)} rows is more than one import can hold ({MAX_IMPORT_ROWS}).")
    names: dict[str, list[EvidenceFile]] = {}
    for file in _visible_files(session, case_id):
        names.setdefault(file.original_filename, []).append(file)
    imported, problems = [], []
    if lines and "name" in lines[0][1][0].lower() and parse_number((lines[0][1] + [""])[1]) is None:
        lines = lines[1:]
    for at, line in lines:
        name = line[0].strip()
        matched = names.get(name, [])
        if len(line) < 2:
            problems.append(dict(line=at, file_name=name, reason="The line needs a file name and a number."))
        elif not matched:
            problems.append(dict(line=at, file_name=name, reason="No file in this case has that name."))
        elif len(matched) > 1:
            problems.append(dict(line=at, file_name=name, reason=f"{len(matched)} files in this case have that name; "
                                 "enter this number on the right file."))
        else:
            try:
                low, high = parse_range(line[1], line[2] if len(line) > 2 else None)
                row = _add_received(session, case_id, matched[0], low, high, source="import", status="confirmed",
                                    user=user, page_count=count_pages(matched[0]))
                imported.append(received_view(row))
            except ProductionNumberError as exc:
                problems.append(dict(line=at, file_name=name, reason=str(exc)))
    return dict(imported=imported, problems=problems)


# ---- what the case holds --------------------------------------------------------------------------------------------

def _stored_rows(session, case_id, file_ids: list[uuid.UUID] | None):
    assignments = select(ProductionAssignment, ProductionSet).join(
        ProductionSet, ProductionSet.id == ProductionAssignment.set_id).where(ProductionAssignment.case_id == case_id)
    received = select(ReceivedNumber).where(ReceivedNumber.case_id == case_id)
    if file_ids is None:
        return [(a, s) for a, s in session.execute(assignments).all()], session.scalars(received).all()
    pairs, rows = [], []
    for start in range(0, len(file_ids), 1000):
        part = file_ids[start:start + 1000]
        pairs.extend((a, s) for a, s in session.execute(assignments.where(ProductionAssignment.evidence_file_id.in_(part))).all())
        rows.extend(session.scalars(received.where(ReceivedNumber.evidence_file_id.in_(part))).all())
    return pairs, rows


def _file_names(session, case_id) -> dict[uuid.UUID, str]:
    from services.financial.source_lineage import visible_evidence_condition
    return dict(session.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(
        EvidenceFile.case_id == case_id, EvidenceFile.deleted_at.is_(None), visible_evidence_condition())).all())


def case_numbers(session, case_id) -> dict[str, Any]:
    """Every number of the case by file, with its conflicts, in three queries however many files. The Evidence list
    reads this once and joins it to its rows, so no row costs a lookup."""
    pairs, received = _stored_rows(session, case_id, None)
    names = _file_names(session, case_id)
    files: dict[str, dict[str, Any]] = {}

    def entry(file_id) -> dict[str, Any]:
        return files.setdefault(str(file_id), dict(evidence_file_id=str(file_id), assigned=[], received=[], suggested=[],
                                                   conflicts=[]))
    for row, number_set in pairs:
        if row.evidence_file_id is not None:
            entry(row.evidence_file_id)["assigned"].append(_assignment_view(row, number_set))
    answered: set[tuple[str, str, str]] = set()
    for row in received:
        if str(row.evidence_file_id) and row.evidence_file_id in names:
            entry(row.evidence_file_id)["received"].append(received_view(row))
            if row.status != "withdrawn":
                answered.add((str(row.evidence_file_id), row.first_text, row.last_text))
    for file_id, name in names.items():
        for item in suggestions_from_name(name):
            if (str(file_id), item["first_text"], item["last_text"]) not in answered:
                entry(file_id)["suggested"].append(item)
    _add_conflicts(files, {str(key): value for key, value in names.items()})
    return dict(files=files, totals=dict(
        files=len(files), assigned=sum(1 for f in files.values() if any(not a["withdrawn"] for a in f["assigned"])),
        received=sum(1 for f in files.values() if any(r["status"] == "confirmed" for r in f["received"])),
        suggested=sum(1 for f in files.values() if f["suggested"]),
        conflicts=sum(1 for f in files.values() if f["conflicts"])))


def _standing(file: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield from (a for a in file["assigned"] if not a["withdrawn"])
    yield from (r for r in file["received"] if r["status"] == "confirmed")
    yield from file["suggested"]


def _add_conflicts(files: dict[str, dict[str, Any]], names: dict[str, str]) -> None:
    """Fill each file's conflicts. Nothing is changed: a conflict is a thing to show."""
    spans: dict[str, list[tuple[int, int, str, dict[str, Any]]]] = {}
    for file_id, file in files.items():
        standing = list(_standing(file))
        for item in standing:
            spans.setdefault(item["prefix_key"], []).append((item["first_number"], item["last_number"], file_id, item))
            size = item["last_number"] - item["first_number"] + 1
            if item["kind"] == KIND_RECEIVED and item.get("page_count") and size != item["page_count"]:
                file["conflicts"].append(dict(kind="pages_differ", words=(
                    f"{item['text']} covers {size} numbers; the file has {item['page_count']} pages.")))
        kept = [item for item in standing if item["kind"] != KIND_ASSIGNED]
        for at, one in enumerate(kept):
            for other in kept[at + 1:]:
                if one["prefix_key"] == other["prefix_key"] and (one["first_number"], one["last_number"]) != (
                        other["first_number"], other["last_number"]):
                    file["conflicts"].append(dict(kind="same_file_differs", words=(
                        f"This file has two different numbers: {one['text']} ({one['kind']}) and "
                        f"{other['text']} ({other['kind']}). Both are kept.")))
    for rows in spans.values():
        rows.sort(key=lambda row: (row[0], row[1]))
        open_rows: list[tuple[int, int, str, dict[str, Any]]] = []
        for row in rows:
            open_rows = [held for held in open_rows if held[1] >= row[0]]
            for held in open_rows:
                if held[2] == row[2]:
                    continue
                for mine, theirs in ((row, held), (held, row)):
                    conflicts = files[mine[2]]["conflicts"]
                    if sum(1 for c in conflicts if c["kind"] == "same_number") < MAX_CONFLICTS_SHOWN:
                        conflicts.append(dict(kind="same_number", other_evidence_file_id=theirs[2], words=(
                            f"{mine[3]['text']} ({mine[3]['kind']}) overlaps {theirs[3]['text']} "
                            f"({theirs[3]['kind']}) on {names.get(theirs[2], 'another file')}.")))
            open_rows.append(row)


def file_numbers(session, case_id, file_id) -> dict[str, Any]:
    """One file's numbers for its panel, with a suggestion's size checked against the pages counted now."""
    file = _case_file(session, case_id, file_id)
    numbers = case_numbers(session, case_id)["files"].get(str(file.id)) or dict(
        evidence_file_id=str(file.id), assigned=[], received=[], suggested=[], conflicts=[])
    pages = count_pages(file) if numbers["suggested"] else None
    for item in numbers["suggested"]:
        size = item["last_number"] - item["first_number"] + 1
        item["page_count"] = pages
        if pages and size != pages:
            numbers["conflicts"].append(dict(kind="pages_differ", words=(
                f"{item['text']} covers {size} numbers; the file has {pages} pages.")))
    return dict(numbers, file_name=file.original_filename, sha256=file.sha256)


def _reference(item: dict[str, Any], page: int | None, number_set: ProductionSet | None = None) -> dict[str, Any]:
    whole = item["text"]
    number = whole
    pages = item.get("page_count")
    if page and item["first_number"] != item["last_number"]:
        value = item["first_number"] + page - 1
        if page_of(item["first_number"], item["last_number"], pages, value):
            if number_set is not None:
                number = format_number(number_set.prefix, value, number_set.padding)
            else:
                width = len(re.search(r"(\d+)\s*$", item["first_text"]).group(1))
                head = re.sub(r"\d+\s*$", "", item["first_text"])
                number = f"{head}{value:0{width}d}"
    label = ("Assigned" if item["kind"] == KIND_ASSIGNED else
             "Received" if item["kind"] == KIND_RECEIVED else SUGGESTED_WORDS)
    return dict(number=number, kind=item["kind"], label=label, level="page" if number != whole else "file")


def references_for(session, case_id, items: Iterable[tuple[Any, int | None]], *,
                   names: dict[str, str] | None = None) -> dict[tuple[str, int | None], list[dict[str, Any]]]:
    """The numbers to print beside each (file, page) citation, in a bounded number of queries. Assigned first, then
    received, then suggested, each with its label: an export never prints a suggestion as if it were a value."""
    wanted = list(dict.fromkeys((str(file_id), page) for file_id, page in items if file_id))
    ids = sorted({uuid.UUID(file_id) for file_id, _ in wanted})
    if not ids:
        return {}
    pairs, received = _stored_rows(session, case_id, ids)
    if names is None:
        names = {}
    missing = [value for value in ids if str(value) not in names]
    for start in range(0, len(missing), 1000):
        names.update({str(key): value for key, value in session.execute(select(
            EvidenceFile.id, EvidenceFile.original_filename).where(
                EvidenceFile.case_id == case_id, EvidenceFile.id.in_(missing[start:start + 1000]))).all()})
    assigned_by: dict[str, list[tuple[dict[str, Any], ProductionSet]]] = {}
    for row, number_set in pairs:
        if row.withdrawn_at is None:
            assigned_by.setdefault(str(row.evidence_file_id), []).append((_assignment_view(row, number_set), number_set))
    received_by: dict[str, list[dict[str, Any]]] = {}
    answered: set[tuple[str, str, str]] = set()
    for row in received:
        if row.status != "withdrawn":
            answered.add((str(row.evidence_file_id), row.first_text, row.last_text))
        if row.status == "confirmed":
            received_by.setdefault(str(row.evidence_file_id), []).append(received_view(row))
    out: dict[tuple[str, int | None], list[dict[str, Any]]] = {}
    for file_id, page in wanted:
        refs = [_reference(view, page, number_set) for view, number_set in assigned_by.get(file_id, [])]
        refs += [_reference(view, page) for view in received_by.get(file_id, [])]
        refs += [_reference(item, None) for item in suggestions_from_name(names.get(file_id))
                 if (file_id, item["first_text"], item["last_text"]) not in answered]
        if refs:
            out[(file_id, page)] = refs
    return out


def reference_words(refs: Iterable[dict[str, Any]] | None) -> str:
    """One citation's numbers in one line, each saying what it is: ``OWL000012 (assigned); 001765 (received)``."""
    words = {KIND_ASSIGNED: "assigned", KIND_RECEIVED: "received", KIND_SUGGESTED: "suggested from the file name, not confirmed"}
    return "; ".join(f"{ref['number']} ({words[ref['kind']]})" for ref in refs or [])


# ---- finding a number -----------------------------------------------------------------------------------------------

def find_number(session, case_id, query: str | None) -> dict[str, Any]:
    """Every file a number or range belongs to, with the page when the range has one number per page. A number with
    no prefix matches every prefix. Withdrawn numbers are found and say so; ``total`` is all of them, ``hits`` the
    first MAX_SEARCH_HITS."""
    try:
        low, high = parse_range(query)
    except ProductionNumberError:
        return dict(hits=[], total=0, parsed=False)
    if not (query or "").strip() or (not low.key and low.width < 4):
        return dict(hits=[], total=0, parsed=False)  # "12" is an ordinary search, not a number

    def covers(key: str, first: int, last: int) -> bool:
        return (not low.key or key == low.key) and first <= high.value and last >= low.value

    hits: list[dict[str, Any]] = []
    paths = dict(session.execute(select(EvidenceFile.id, EvidenceFile.stored_path).where(
        EvidenceFile.case_id == case_id, EvidenceFile.deleted_at.is_(None))).all())
    names = _file_names(session, case_id)
    pairs, received = _stored_rows(session, case_id, None)

    def hit(file_id, name, item, *, words: str, pages: int | None) -> None:
        page = page_of(item["first_number"], item["last_number"], pages, low.value)
        known = file_id is not None and file_id in names
        note = None if page or low.value != high.value or not pages else PAGE_NOT_CERTAIN
        hits.append(dict(evidence_file_id=str(file_id) if known else None, file_name=name, number=item["text"],
                         kind=item["kind"], label=words, page=page, note=note if known else
                         "The file with this number has been removed from the case."))

    for row, number_set in pairs:
        view = _assignment_view(row, number_set)
        if covers(view["prefix_key"], view["first_number"], view["last_number"]):
            words = f"Withdrawn: {view['withdrawn_reason']}" if view["withdrawn"] else f"Assigned in {number_set.name}"
            hit(row.evidence_file_id, row.file_name, view, words=words, pages=None if view["withdrawn"] else view["page_count"])
    answered: set[tuple[str, str, str]] = set()
    for row in received:
        if row.status != "withdrawn":
            answered.add((str(row.evidence_file_id), row.first_text, row.last_text))
        if row.status == "confirmed" and row.evidence_file_id in names and covers(row.prefix_key, row.first_number, row.last_number):
            view = received_view(row)
            hit(row.evidence_file_id, names[row.evidence_file_id], view, words=view["label"], pages=row.page_count)
    checked = 0
    for file_id, name in names.items():
        for item in suggestions_from_name(name):
            if (str(file_id), item["first_text"], item["last_text"]) in answered or not covers(
                    item["prefix_key"], item["first_number"], item["last_number"]):
                continue
            checked += 1
            pages = count_pages(stored_path=paths.get(file_id)) if checked <= PAGE_CHECK_HITS else None
            hit(file_id, name, item, words=SUGGESTED_WORDS, pages=pages)
    return dict(hits=hits[:MAX_SEARCH_HITS], total=len(hits), parsed=True)


def file_ids_for_query(session, case_id, query: str | None) -> list[uuid.UUID]:
    """The files a text box's words name by number, for the Evidence search."""
    found = find_number(session, case_id, query)
    return [uuid.UUID(hit["evidence_file_id"]) for hit in found["hits"] if hit["evidence_file_id"]]


# ---- stamped copies -------------------------------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stamped_view(row: ProductionStampedCopy) -> dict[str, Any]:
    return dict(id=str(row.id), assignment_id=str(row.assignment_id), file_name=row.file_name, sha256=row.sha256,
                size=row.size, source_sha256=row.source_sha256, derived=True,
                created_at=row.created_at.isoformat() if row.created_at else None)


def stamp_copy(session, case_id, assignment_id, *, user=None) -> ProductionStampedCopy:
    """A new PDF with the numbers printed on it. The original is only read: its hash is measured before and after and
    must equal the recorded one, or nothing is kept. The copy is a derived file with its own hash."""
    import fitz

    row = session.get(ProductionAssignment, assignment_id)
    if row is None or row.case_id != case_id:
        raise ProductionNumberError("That number is not in this case.", 404)
    if row.withdrawn_at is not None:
        raise ProductionNumberError("A withdrawn number is not stamped.", 409)
    file = session.get(EvidenceFile, row.evidence_file_id) if row.evidence_file_id else None
    source = _resolve(file) if file is not None else None
    if file is None or source is None or not source.is_file():
        raise ProductionNumberError("The original of this file is not available.", 409)
    if source.suffix.lower() != ".pdf":
        raise ProductionNumberError("Only a PDF can carry stamped numbers; this file keeps its number beside it.")
    number_set = session.get(ProductionSet, row.set_id)
    before = _sha256(source)
    if before != file.sha256:
        raise ProductionNumberError("The original no longer matches its recorded hash, so it was not stamped.", 409)
    copy_id = uuid.uuid4()
    target = _copy_root() / str(case_id) / f"{copy_id}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_suffix(".part")
    try:
        with fitz.open(source) as document:
            if document.needs_pass:
                raise ProductionNumberError("This PDF is password protected, so it cannot be stamped.")
            if row.level == "page" and document.page_count != row.page_count:
                raise ProductionNumberError("This file's pages no longer match its numbers.", 409)
            for index, page in enumerate(document):
                if row.level == "file" and index:
                    break
                _stamp_page(page, format_number(number_set.prefix, row.first_number + index, number_set.padding))
            document.save(scratch, garbage=1, deflate=True)
        if _sha256(source) != before:
            raise ProductionNumberError("The original changed while it was read, so the copy was not kept.", 409)
        digest, size = _sha256(scratch), scratch.stat().st_size
        os.replace(scratch, target)
    finally:
        scratch.unlink(missing_ok=True)
    stem = Path(row.file_name).stem
    copy = ProductionStampedCopy(id=copy_id, case_id=case_id, assignment_id=row.id, storage_path=str(target),
                                 file_name=f"{_assignment_text(row, number_set)} {stem} (stamped copy).pdf"[:512],
                                 sha256=digest, size=size, source_sha256=before,
                                 created_by_user_id=getattr(user, "id", None))
    session.add(copy)
    session.flush()
    return copy


def _stamp_page(page, number: str) -> None:
    """The number in the bottom margin, right aligned, whichever way the page is turned. Text only, no box: a filled
    box could cover what is on the page."""
    import fitz
    box = fitz.Rect(page.rect.x0 + 18, page.rect.y1 - 22, page.rect.x1 - 18, page.rect.y1 - 6)
    page.insert_textbox(box * page.derotation_matrix, number, fontsize=9, fontname="helv", color=(0, 0, 0),
                        align=fitz.TEXT_ALIGN_RIGHT, rotate=page.rotation)


def stamped_copies(session, case_id, assignment_id=None) -> list[ProductionStampedCopy]:
    query = select(ProductionStampedCopy).where(ProductionStampedCopy.case_id == case_id)
    if assignment_id is not None:
        query = query.where(ProductionStampedCopy.assignment_id == assignment_id)
    return session.scalars(query.order_by(ProductionStampedCopy.created_at)).all()


def stamped_path(session, case_id, copy_id) -> tuple[ProductionStampedCopy, Path]:
    row = session.get(ProductionStampedCopy, copy_id)
    if row is None or row.case_id != case_id:
        raise ProductionNumberError("That copy is not in this case.", 404)
    path = Path(row.storage_path)
    if not path.is_file():
        raise ProductionNumberError("That stamped copy is no longer stored; make it again.", 410)
    return row, path
