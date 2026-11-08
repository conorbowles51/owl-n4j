"""Citations in answers, report sections and summaries: one parser, one check against the case.

Three schemes name the object a claim rests on:

- ``doc://<evidence_file_id>/<page>`` a page of an evidence file. ``doc://<evidence_file_id>`` when no page was
  given: the file opens with "page not given", never at a page nobody cited. Older answers name the file instead of
  its id (``doc://<url-encoded filename>[/<page>]``); such a link still opens when exactly one visible file of the case
  has that name, and offers the files to choose from when several do. It is never resolved by guessing one of them.
- ``txn://<transaction_id>`` a ledger row; it opens the Financial page on that row, at its statement page.
- ``rec://<record_uid>[#<field>]`` a phone record (03 section 11.5).

The Financial page links agent answers wrote before ``txn://`` (``/cases/<case>/financial?...&payment=<id>``) are
read as ``txn://`` citations, so they keep working and are checked the same way.

A citation whose target is not in the case is ``not_in_case``: said in the same words whether or not the object
exists in another case, and never shown as a link that opens nothing.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field as _field
from typing import Any, Iterable
from urllib.parse import quote, unquote

UUID_TEXT = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_UUID = re.compile(rf"^{UUID_TEXT}$")
# A Markdown link target: ](target) or ](<target>); the target may carry an optional "title".
_LINK = re.compile(r"\]\(\s*<?((?:doc|txn|rec|evidence)://[^)>\s]*|(?:https?://[^)\s>]*?)?/?cases/[^)\s>]*)>?(?:\s+\"[^\"]*\")?\s*\)")
# a Loupe page written with a host: https://<any host>/cases/<id>/... or https://cases/<id>/... (the host dropped)
_APP_URL = re.compile(rf"^https?://(?:[^/\s]+/)*?(cases/{UUID_TEXT}(?:[/?#]\S*)?)$")
_HOSTED_LINK = re.compile(r"(\]\(\s*<?)(https?://[^)\s>]+)")
_FINANCIAL_PATH = re.compile(rf"^(?:https?://[^/]+)?/cases/({UUID_TEXT})/financial\?(\S*)$")
_PAYMENT_PARAM = re.compile(rf"(?:^|&)payment=({UUID_TEXT})(?:&|$)")

NOT_IN_CASE = "Not in this case."
OTHER_CASE = "A payment of another case: it opens in that case, where that case's own access applies."
PAGE_NOT_GIVEN = "Page not given."
SCHEMES = ("doc", "txn", "rec")


@dataclass(frozen=True)
class Citation:
    """One parsed citation. ``target`` is a lower-case id for txn/rec and for doc by id; a filename for doc by name."""

    href: str
    scheme: str
    target: str
    by_name: bool = False
    page: int | None = None
    field: str | None = None
    legacy: bool = False
    linked_case_id: str | None = None

    def key(self) -> str:
        return self.href


def _page(text: str) -> int | None:
    if text.isdigit():
        value = int(text)
        return value if value >= 1 else None
    return None


def parse_citation(href: str | None) -> Citation | None:
    """The citation an href names, or None when it is not a citation (an ordinary web link, a bare path)."""
    if not href:
        return None
    href = href.strip()
    if href.startswith("txn://"):
        target = href[6:].strip("/")
        return Citation(href, "txn", target.lower()) if _UUID.match(target) else None
    if href.startswith("rec://"):
        rest = href[6:]
        uid, _, field_path = rest.partition("#")
        uid = uid.strip("/")
        if not _UUID.match(uid):
            return None
        return Citation(href, "rec", uid.lower(), field=unquote(field_path) or None)
    if href.startswith("doc://") or href.startswith("evidence://"):
        legacy = href.startswith("evidence://")
        rest = href[len("evidence://"):] if legacy else href[6:]
        page = None
        head, slash, tail = rest.rpartition("/")
        if not legacy and slash and tail.strip().isdigit():
            rest, page = head, _page(tail.strip())
        elif not legacy and slash and not tail:
            rest = head
        target = rest.strip()
        try:
            target = unquote(target)
        except Exception:  # noqa: BLE001 - a literal percent sign stays as written
            pass
        if not target:
            return None
        if _UUID.match(target):
            return Citation(href, "doc", target.lower(), page=page, legacy=legacy)
        return Citation(href, "doc", target, by_name=True, page=page, legacy=legacy)
    match = _FINANCIAL_PATH.match(app_path(href) or href)
    if match:
        payment = _PAYMENT_PARAM.search(match.group(2))
        if payment:
            return Citation(href, "txn", payment.group(1).lower(), legacy=True, linked_case_id=match.group(1).lower())
    return None


def app_path(href: str | None) -> str | None:
    """The in-app path of a link a model wrote with a host (``https://example.com/cases/<id>/...`` or
    ``https://cases/<id>/...``): Loupe's own pages are never on another host. None otherwise."""
    match = _APP_URL.match((href or "").strip())
    return "/" + match.group(1) if match else None


def citations_in(text: str | None) -> list[Citation]:
    """Every citation link in Markdown text, in order, each href once."""
    seen: dict[str, Citation] = {}
    for match in _LINK.finditer(text or ""):
        citation = parse_citation(match.group(1))
        if citation is not None and citation.href not in seen:
            seen[citation.href] = citation
    return list(seen.values())


def doc_href(evidence_file_id: Any, page: int | None = None) -> str:
    return f"doc://{evidence_file_id}/{page}" if page else f"doc://{evidence_file_id}"


def txn_href(transaction_id: Any) -> str:
    return f"txn://{transaction_id}"


# ---- the check against the case ----------------------------------------------------------------------------------


@dataclass
class Resolution:
    href: str
    scheme: str
    status: str  # ok | not_in_case | ambiguous
    reason: str | None = None
    page: int | None = None
    page_given: bool = False
    evidence_file_id: str | None = None
    filename: str | None = None
    candidates: list[dict[str, Any]] = _field(default_factory=list)
    transaction_id: str | None = None
    record_uid: str | None = None
    field: str | None = None
    legacy: bool = False
    detail: dict[str, Any] = _field(default_factory=dict)
    production_numbers: list[dict[str, Any]] = _field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out = {key: value for key, value in self.__dict__.items() if value not in (None, [], {})}
        out["page_given"] = self.page_given
        out["legacy"] = self.legacy
        return out


def _as_uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _files_by_id(session, case_id, ids: Iterable[str]) -> dict[str, Any]:
    from sqlalchemy import select

    from postgres.models.evidence import EvidenceFile
    wanted = sorted({_as_uuid(value) for value in ids})
    if not wanted:
        return {}
    rows = session.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_(wanted)))
    return {str(row.id): row.original_filename for row in rows}


