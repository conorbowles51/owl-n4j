"""Tests for the pre-processing check that says which uploads are bank files.

The check is the road, not the backstop.  ``app.pipeline.financial_route`` in
the evidence engine stops a bank file that reached the document pipeline
anyway; this answers the question early enough that nobody has to be stopped.
Because it is the road, its failure modes are all quiet ones, and the tests are
organised around them rather than around the functions.

The four silent failures this module exists to catch
----------------------------------------------------

*A bank file reported as ordinary.*  The whole point, inverted.  Held by the
per-format tests and by the ambiguity test, which also pins that a file two
formats claim is never reported as one of them.

*A file nobody could classify reported as ordinary.*  Worse than the first,
because it looks like a considered answer.  An unreadable path, a directory, a
missing stored path and a detector that raises must all come back distinguishable
from ``not_native`` and must all block.  ``BLOCKING_OUTCOMES`` is asserted
against the full set of outcomes so that a new one cannot be added without
landing on a side of that line.

*A file dropped rather than answered.*  An interface that asks about five files
and gets three back shows a clean bill of health for the two it never heard
about.  Every requested id comes back, in order, including ids that are not in
the case.

*A file from another case answered.*  The check reads paths and file names, so
being able to ask about an arbitrary id would leak both.  A file in another
case and a file that does not exist are asserted to be byte-identical answers
apart from the echoed id.

Why the endpoint is tested statically
-------------------------------------

``routers.evidence`` imports ``routers.auth``, which imports ``jose``, which is
not installed in every environment this suite runs in -- the same reason the
suite already reports one collection error.  The endpoint's syntax tree is
readable without importing it, so the four properties that would be silent if
wrong are pinned that way.  Weaker than an executed assertion, and stronger
than the nothing that is otherwise available: the permission tuple, the batch
cap, the resolver it hands to the service and the re-raise its neighbour omits
would each be wrong in a way no other test in this repository would notice.

The fixtures are imported from the parser suites rather than restated, for the
reason ``test_financial_native`` gives: a second copy of a file layout drifts
from the first the moment either changes, and the two then disagree silently.
"""

from __future__ import annotations

import ast
import json
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from services.financial import native
from services.financial.native import NativeFormat
from services.financial.route_check import (
    BLOCKING_OUTCOMES,
    FileRouteCheck,
    check_case_files,
    check_head,
    check_path,
    summarise,
)

# The parser suites' own fixture builders.  See the module docstring.
from tests.test_financial_camt053 import build as camt_build, ntry, stmt
from tests.test_financial_native import (
    NACHA_SIMPLE,
    bai2_bytes,
    camt_bytes,
    mt940_bytes,
    nacha_bytes,
)

TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
]

#: One file of each format the ledger reads exactly.
NATIVE_FILES = {
    "camt053": camt_bytes(),
    "bai2": bai2_bytes(),
    "mt940": mt940_bytes(),
    "nacha": nacha_bytes(NACHA_SIMPLE),
}

#: Claimed by camt.053 and by MT940 at once.  Restated rather than imported
#: because in ``test_financial_native`` it is a local inside the test that owns
#: it; ``test_the_contrived_file_is_still_ambiguous`` below makes the copy
#: self-checking, so a backend change that ended the ambiguity would fail here
#: rather than quietly turn every ambiguity test in this module vacuous.
CONTRIVED_AMBIGUOUS = (
    b'<?xml version="1.0"?>'
    b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
    b"<BkToCstmrStmt><Nrtv>{4:</Nrtv></BkToCstmrStmt></Document>"
)

#: Something the document pipeline is the right home for.
ORDINARY_DOCUMENT = (
    b"MEMORANDUM\n\nTo: file\nRe: retainer\n\n"
    b"Enclosed please find the executed engagement letter.\n"
)

#: Every outcome the service can return.  Written out so that adding one to the
#: service without deciding whether it blocks fails ``test_every_outcome_is_on_
#: one_side_of_the_blocking_line``.
ALL_OUTCOMES = frozenset(
    {"native", "ambiguous", "not_native", "unreadable", "undetermined", "not_found"}
)


def route_check_source_tree() -> ast.Module:
    path = Path(__file__).resolve().parent.parent / "routers" / "evidence.py"
    return ast.parse(path.read_text(encoding="utf-8"))


