"""What was exported, and the separate record of when it was exported.

An export is a document put in front of someone: opposing counsel, a court, a
client.  The question that follows it is always the same one -- is this the
same document I was given before -- and the only answer worth having is one
that can be checked rather than asserted.

The obstacle was a single line.  The renderer stamped ``datetime.now()`` into
the body of the page, so two exports of an unchanged ledger differed, and they
differed in a way that defeats every cheap check a recipient might run.  A
digest over the bytes said "different".  A diff said "different, here".  So a
recipient asking whether the figures had moved had no way to find out except to
read both documents, and the one property that would have answered the question
instantly had been spent on recording a fact nobody had asked for.

The fix is a separation, not a deletion.  The generation time is real and worth
keeping; it is simply not a property of the document.  Two exports of the same
ledger under the same filters *are the same exhibit*, whatever days they were
printed on, and the act of printing is a separate event about which "when" is
the interesting question.  So the document becomes a pure function of the
evidence and the filter state, and the act of exporting becomes a manifest that
carries the time, the digest of what was produced, and the version of the code
that produced it.

What this buys, concretely.  A recipient can be told the digest and check it
without holding the ledger.  A regeneration months later can be compared to the
manifest to prove the underlying figures have not moved -- or to prove exactly
that they have, which is the more valuable answer of the two, and which the old
arrangement could not distinguish from a clock ticking.  And an export can be
re-derived from an archived manifest without the archive having to store the
document, because the document is reproducible and the manifest says which
inputs and which code to reproduce it from.

Why the digest is over the HTML.  ``render_financial_export`` may hand back a
PDF, and a PDF is not reproducible in the way this module needs: the format
carries a creation date and a document identifier of its own, written by the
renderer at write time and outside this code's control.  Hashing that would
produce a manifest whose digest changed on every run, which is the defect being
fixed, dressed as its own remedy.  So the digest is taken over the HTML, which
is the artifact this code fully determines and the one the PDF is a rendering
of.  The manifest says which it did, in ``digest_covers``, so the scope of the
claim is on the record rather than in someone's memory of it.

Why a naive timestamp is refused.  A time with no zone is not a time -- it is a
number that means different moments depending on where the process that wrote
it happened to be running, which is exactly the ambiguity a manifest exists to
remove.  This is the one field in the manifest that cannot be re-derived later,
so it is the one field with nothing to fall back on if it is wrong.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.financial.version import code_version

# What the digest is taken over.  Named rather than implied, because a manifest
# that did not say would be read as covering whatever the reader assumed.
DIGEST_COVERS_HTML = "export_html"

MANIFEST_SCHEMA = "loupe.financial.export_manifest/1"


class ExportManifestError(Exception):
    """A manifest cannot be built as asked."""


@dataclass(frozen=True, slots=True)
class ExportManifest:
    """The record of one act of exporting.

    Frozen because a manifest describes something that already happened.  A
    mutable one would let the record of an export drift away from the export,
    which is the failure it exists to prevent.
    """

    schema: str
    document_sha256: str
    digest_covers: str
    byte_count: int
    generated_at: datetime
    case_name: str
    filters_description: str
    transaction_count: int
    code_version: str

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ExportManifestError(
                "generated_at must carry a timezone; a naive timestamp records "
                "a number, not a moment"
            )
        if self.transaction_count < 0:
            raise ExportManifestError("transaction_count is negative")
        if self.byte_count < 0:
            raise ExportManifestError("byte_count is negative")

    def as_dict(self) -> dict[str, Any]:
        """The manifest as plain data, with the timestamp in UTC.

        Converted to UTC rather than written in whatever zone it arrived in, so
        that two manifests can be compared without either reader having to
        reason about offsets.  The offset is not lost -- it was never the
        subject; the moment was.
        """
        return {
            "schema": self.schema,
            "document_sha256": self.document_sha256,
            "digest_covers": self.digest_covers,
            "byte_count": self.byte_count,
            "generated_at": self.generated_at.astimezone(timezone.utc).isoformat(),
            "case_name": self.case_name,
            "filters_description": self.filters_description,
            "transaction_count": self.transaction_count,
            "code_version": self.code_version,
        }

    def to_json(self) -> str:
        """Sorted keys and no incidental whitespace, so the JSON is stable too.

        A manifest that serialised differently on different runs would need a
        manifest of its own.
        """
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def document_digest(document: str) -> str:
    """The sha256 of the document as it will be delivered.

    Encoded UTF-8 explicitly.  Relying on the platform default would make the
    digest a property of the machine as well as of the document, which is the
    class of bug this whole module is about.
    """
    if not isinstance(document, str):
        raise ExportManifestError("document must be the rendered HTML string")
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def manifest_for(
    document: str,
    *,
    case_name: str,
    filters_description: str = "",
    transaction_count: int,
    generated_at: datetime | None = None,
) -> ExportManifest:
    """Describe one export of ``document``.

    ``generated_at`` is a parameter rather than always being read from the
    clock so that a caller replaying an archived export can say when the export
    it is describing actually happened.  It defaults to now, in UTC, because the
    common case is an export happening at the moment this is called.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    if isinstance(transaction_count, bool) or not isinstance(transaction_count, int):
        raise ExportManifestError("transaction_count must be an int")
    return ExportManifest(
        schema=MANIFEST_SCHEMA,
        document_sha256=document_digest(document),
        digest_covers=DIGEST_COVERS_HTML,
        byte_count=len(document.encode("utf-8")),
        generated_at=generated_at,
        case_name=case_name,
        filters_description=filters_description,
        transaction_count=transaction_count,
        code_version=code_version(),
    )


def describes(manifest: ExportManifest, document: str) -> bool:
    """Whether ``manifest`` is the manifest of ``document``.

    The check a recipient runs, and the check a regeneration runs against an
    archived manifest to show the figures have not moved.  Compares the digest
    rather than the bytes so that it costs the same for a large export as a
    small one, and so that it can be run by someone holding only the manifest.
    """
    return manifest.document_sha256 == document_digest(document)
