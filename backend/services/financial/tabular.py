"""Bank and payment-app statements exported as spreadsheets: CSV, XLSX and XLS.

A spreadsheet export is a table with no format of its own: which column is the
date, which the money and which way the money went is a property of the bank
that wrote it.  So this reader does three things the byte-format readers in
:mod:`services.financial.native` never need to:

* it finds the heading row under whatever banner lines the bank put above it;
* it GUESSES a column mapping from the headings (``guess_layout``) and says it
  guessed; a person confirms the mapping when they store the file, and the
  confirmed mapping is reused for the next file with the same headings
  (``layout_key``) in the case;
* every row it reads carries the file, the sheet and the line it came from.

Nothing the reader is unsure of is dropped.  A totals line, a pending payment,
a line with an amount but no readable date, a line whose debit and credit are
both filled: each is listed as a skipped row with its line and the reason, and
counts in ``parsed_row_count`` beside the rows that would be stored.

The money is proved where the file allows it.  A balance column is checked row
by row (newest-first and oldest-first both tried); a file whose balances do not
follow from its amounts is ``unbalanced`` and needs a person's decision before
its rows count in totals.  A file with no balance column has no arithmetic to
run and says so (``unavailable``).

Payment-app exports (Cash App, Venmo, PayPal, a bank's Zelle history) are the
same reader: their headings are in the vocabulary below, not in separate code.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional, Sequence

from postgres.models.enums import (
    DateSource,
    ExtractionLayer,
    LocatorKind,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.locators import Locator
from services.financial.proof_class import SourceShape, assign_proof_class

#: File endings read as spreadsheets, and the loader each one uses.
TABULAR_KINDS: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "csv",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xls": "xls",
}
#: Rows looked at to find the heading row.  Bank banners run to a dozen lines.
HEADER_SCAN_ROWS = 40
#: A spreadsheet larger than this is refused with its size, never read in part.
MAX_TABULAR_ROWS = 200_000
#: An Excel workbook is expanded in memory; above this the file is refused.
MAX_WORKBOOK_BYTES = 25 * 1024 * 1024

LOCATOR = Locator(kind=LocatorKind.not_positional)

ROLES = ("date", "posted_date", "description", "memo", "amount", "debit", "credit", "balance", "type",
         "status", "counterparty", "from_party", "to_party", "reference", "currency", "account")

# Heading wording per role, folded (lower case, accents and punctuation removed).  Earlier entries win when
# two columns claim one role.  Spanish wording is here because the cases hold Mexican bank exports.
VOCABULARY: dict[str, tuple[str, ...]] = {
    "date": ("transaction date", "trans date", "txn date", "date", "datetime", "date time", "fecha",
             "fecha de operacion", "fecha operacion", "booking date", "date posted", "posting date",
             "post date", "posted date", "value date", "effective date", "processed date", "process date",
             "settlement date", "settled date"),
    "posted_date": ("posting date", "post date", "posted date", "date posted", "booking date",
                    "fecha de aplicacion", "value date"),
    "description": ("description", "transaction description", "details", "transaction details", "narrative",
                    "particulars", "descripcion", "concepto", "payee", "merchant", "name"),
    "memo": ("memo", "note", "notes", "reference description", "additional info", "extended description"),
    "amount": ("amount", "transaction amount", "amount total", "amount usd", "net amount", "net", "gross",
               "importe", "monto", "value", "amt"),
    "debit": ("debit", "debits", "debit amount", "amount debit", "withdrawal", "withdrawals", "withdrawal amount",
              "money out", "paid out", "outflow", "cargo", "cargos", "retiro", "retiros"),
    "credit": ("credit", "credits", "credit amount", "amount credit", "deposit", "deposits", "deposit amount",
               "money in", "paid in", "inflow", "abono", "abonos", "deposito", "depositos"),
    "balance": ("balance", "running balance", "ledger balance", "balance after", "account balance", "saldo"),
    "type": ("transaction type", "type", "tran type", "tran code", "transaction code", "trans code", "debit credit", "dr cr", "cr dr", "credit debit",
             "indicator", "tipo"),
    "status": ("status", "transaction status", "estado"),
    "counterparty": ("name of sender receiver", "counterparty", "name", "payee", "merchant"),
    # Payment apps print both parties; the other party is the receiver when money goes out, else the sender.
    "from_party": ("from", "sender", "payer", "from name"),
    "to_party": ("to", "receiver", "recipient", "beneficiary", "to name"),
    "reference": ("check number", "check no", "check", "cheque number", "cheque no", "reference", "ref",
                  "trace number",
                  "reference number", "transaction id", "id", "confirmation", "confirmation number",
                  "serial", "folio", "referencia"),
    "currency": ("currency", "ccy", "curr", "moneda"),
    # Plain "Account" is left out: Cash App prints the funding card under it, not this account.
    "account": ("account number", "account no", "acct number", "numero de cuenta", "cuenta",
                "bank account last4", "account last4", "account last 4"),
}

# Lines in the table that are not payments.  Matched on the folded description (or the whole line).
_TOTALS = re.compile(r"^(total|totals|subtotal|sub total|grand total|totales|total de)\b")
_BALANCE_LINE = re.compile(
    r"^(opening|closing|beginning|ending|starting|previous|new|available|current|ledger)? ?balance"
    r"( brought| carried)?( forward| b f| c f)?\b|^balance (forward|brought forward|carried forward)\b"
    r"|^saldo (inicial|final|anterior)\b")
_OPENING = re.compile(r"^(opening|beginning|starting|previous) balance|^balance (forward|brought forward)"
                      r"|^saldo (inicial|anterior)")
_CLOSING = re.compile(r"^(closing|ending|new) balance|^balance carried forward|^saldo final")
# Status words.  A status naming neither kind is listed as unsure, never stored on a guess.
_DONE_STATUS_WORDS = {"complete", "completed", "posted", "cleared", "settled", "success", "successful", "paid",
                      "processed", "booked", "charged", "deposited", "sent", "received", "transferred",
                      "refunded", "aplicado", "liquidado", "approved"}
_NOT_MOVED_STATUS_WORDS = {"pending", "failed", "declined", "canceled", "cancelled", "denied", "rejected",
                           "expired", "waiting", "scheduled", "issued", "requested", "incomplete", "unclaimed",
                           "held", "rechazado", "cancelado", "pendiente"}
_OUT_TYPES = {"debit", "dr", "d", "withdrawal", "debito", "cargo", "sent", "payment sent", "out"}
_IN_TYPES = {"credit", "cr", "c", "deposit", "credito", "abono", "received", "payment received", "in"}
_ACCOUNT_IN_BANNER = re.compile(
    r"(?:account|acct|a/c|cuenta)\s*(?:number|no\.?|num|#)?\s*[:#]?\s*([0-9][0-9 \-]{3,}[0-9]|[x*•]+[0-9]{3,})",
    re.IGNORECASE)
_CURRENCY_SIGNS = {"$": None, "US$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY", "MX$": "MXN"}
_CURRENCY_CODE = re.compile(r"\b(USD|MXN|EUR|GBP|CAD|JPY|CHF|AUD)\b", re.IGNORECASE)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_MONTHS.update({"sept": 9, "ene": 1, "abr": 4, "ago": 8, "dic": 12})


class TabularError(Exception):
    """The spreadsheet could not be read as a statement; the message says why."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@dataclass