def endpoint_tree() -> ast.AsyncFunctionDef:
    """The check endpoint's own syntax tree, found by name."""
    for node in ast.walk(route_check_source_tree()):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "check_evidence_financial_route"
        ):
            return node
    raise AssertionError("routers.evidence has no check_evidence_financial_route")


# ---------------------------------------------------------------------------
# What the four formats look like
# ---------------------------------------------------------------------------


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self._directory = Path(tempfile.mkdtemp(prefix="loupe-route-check-"))

    def tearDown(self):
        shutil.rmtree(self._directory, ignore_errors=True)

    def written(self, data: bytes, name: str = "statement") -> Path:
        path = self._directory / name
        path.write_bytes(data)
        return path

    def check(self, data: bytes, name: str = "statement") -> FileRouteCheck:
        return check_path(self.written(data, name), file_id="F", file_name=name)

    def test_each_native_format_is_recognised(self):
        """One claimant, and the file is exclusively that format.

        ``is_ambiguous`` is asserted here rather than only against the contrived
        file because ``outcome`` answers "native" without ever consulting it, so
        a property that called a single claimant ambiguous would go unnoticed by
        every other test in this module.  The interface reads the two
        separately, and "native, and also ambiguous" is a state it cannot show.
        """
        for expected, data in sorted(NATIVE_FILES.items()):
            with self.subTest(format=expected):
                check = self.check(data, f"{expected}.dat")
                self.assertTrue(check.is_native)
                self.assertFalse(check.is_ambiguous)
                self.assertEqual(check.detected_format, expected)
                self.assertEqual(check.outcome, "native")
                self.assertEqual(check.claimants, (expected,))
                self.assertTrue(check.blocks_document_processing)
                self.assertIsNone(check.reason)

    def test_the_contrived_file_is_still_ambiguous(self):
        """The copied fixture still does what it was copied for.

        Without this, a backend change that ended the ambiguity would leave
        every ambiguity assertion below passing against a file that is simply
        camt.053, and the interface's ambiguity path would go untested in
        silence.
        """
        self.assertEqual(
            native.sniff(CONTRIVED_AMBIGUOUS),
            (NativeFormat.camt053, NativeFormat.mt940),
        )

    def test_a_file_two_formats_claim_is_not_reported_as_either(self):
        """Ambiguity is an answer about the file, not a tie to break.

        Reporting the first claimant would make the format a property of the
        order ``NativeFormat`` happens to declare its members in, and the
        interface would offer the ledger route for a file ``read_native``
        refuses outright.
        """
        check = self.check(CONTRIVED_AMBIGUOUS, "contrived.xml")
        self.assertTrue(check.is_ambiguous)
        self.assertFalse(check.is_native)
        self.assertIsNone(check.detected_format)
        self.assertEqual(check.outcome, "ambiguous")
        self.assertEqual(check.claimants, ("camt053", "mt940"))
        self.assertTrue(check.blocks_document_processing)

    def test_an_ordinary_document_is_left_alone(self):
        check = self.check(ORDINARY_DOCUMENT, "memo.txt")
        self.assertEqual(check.outcome, "not_native")
        self.assertEqual(check.claimants, ())
        self.assertIsNone(check.detected_format)
        self.assertFalse(check.blocks_document_processing)
        self.assertIsNone(check.reason)

    def test_an_empty_file_is_left_alone(self):
        """Nothing claims nothing, and the document pipeline says so better.

        An empty upload is a real thing that happens, and refusing it here
        would replace the extractor's accurate complaint with a routing
        decision that explains nothing.
        """
        check = self.check(b"", "empty.dat")
        self.assertEqual(check.outcome, "not_native")
        self.assertFalse(check.blocks_document_processing)

    def test_check_head_matches_the_detector(self):
        for expected, data in sorted(NATIVE_FILES.items()):
            with self.subTest(format=expected):
                claimants, error = check_head(data)
                self.assertIsNone(error)
                self.assertEqual(
                    claimants, tuple(fmt.value for fmt in native.sniff(data))
                )


