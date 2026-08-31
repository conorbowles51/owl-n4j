"""The pre-stage that keeps bank files out of the document pipeline.

What is checked here is the wiring, not the detector.  Whether a byte string is
camt.053 is the backend's question and the backend's four parser suites answer
it at length.  The questions that only exist on this side of the service
boundary are narrower, and all four have a silent failure mode:

*Can the detector be reached at all.*  It lives in a sibling package on disk,
not an installed dependency, imported by inserting a path at first use.  A
build where that import fails does not stop; it processes bank files as
documents and says nothing about it in the output.  So the reachability of the
detector is asserted directly, the same way ``test_pdf_table_geometry`` asserts
the reachability of the table reader, and for a worse reason: a missing table
reader costs layout, a missing detector costs the distinction between a figure
that was parsed and a figure that was inferred.

*Whether a decision is recorded when nothing interesting happened.*  A
``financial_route`` key written only on the branch that refuses cannot tell a
run that looked and found an ordinary document from a run of a build that never
looked.  Those want different responses, so both are asserted.

*Whether reading a prefix is the same as reading the file.*  It has to be: the
alternative is loading a year of a busy account into memory before anyone has
decided the file is worth opening.  ``sniff`` truncates to its own window
before looking, so the two are the same answer rather than an approximation --
and ``test_a_prefix_read_matches_the_whole_file`` is what holds them together
against a later change to either side.

*Whether a refused job stops.*  The orchestrator's own failure handling
re-raises, which returns the exception to arq and earns a retry.  A file's
format does not change between attempts, so a raise here would burn workers
forever on a file that is not broken.

That last one is checked statically, by reading the orchestrator's syntax tree
rather than running it.  This module deliberately imports only
``app.pipeline.financial_route``: importing the orchestrator drags in modules
that need a newer interpreter than every supported environment has, and a test
that cannot run proves nothing.  A static assertion about a ``return`` is a
weaker thing than an executed one, but it is not nothing, and the alternative
on this interpreter is no assertion at all.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys

import pytest

from app.pipeline import financial_route

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
ORCHESTRATOR = pathlib.Path(financial_route.__file__).with_name("orchestrator.py")


def _load_backend_fixture(name: str, relative: str):
    """Import one of the backend's parser fixture builders by path.

    By path, and under a private name, because both services have a package
    called ``tests`` and a plain import would find this one.  Built rather than
    restated for the reason the backend's own adapter suite gives: a second
    copy of the NACHA record layout would drift from the first, and the two
    would then disagree silently, which is the worst thing a fixture can do.
    """
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, BACKEND / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


camt = _load_backend_fixture("_route_fx_camt", "tests/test_financial_camt053.py")
bai2 = _load_backend_fixture("_route_fx_bai2", "tests/test_financial_bai2.py")
mt940 = _load_backend_fixture("_route_fx_mt940", "tests/test_financial_mt940.py")
nacha = _load_backend_fixture("_route_fx_nacha", "tests/test_financial_nacha.py")


NATIVE_FILES = {
    "camt053": camt.build(),
    "bai2": bai2.build().encode("utf-8"),
    "mt940": mt940.build().encode("utf-8"),
    "nacha": nacha.joined(
        [
            nacha.file_header(),
            nacha.batch_header(),
            nacha.entry(),
            nacha.batch_control(),
            nacha.file_control(),
        ]
    ).encode("utf-8"),
}

#: A letter.  The thing the document pipeline is for.
A_DOCUMENT = b"Dear Sir,\n\nPlease find enclosed the statements you asked for.\n"

#: Claimed by camt.053 and by MT940 at once, taken verbatim from the backend's
#: own ambiguity test so that the two cannot drift into disagreeing about what
#: ambiguity looks like.
CONTRIVED_AMBIGUOUS = (
    b'<?xml version="1.0"?>'
    b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
    b"<BkToCstmrStmt><Nrtv>{4:</Nrtv></BkToCstmrStmt></Document>"
)


def written(tmp_path, data: bytes, name: str = "statement") -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


@pytest.fixture
def without_detector(monkeypatch):
    """A deployment that cannot see the backend package at all."""
    monkeypatch.setattr(financial_route, "_detector", None)
    monkeypatch.setattr(financial_route, "_detector_attempted", True)
    monkeypatch.setattr(
        financial_route,
        "_detector_failure",
        "ModuleNotFoundError: No module named 'services'",
    )


# ---------------------------------------------------------------------------
# The detector is reachable
# ---------------------------------------------------------------------------


def test_the_backend_detector_is_reachable():
    """If this fails, every other test here still passes -- on the fallback.

    Which is the hazard in full: a build with no detector routes nothing, and
    a bank file processed as a document looks, from the outside, exactly like a
    bank file nobody sent.
    """
    detector = financial_route._load_detector()
    assert detector is not None, financial_route._detector_failure
    assert hasattr(detector, "sniff")
    assert isinstance(detector.SNIFF_BYTES, int)
    assert detector.SNIFF_BYTES > 0


# ---------------------------------------------------------------------------
# What each kind of file does
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expected", sorted(NATIVE_FILES))
def test_each_native_format_is_recognised(tmp_path, expected):
    """One claimant, and the file is exclusively that format.

    ``is_ambiguous`` is asserted here rather than only against the contrived
    file because ``outcome`` answers "native" without ever consulting it -- so
    a property that called a single claimant ambiguous would go unnoticed by
    every other test in this module, and did, until a mutant said so.  The two
    are read separately by the check endpoint and by the interface, where
    "native, and also ambiguous" is a state neither knows how to show.
    """
    route = financial_route.detect_financial_route(
        written(tmp_path, NATIVE_FILES[expected], expected)
    )
    assert route.is_native
    assert not route.is_ambiguous
    assert route.detected_format == expected
    assert route.outcome == "native"
    assert route.claimants == (expected,)


def test_a_document_is_left_to_the_document_pipeline(tmp_path):
    route = financial_route.detect_financial_route(
        written(tmp_path, A_DOCUMENT, "letter.txt")
    )
    assert not route.is_native
    assert not route.is_ambiguous
    assert route.outcome == "not_native"
    assert route.detected_format is None


def test_an_empty_file_is_left_to_the_document_pipeline(tmp_path):
    route = financial_route.detect_financial_route(written(tmp_path, b"", "empty"))
    assert not route.is_native
    assert route.outcome == "not_native"


def test_a_file_two_formats_claim_is_not_refused(tmp_path):
    """Ambiguity is recorded and then let past, which looks wrong and is not.

    Refusing here would be refusing on the grounds that the file belongs to the
    ledger -- but the ledger cannot read it either.  ``read_native`` requires
    exactly one claimant and raises ``AmbiguousFormatError`` on this input, so
    turning the job away would leave the file with no path at all rather than
    with the wrong one.  The document pipeline will make something of it, the
    ambiguity is on the job for whoever looks, and nothing claims the figures
    were parsed.
    """
    route = financial_route.detect_financial_route(
        written(tmp_path, CONTRIVED_AMBIGUOUS, "contrived.xml")
    )
    assert route.is_ambiguous
    assert not route.is_native
    assert route.outcome == "ambiguous"
    assert route.detected_format is None
    assert route.claimants == ("camt053", "mt940")


# ---------------------------------------------------------------------------
# Reading a prefix
# ---------------------------------------------------------------------------


def test_a_prefix_read_matches_the_whole_file(tmp_path):
    """The claim :func:`detect_financial_route` makes in its own docstring.

    The size assertion is not decoration.  Every other fixture in this module
    is smaller than the sniff window, so against any of them a prefix read and
    a whole-file read are the same bytes and this test could not fail however
    the reading was done.
    """
    detector = financial_route._load_detector()
    entries = "".join(
        camt.ntry("100.0%d" % (index % 10), reference="REF-%d" % index)
        for index in range(40)
    )
    long_file = camt.build(statements=camt.stmt(entries=entries))
    assert len(long_file) > detector.SNIFF_BYTES

    route = financial_route.detect_financial_route(
        written(tmp_path, long_file, "long.xml")
    )
    assert route.claimants == tuple(
        fmt.value for fmt in detector.sniff(long_file)
    )
    assert route.detected_format == "camt053"


def test_no_more_than_the_sniff_window_is_read(tmp_path, monkeypatch):
    """A file too large to hold in memory is not held in memory.

    Asserted on the read itself rather than on the answer, because the answer
    is identical either way -- which is exactly why a regression to
    ``handle.read()`` would be invisible without this.
    """
    detector = financial_route._load_detector()
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

    def recording_open(path, mode="r", *args, **kwargs):
        return Recording(real_open(path, mode, *args, **kwargs))

    monkeypatch.setattr(financial_route, "open", recording_open, raising=False)
    financial_route.detect_financial_route(
        written(tmp_path, NATIVE_FILES["camt053"], "camt.xml")
    )
    assert requested == [detector.SNIFF_BYTES]


# ---------------------------------------------------------------------------
# Files that cannot be read, and builds that cannot detect
# ---------------------------------------------------------------------------


def test_a_job_with_no_file_path_is_recorded_and_let_past():
    route = financial_route.detect_financial_route(None)
    assert route.outcome == "unreadable"
    assert route.read_error == "job has no file path"
    assert not route.is_native


def test_a_file_that_will_not_open_is_recorded_and_let_past(tmp_path):
    """Not this stage's failure to report.

    A file the pipeline cannot open fails at extraction with a better message
    than anything here could give, so the route records what it saw and leaves
    the reporting to the stage built for it.
    """
    route = financial_route.detect_financial_route(str(tmp_path / "absent"))
    assert route.outcome == "unreadable"
    assert "FileNotFoundError" in route.read_error
    assert not route.is_native


def test_a_directory_is_recorded_and_let_past(tmp_path):
    route = financial_route.detect_financial_route(str(tmp_path))
    assert route.outcome == "unreadable"
    assert not route.is_native


def test_without_the_detector_nothing_is_routed(tmp_path, without_detector):
    """A camt.053 file, and a build that cannot tell.

    It goes to the document pipeline, because there is nothing else to do with
    it -- but ``detector_available`` is false on the record, so the run that
    could not look is distinguishable afterwards from the run that looked.
    """
    route = financial_route.detect_financial_route(
        written(tmp_path, NATIVE_FILES["camt053"], "camt.xml")
    )
    assert not route.is_native
    assert not route.detector_available
    assert route.outcome == "detector_unavailable"
    assert "ModuleNotFoundError" in route.detector_error


def test_a_detector_that_raises_does_not_route(tmp_path, monkeypatch):
    """A detector that raises is not a router.

    Separated from the unavailable case because they are different faults with
    the same consequence, and a single ``outcome`` covering both would lose the
    difference between a deployment problem and a bug in the sniffer.
    """

    class Exploding:
        SNIFF_BYTES = 4096

        @staticmethod
        def sniff(_head):
            raise RuntimeError("boom")

    monkeypatch.setattr(financial_route, "_detector", Exploding)
    monkeypatch.setattr(financial_route, "_detector_attempted", True)
    route = financial_route.detect_financial_route(
        written(tmp_path, NATIVE_FILES["camt053"], "camt.xml")
    )
    assert not route.is_native
    assert route.outcome == "detector_unavailable"
    assert "RuntimeError: boom" in route.detector_error


# ---------------------------------------------------------------------------
# What is written down
# ---------------------------------------------------------------------------


def test_the_same_keys_are_written_whatever_happened(tmp_path):
    """A key that appears only on the interesting branch answers nothing.

    ``checked`` is what separates "looked, found an ordinary document" from
    "this build has no pre-stage in it", and it is only worth having if it is
    written on the dull branch too.
    """
    native = financial_route.detect_financial_route(
        written(tmp_path, NATIVE_FILES["bai2"], "bai2.txt")
    ).as_state()
    ordinary = financial_route.detect_financial_route(
        written(tmp_path, A_DOCUMENT, "letter.txt")
    ).as_state()

    assert native.keys() == ordinary.keys()
    assert native["checked"] is True and ordinary["checked"] is True
    assert native["outcome"] == "native"
    assert ordinary["outcome"] == "not_native"
    assert native["detected_format"] == "bai2"
    assert ordinary["detected_format"] is None


def test_the_state_holds_every_claimant_not_just_the_first(tmp_path):
    state = financial_route.detect_financial_route(
        written(tmp_path, CONTRIVED_AMBIGUOUS, "contrived.xml")
    ).as_state()
    assert state["claimants"] == ["camt053", "mt940"]
    assert state["detected_format"] is None


def test_the_state_is_json_serialisable(tmp_path):
    """It is going into a JSONB column, so a tuple in it is a failed commit."""
    import json

    for data in (*NATIVE_FILES.values(), A_DOCUMENT, CONTRIVED_AMBIGUOUS):
        state = financial_route.detect_financial_route(
            written(tmp_path, data, "f")
        ).as_state()
        assert json.loads(json.dumps(state)) == state


# ---------------------------------------------------------------------------
# What the person is told
# ---------------------------------------------------------------------------


def test_the_refusal_names_the_format_and_the_next_step(tmp_path):
    route = financial_route.detect_financial_route(
        written(tmp_path, NATIVE_FILES["mt940"], "acct.sta")
    )
    message = financial_route.refusal_message(route, "acct.sta")
    assert "acct.sta" in message
    assert "mt940" in message
    assert "Nothing was changed and nothing was lost" in message
    assert "financial route" in message


def test_the_refusal_reads_without_a_file_name(tmp_path):
    route = financial_route.detect_financial_route(
        written(tmp_path, NATIVE_FILES["nacha"], "ach")
    )
    assert financial_route.refusal_message(route, None).startswith("This file is nacha")


# ---------------------------------------------------------------------------
# How the orchestrator uses it
# ---------------------------------------------------------------------------


def _run_pipeline_tree() -> ast.AST:
    tree = ast.parse(ORCHESTRATOR.read_text())
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and node.name == "run_pipeline"
    )


def test_the_orchestrator_imports_what_it_calls():
    """The cheapest possible check, and it has already been worth having.

    ``financial_route`` was written and wired in before this import existed,
    and nothing in this environment could import the orchestrator to find out.
    """
    tree = ast.parse(ORCHESTRATOR.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert {"detect_financial_route", "refusal_message"} <= imported


def test_the_refused_job_returns_rather_than_raising():
    """Raising would hand the job back to arq, which retries it.

    A file's format is the same on the second attempt as on the first, so the
    retry reaches the same answer and burns a worker to do it.  This is the one
    property of the pre-stage that is invisible until production and cheap to
    reverse by accident, which is why it is asserted even though it can only be
    asserted statically here.
    """
    branch = next(
        node
        for node in ast.walk(_run_pipeline_tree())
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Attribute)
        and node.test.attr == "is_native"
    )
    kinds = [type(node).__name__ for node in ast.walk(branch)]
    assert "Return" in kinds
    assert "Raise" not in kinds


def test_the_route_is_decided_before_the_cost_context_opens():
    """A job about to be turned away leaves no cost record for work nobody did."""
    function = _run_pipeline_tree()
    detection = min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Name) and node.id == "detect_financial_route"
    )
    cost_context = min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Name) and node.id == "ingestion_cost_context"
    )
    assert detection < cost_context
