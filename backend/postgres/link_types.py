"""One registry of link target types for every case-building container.

Workspace entries (notes, findings, theories), the Notebook view over them, dossier links and assessment support,
dossier interview evidence and task links all take their allowed target types from here. The database checks, the
routers, the services and the generated TypeScript type (`frontend_v2/src/generated/link-types.ts`, written by
`python -m scripts.generate_link_types`) are derived from these tuples, so a type is added in one place.

Phone types point at records that the phone build (cb-capture, cb-interpret) owns. Each is validated against the
case by a resolver that the phone build registers with `register_phone_resolver`. Until a resolver is registered,
a phone link is refused with `PHONE_TYPE_UNAVAILABLE_MESSAGE`; nothing is stored unchecked.

This module imports nothing from the application so that models, migrations and services can all import it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

CORE_TYPES: tuple[str, ...] = (
    "evidence",
    "graph_entity",
    "dossier",
    "entry",
    "task",
    "deadline",
    "timeline_event",
    "agent_artifact",
    "witness",
)

PHONE_TYPES: tuple[str, ...] = (
    "phone_record",
    "phone_file",
    "phone_thread",
    "phone_identity",
    "phone_extraction",
    "phone_analysis",
    "phone_selection",
    "phone_view",
    "statement_check",
)

# Money (the ledger): an account, a party (a person or business behind accounts) and one ledger row. Each is checked
# against the case by services.financial_link_targets; a pin holds a message, the payment and its statement page.
FINANCIAL_TYPES: tuple[str, ...] = (
    "financial_account",
    "financial_party",
    "financial_transaction",
)

# A quote: one range of a document's stored text (services/evidence_page_text). A type of its own because a container
# holds a target once, and a finding may hold several quotes of one document. The server writes its anchor.
EVIDENCE_TEXT_TYPES: tuple[str, ...] = ("evidence_passage",)

# Old Notebook names that the Notebook still accepts and maps onto the canonical names.
NOTEBOOK_ALIASES: dict[str, str] = {"entity": "graph_entity", "document": "evidence"}

# Per container, in display order. 07 section 6.1 decides which phone types each container takes.
WORKSPACE_TYPES: tuple[str, ...] = CORE_TYPES + PHONE_TYPES + FINANCIAL_TYPES + EVIDENCE_TEXT_TYPES
DOSSIER_TYPES: tuple[str, ...] = (
    "entry",
    "task",
    "evidence",
    "deadline",
    "timeline_event",
    "agent_artifact",
    "graph_entity",
    "dossier",
) + tuple(value for value in PHONE_TYPES if value != "phone_view") + FINANCIAL_TYPES + EVIDENCE_TEXT_TYPES
NOTEBOOK_TYPES: tuple[str, ...] = (
    "entity",
    "evidence",
    "document",
    "timeline_event",
    "agent_artifact",
) + PHONE_TYPES + EVIDENCE_TEXT_TYPES
TASK_TYPES: tuple[str, ...] = ("dossier", "entry", "evidence") + PHONE_TYPES
INTERVIEW_EVIDENCE_TYPES: tuple[str, ...] = (
    "evidence",
    "phone_record",
    "phone_file",
    "phone_analysis",
    "statement_check",
)

CONTAINERS: dict[str, tuple[str, ...]] = {
    "workspace": WORKSPACE_TYPES,
    "dossier": DOSSIER_TYPES,
    "notebook": NOTEBOOK_TYPES,
    "task": TASK_TYPES,
    "interview_evidence": INTERVIEW_EVIDENCE_TYPES,
}

ALL_TYPES: tuple[str, ...] = tuple(dict.fromkeys(value for types in CONTAINERS.values() for value in types))

PHONE_TYPE_UNAVAILABLE_MESSAGE = (
    "Phone links of type {target_type} cannot be added yet: phone records are not loaded in Loupe until the "
    "phone intake is built, so the link could not be checked against this case"
)


def sql_in_check(column: str, types: tuple[str, ...]) -> str:
    """The text of a database check that `column` holds one of `types`."""

    return f"{column} IN (" + ", ".join(f"'{value}'" for value in types) + ")"


def is_financial_type(target_type: str | None) -> bool:
    return target_type in FINANCIAL_TYPES


def is_phone_type(target_type: str | None) -> bool:
    return target_type in PHONE_TYPES


def allowed(container: str, target_type: str | None) -> bool:
    return target_type in CONTAINERS[container]


class LinkTargetError(ValueError):
    """A link target was refused; the message is written for the person who tried to add it."""


class PhoneLinkUnavailable(LinkTargetError):
    """The phone type has no resolver yet."""


@dataclass(frozen=True)
class PhoneTarget:
    """What a resolver confirms about a phone target in a case.

    `mapping_versions` is the mapping version set behind the record at collect time (07 section 6.3). It is stored
    on the link and never rewritten. `members` is the record id list a `phone_selection` freezes.
    """

    label: str | None
    mapping_versions: Mapping[str, Any]
    members: tuple[str, ...] = ()
    metadata: Mapping[str, Any] | None = None
    # For phone_analysis: the frozen snapshot (PHONE_ANALYSIS_SNAPSHOT_FIELDS), set by resolve_phone_target.
    snapshot: Mapping[str, Any] | None = None


# resolver(db, case_id, target_id) -> PhoneTarget, or None when the target is not in that case.
PhoneResolver = Callable[[Any, Any, str], "PhoneTarget | None"]
_RESOLVERS: dict[str, PhoneResolver] = {}


def register_phone_resolver(target_type: str, resolver: PhoneResolver) -> None:
    if target_type not in PHONE_TYPES:
        raise ValueError(f"{target_type} is not a phone link type")
    _RESOLVERS[target_type] = resolver


def unregister_phone_resolver(target_type: str) -> None:
    _RESOLVERS.pop(target_type, None)


def has_phone_resolver(target_type: str) -> bool:
    return target_type in _RESOLVERS


def resolve_phone_target(db: Any, case_id: Any, target_type: str, target_id: str) -> PhoneTarget:
    """Check a phone target against the case. Refuses with a stated reason; never passes a target unchecked."""

    resolver = _RESOLVERS.get(target_type)
    if resolver is None:
        raise PhoneLinkUnavailable(PHONE_TYPE_UNAVAILABLE_MESSAGE.format(target_type=target_type))
    target = resolver(db, case_id, target_id)
    if target is None:
        raise LinkTargetError(f"The phone item {target_id} ({target_type}) was not found in this case")
    if not isinstance(target.mapping_versions, Mapping):
        raise LinkTargetError(f"The phone item {target_id} has no mapping version set; it cannot be linked")
    if target_type == "phone_analysis":
        # A result is linked as the frozen snapshot that produced it; a recompute is a different snapshot id.
        snapshot = (target.metadata or {}).get("snapshot")
        canonical = validate_phone_analysis_snapshot(snapshot)
        if phone_analysis_snapshot_id(canonical) != target_id:
            raise LinkTargetError(f"The phone analysis {target_id} does not match its snapshot; it cannot be linked")
        target = replace(target, snapshot=canonical, mapping_versions=canonical["mapping_versions"])
    return target


def phone_anchor(target: PhoneTarget, source_anchor: Mapping[str, Any] | None) -> dict[str, Any]:
    """The source anchor stored on a phone link: the caller's anchor plus the mapping version set at collect time."""

    anchor = dict(source_anchor or {})
    anchor["mapping_versions"] = dict(target.mapping_versions)
    if target.snapshot is not None:
        anchor["snapshot"] = dict(target.snapshot)
    return anchor