# ---------------------------------------------------------------------------
# Reading no more than the window
# ---------------------------------------------------------------------------


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self._directory = Path(tempfile.mkdtemp(prefix="loupe-route-read-"))

    def tearDown(self):
        shutil.rmtree(self._directory, ignore_errors=True)

    def written(self, data: bytes, name: str = "statement") -> Path:
        path = self._directory / name
        path.write_bytes(data)
        return path

    def test_a_prefix_read_matches_the_whole_file(self):
        """The claim :func:`check_path` makes in its own docstring.

        The size assertion is not decoration.  Every other fixture in this
        module is smaller than the sniff window, so against any of them a
        prefix read and a whole-file read are the same bytes and this test
        could not fail however the reading was done.
        """
        entries = "".join(
            ntry("100.0%d" % (index % 10), reference="REF-%d" % index)
            for index in range(40)
        )
        long_file = camt_build(statements=stmt(entries=entries))
        self.assertGreater(len(long_file), native.SNIFF_BYTES)

        check = check_path(
            self.written(long_file, "long.xml"), file_id="F", file_name="long.xml"
        )
        self.assertEqual(
            check.claimants, tuple(fmt.value for fmt in native.sniff(long_file))
        )
        self.assertEqual(check.detected_format, "camt053")

    def test_no_more_than_the_sniff_window_is_read(self):
        """A year of a busy account is not pulled into memory to be classified.

        Asserted on the read itself rather than on the answer, because the
        answer is identical either way -- which is exactly why a regression to
        ``handle.read()`` would be invisible without this.  Fifty of those in
        one request is the difference between a cheap question and an outage.
        """
        requested: list[int] = []
        real_open = open

        class Recording:
            """A handle that remembers how much was asked of it."""

            def __init__(self, handle):
                self._handle = handle

            def read(self, size=-1):
                requested.append(size)
                return self._handle.read(size)

            def __enter__(self):
                return self

            def __exit__(self, *exception):
                return self._handle.__exit__(*exception)

        path = self.written(NATIVE_FILES["camt053"], "camt.xml")
        with mock.patch(
            "services.financial.route_check.open",
            lambda p, m="r", *a, **k: Recording(real_open(p, m, *a, **k)),
            create=True,
        ):
            check_path(path, file_id="F", file_name="camt.xml")
        self.assertEqual(requested, [native.SNIFF_BYTES])

    def test_a_file_that_is_not_there_blocks_rather_than_passing(self):
        """"Could not look" must never read as "looked, and it is ordinary"."""
        check = check_path(
            self._directory / "absent.dat", file_id="F", file_name="absent.dat"
        )
        self.assertEqual(check.outcome, "unreadable")
        self.assertTrue(check.blocks_document_processing)
        self.assertIn("FileNotFoundError", check.reason)

    def test_a_directory_blocks_rather_than_passing(self):
        directory = self._directory / "folder"
        directory.mkdir()
        check = check_path(directory, file_id="F", file_name="folder")
        self.assertEqual(check.outcome, "unreadable")
        self.assertTrue(check.blocks_document_processing)

    def test_a_file_with_no_stored_path_blocks_rather_than_passing(self):
        """``stored_path`` is NOT NULL, so this is the resolver returning None.

        Which it does whenever the recorded layout does not exist in this
        process -- a container reading a path the host wrote.  Treating that as
        "ordinary document" would send every file of a mis-mounted deployment
        to the model, which is the failure this whole check exists to prevent,
        applied to everything at once.
        """
        check = check_path(None, file_id="F", file_name="unmapped.dat")
        self.assertEqual(check.outcome, "unreadable")
        self.assertTrue(check.blocks_document_processing)
        self.assertEqual(check.reason, "the file has no stored path")


# ---------------------------------------------------------------------------
# A detector that will not answer
# ---------------------------------------------------------------------------


class DetectorFaultTests(unittest.TestCase):
    def setUp(self):
        self._directory = Path(tempfile.mkdtemp(prefix="loupe-route-fault-"))

    def tearDown(self):
        shutil.rmtree(self._directory, ignore_errors=True)

    def test_a_raising_detector_is_undetermined_not_ordinary(self):
        """The bytes were read and no answer came back, and that is not a pass.

        ``undetermined`` is the one word this module and the engine's
        ``FinancialRoute`` spell differently for the same condition; the engine
        says ``detector_unavailable`` because on that side the usual cause is a
        missing import.  What both must share is that neither is a green light,
        and that is what is asserted here.
        """
        path = self._directory / "camt.xml"
        path.write_bytes(NATIVE_FILES["camt053"])
        with mock.patch.object(native, "sniff", side_effect=RuntimeError("boom")):
            # Asserted as well as silenced.  The response says only that the
            # file could not be classified; the traceback that says why exists
            # once, in the log, and a swallowed exception with no record of it
            # is the kind of fault that is diagnosed by guesswork.
            with self.assertLogs("services.financial.route_check", level="ERROR"):
                check = check_path(path, file_id="F", file_name="camt.xml")
        self.assertEqual(check.outcome, "undetermined")
        self.assertTrue(check.blocks_document_processing)
        self.assertFalse(check.is_native)
        self.assertEqual(check.claimants, ())
        self.assertIn("RuntimeError", check.reason)
        self.assertIn("boom", check.reason)

    def test_check_head_reports_the_fault_rather_than_raising(self):
        """One unclassifiable file must not fail the check for the other forty-nine."""
        with mock.patch.object(native, "sniff", side_effect=ValueError("nope")):
            with self.assertLogs("services.financial.route_check", level="ERROR"):
                claimants, error = check_head(b"anything")
        self.assertEqual(claimants, ())
        self.assertIn("ValueError", error)


