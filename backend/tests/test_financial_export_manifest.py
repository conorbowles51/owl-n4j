"""The export as a reproducible document, and the manifest that dates it.

Two things are under test and they pull in opposite directions, which is why
they are tested together.

The document must be a pure function of its inputs.  That is asserted the only
way it can be honestly asserted -- by rendering twice with the clock moved
between the renders and comparing bytes -- because the defect being guarded
against was a clock reading in the body, and a test that did not move the clock
would have passed against the broken code.

The manifest must record the things the document deliberately no longer
carries.  So the assertions on it are mostly about refusing to record them
badly: a naive timestamp, a count that contradicts the document, a digest whose
scope is left to the reader's assumption.

There is no golden vector over the rendered HTML here, and the omission is
deliberate.  A reference must never change, so ``test_financial_references``
pins its derivation to a literal.  An export's HTML is expected to change --
restyling the header is a normal act -- and what must hold is that it does not
change *between two renders of the same evidence by the same build*.  Pinning a
literal would convert every stylesheet edit into a failing test whose only
repair is to paste in the new value, which trains the reflex that makes golden
vectors worthless where they do matter.  ``code_version`` in the manifest is
what lets a digest change be attributed to a release rather than to the figures.
"""
from __future__ import annotations

import importlib
import json
import unittest
from dataclasses import fields
from datetime import datetime, timedelta, timezone, tzinfo
from unittest import mock

from services.financial.export_manifest import (
    DIGEST_COVERS_HTML,
    MANIFEST_SCHEMA,
    ExportManifest,
    ExportManifestError,
    describes,
    document_digest,
    manifest_for,
)
from services.financial.version import code_version
from services.financial_export_service import (
    _group_transactions_for_export,
    build_financial_export_html,
    render_financial_export,
)

CASE = "Case Alpha"
FILTERS = 'Search: "counsel"'


def transaction(key: str = "tx-1", **overrides) -> dict:
    row = {
        "key": key,
        "date": "2026-04-01",
        "name": "Wire transfer",
        "amount": 1200.0,
        "category": "Legal/Professional",
        "from_entity": {"key": "sender-a", "name": "Sender A"},
        "to_entity": {"key": "beneficiary-a", "name": "Beneficiary A"},
        "summary": "Transfer to outside counsel",
        "source_filename": "bank_statement.pdf",
        "source_page": 4,
        "evidence_source_type": "bank_statement",
    }
    row.update(overrides)
    return row


def render(transactions=None, case_name: str = CASE, filters: str = FILTERS) -> str:
    return build_financial_export_html(
        transactions=transactions if transactions is not None else [transaction()],
        case_name=case_name,
        filters_description=filters,
    )


class _FrozenDatetime(datetime):
    """A ``datetime`` whose ``now`` is a fixed instant.

    A subclass rather than a mock so that anything the module under test does
    with the class -- ``strftime``, arithmetic, comparison -- keeps working;
    only the reading of the clock is replaced.
    """

    _instant = datetime(2000, 1, 1)

    @classmethod
    def now(cls, tz=None):
        return cls._instant if tz is None else cls._instant.replace(tzinfo=tz)

    @classmethod
    def utcnow(cls):
        return cls._instant


def _at(instant: datetime):
    """Patch the ``datetime`` module's class, for modules imported afterwards."""
    frozen = type("FrozenAt", (_FrozenDatetime,), {"_instant": instant})
    return mock.patch("datetime.datetime", frozen)


def _render_with_clock_at(instant: datetime) -> str:
    """Render with the system clock reading ``instant``.

    The service module is reloaded inside the patch so that its own
    ``from datetime import ...`` binds the replaced class; without the reload a
    reintroduced clock read would go undetected, because the module would still
    be holding the real one from its original import.
    """
    import services.financial_export_service as service

    with _at(instant):
        reloaded = importlib.reload(service)
        try:
            return reloaded.build_financial_export_html(
                transactions=[transaction()],
                case_name=CASE,
                filters_description=FILTERS,
            )
        finally:
            importlib.reload(service)  # restore the real clock for other tests


def _clock_probe():
    """A renderer that *does* stamp the clock, to prove ``_at`` bites."""

    def probe(instant: datetime) -> str:
        with _at(instant):
            module = importlib.import_module("datetime")
            return module.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return probe