class Sheet:
    """One table: a CSV file, or one worksheet.  ``rows`` are (line number, cells), blanks kept."""

    name: Optional[str]
    rows: list[tuple[int, list[Any]]]


def tabular_kind(file_name: Optional[str]) -> Optional[str]:
    """``csv``, ``xlsx`` or ``xls`` from the file's ending, else ``None``."""
    if not file_name:
        return None
    lowered = file_name.lower()
    for ending, kind in TABULAR_KINDS.items():
        if lowered.endswith(ending):
            return kind
    return None


def _decode(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for encoding in ("utf-8", "cp1252"):  # Windows exports are cp1252
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")  # every byte has a latin-1 reading, so nothing is replaced


def _csv_sheet(data: bytes, file_name: Optional[str]) -> Sheet:
    text = _decode(data)
    sample = text[:16384]
    delimiter = "\t" if (file_name or "").lower().endswith(".tsv") else None
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows: list[tuple[int, list[Any]]] = []
    line = 1
    for record in reader:
        rows.append((line, list(record)))
        line = reader.line_num + 1
        if len(rows) > MAX_TABULAR_ROWS:
            raise TabularError(f"the file has more than {MAX_TABULAR_ROWS:,} lines; it was not read")
    return Sheet(name=None, rows=rows)


def _xlsx_sheets(data: bytes) -> list[Sheet]:
    import openpyxl

    if len(data) > MAX_WORKBOOK_BYTES:
        raise TabularError(f"the workbook is {len(data):,} bytes, above the {MAX_WORKBOOK_BYTES:,}-byte limit;"
                           " it was not read")
    book = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    sheets = []
    for ws in book.worksheets:
        if ws.max_row > MAX_TABULAR_ROWS:
            raise TabularError(f"sheet {ws.title!r} has {ws.max_row:,} rows, above {MAX_TABULAR_ROWS:,}; "
                               "the workbook was not read")
        grid = [list(row) for row in ws.iter_rows(values_only=True)]
        # A merged cell holds its value in the top-left cell only; every cell it covers shows that value.
        for merged in ws.merged_cells.ranges:
            value = ws.cell(merged.min_row, merged.min_col).value
            for r in range(merged.min_row, min(merged.max_row, len(grid)) + 1):
                cells = grid[r - 1]
                while len(cells) < merged.max_col:
                    cells.append(None)
                for c in range(merged.min_col, merged.max_col + 1):
                    cells[c - 1] = value
        sheets.append(Sheet(name=ws.title, rows=[(i + 1, cells) for i, cells in enumerate(grid)]))
    return sheets


def _xls_sheets(data: bytes) -> list[Sheet]:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=data, formatting_info=True)
    except (NotImplementedError, xlrd.XLRDError):
        book = xlrd.open_workbook(file_contents=data)
    sheets = []
    for ws in book.sheets():
        if ws.nrows > MAX_TABULAR_ROWS:
            raise TabularError(f"sheet {ws.name!r} has {ws.nrows:,} rows, above {MAX_TABULAR_ROWS:,}; "
                               "the workbook was not read")
        grid = []
        for r in range(ws.nrows):
            cells = []
            for c in range(ws.ncols):
                cell = ws.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        cells.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
                    except (ValueError, OverflowError):
                        cells.append(cell.value)
                elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    cells.append(None)
                else:
                    cells.append(cell.value)
            grid.append(cells)
        for r0, r1, c0, c1 in getattr(ws, "merged_cells", ()) or ():
            value = grid[r0][c0] if r0 < len(grid) and c0 < len(grid[r0]) else None
            for r in range(r0, min(r1, len(grid))):
                for c in range(c0, min(c1, len(grid[r]))):
                    grid[r][c] = value
        sheets.append(Sheet(name=ws.name, rows=[(i + 1, cells) for i, cells in enumerate(grid)]))
    return sheets