# ---------------------------------------------------------------------------
# Which files a caller is allowed to ask about
# ---------------------------------------------------------------------------


class CaseScopingTests(unittest.TestCase):
    """Two cases, so that scoping is tested against a populated neighbour.

    A single-case fixture would pass with no filtering at all, because there
    would be nothing to leak.

    The database is a file on disk rather than ``:memory:``, matching
    ``test_financial_native_ingest``: the service takes a session from its
    caller today, and a suite that shares one connection with it would stop
    reflecting production the moment it opened one of its own.
    """

    def setUp(self):
        self._directory = Path(tempfile.mkdtemp(prefix="loupe-route-scope-"))
        self.engine = create_engine(
            f"sqlite+pysqlite:///{self._directory / 'evidence.db'}", future=True
        )

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )
        self.db = self.SessionLocal()

        self.user = User(
            id=uuid.uuid4(),
            email="investigator@example.test",
            name="Investigator",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid.uuid4(),
            title="Route Check Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid.uuid4(),
            title="Somebody Else's Matter",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case, self.other_case])
        self.db.commit()
        self._files = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- helpers ------------------------------------------------------------

    def evidence(self, data: bytes, *, case=None, name: str = None) -> EvidenceFile:
        self._files += 1
        name = name or f"upload-{self._files}.dat"
        path = self._directory / name
        path.write_bytes(data)
        record = EvidenceFile(
            id=uuid.uuid4(),
            case_id=(case or self.case).id,
            original_filename=name,
            stored_path=str(path),
            sha256=f"{self._files:064d}",
        )
        self.db.add(record)
        self.db.commit()
        return record

    def check(self, file_ids):
        return check_case_files(
            self.db,
            case_id=self.case.id,
            file_ids=file_ids,
            resolve_path=lambda stored: Path(stored) if stored else None,
        )

    # -- tests --------------------------------------------------------------

    def test_a_bank_file_in_the_case_is_named(self):
        record = self.evidence(NATIVE_FILES["camt053"], name="jan-statement.xml")
        (check,) = self.check([record.id])
        self.assertEqual(check.outcome, "native")
        self.assertEqual(check.detected_format, "camt053")
        self.assertEqual(check.file_id, str(record.id))
        self.assertEqual(check.file_name, "jan-statement.xml")

    def test_every_requested_id_comes_back(self):
        """Silence about a file is the failure this check exists to end.

        Three answers to a five-file question would show the interface a clean
        result for two files nothing ever looked at.
        """
        records = [
            self.evidence(NATIVE_FILES["bai2"]),
            self.evidence(ORDINARY_DOCUMENT),
            self.evidence(NATIVE_FILES["mt940"]),
        ]
        absent = [uuid.uuid4(), uuid.uuid4()]
        requested = [records[0].id, absent[0], records[1].id, absent[1], records[2].id]

        checks = self.check(requested)
        self.assertEqual([check.file_id for check in checks], [str(i) for i in requested])
        self.assertEqual(
            [check.outcome for check in checks],
            ["native", "not_found", "not_native", "not_found", "native"],
        )

    def test_another_cases_file_is_indistinguishable_from_one_that_does_not_exist(self):
        """Asking must not be a way to learn what is in a case you cannot see.

        The answer carries a file name and is derived from a stored path, so an
        unscoped check would hand both to anyone who could guess a UUID.  The
        two answers are compared whole rather than by outcome alone, because a
        reason or a file name that differed would leak just as much as an
        outcome that did.
        """
        elsewhere = self.evidence(NATIVE_FILES["camt053"], case=self.other_case)
        imaginary = uuid.uuid4()

        leaked, invented = self.check([elsewhere.id, imaginary])
        self.assertEqual(leaked.outcome, "not_found")
        self.assertEqual(
            {k: v for k, v in leaked.as_dict().items() if k != "file_id"},
            {k: v for k, v in invented.as_dict().items() if k != "file_id"},
        )
        self.assertIsNone(leaked.file_name)

    def test_a_missing_file_does_not_block(self):
        """``process/background`` already refuses the whole request over one.

        Counting it as blocking would make the interface interrupt with a
        routing question about a file that is not there, instead of letting the
        process call give the accurate 404.
        """
        (check,) = self.check([uuid.uuid4()])
        self.assertFalse(check.blocks_document_processing)

    def test_a_repeated_id_is_answered_once(self):
        record = self.evidence(NATIVE_FILES["nacha"])
        checks = self.check([record.id, record.id, record.id])
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].outcome, "native")

    def test_no_ids_is_no_answers(self):
        self.assertEqual(self.check([]), [])

    def test_the_resolver_is_what_finds_the_file(self):
        """The stored path is not assumed to be a path in this process.

        The engine writes one layout and the host reads another.  Here the
        stored path exists nowhere and only the resolver knows where the bytes
        are, so a service that opened ``stored_path`` directly fails.
        """
        record = self.evidence(NATIVE_FILES["camt053"], name="real.xml")
        real_path = Path(record.stored_path)
        record.stored_path = "/container/only/never-on-this-host.xml"
        self.db.commit()

        seen: list[str] = []

        def resolve(stored):
            seen.append(stored)
            return real_path

        (check,) = check_case_files(
            self.db,
            case_id=self.case.id,
            file_ids=[record.id],
            resolve_path=resolve,
        )
        self.assertEqual(seen, ["/container/only/never-on-this-host.xml"])
        self.assertEqual(check.outcome, "native")

    def test_a_resolver_that_finds_nothing_blocks(self):
        record = self.evidence(NATIVE_FILES["camt053"])
        (check,) = check_case_files(
            self.db,
            case_id=self.case.id,
            file_ids=[record.id],
            resolve_path=lambda stored: None,
        )
        self.assertEqual(check.outcome, "unreadable")
        self.assertTrue(check.blocks_document_processing)