class ReproducibilityTests(unittest.TestCase):
    """The property the whole change exists to establish."""

    def test_two_renders_years_apart_are_byte_identical(self):
        """The clock genuinely moves between the two renders.

        This is the test the whole change is for, so it is worth being exact
        about why it is built the way it is.  Rendering twice in quick
        succession and comparing would have *passed against the broken code*:
        the old timestamp was formatted to the minute, so two renders inside
        the same minute agreed. A test that cannot fail against the defect it
        names is decoration.

        So the clock is replaced, and the module reloaded under the
        replacement.  The reload is the part that matters: the service binds
        ``datetime`` at import time with ``from datetime import ...``, so a
        module already imported keeps its own reference and patching the
        ``datetime`` module afterwards would reach nothing.  Reloading
        re-executes the import against the patched module, which is what makes
        this catch a *reintroduced* clock read and not merely the absence of
        the one that was removed.

        ``test_the_clock_replacement_actually_takes_effect`` below proves the
        mechanism works, so a future refactor that quietly defeats it fails
        loudly rather than leaving this passing for the wrong reason.
        """
        first = _render_with_clock_at(datetime(2026, 4, 1, 9, 30, 15))
        second = _render_with_clock_at(datetime(2031, 11, 23, 22, 5, 51))

        self.assertEqual(first, second)
        self.assertEqual(document_digest(first), document_digest(second))

    def test_the_clock_replacement_actually_takes_effect(self):
        """Proof that the test above is capable of failing.

        A module that reads the patched clock and renders it must produce
        different output at the two instants.  If this fails, the harness is
        broken and the byte-identity assertion above proves nothing.
        """
        probe = _clock_probe()
        self.assertNotEqual(
            probe(datetime(2026, 4, 1, 9, 30, 15)),
            probe(datetime(2031, 11, 23, 22, 5, 51)),
        )

    def test_the_rendered_document_holds_no_generation_stamp(self):
        """Names the specific failure, in case a *fixed* date is stamped in.

        A hardcoded date would be reproducible and still wrong, so byte
        identity alone would not catch it.
        """
        self.assertNotIn("Generated:", render())

    def test_differing_evidence_changes_the_document(self):
        """Byte-identity would be trivially satisfiable by a constant page."""
        self.assertNotEqual(render(), render([transaction(amount=1200.01)]))

    def test_differing_filters_change_the_document(self):
        """The filter state is part of what the exhibit is, not decoration.

        Two exports of the same case under different filters are different
        exhibits and must not share a digest.
        """
        self.assertNotEqual(render(), render(filters="Categories: Legal/Professional"))

    def test_differing_case_name_changes_the_document(self):
        self.assertNotEqual(render(), render(case_name="Case Beta"))


class GroupingTests(unittest.TestCase):
    """Every row handed in reaches the document.

    The ordering was already covered indirectly; what was not covered is that
    ordering is lossless.  It was not: deduplication ran on ``tx.get("key")``,
    so ``None`` entered the seen set on the first keyless row and silently
    swallowed the rest.
    """

    def test_rows_without_keys_are_all_kept(self):
        rows = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        self.assertEqual(
            [row["name"] for row in _group_transactions_for_export(rows)],
            ["A", "B", "C"],
        )

    def test_two_rows_with_identical_values_are_two_rows(self):
        """A matching pair of cash withdrawals is ordinary, not a duplicate.

        Tracked by identity rather than equality for this reason: equal content
        is what a real repeated payment looks like.
        """
        rows = [{"amount": 50.0}, {"amount": 50.0}]
        self.assertEqual(len(_group_transactions_for_export(rows)), 2)

    def test_a_child_follows_its_parent(self):
        rows = [
            {"key": "p", "is_parent": True, "name": "P"},
            {"key": "z", "name": "Z"},
            {"key": "c", "parent_transaction_key": "p", "name": "C"},
        ]
        self.assertEqual(
            [row["name"] for row in _group_transactions_for_export(rows)],
            ["P", "C", "Z"],
        )

    def test_a_child_whose_parent_was_filtered_out_still_appears(self):
        """Filtering can separate a child from its parent, and often does.

        The child is evidence in its own right; dropping it because the row it
        was indented under is absent would remove a transaction from an exhibit
        on the strength of a display convention.
        """
        rows = [
            {"key": "c", "parent_transaction_key": "absent", "name": "C"},
            {"key": "z", "name": "Z"},
        ]
        self.assertEqual(
            sorted(row["name"] for row in _group_transactions_for_export(rows)),
            ["C", "Z"],
        )

    def test_the_same_key_twice_is_emitted_once(self):
        """The one case where a row is deliberately not emitted twice.

        A repeated key means the same node came back from the query twice, and
        the interleave depends on being able to say so.
        """
        rows = [{"key": "k", "name": "A"}, {"key": "k", "name": "B"}]
        self.assertEqual(len(_group_transactions_for_export(rows)), 1)

    def test_ordering_is_a_function_of_the_input(self):
        rows = [
            {"key": "p", "is_parent": True, "name": "P"},
            {"key": "c", "parent_transaction_key": "p", "name": "C"},
            {"name": "unkeyed"},
        ]
        self.assertEqual(
            _group_transactions_for_export(rows),
            _group_transactions_for_export(rows),
        )