def load_sheets(data: bytes, kind: str, file_name: Optional[str] = None) -> list[Sheet]:
    """Every table in the file, blanks kept so line numbers are the file's own."""
    if kind == "csv":
        return [_csv_sheet(data, file_name)]
    if kind == "xlsx":
        return _xlsx_sheets(data)
    if kind == "xls":
        return _xls_sheets(data)
    raise TabularError(f"{kind!r} is not a spreadsheet kind this reader knows")


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------


def fold(value: Any) -> str:
    """Heading or label text compared without case, accents or punctuation."""
    if value is None:
        return ""
    # "ProcessedDate" and "Processed Date" are one heading.
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", unicodedata.normalize("NFKD", str(value)))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _blank(cells: Sequence[Any]) -> bool:
    return all(_text(cell) == "" for cell in cells)


def parse_amount(value: Any) -> tuple[Optional[Decimal], Optional[str]]:
    """A cell's money as a signed Decimal, or (None, why) when it cannot be read; (None, None) when empty."""
    if value is None or isinstance(value, bool):
        return None, None
    if isinstance(value, (int, float)):
        number = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
        return _cents(number, value)
    text = str(value).strip().strip('"').strip().replace("−", "-").replace("\xa0", " ")
    if text in ("", "-", "--", "—", "–", "n/a", "N/A"):
        return None, None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    upper = text.upper()
    if upper.endswith(("CR", "DR")) and not upper.endswith(("USDCR",)):
        negative = negative or upper.endswith("DR")
        text = text[:-2].strip()
    text = _CURRENCY_CODE.sub("", text)
    for sign in sorted(_CURRENCY_SIGNS, key=len, reverse=True):
        text = text.replace(sign, "")
    text = text.replace(" ", "")
    while text[:1] in "+-" and text:
        negative = negative ^ (text[0] == "-")
        text = text[1:]
    if text.endswith("-"):
        negative, text = not negative, text[:-1]
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", text):
            text = text.replace(",", "")
        elif re.fullmatch(r"\d+,\d{1,2}", text):
            text = text.replace(",", ".")
        else:
            return None, f"amount {value!r} cannot be read as money"
    if not re.fullmatch(r"\d+(\.\d+)?|\.\d+", text):
        return None, f"amount {value!r} cannot be read as money"
    number = Decimal(text)
    return _cents(-number if negative else number, value)