def _files_by_name(session, case_id, names: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """Visible files of the case for each name: internal copies and phone thread documents are not separate files."""
    from sqlalchemy import select

    from postgres.models.evidence import EvidenceFile
    from services.financial.source_lineage import visible_evidence_condition
    wanted = sorted(set(names))
    out: dict[str, list[dict[str, Any]]] = {name: [] for name in wanted}
    if not wanted:
        return out
    rows = session.execute(select(EvidenceFile.id, EvidenceFile.original_filename, EvidenceFile.created_at,
                                  EvidenceFile.size, EvidenceFile.sha256).where(
        EvidenceFile.case_id == case_id, EvidenceFile.original_filename.in_(wanted),
        visible_evidence_condition()).order_by(EvidenceFile.created_at, EvidenceFile.id))
    for row in rows:
        out[row.original_filename].append(dict(
            evidence_file_id=str(row.id), filename=row.original_filename,
            uploaded_at=row.created_at.isoformat() if row.created_at else None, size=int(row.size or 0),
            sha256_prefix=(row.sha256 or "")[:12]))
    return out


def _transactions(session, case_id, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    from sqlalchemy import select

    from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
    from services.financial.transactions import LOCATOR_PROVENANCE_KEY
    wanted = sorted({_as_uuid(value) for value in ids})
    if not wanted:
        return {}
    rows = session.execute(select(
        FinancialTransaction.id, FinancialTransaction.ledger_status, FinancialTransaction.superseded_by_id,
        FinancialTransaction.provenance[LOCATOR_PROVENANCE_KEY].label("locator"),
        FinancialSourceDocument.evidence_file_id).outerjoin(
        FinancialSourceDocument, FinancialSourceDocument.id == FinancialTransaction.source_document_id).where(
        FinancialTransaction.case_id == case_id, FinancialTransaction.id.in_(wanted)))
    out = {}
    for row in rows:
        locator = row.locator if isinstance(row.locator, dict) else {}
        page = locator.get("page")
        out[str(row.id)] = dict(
            ledger_status=row.ledger_status,
            superseded_by_id=str(row.superseded_by_id) if row.superseded_by_id else None,
            page=page if isinstance(page, int) and not isinstance(page, bool) and page >= 1 else None,
            evidence_file_id=str(row.evidence_file_id) if row.evidence_file_id else None)
    return out


def _records(session, case_id, ids: Iterable[str]) -> set[str] | None:
    """Phone records of the case among ``ids``; None when this database has no phone records table."""
    from sqlalchemy import inspect, text
    wanted = sorted(set(ids))
    if not wanted:
        return set()
    # the session's own connection: a table made inside its transaction is seen, and no second connection is opened
    bind = session.connection()
    if not inspect(bind).has_table("pv_record"):
        return None
    if bind.dialect.name == "postgresql":
        rows = session.execute(text("SELECT record_uid FROM pv_record WHERE case_id = :c AND record_uid = "
                                    "ANY(CAST(:u AS uuid[]))"), {"c": str(case_id), "u": wanted})
    else:
        rows = session.execute(text("SELECT record_uid FROM pv_record WHERE case_id = :c AND lower(record_uid) IN (%s)"
                                    % ",".join(f":u{i}" for i in range(len(wanted)))),
                               {"c": str(case_id), **{f"u{i}": value for i, value in enumerate(wanted)}})
    return {str(row[0]).lower() for row in rows}


def resolve_citations(session, case_id, citations: Iterable[Citation]) -> list[Resolution]:
    """Check each citation against the case, in a bounded number of queries (one per kind)."""
    case_uuid = _as_uuid(case_id)
    citations = list(citations)
    by_id = _files_by_id(session, case_uuid, [c.target for c in citations if c.scheme == "doc" and not c.by_name])
    by_name = _files_by_name(session, case_uuid, [c.target for c in citations if c.scheme == "doc" and c.by_name])
    txns = _transactions(session, case_uuid, [c.target for c in citations if c.scheme == "txn"])
    records = _records(session, case_uuid, [c.target for c in citations if c.scheme == "rec"])
    out = []
    for c in citations:
        r = Resolution(href=c.href, scheme=c.scheme, status="ok", legacy=c.legacy or c.by_name)
        if c.scheme == "doc":
            r.page, r.page_given = c.page, c.page is not None
            if not c.by_name:
                if c.target in by_id:
                    r.evidence_file_id, r.filename = c.target, by_id[c.target]
                else:
                    r.status, r.reason = "not_in_case", NOT_IN_CASE
            else:
                found = by_name.get(c.target, [])
                r.filename = c.target
                if len(found) == 1:
                    r.evidence_file_id = found[0]["evidence_file_id"]
                elif found:
                    r.status, r.candidates = "ambiguous", found
                    r.reason = (f"{len(found)} files in this case are called {c.target}; the citation does not say "
                                "which. Choose one.")
                else:
                    r.status, r.reason = "not_in_case", NOT_IN_CASE
        elif c.scheme == "txn":
            row = txns.get(c.target)
            r.transaction_id = c.target
            if c.linked_case_id and c.linked_case_id != str(case_uuid):
                # a link that names its own case (an all-cases answer): never looked up here, opened in that case
                r.status, r.reason = "other_case", OTHER_CASE
                r.detail = {"case_id": c.linked_case_id}
            elif row is None:
                r.status, r.reason = "not_in_case", NOT_IN_CASE
            else:
                r.page, r.page_given = row["page"], row["page"] is not None
                r.evidence_file_id = row["evidence_file_id"]
                r.detail = {"ledger_status": row["ledger_status"]}
                if row["superseded_by_id"]:
                    r.detail["superseded_by_id"] = row["superseded_by_id"]
        elif c.scheme == "rec":
            r.record_uid, r.field = c.target, c.field
            if records is None or c.target not in records:
                r.status, r.reason = "not_in_case", NOT_IN_CASE
        out.append(r)
    return _with_production_numbers(session, case_uuid, out)


def _with_production_numbers(session, case_id, resolutions: list[Resolution]) -> list[Resolution]:
    """Beside each citation of a file, the production numbers of the cited page, each saying what kind it is."""
    from sqlalchemy import inspect

    from services.production_numbers import references_for
    cited = [r for r in resolutions if r.status == "ok" and r.evidence_file_id]
    if cited and inspect(session.connection()).has_table("production_assignments"):
        names = {r.evidence_file_id: r.filename for r in cited if r.filename}
        found = references_for(session, case_id, [(r.evidence_file_id, r.page) for r in cited], names=names)
        for r in cited:
            r.production_numbers = found.get((r.evidence_file_id, r.page), [])
    return resolutions


def check_text(session, case_id, text: str | None) -> dict[str, Any]:
    """The answer check: every citation in ``text`` against the case. Counts and the citations that failed."""
    resolutions = resolve_citations(session, case_id, citations_in(text))
    counts = {"total": len(resolutions), "ok": 0, "not_in_case": 0, "ambiguous": 0, "other_case": 0}
    for r in resolutions:
        counts[r.status] += 1
    by_scheme: dict[str, int] = {}
    for r in resolutions:
        by_scheme[r.scheme] = by_scheme.get(r.scheme, 0) + 1
    return {**counts, "by_scheme": by_scheme, "page_not_given": sum(
        1 for r in resolutions if r.scheme == "doc" and r.status == "ok" and not r.page_given),
            "problems": [r.to_json() for r in resolutions if r.status in ("not_in_case", "ambiguous")]}


def canonicalize(session, case_id, text: str | None) -> str:
    """Rewrite citations to their stable form before an answer is stored: a file named once in the case becomes its
    id (a later upload with the same name cannot make the citation ambiguous), and a Financial page payment link
    becomes ``txn://``. A link to a Loupe page written with a host (``https://example.com/cases/...``) becomes the
    in-app path. A name several files share, anything not in the case, and a payment link that carries another case
    stay as written for the check to mark. Page numbers are never added or changed."""
    text = _strip_link_hosts(text or "")
    citations = citations_in(text)
    wanted = [c for c in citations if (c.scheme == "doc" and c.by_name and not c.legacy) or
              (c.scheme == "txn" and c.legacy)]
    if not wanted:
        return text
    rewrite: dict[str, str] = {}
    for r, c in zip(resolve_citations(session, case_id, wanted), wanted):
        if r.status != "ok":
            continue
        if c.scheme == "doc" and r.evidence_file_id:
            rewrite[c.href] = doc_href(r.evidence_file_id, c.page)
        elif c.scheme == "txn":
            rewrite[c.href] = txn_href(c.target)
    if not rewrite:
        return text

    def replace(match: re.Match) -> str:
        new = rewrite.get(match.group(1))
        return match.group(0).replace(match.group(1), new, 1) if new else match.group(0)
    return _LINK.sub(replace, text)


def _strip_link_hosts(text: str) -> str:
    """A link to a Loupe page written with an invented host becomes the in-app path."""
    def strip(match: re.Match) -> str:
        path = app_path(match.group(2))
        return match.group(1) + path if path else match.group(0)
    return _HOSTED_LINK.sub(strip, text)


def encode_filename_links(text: str | None) -> str:
    """``](doc://March statement.pdf/4)`` cannot be clicked (a link target holds no space): encode the name."""
    def encode(match: re.Match) -> str:
        target = match.group(1)
        head, slash, tail = target.rpartition("/")
        name, page = (head, tail) if slash and tail.strip().isdigit() else (target, "")
        encoded = quote(unquote(name.strip()), safe="")
        return f"](doc://{encoded}/{page.strip()})" if page else f"](doc://{encoded})"
    return re.sub(r"\]\(\s*<?doc://([^)>]*?)>?\s*\)", encode, text or "")


def chunk_page(metadata: dict[str, Any]) -> int | None:
    """A document passage's page from its search metadata; None when it gives none (never page 1 by default)."""
    value = metadata.get("page_start")
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if page >= 1 else None


def chunk_cite(metadata: dict[str, Any]) -> str | None:
    """The doc:// citation of a document passage: by evidence file id when the passage carries one, else by name."""
    page = chunk_page(metadata)
    file_id = str(metadata.get("evidence_file_id") or "").strip()
    if _UUID.match(file_id):
        return doc_href(file_id.lower(), page)
    name = str(metadata.get("filename") or metadata.get("doc_name") or metadata.get("file_name") or "").strip()
    if not name:
        return None
    encoded = quote(name, safe="")
    return f"doc://{encoded}/{page}" if page else f"doc://{encoded}"
