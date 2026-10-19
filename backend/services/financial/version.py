"""Identity of the code and rules that produced a financial result.

Every run in the ledger records a ``code_version`` and a ``ruleset_version``.
Those fields are only worth having if they cannot be wrong, so nothing here is
declared by hand: the code version is *derived* from the bytes of the pipeline
that actually ran, and the ruleset version is derived from the rules that were
actually in force.

The distinction matters under examination.  A hand-maintained constant answers
"what did someone remember to type", which is not evidence of anything.  A
fingerprint over the source answers "what code read this statement", and it can
be recomputed by anyone holding the same tree, which is the property that makes
it worth putting in front of a court.

The cost of that choice is honest churn: editing a comment in this package
changes the fingerprint, because the fingerprint is over bytes and a comment is
bytes.  That is the correct trade.  A version that only moves when someone
decides it should is exactly the version that is stale when it matters.

The declared semantic part is retained for humans, so the recorded value reads
as ``1.0.0+ab12cd34ef567890``: the left half says roughly what this is, the
right half says exactly what it was.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

# The human-readable half of the code version.  Bump it for meaning, not for
# accuracy: accuracy is the fingerprint's job, and the fingerprint moves on its
# own whenever the source moves.
PIPELINE_VERSION = "1.0.0"

# How much of the fingerprint is kept.  Sixteen hex characters is 64 bits, which
# is far beyond what is needed to distinguish the builds of one package from one
# another, and it leaves the recorded value short enough to read aloud.
_FINGERPRINT_CHARS = 16

# Marker used when the source cannot be read — a frozen or packaged deployment,
# or a permissions problem.  It is deliberately loud.  Recording a bare
# ``1.0.0`` in that situation would assert a precision that was never
# established, and a version field that is sometimes a measurement and
# sometimes a guess is worse than one that says which it is.
UNVERIFIED = "unverified"

_PACKAGE_ROOT = Path(__file__).resolve().parent

_code_version_cache: str | None = None
_detail_cache: dict[str, str] | None = None


def _source_files() -> list[Path]:
    """Every Python source file that makes up this package, in a stable order.

    The package directory is the unit deliberately.  It is the boundary that
    already exists in the tree, so a new module is included by the act of
    creating it rather than by remembering to add it to a list here — and a
    list that must be remembered is a list that will eventually be wrong.
    """
    files = [
        path
        for path in _PACKAGE_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    return sorted(files, key=lambda path: path.relative_to(_PACKAGE_ROOT).as_posix())


def code_fingerprint_detail() -> dict[str, str]:
    """Per-file digests behind the code version, keyed by relative path.

    The aggregate fingerprint is what gets stored; this is what gets shown when
    someone asks why two runs of "the same" pipeline disagree.  Comparing two
    of these names the file that differs instead of merely proving that one
    does.
    """
    global _detail_cache
    if _detail_cache is not None:
        return dict(_detail_cache)

    detail: dict[str, str] = {}
    for path in _source_files():
        relative = path.relative_to(_PACKAGE_ROOT).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        detail[relative] = digest

    _detail_cache = detail
    return dict(detail)


def code_version() -> str:
    """The version of the pipeline code, derived from its own source.

    Returns ``{PIPELINE_VERSION}+{fingerprint}``, or
    ``{PIPELINE_VERSION}+unverified`` if the source could not be read.  Never
    raises: a run that cannot fingerprint itself must still be recordable, and
    must still say so.
    """
    global _code_version_cache
    if _code_version_cache is not None:
        return _code_version_cache

    try:
        detail = code_fingerprint_detail()
        if not detail:
            raise FileNotFoundError(f"no source files under {_PACKAGE_ROOT}")

        hasher = hashlib.sha256()
        for relative, digest in detail.items():
            # The path is hashed alongside the content so that renaming a file
            # changes the fingerprint.  A rename changes which module runs, so
            # it must not be invisible here.  The null byte cannot occur in a
            # path or a hex digest, so the framing is unambiguous.
            hasher.update(relative.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(digest.encode("ascii"))
            hasher.update(b"\0")
        fingerprint = hasher.hexdigest()[:_FINGERPRINT_CHARS]
    except (OSError, ValueError):
        fingerprint = UNVERIFIED

    _code_version_cache = f"{PIPELINE_VERSION}+{fingerprint}"
    return _code_version_cache


def ruleset_version(ruleset: Mapping[str, Any] | None) -> str | None:
    """The version of a ruleset, derived from the rules themselves.

    ``None`` in gives ``None`` out, recording honestly that no ruleset was in
    force rather than inventing a version for an absence.

    The ruleset must be JSON-canonical.  A value that cannot be serialised
    raises ``TypeError`` rather than being coerced, because a coerced rule is a
    rule whose recorded version no longer identifies it, and silently losing
    the link between a result and the rules that produced it is the specific
    failure this function exists to prevent.
    """
    if ruleset is None:
        return None

    canonical = json.dumps(
        ruleset,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"rules+{digest[:_FINGERPRINT_CHARS]}"


def reset_caches() -> None:
    """Discard memoised fingerprints.

    Only needed by tests that write to the package directory.  The source of a
    running process does not change under it in any deployment this system
    supports, so the caches are otherwise correct for the life of the process.
    """
    global _code_version_cache, _detail_cache
    _code_version_cache = None
    _detail_cache = None