# ---------------------------------------------------------------------------
# The shape the interface reads
# ---------------------------------------------------------------------------


class ReportShapeTests(unittest.TestCase):
    def every_outcome(self) -> dict[str, FileRouteCheck]:
        """One check per outcome, built directly rather than through the disk.

        Constructed here so that the shape assertions cover outcomes the rest
        of the module reaches only through a filesystem or a patched detector,
        and so that a new outcome missing from ``ALL_OUTCOMES`` is caught.
        """
        return {
            "native": FileRouteCheck(file_id="1", claimants=("camt053",)),
            "ambiguous": FileRouteCheck(file_id="2", claimants=("camt053", "mt940")),
            "not_native": FileRouteCheck(file_id="3"),
            "unreadable": FileRouteCheck(file_id="4", reason="OSError: nope"),
            "undetermined": FileRouteCheck(
                file_id="5", reason="RuntimeError: boom", undetermined=True
            ),
            "not_found": FileRouteCheck(file_id="6", missing=True, reason="no such file"),
        }

    def test_the_fixture_covers_every_outcome(self):
        built = self.every_outcome()
        self.assertEqual(set(built), ALL_OUTCOMES)
        for expected, check in built.items():
            with self.subTest(outcome=expected):
                self.assertEqual(check.outcome, expected)

    def test_every_outcome_is_on_one_side_of_the_blocking_line(self):
        """A new outcome cannot be added without deciding whether it interrupts.

        Left undecided it would default to not blocking, which is the direction
        that loses bank files.
        """
        self.assertTrue(BLOCKING_OUTCOMES.issubset(ALL_OUTCOMES))
        self.assertEqual(
            BLOCKING_OUTCOMES,
            {"native", "ambiguous", "unreadable", "undetermined"},
        )
        for expected, check in self.every_outcome().items():
            with self.subTest(outcome=expected):
                self.assertEqual(
                    check.blocks_document_processing, expected in BLOCKING_OUTCOMES
                )

    def test_the_same_keys_are_written_whatever_happened(self):
        """A key present only on the interesting branch cannot be relied on.

        The interface would have no way to tell a file that was checked and
        found unremarkable from one a build too old to check never looked at.
        """
        shapes = {
            frozenset(check.as_dict()) for check in self.every_outcome().values()
        }
        self.assertEqual(len(shapes), 1)
        self.assertEqual(
            shapes.pop(),
            {
                "file_id",
                "file_name",
                "claimants",
                "detected_format",
                "outcome",
                "blocks_document_processing",
                "reason",
            },
        )

    def test_the_report_is_json_serialisable(self):
        """It is returned from an endpoint, so a tuple in it is a 500."""
        for expected, check in self.every_outcome().items():
            with self.subTest(outcome=expected):
                restored = json.loads(json.dumps(check.as_dict()))
                self.assertEqual(restored["outcome"], expected)
                self.assertIsInstance(restored["claimants"], list)

    def test_the_summary_counts_what_the_checks_say(self):
        summary = summarise(self.every_outcome().values())
        self.assertEqual(summary["checked"], 6)
        self.assertEqual(summary["native"], 1)
        self.assertEqual(summary["blocking"], 4)
        self.assertEqual(summary["outcomes"], {name: 1 for name in ALL_OUTCOMES})

    def test_the_summary_agrees_with_the_checks_about_blocking(self):
        """Computed from the checks, not by re-testing the outcome strings.

        Two copies of the rule would let the badge and the dialog disagree
        about the same file.
        """
        checks = list(self.every_outcome().values())
        self.assertEqual(
            summarise(checks)["blocking"],
            sum(check.blocks_document_processing for check in checks),
        )

    def test_an_empty_summary_is_still_a_summary(self):
        self.assertEqual(
            summarise([]),
            {"checked": 0, "native": 0, "blocking": 0, "outcomes": {}},
        )