# 07 section 6.4 item 13: a phone_analysis snapshot freezes what produced the result.
PHONE_ANALYSIS_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "kind",
    "subject",
    "window",
    "parameters",
    "mapping_versions",
    "record_ids",
    "summary_counts",
)


def validate_phone_analysis_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Check a phone_analysis snapshot has exactly the frozen shape, and return it in canonical form."""

    if not isinstance(snapshot, Mapping):
        raise LinkTargetError("A phone analysis snapshot must be an object")
    missing = [name for name in PHONE_ANALYSIS_SNAPSHOT_FIELDS if name not in snapshot]
    extra = sorted(set(snapshot) - set(PHONE_ANALYSIS_SNAPSHOT_FIELDS))
    if missing or extra:
        raise LinkTargetError(
            "A phone analysis snapshot needs exactly kind, subject, window, parameters, mapping_versions, "
            f"record_ids and summary_counts (missing: {', '.join(missing) or 'none'}; "
            f"not allowed: {', '.join(extra) or 'none'})"
        )
    if not isinstance(snapshot["kind"], str) or not snapshot["kind"].strip():
        raise LinkTargetError("A phone analysis snapshot needs a kind")
    window = snapshot["window"]
    if not isinstance(window, Mapping) or not {"start", "end"} <= set(window):
        raise LinkTargetError("A phone analysis snapshot window needs a start and an end")
    for name in ("parameters", "mapping_versions", "summary_counts"):
        if not isinstance(snapshot[name], Mapping):
            raise LinkTargetError(f"A phone analysis snapshot {name} must be an object")
    for name, value in snapshot["summary_counts"].items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise LinkTargetError(f"Summary count {name} must be a whole number")
    record_ids = snapshot["record_ids"]
    if not isinstance(record_ids, (list, tuple)) or not all(isinstance(value, str) and value for value in record_ids):
        raise LinkTargetError("A phone analysis snapshot record_ids must be a list of record ids")
    canonical = {name: snapshot[name] for name in PHONE_ANALYSIS_SNAPSHOT_FIELDS}
    canonical["record_ids"] = list(record_ids)
    return canonical


def phone_analysis_snapshot_id(snapshot: Mapping[str, Any]) -> str:
    """A stable id for a snapshot: the same inputs and result give the same id, a recompute that differs does not."""

    canonical = validate_phone_analysis_snapshot(snapshot)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "pa_" + hashlib.sha256(encoded).hexdigest()