def _cents(number: Decimal, original: Any) -> tuple[Optional[Decimal], Optional[str]]:
    try:
        rounded = number.quantize(Decimal("0.01"))
    except InvalidOperation:
        return None, f"amount {original!r} cannot be read as money"
    if rounded != number and abs(rounded - number) > Decimal("0.000001"):
        return None, f"amount {original!r} has more than two decimal places"
    return rounded, None


_NUMERIC_DATE = re.compile(r"^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})$")
_WORD_DATE_DMY = re.compile(r"^(\d{1,2})[ \-/.]([a-z]{3,9})\.?[ \-/.,]*(\d{2,4})$")
_WORD_DATE_MDY = re.compile(r"^([a-z]{3,9})\.? (\d{1,2}),? (\d{2,4})$")
_TIME_TAIL = re.compile(r"[T ]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?\s*(am|pm)?\s*([+-]\d{2}:?\d{2}|z|[a-z]{2,4})?$",
                        re.IGNORECASE)


def date_shape(value: Any) -> Optional[tuple[int, int, int]]:
    """For a d/m/y-or-m/d/y text date, its three numbers (else ``None``); used to settle the file's order."""
    if isinstance(value, (date, datetime)) or value is None:
        return None
    text = _TIME_TAIL.sub("", str(value).strip())
    match = _NUMERIC_DATE.match(text)
    if not match or len(match.group(1)) == 4:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def parse_date(value: Any, order: Optional[str], window: Any) -> tuple[Optional[date], Optional[str]]:
    """A cell's calendar date under the file's date order, or (None, why).

    ``order`` is ``month_first`` or ``day_first`` for numeric dates whose first two parts are both 12 or less.
    """
    if value is None or _text(value) == "":
        return None, "no date"
    if isinstance(value, datetime):
        return value.date(), None
    if isinstance(value, date):
        return value, None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 20000 <= value <= 80000:  # an Excel day number the workbook did not format as a date
            return date(1899, 12, 30) + timedelta(days=int(value)), None
        return None, f"date {value!r} cannot be read"
    text = _TIME_TAIL.sub("", str(value).strip()).strip().rstrip(",")
    lowered = text.lower()
    try:
        if re.fullmatch(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", text):
            y, m, d = (int(p) for p in re.split(r"[-/.]", text))
            return date(y, m, d), None
        if re.fullmatch(r"\d{8}", text) and text[:2] in ("19", "20"):
            return date(int(text[:4]), int(text[4:6]), int(text[6:])), None
        match = _NUMERIC_DATE.match(text)
        if match:
            a, b, y = int(match.group(1)), int(match.group(2)), match.group(3)
            if a > 12 and b <= 12:
                d, m = a, b
            elif b > 12 and a <= 12:
                m, d = a, b
            elif order == "day_first":
                d, m = a, b
            elif order == "month_first":
                m, d = a, b
            else:
                return None, f"date {value!r} could be day-first or month-first"
            return date(_year(y, m, d, window, value), m, d), None
        match = _WORD_DATE_DMY.match(lowered)
        if match and match.group(2)[:4].rstrip(".") in _MONTHS or (match and match.group(2)[:3] in _MONTHS):
            month = _MONTHS.get(match.group(2)[:4], _MONTHS.get(match.group(2)[:3]))
            d = int(match.group(1))
            return date(_year(match.group(3), month, d, window, value), month, d), None
        match = _WORD_DATE_MDY.match(lowered)
        if match and (match.group(1)[:4] in _MONTHS or match.group(1)[:3] in _MONTHS):
            month = _MONTHS.get(match.group(1)[:4], _MONTHS.get(match.group(1)[:3]))
            d = int(match.group(2))
            return date(_year(match.group(3), month, d, window, value), month, d), None
    except (ValueError, TabularError) as exc:
        return None, f"date {value!r} cannot be read ({exc})" if isinstance(exc, TabularError) else \
            f"date {value!r} is not a calendar date"
    return None, f"date {value!r} cannot be read"


def _year(text: str, month: int, day: int, window: Any, original: Any) -> int:
    if len(text) == 4:
        return int(text)
    if len(text) == 2 and window is not None:
        try:
            return window.resolve(int(text), month, day, context=f"spreadsheet date {original!r}").year
        except Exception as exc:  # noqa: BLE001 - the window's refusal is the reason shown
            raise TabularError(str(exc)) from exc
    raise TabularError(f"year {text!r} has no century")


# ---------------------------------------------------------------------------
# Layout: which column is which
# ---------------------------------------------------------------------------


def _role_of(heading: str) -> list[str]:
    folded = fold(heading)
    if not folded:
        return []
    roles = []
    for role, words in VOCABULARY.items():
        if folded in words:
            roles.append(role)
    return roles


def layout_key(headings: Sequence[Any]) -> str:
    """The same headings in the same order are the same layout, whatever the file name or banner."""
    folded = "|".join(fold(h) for h in headings).rstrip("|")
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()[:24]


def _header_row(sheet: Sheet) -> Optional[int]:
    """Index (into sheet.rows) of the first row whose headings name a date and money."""
    for index, (_, cells) in enumerate(sheet.rows[:HEADER_SCAN_ROWS]):
        roles = {role for cell in cells for role in _role_of(cell)}
        if ("date" in roles or "posted_date" in roles) and roles & {"amount", "debit", "credit"}:
            return index
    return None


def guess_layout(sheet: Sheet) -> Optional[dict]:
    """The column mapping this reader proposes for one table, or ``None`` when no heading row is found."""
    index = _header_row(sheet)
    if index is None:
        return None
    line, headings = sheet.rows[index]
    columns: dict[str, Optional[int]] = {role: None for role in ROLES}
    # Most specific wording first: a heading that names exactly one role takes it before a heading that could
    # be several ("Name" is a description or a counterparty; "Posting Date" a date or a posted date).
    # Among headings competing for one role, the earlier word in the vocabulary wins ("Net" before "Gross").
    pairs = sorted(
        (len(roles), VOCABULARY[role].index(fold(headings[c])), c, role)
        for c, roles in ((c, _role_of(h)) for c, h in enumerate(headings))
        for role in roles
    )
    for _, _, c, role in pairs:
        if columns[role] is None and c not in columns.values():
            columns[role] = c
    if columns["date"] is None and columns["posted_date"] is not None:
        columns["date"], columns["posted_date"] = columns["posted_date"], None
    if columns["amount"] is not None and (columns["debit"] is not None and columns["credit"] is not None):
        columns["amount"] = None  # two money columns say the direction; a third would be a duplicate
    banner = [" | ".join(_text(c) for c in cells if _text(c)) for _, cells in sheet.rows[:index]]
    banner = [b for b in banner if b]
    return {
        "sheet": sheet.name,
        "header_line": line,
        "headings": [_text(h) for h in headings],
        "columns": columns,
        "amount_sign": "negative_is_out",
        "date_order": None,
        "layout_key": layout_key(headings),
        "banner": banner,
        "source": "guessed",
    }


def _clean_layout(layout: dict, guessed: dict) -> dict:
    """A person's mapping over the guessed one: only known roles and real column numbers are kept."""
    width = len(guessed["headings"])
    columns = dict(guessed["columns"])
    for role, value in (layout.get("columns") or {}).items():
        if role in columns:
            columns[role] = value if isinstance(value, int) and 0 <= value < width else None
    # A mapping handed in is a person's: the one they sent, or the one they confirmed on an earlier file.
    merged = {**guessed, "columns": columns, "source": "confirmed"}
    if layout.get("amount_sign") in ("negative_is_out", "negative_is_in"):
        merged["amount_sign"] = layout["amount_sign"]
    if layout.get("date_order") in ("month_first", "day_first"):
        merged["date_order"] = layout["date_order"]
    for key in ("confirmed_by", "confirmed_at", "confirmed_document_id"):
        if layout.get(key):
            merged[key] = layout[key]
    return merged


# ---------------------------------------------------------------------------
# Reading rows
# ---------------------------------------------------------------------------


@dataclass
class TabularRow:
    """One line of the table that is not blank: either a reading or the reason it is not one."""

    sheet: Optional[str]
    line: int
    account_key: Optional[str] = None
    when: Optional[date] = None
    posted: Optional[date] = None
    amount: Optional[Decimal] = None   # signed: negative is money out of the account
    balance: Optional[Decimal] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    counterparty: Optional[str] = None
    kind: Optional[str] = None
    reference: Optional[str] = None
    skip: Optional[str] = None
    unsure: bool = False


@dataclass
class TabularDocument:
    """What the reader made of one file, kept on the reading for the precheck and the stored document."""

    kind: str
    file_name: Optional[str]
    layouts: list[dict]
    rows: list[TabularRow]
    source_shape: SourceShape = SourceShape.native_without_control_totals
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.unavailable
    #: A spreadsheet raises no reservation: a file whose balances break is ``unbalanced`` and that alone
    #: keeps it out of totals until a person rules.  What the reader wants the person to know is ``notes``.
    admissibility_reservations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    banner_account: Optional[str] = None
    banner_institution: Optional[str] = None
    currency: Optional[str] = None
    sheets_without_table: list[str] = field(default_factory=list)

    @property
    def proof_class(self):
        return assign_proof_class(self.source_shape, self.reconciliation_status)


def _cell(cells: Sequence[Any], index: Optional[int]) -> Any:
    if index is None or index >= len(cells):
        return None
    return cells[index]


def _ach_code(kind: str) -> Optional[str]:
    """An ACH transaction code's side for the receiving account: 2x-5x ending 1-4 credit it, 6-9 debit it."""
    if len(kind) == 2 and kind.isdigit() and kind[0] in "2345":
        if kind[1] in "1234":
            return "in"
        if kind[1] in "6789":
            return "out"
    return None


def _settle_date_order(sheet: Sheet, start: int, column: Optional[int]) -> tuple[Optional[str], str]:
    """(order, how it was settled) from the file's own dates: a part above 12 proves which is the day."""
    if column is None:
        return None, "none"
    day_first = month_first = False
    for _, cells in sheet.rows[start:]:
        shape = date_shape(_cell(cells, column))
        if shape:
            a, b, _ = shape
            day_first = day_first or (a > 12 >= b)
            month_first = month_first or (b > 12 >= a)
    if day_first and month_first:
        return None, "conflict"
    if day_first:
        return "day_first", "file"
    if month_first:
        return "month_first", "file"
    return None, "none"


def _banner_facts(banner: Sequence[str]) -> tuple[Optional[str], Optional[str]]:
    account = institution = None
    for line in banner:
        match = _ACCOUNT_IN_BANNER.search(line)
        if match and account is None:
            account = match.group(1).strip()
        for part in re.split(r"[,;|]", line):
            folded = fold(part)
            if institution is None and re.search(r"\b(bank|banco|credit union|savings|trust)\b", folded) \
                    and not _ACCOUNT_IN_BANNER.search(part) and len(part.strip()) <= 80:
                institution = part.strip()
    return account, institution


def _read_sheet(sheet: Sheet, layout: dict, window: Any, default_currency: Optional[str],
                banner_account: Optional[str]) -> tuple[list[TabularRow], list[str]]:
    columns = layout["columns"]
    header_index = next(i for i, (line, _) in enumerate(sheet.rows) if line == layout["header_line"])
    order = layout.get("date_order")
    notes: list[str] = []
    settled, how = _settle_date_order(sheet, header_index + 1, columns.get("date"))
    if how == "file":
        if order and order != settled:
            notes.append(f"the confirmed date order is {order.replace('_', '-')}, but the file's own dates are "
                         f"{settled.replace('_', '-')}; the file's order is used")
        order = settled
    elif how == "conflict":
        notes.append("the file's dates are written both day-first and month-first; dates that could be either "
                     "are listed as unsure")
        order = None
    layout["date_order_used"] = order
    layout["date_order_source"] = "file" if how == "file" else ("confirmed" if order else "undetermined")
    headings = [fold(h) for h in layout["headings"]]
    rows: list[TabularRow] = []
    sign = -1 if layout.get("amount_sign") == "negative_is_in" else 1
    for line, cells in sheet.rows[header_index + 1:]:
        if _blank(cells):
            continue
        row = TabularRow(sheet=sheet.name, line=line)
        rows.append(row)
        if [fold(c) for c in cells[:len(headings)]] == headings:
            row.skip = "the heading row repeated"
            continue
        description = _text(_cell(cells, columns.get("description")))
        memo = _text(_cell(cells, columns.get("memo")))
        row.description = " ".join(p for p in (description, memo) if p) or None
        row.counterparty = _text(_cell(cells, columns.get("counterparty"))) or None
        row.kind = _text(_cell(cells, columns.get("type"))) or None
        row.reference = _text(_cell(cells, columns.get("reference"))) or None
        account = _text(_cell(cells, columns.get("account")))
        row.account_key = account or banner_account
        label = fold(row.description or " ".join(_text(c) for c in cells))
        money_cells = [_cell(cells, columns.get(r)) for r in ("amount", "debit", "credit")]
        parsed = [parse_amount(c) for c in money_cells]
        balance, balance_problem = parse_amount(_cell(cells, columns.get("balance")))
        row.balance = balance
        if _TOTALS.match(label) or _BALANCE_LINE.match(label):
            row.skip = "a totals or balance line, not a payment"
            continue
        if columns.get("status") is not None:
            printed_status = _text(_cell(cells, columns.get("status")))
            words = set(fold(printed_status).split())
            if words & _NOT_MOVED_STATUS_WORDS:
                row.skip = f"status is {printed_status!r}: not money that moved"
                continue
            if words and not words & _DONE_STATUS_WORDS:
                row.skip, row.unsure = f"status {printed_status!r} does not say whether the money moved", True
                continue
        problems = [p for _, p in parsed if p] + ([balance_problem] if balance_problem else [])
        values = [v for v, _ in parsed]
        when, date_problem = parse_date(_cell(cells, columns.get("date")), order, window)
        posted, _ = parse_date(_cell(cells, columns.get("posted_date")), order, window)
        row.when, row.posted = when or posted, posted
        if row.when is None and all(v is None for v in values) and not problems:
            row.skip = "no date and no amount: a note or heading line"
            continue
        if row.when is None:
            row.skip, row.unsure = f"has money but {date_problem}", True
            continue
        if problems:
            row.skip, row.unsure = problems[0], True
            continue
        amount, debit, credit = values
        if columns.get("debit") is not None or columns.get("credit") is not None:
            debit = abs(debit) if debit is not None else None
            credit = abs(credit) if credit is not None else None
            if debit and credit:
                row.skip, row.unsure = "both the debit and the credit column have an amount", True
                continue
            signed = -debit if debit else (credit if credit else None)
            if signed is None and amount is not None:
                signed = amount * sign
        else:
            signed = amount * sign if amount is not None else None
        if signed is not None and row.kind:
            kind = fold(row.kind)
            if kind in _OUT_TYPES or _ach_code(kind) == "out":
                signed = -abs(signed)
            elif kind in _IN_TYPES or _ach_code(kind) == "in":
                signed = abs(signed)
        if signed is None:
            row.skip, row.unsure = "a date but no amount", True
            continue
        if row.counterparty is None:
            party = _cell(cells, columns.get("to_party" if signed < 0 else "from_party"))
            row.counterparty = _text(party) or None
        if signed == 0:
            row.skip = "the amount is zero"
            continue
        if window is not None and not (window.earliest <= row.when <= window.latest):
            row.skip, row.unsure = f"date {row.when.isoformat()} is outside the case's date range", True
            continue
        currency_cell = _text(_cell(cells, columns.get("currency"))).upper()
        row.currency = currency_cell if re.fullmatch(r"[A-Z]{3}", currency_cell) else default_currency
        row.amount = signed
    return rows, notes


def _check_balances(rows: list[TabularRow]) -> tuple[ReconciliationStatus, list[str]]:
    """Whether each printed balance follows from the one before and the amount between, in either order."""
    money = [r for r in rows if r.skip is None and r.amount is not None]
    with_balance = [r for r in money if r.balance is not None]
    if len(with_balance) < 2 or len(with_balance) != len(money):
        return ReconciliationStatus.unavailable, []
    oldest_first = [i for i in range(1, len(money)) if money[i - 1].balance + money[i].amount != money[i].balance]
    newest_first = [i for i in range(1, len(money)) if money[i].balance + money[i - 1].amount != money[i - 1].balance]
    if not oldest_first or not newest_first:
        return ReconciliationStatus.balanced, []
    breaks = oldest_first if len(oldest_first) <= len(newest_first) else newest_first
    first = money[breaks[0]]
    sheet = f"sheet {first.sheet!r} " if first.sheet else ""
    return ReconciliationStatus.unbalanced, [
        f"the balance column does not follow from the amounts at {len(breaks)} line"
        f"{'' if len(breaks) == 1 else 's'} (first: {sheet}line {first.line})"]


def read_tabular_document(
    data: bytes,
    *,
    file_name: Optional[str],
    window: Any = None,
    default_currency: Optional[str] = None,
    layouts: Optional[Iterable[dict]] = None,
) -> TabularDocument:
    """Read every statement table in one spreadsheet file under the guessed or the given mapping.

    ``layouts`` are mappings a person confirmed: one is used for the table whose sheet name and headings
    (``layout_key``) it names, in place of the guess.  A table no heading row is found in is listed in
    ``sheets_without_table`` and contributes no rows.
    """
    kind = tabular_kind(file_name)
    if kind is None:
        raise TabularError(f"{file_name!r} is not a CSV, XLSX or XLS file")
    sheets = load_sheets(data, kind, file_name)
    given = list(layouts or [])
    used_layouts: list[dict] = []
    all_rows: list[TabularRow] = []
    notes: list[str] = []
    without: list[str] = []
    currency = default_currency.upper() if default_currency else None
    banner_account = institution = None
    statement_sheets = [(s, guess_layout(s)) for s in sheets]
    for sheet, guessed in statement_sheets:
        if guessed is None:
            if not all(_blank(c) for _, c in sheet.rows):
                without.append(sheet.name or "file")
            continue
        chosen = next((g for g in given if g.get("layout_key") == guessed["layout_key"]
                       and g.get("sheet") in (None, sheet.name)), None)
        layout = _clean_layout(chosen, guessed) if chosen else guessed
        account, bank = _banner_facts(layout["banner"])
        if account is None and layout["columns"].get("account") is None and \
                sum(1 for _, g in statement_sheets if g) > 1:
            # Several statement sheets and no account printed: each sheet is its own unnamed account, so two
            # sheets' rows are never put on one account by default.
            account = f"sheet {sheet.name}"
        if not (account or "").startswith("sheet "):
            banner_account = banner_account or account
        institution = institution or bank
        rows, sheet_notes = _read_sheet(sheet, layout, window, currency, account)
        if layout["columns"].get("currency") is None and currency is None and any(
                r.skip is None for r in rows):
            raise TabularError("the file prints no currency; enter the currency of this account and read it again")
        all_rows.extend(rows)
        notes.extend(sheet_notes)
        used_layouts.append(layout)
    if not used_layouts:
        raise TabularError("no table with a date column and a money column was found in the first "
                           f"{HEADER_SCAN_ROWS} lines of any sheet; the file is not read as a statement")
    status, balance_notes = _check_balances(all_rows)
    unsure = sum(1 for r in all_rows if r.unsure)
    if unsure:
        notes.append(f"{unsure} line{'' if unsure == 1 else 's'} could not be read with certainty and "
                     "are listed as unsure; they are not stored")
    if any(layout["source"] == "guessed" for layout in used_layouts):
        notes.append("the column mapping is the reader's guess; storing the file confirms it for this layout")
    return TabularDocument(
        kind=kind, file_name=file_name, layouts=used_layouts, rows=all_rows,
        reconciliation_status=status, notes=balance_notes + notes,
        banner_account=banner_account, banner_institution=institution, currency=currency,
        sheets_without_table=without,
    )


def to_minor(amount: Decimal) -> int:
    return int((abs(amount) * 100).to_integral_value())


def row_direction(amount: Decimal) -> TransactionDirection:
    return TransactionDirection.debit if amount < 0 else TransactionDirection.credit


def row_source(document: TabularDocument, row: TabularRow) -> dict:
    """The label every stored row carries: read from this file, at this sheet and line."""
    source = {"read_from": "file", "file_kind": document.kind, "line": row.line}
    if document.file_name:
        source["file"] = document.file_name
    if row.sheet:
        source["sheet"] = row.sheet
    return source


#: Document metadata key holding the mappings a stored spreadsheet was read with (who confirmed, when).
TABULAR_LAYOUTS_METADATA_KEY = "tabular_layouts"
#: Transaction metadata key holding where the row was read: file, sheet, line.
ROW_SOURCE_METADATA_KEY = "read_from_file"

_LAYOUT_FIELDS = ("sheet", "header_line", "headings", "columns", "amount_sign", "date_order", "date_order_used",
                  "date_order_source", "layout_key", "source", "confirmed_by", "confirmed_at",
                  "confirmed_document_id")


def public_layouts(document: "TabularDocument") -> list[dict]:
    """The mappings as shown to a person and stored on the document (banner text left out)."""
    return [{key: layout.get(key) for key in _LAYOUT_FIELDS if key in layout} for layout in document.layouts]


DATE_SOURCE = DateSource.transaction
#: Layer 0, as the schema intends for a bank export (``SourceShape.native_without_control_totals`` names "a bank
#: CSV export" and the ledger refuses that shape at any other layer).  The structure constrains the fields; the
#: column mapping is shown to the person who stores the file, and stored with their name on the document.
EXTRACTION_LAYER = ExtractionLayer.native