# ---------------------------------------------------------------------------
# The endpoint, read rather than called
# ---------------------------------------------------------------------------


class EndpointTests(unittest.TestCase):
    """See the module docstring for why these are static."""

    def test_the_endpoint_exists_and_is_a_post(self):
        node = endpoint_tree()
        paths = [
            decorator.args[0].value
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "post"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ]
        self.assertEqual(paths, ["/route-check"])

    def test_viewing_the_case_is_what_it_asks_for(self):
        """A read, so ``case:view`` -- and not the ``evidence:upload`` that
        ``/process/background`` requires, which would make the cheap question
        need the expensive permission.
        """
        source = ast.unparse(endpoint_tree())
        self.assertIn("required_permission=('case', 'view')", source)
        self.assertIn("check_case_access", source)

    def test_the_batch_is_capped(self):
        """Fifty ids is fifty file reads, and the cap is the one the process
        call already enforces so that a check cannot be asked about a batch
        that could not be processed anyway.

        Asserted as a comparison rather than as the presence of the name.  The
        name appears twice in this endpoint -- once in the guard and once in
        the message that quotes it -- so a substring test stays green while the
        guard itself compares against something else entirely, which is exactly
        the mutation that found this.
        """
        compared_against = [
            comparator.id
            for node in ast.walk(endpoint_tree())
            if isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Gt)
            and ast.unparse(node.left) == "len(request.file_ids)"
            for comparator in node.comparators
            if isinstance(comparator, ast.Name)
        ]
        self.assertEqual(compared_against, ["MAX_BATCH_SIZE"])

    def test_the_router_hands_over_its_own_path_resolver(self):
        """The service has no default for this, and this is why.

        Passing anything else -- or letting the service assume ``stored_path``
        is openable -- reads the wrong layout in a container and reports every
        file unreadable.
        """
        source = ast.unparse(endpoint_tree())
        self.assertIn("resolve_path=_resolve_stored_path", source)

    def test_an_http_error_stays_the_error_it_was(self):
        """The neighbouring endpoint omits this and turns its own 403s into 500s.

        A permission denial arriving as "internal server error" tells the user
        to file a bug about a system that is working correctly.
        """
        handlers = [
            handler
            for node in ast.walk(endpoint_tree())
            if isinstance(node, ast.Try)
            for handler in node.handlers
        ]
        names = [
            handler.type.id
            for handler in handlers
            if isinstance(handler.type, ast.Name)
        ]
        self.assertIn("HTTPException", names)
        self.assertLess(
            names.index("HTTPException"),
            names.index("Exception"),
            "HTTPException must be re-raised before the catch-all",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
