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
    "money_signals": ("1a.1", "bd3641f548e85576"),
    "message_reconciliation": ("2.3", "ffedaf987c223271"),
    "deletion_timeline": ("3.2", "3899f38f95baea84"),
    "relationships": ("11.2", "d2415dadbd83d048"),
    "awareness": ("4.1-groups", "9cedd74c445622e5"),
    "device_users": ("5.2-use", "cd7bf7201f8f4b6b"),
    "typed_words": ("7.1", "ebdc62fe49dc2742"),
    "intent": ("9.1", "3a46cb8858a18271"),
    "common_contacts": ("14.1", "46ee93fe71781001"),
}


def test_every_built_analysis_has_a_recorded_version_and_fingerprint():
    assert sorted(RECORDED) == sorted(BUILT)
    for name in BUILT:
        module = importlib.import_module("services.phone_analysis." + name)
        with open(inspect.getsourcefile(module), "rb") as fh:
            fingerprint = hashlib.sha256(fh.read()).hexdigest()[:16]
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
