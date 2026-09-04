"""Idempotent Phase 3 Dossier backfill used by Alembic and reconciliation tests."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

import sqlalchemy as sa


MIGRATION_NAMESPACE = uuid.UUID("f508c9ab-9831-4474-923d-121e54b0858c")


def _uuid(source: str) -> uuid.UUID:
    return uuid.uuid5(MIGRATION_NAMESPACE, source)


def _data(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _reflect(connection: sa.Connection, *names: str) -> dict[str, sa.Table]:
    metadata = sa.MetaData()
    return {name: sa.Table(name, metadata, autoload_with=connection) for name in names}


def backfill_dossiers(connection: sa.Connection) -> dict[str, int]:
    """Backfill profiles/witnesses without guessing ambiguous graph identities."""
    tables = _reflect(
        connection,
        "case_profiles",
        "case_profile_graph_node_links",
        "case_profile_evidence_links",
        "case_profile_note_links",
        "case_profile_finding_links",
        "workspace_witnesses",
        "workspace_entry_links",
        "dossier_roles",
        "dossier_links",
        "dossier_assessments",
        "dossier_interviews",
        "dossier_legacy_mappings",
    )
    profiles = tables["case_profiles"]
    graph_links = tables["case_profile_graph_node_links"]
    mappings = tables["dossier_legacy_mappings"]
    now = datetime.now(timezone.utc)

    existing_mappings = {
        (str(row.case_id), row.source_type, row.source_id): row.dossier_id
        for row in connection.execute(sa.select(mappings)).mappings()
    }
    witness_rows = list(connection.execute(sa.select(tables["workspace_witnesses"])).mappings())
    witness_profile_ids = {
        _uuid(f"witness:{row.case_id}:{row.witness_id}") for row in witness_rows
    }
    profile_rows = list(connection.execute(sa.select(profiles)).mappings())
    links_by_profile: dict[uuid.UUID, list[str]] = {}
    for row in connection.execute(sa.select(graph_links)).mappings():
        links_by_profile.setdefault(row.profile_id, []).append(row.node_key)
    single_claims = Counter(
        keys[0]
        for row in profile_rows
        if len(keys := list(dict.fromkeys(links_by_profile.get(row.id, [])))) == 1
        and row.archived_at is None
    )

    counts = Counter()
    for row in profile_rows:
        keys = list(dict.fromkeys(links_by_profile.get(row.id, [])))
        canonical = keys[0] if len(keys) == 1 and (row.archived_at is not None or single_claims[keys[0]] == 1) else None
        review = len(keys) > 1 or (row.archived_at is None and len(keys) == 1 and single_claims[keys[0]] > 1)
        connection.execute(
            profiles.update().where(profiles.c.id == row.id).values(
                canonical_entity_key=canonical,
                linkage_state="linked" if canonical else "unlinked",
                needs_link_review=review,
                graph_entity_deleted=False,
                status=row.status or "active",
            )
        )
        counts["profiles"] += 1
        if review:
            counts["review_items"] += 1
        key = (str(row.case_id), "case_profile", str(row.id))
        if row.id not in witness_profile_ids and row.get("legacy_source") != "workspace_witness" and key not in existing_mappings:
            connection.execute(mappings.insert().values(
                id=_uuid(f"mapping:case_profile:{row.id}"), case_id=row.case_id,
                dossier_id=row.id, source_type="case_profile", source_id=str(row.id),
                migration_metadata={"candidate_graph_keys": keys}, created_at=now, updated_at=now,
            ))
            existing_mappings[key] = row.id

    # Preserve every existing profile relationship in the general Dossier link model.
    link_sources = (
        ("case_profile_evidence_links", "evidence", "evidence_file_id"),
        ("case_profile_note_links", "entry", "workspace_entry_id"),
        ("case_profile_finding_links", "entry", "workspace_entry_id"),
    )
    dossier_links = tables["dossier_links"]
    existing_general = {
        (row.dossier_id, row.target_type, row.target_id)
        for row in connection.execute(sa.select(dossier_links)).mappings()
    }
    for table_name, target_type, id_column in link_sources:
        table = tables[table_name]
        for row in connection.execute(sa.select(table)).mappings():
            target = row.get(id_column)
            if target is None:
                continue
            target_id = str(target)
            key = (row.profile_id, target_type, target_id)
            if key in existing_general:
                continue
            anchor = {}
            if table_name == "case_profile_evidence_links":
                if row.get("page") is not None:
                    anchor["page"] = row.page
                if row.get("excerpt"):
                    anchor["excerpt"] = row.excerpt
            connection.execute(dossier_links.insert().values(
                id=_uuid(f"link:{row.profile_id}:{target_type}:{target_id}"),
                dossier_id=row.profile_id, case_id=row.case_id, target_type=target_type,
                target_id=target_id, relationship_type=row.get("relationship_type"),
                source_anchor=anchor, created_by_user_id=row.get("created_by_user_id"),
                created_at=row.created_at or now, updated_at=row.updated_at or now,
            ))
            existing_general.add(key)
            counts["links"] += 1

    roles = tables["dossier_roles"]
    assessments = tables["dossier_assessments"]
    interviews = tables["dossier_interviews"]
    witness_map: dict[tuple[str, str], uuid.UUID] = {
        (case_id, source_id): dossier_id
        for (case_id, source_type, source_id), dossier_id in existing_mappings.items()
        if source_type == "workspace_witness"
    }
    for witness in witness_rows:
        source_id = str(witness.witness_id)
        map_key = (str(witness.case_id), source_id)
        if map_key in witness_map:
            continue
        payload = _data(witness.data)
        dossier_id = _uuid(f"witness:{witness.case_id}:{source_id}")
        if connection.execute(sa.select(profiles.c.id).where(profiles.c.id == dossier_id)).scalar_one_or_none() is None:
            connection.execute(profiles.insert().values(
                id=dossier_id, case_id=witness.case_id, profile_type="person",
                display_name=_text(payload.get("name")) or f"Legacy witness {source_id}",
                summary=_text(payload.get("statement_summary")),
                importance=None, canonical_entity_key=None, linkage_state="unlinked",
                status=_text(payload.get("status")) or "active", needs_link_review=False,
                graph_entity_deleted=False, legacy_source="workspace_witness", legacy_id=source_id,
                created_by_user_id=None, updated_by_user_id=None, archived_at=None,
                archived_by_user_id=None, created_at=witness.created_at or now,
                updated_at=witness.updated_at or now,
            ))
        else:
            connection.execute(profiles.update().where(profiles.c.id == dossier_id).values(
                legacy_source="workspace_witness", legacy_id=source_id,
            ))
        connection.execute(mappings.insert().values(
            id=_uuid(f"mapping:witness:{witness.case_id}:{source_id}"), case_id=witness.case_id,
            dossier_id=dossier_id, source_type="workspace_witness", source_id=source_id,
            migration_metadata={"legacy_payload_preserved": True},
            created_at=witness.created_at or now, updated_at=witness.updated_at or now,
        ))
        witness_map[map_key] = dossier_id
        counts["witnesses"] += 1

        role_names = [payload.get("role")]
        category = _text(payload.get("category"))
        if category:
            role_names.append(category)
        for role_name in dict.fromkeys(filter(None, (_text(v) for v in role_names))):
            normalized = " ".join(role_name.lower().split())
            connection.execute(roles.insert().values(
                id=_uuid(f"role:{dossier_id}:{normalized}"), dossier_id=dossier_id,
                case_id=witness.case_id, name=role_name, normalized_name=normalized,
                is_builtin=normalized == "witness", template_key="litigation" if normalized in {"friendly", "neutral", "adverse"} else None,
                created_by_user_id=None, created_at=witness.created_at or now, updated_at=witness.updated_at or now,
            ))

        for field, label in (
            ("category", "Legacy classification"), ("status", "Legacy status"),
            ("statement_summary", "Legacy statement summary"), ("risk", "Legacy risk"),
            ("strategy", "Legacy strategy"), ("credibility", "Legacy credibility"),
        ):
            content = _text(payload.get(field))
            if content:
                connection.execute(assessments.insert().values(
                    id=_uuid(f"assessment:{dossier_id}:{field}"), dossier_id=dossier_id,
                    case_id=witness.case_id, category=field.replace("_", " "), content=content,
                    assessment_date=_date(payload.get("updated_at")), author_user_id=None,
                    updated_by_user_id=None, legacy_label=label,
                    created_at=witness.created_at or now, updated_at=witness.updated_at or now,
                ))
        raw_interviews = payload.get("interviews")
        if isinstance(raw_interviews, list):
            for index, raw in enumerate(raw_interviews):
                item = raw if isinstance(raw, dict) else {"statement": raw}
                notes = _text(item.get("working_notes") or item.get("notes") or item.get("statement"))
                connection.execute(interviews.insert().values(
                    id=_uuid(f"interview:{dossier_id}:{index}"), dossier_id=dossier_id,
                    case_id=witness.case_id, interview_date=_datetime(item.get("date")),
                    participants=item.get("participants") if isinstance(item.get("participants"), list) else [],
                    interviewer_user_ids=[], status=_text(item.get("status")) or "legacy",
                    working_notes=notes, created_by_user_id=None, updated_by_user_id=None,
                    created_at=witness.created_at or now, updated_at=witness.updated_at or now,
                ))
                counts["interviews"] += 1

    # Repoint Phase 1 links via the durable witness migration map.
    entry_links = tables["workspace_entry_links"]
    for link in connection.execute(sa.select(entry_links).where(entry_links.c.target_type == "witness")).mappings():
        dossier_id = witness_map.get((str(link.case_id), str(link.target_id)))
        if dossier_id is None:
            continue
        duplicate = connection.execute(sa.select(entry_links.c.id).where(
            entry_links.c.entry_id == link.entry_id,
            entry_links.c.target_type == "dossier",
            entry_links.c.target_id == str(dossier_id),
        )).scalar_one_or_none()
        if duplicate:
            connection.execute(entry_links.delete().where(entry_links.c.id == link.id))
        else:
            connection.execute(entry_links.update().where(entry_links.c.id == link.id).values(
                target_type="dossier", target_id=str(dossier_id),
                target_label=link.target_label or "Migrated witness dossier",
            ))
        counts["entry_links_repointed"] += 1

    return dict(counts)