class _ZoneWithoutOffset(tzinfo):
    """A zone that has a name and no offset, which is what ``tzinfo`` gives you.

    The base class returns ``None`` from ``utcoffset``, so a subclass that
    implements only ``tzname`` -- an easy thing to write -- produces a datetime
    that passes an ``is not None`` check on ``tzinfo`` and still cannot be
    placed on a timeline.
    """

    def utcoffset(self, dt):
        return None

    def tzname(self, dt):
        return "NOWHERE"

    def dst(self, dt):
        return None


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.html = render()

    def test_the_manifest_describes_the_document_it_was_built_from(self):
        manifest = manifest_for(
            self.html, case_name=CASE, filters_description=FILTERS, transaction_count=1
        )
        self.assertTrue(describes(manifest, self.html))

    def test_the_manifest_does_not_describe_a_changed_document(self):
        manifest = manifest_for(
            self.html, case_name=CASE, filters_description=FILTERS, transaction_count=1
        )
        self.assertFalse(describes(manifest, self.html + " "))

    def test_the_scope_of_the_digest_is_recorded(self):
        """A recipient must not have to guess what was hashed."""
        manifest = manifest_for(self.html, case_name=CASE, transaction_count=1)
        self.assertEqual(manifest.digest_covers, DIGEST_COVERS_HTML)
        self.assertEqual(manifest.schema, MANIFEST_SCHEMA)

    def test_the_byte_count_is_of_the_encoded_document(self):
        """Characters and bytes differ the moment a name is not ASCII."""
        html = render([transaction(name="Paiement à Sécurité Générale")])
        manifest = manifest_for(html, case_name=CASE, transaction_count=1)
        self.assertEqual(manifest.byte_count, len(html.encode("utf-8")))
        self.assertGreater(manifest.byte_count, len(html))

    def test_a_naive_timestamp_is_refused(self):
        """The one field that cannot be re-derived, so the one with no fallback."""
        with self.assertRaises(ExportManifestError):
            manifest_for(
                self.html,
                case_name=CASE,
                transaction_count=1,
                generated_at=datetime(2026, 4, 1, 9, 30),
            )

    def test_an_aware_timestamp_in_any_zone_is_accepted_and_normalised(self):
        """The offset was never the subject; the moment was."""
        eastern = timezone(timedelta(hours=-4))
        manifest = manifest_for(
            self.html,
            case_name=CASE,
            transaction_count=1,
            generated_at=datetime(2026, 4, 1, 9, 30, tzinfo=eastern),
        )
        self.assertIn("2026-04-01T13:30:00+00:00", manifest.as_dict()["generated_at"])

    def test_two_manifests_of_one_document_differ_only_in_time(self):
        """Which is the separation working: the document is not the event."""
        first = manifest_for(self.html, case_name=CASE, transaction_count=1)
        second = manifest_for(
            self.html,
            case_name=CASE,
            transaction_count=1,
            generated_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(first.document_sha256, second.document_sha256)
        differing = {
            field
            for field in first.as_dict()
            if first.as_dict()[field] != second.as_dict()[field]
        }
        self.assertEqual(differing, {"generated_at"})

    def test_a_bool_transaction_count_is_refused(self):
        """``True`` is an ``int``, and a flag where a count belongs is a bug."""
        for value in (True, False):
            with self.subTest(value=value):
                with self.assertRaises(ExportManifestError):
                    manifest_for(self.html, case_name=CASE, transaction_count=value)

    def test_a_negative_count_is_refused(self):
        with self.assertRaises(ExportManifestError):
            manifest_for(self.html, case_name=CASE, transaction_count=-1)

    def test_bytes_are_refused_where_the_document_belongs(self):
        """Encoding twice would digest a different thing without complaining."""
        with self.assertRaises(ExportManifestError):
            document_digest(self.html.encode("utf-8"))

    def test_the_manifest_cannot_be_edited_after_the_fact(self):
        manifest = manifest_for(self.html, case_name=CASE, transaction_count=1)
        with self.assertRaises(Exception):
            manifest.document_sha256 = "0" * 64

    def test_the_serialised_form_is_stable(self):
        """A manifest that serialised differently per run would need a manifest."""
        manifest = manifest_for(
            self.html,
            case_name=CASE,
            transaction_count=1,
            generated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(manifest.to_json(), manifest.to_json())
        # Keys in sorted order and no incidental whitespace, asserted concretely
        # rather than by re-sorting the output, which could not disagree with it.
        self.assertTrue(manifest.to_json().startswith('{"byte_count":'))
        self.assertNotIn(", ", manifest.to_json())
        self.assertEqual(
            list(json.loads(manifest.to_json())),
            sorted(json.loads(manifest.to_json())),
        )

    def test_the_code_version_is_recorded(self):
        """So that a digest change can be attributed to a release, not to figures."""
        manifest = manifest_for(self.html, case_name=CASE, transaction_count=1)
        self.assertTrue(manifest.code_version)
        self.assertNotEqual(manifest.code_version, "")

    def test_the_code_version_is_the_running_one(self):
        """A version stamped from a literal would agree with itself forever.

        Which is the failure this field exists to prevent: a manifest whose
        recorded version cannot distinguish the build that made it from the
        build reading it explains nothing about a digest that has moved.
        """
        manifest = manifest_for(self.html, case_name=CASE, transaction_count=1)
        self.assertEqual(manifest.code_version, code_version())

    def test_the_declared_constants_are_pinned(self):
        """These two strings are promises made to documents already archived.

        Asserted as literals rather than against the constants they name, which
        is a comparison that cannot fail.  ``digest_covers`` is the sentence a
        recipient acts on -- it tells them to hash the HTML and not the PDF they
        may be holding -- so it saying the wrong thing is worse than it being
        absent.  ``schema`` is what lets a manifest written today be parsed by
        code shipped later, so changing it is a deliberate migration, never a
        side effect of an edit.
        """
        self.assertEqual(DIGEST_COVERS_HTML, "export_html")
        self.assertEqual(MANIFEST_SCHEMA, "loupe.financial.export_manifest/1")

    def test_as_dict_carries_every_field(self):
        """The serialised form is the manifest; a field it omits is a field lost.

        Tied to ``fields()`` rather than to a written-out list, so that adding a
        field to the dataclass without adding it to the payload fails here
        instead of shipping a manifest that is silently missing it.
        """
        manifest = manifest_for(
            self.html,
            case_name=CASE,
            filters_description=FILTERS,
            transaction_count=3,
            generated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        payload = manifest.as_dict()

        self.assertEqual(set(payload), {f.name for f in fields(manifest)})
        self.assertEqual(payload["schema"], MANIFEST_SCHEMA)
        self.assertEqual(payload["digest_covers"], DIGEST_COVERS_HTML)
        self.assertEqual(payload["document_sha256"], document_digest(self.html))
        self.assertEqual(payload["byte_count"], len(self.html.encode("utf-8")))
        self.assertEqual(payload["case_name"], CASE)
        self.assertEqual(payload["filters_description"], FILTERS)
        self.assertEqual(payload["transaction_count"], 3)
        self.assertEqual(payload["code_version"], code_version())
        self.assertEqual(payload["generated_at"], "2026-04-01T00:00:00+00:00")

    def test_a_zone_that_cannot_state_its_offset_is_refused(self):
        """A named zone with no offset is as unusable as no zone at all.

        ``tzinfo`` being present is not the property that matters; being able to
        place the moment on a line is.  The base ``tzinfo`` returns ``None`` from
        ``utcoffset``, so this is reachable by anyone who subclasses it and
        implements only ``tzname`` -- and the resulting manifest would carry a
        timestamp that ``astimezone`` cannot convert.
        """
        with self.assertRaises(ExportManifestError):
            manifest_for(
                self.html,
                case_name=CASE,
                transaction_count=1,
                generated_at=datetime(2026, 4, 1, tzinfo=_ZoneWithoutOffset()),
            )

    def test_a_negative_byte_count_is_refused(self):
        """Unreachable through ``manifest_for``, which is why it is asserted here.

        ``byte_count`` is computed from the document today, but the manifest is
        also the thing a replay reconstructs from an archive, and a stored
        record can carry anything.
        """
        with self.assertRaises(ExportManifestError):
            ExportManifest(
                schema=MANIFEST_SCHEMA,
                document_sha256="0" * 64,
                digest_covers=DIGEST_COVERS_HTML,
                byte_count=-1,
                generated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                case_name=CASE,
                filters_description="",
                transaction_count=0,
                code_version="1.0.0",
            )


class DigestTests(unittest.TestCase):
    """The digest itself, pinned to a literal.

    Unlike the rendered HTML, *this* derivation must never move: a manifest
    archived today has to be checkable by code shipped years from now.  The
    expected value is written out rather than computed, because a value derived
    from the code at test time cannot contradict the code.
    """

    EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ASCII = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_the_empty_document(self):
        self.assertEqual(document_digest(""), self.EMPTY)

    def test_a_known_ascii_document(self):
        self.assertEqual(document_digest("hello"), self.ASCII)

    def test_the_encoding_is_utf_8_and_not_the_platform_default(self):
        """Otherwise the digest is a property of the machine as well.

        Asserted against the encoding rather than a literal, so this test says
        what it means: a digest taken under latin-1 would differ here.
        """
        import hashlib

        text = "Sécurité"
        self.assertEqual(
            document_digest(text),
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        self.assertNotEqual(
            document_digest(text),
            hashlib.sha256(text.encode("latin-1")).hexdigest(),
        )


class RenderedExportTests(unittest.TestCase):
    """What the caller actually receives."""

    def test_the_render_carries_its_own_manifest(self):
        rendered = render_financial_export([transaction()], CASE, FILTERS)
        self.assertIsInstance(rendered["manifest"], ExportManifest)

    def test_the_manifest_describes_the_html_even_when_a_pdf_is_returned(self):
        """The digest's scope does not change with the delivery format.

        Where weasyprint is installed the ``content`` is PDF bytes whose digest
        is not the manifest's; ``digest_covers`` is how a recipient learns that
        without experimenting.
        """
        rendered = render_financial_export([transaction()], CASE, FILTERS)
        manifest = rendered["manifest"]
        self.assertEqual(manifest.digest_covers, DIGEST_COVERS_HTML)
        html = build_financial_export_html(
            transactions=[transaction()], case_name=CASE, filters_description=FILTERS
        )
        self.assertTrue(describes(manifest, html))

    def test_the_existing_keys_are_unchanged(self):
        """The router reads three keys and must keep working untouched."""
        rendered = render_financial_export([transaction()], CASE, FILTERS)
        self.assertLessEqual(
            {"content", "media_type", "extension"}, set(rendered)
        )
        self.assertIsInstance(rendered["content"], bytes)

    def test_the_count_is_of_the_rows_in_the_document(self):
        """Not of the rows handed in, when the two differ."""
        rows = [transaction("k"), transaction("k", name="same key again")]
        rendered = render_financial_export(rows, CASE, FILTERS)
        self.assertEqual(rendered["manifest"].transaction_count, 1)
        self.assertIn(">1<", rendered["content"].decode("utf-8"))

    def test_two_renders_produce_equal_digests(self):
        first = render_financial_export([transaction()], CASE, FILTERS)["manifest"]
        second = render_financial_export([transaction()], CASE, FILTERS)["manifest"]
        self.assertEqual(first.document_sha256, second.document_sha256)


if __name__ == "__main__":
    unittest.main()
