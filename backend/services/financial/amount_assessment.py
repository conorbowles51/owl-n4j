"""Read-only assessment of a selected span of canonical evidence text.

Offsets are Unicode code points, matching Python and stored source locations.
Currency is caller-supplied context, never a finding about the source. This does
not identify a transaction, admit evidence, or change any ledger value.
"""
import hashlib

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from services.financial.money import MoneyError
from services.financial.suspect_amounts import TextOrigin, read_amount


class AmountAssessmentError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def assess_source_amount(session, *, case_id, evidence_file_id, start_char,
                         end_char, expected_text, content_sha256, currency):
    if (type(start_char) is not int or type(end_char) is not int
            or start_char < 0 or not 0 < end_char - start_char <= 128):
        raise AmountAssessmentError("Select between 1 and 128 Unicode code points.")
    # One query binds the text and metadata to the same case-scoped snapshot.
    source = session.execute(select(
        EvidenceDocumentText.content, EvidenceDocumentText.content_sha256,
        EvidenceDocumentText.source_locations,
    ).join(EvidenceFile, EvidenceFile.id == EvidenceDocumentText.evidence_file_id).where(
        EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id,
    )).one_or_none()
    if source is None:
        raise AmountAssessmentError("Source text not found in this case.", 404)
    content, stored_hash, locations = source
    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if stored_hash != actual_hash or content_sha256 != actual_hash:
        raise AmountAssessmentError("Source text changed or its digest is inconsistent. Reload it.", 409)
    if end_char > len(content) or content[start_char:end_char] != expected_text:
        raise AmountAssessmentError("The selected text does not match the source offsets.", 409)

    # A missing, malformed or overlapping page map cannot establish origin.
    origin = TextOrigin.unknown
    page_number = None
    covering = []
    malformed = not isinstance(locations, list)
    for location in locations if isinstance(locations, list) else []:
        if not isinstance(location, dict):
            malformed = True
            continue
        if location.get("kind") != "page":
            continue
        left, right = location.get("start_char"), location.get("end_char")
        if type(left) is not int or type(right) is not int or not 0 <= left < right <= len(content):
            malformed = True
            continue
        if start_char < right and end_char > left:
            covering.append(location)
    if not malformed and len(covering) == 1:
        location = covering[0]
        if location["start_char"] <= start_char and end_char <= location["end_char"]:
            page = location.get("page_number")
            if type(page) is int and page > 0:
                page_number = page
                try:
                    origin = TextOrigin(location.get("text_origin"))
                except (TypeError, ValueError):
                    pass
    try:
        reading = read_amount(content[start_char:end_char], currency, origin)
    except MoneyError as exc:
        raise AmountAssessmentError(str(exc)) from exc
    assessment = reading.to_json()
    if "minor_units" in assessment:
        assessment["minor_units"] = str(assessment["minor_units"])
    for proposal in assessment.get("proposals", []):
        proposal["minor_units"] = str(proposal["minor_units"])
    return {
        "case_id": str(case_id), "evidence_file_id": str(evidence_file_id),
        "content_sha256": actual_hash, "start_char": start_char, "end_char": end_char,
        "offset_unit": "unicode_code_points", "page_number": page_number,
        "currency_source": "caller_supplied", "assessment": assessment,
        "applied": False,
        "limitation": "Selected text only; this does not establish that it is a transaction amount or admit it to totals.",
    }
