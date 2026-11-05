"""A built analysis whose code changes must decide its VERSION (05 section 3.2: a change of algorithm is a new version).

A run is reused when the case's input, the parameters and the VERSION are equal, so a module changed without a new
VERSION keeps showing the results of its old code on rerun. This test holds each built module's VERSION and a
fingerprint of its source. When the source changes the test fails: bump VERSION if any result, wording stored in a
result, coverage line or count can change, then record the new VERSION and fingerprint here.
"""
from __future__ import annotations

import hashlib
import importlib
import inspect

from services.phone_analysis.approaches import BUILT

RECORDED = {
    "money_signals": ("1a.3", "53fb4a35cf1c7682"),
    "message_reconciliation": ("2.4", "b1a454ab3f40990c"),
    "deletion_timeline": ("3.3", "a20035b3cefc95f2"),
    "relationships": ("11.3", "99a53d9d7ded8624"),
    "awareness": ("4.2-aware", "6fa3a12d0cdd5709"),
    "device_users": ("5.4-graded-use", "7b73667105388270"),
    "typed_words": ("7.3", "e323b05b2b998e4a"),
    "intent": ("9.4", "fea034deb1e463be"),
    "common_contacts": ("14.1", "46ee93fe71781001"),
    "reparse_comparison": ("17.3-3", "d48da93ea48deb92"),
    "contact_matrix": ("15.1", "49cad534aa52a2bf"),
    "number_switching": ("16.2", "a70e7b04ce0370c5"),
    "extraction_comparison": ("12.1", "919fdb03776732f1"),
    "other_devices": ("6.2", "12f2561e59ff2f19"),
    "plans": ("10.4", "ed90ecb590af854e"),
}


def test_every_built_analysis_has_a_recorded_version_and_fingerprint():
    assert sorted(RECORDED) == sorted(BUILT)
    for name in BUILT:
        module = importlib.import_module("services.phone_analysis." + name)
        with open(inspect.getsourcefile(module), "rb") as fh:
            digest = hashlib.sha256(fh.read())
        # a module whose results also depend on a helper module names it in VERSION_SOURCES (money_signals: the
        # 4.3.8 pairing strengths in money_pairings), so a change there also asks for a new VERSION
        for extra in getattr(module, "VERSION_SOURCES", ()):
            with open(inspect.getsourcefile(importlib.import_module("services.phone_analysis." + extra)), "rb") as fh:
                digest.update(fh.read())
        fingerprint = digest.hexdigest()[:16]
        assert (module.VERSION, fingerprint) == RECORDED[name], (
            "%s changed: bump VERSION if its results can change, then record (VERSION, fingerprint) = (%r, %r)"
            % (name, module.VERSION, fingerprint))


def test_every_signal_label_reads_with_exist():
    """The coverage line reads "<label> exist on all N phones" (framework.coverage_sentence), so a label is plural:
    "A known owner exist" was seen on the live screen."""
    for name in BUILT:
        module = importlib.import_module("services.phone_analysis." + name)
        for sig in getattr(module, "SIGNALS", ()):
            assert not sig["label"].startswith(("A ", "An ", "One ")), (name, sig["label"])
