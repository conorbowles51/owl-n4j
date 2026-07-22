from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.pipeline.extract_entities import RawEntity, RawRelationship
from app.models.job import EvidenceClaim


@dataclass(frozen=True)
class GroundedClaim:
    id: str
    case_id: str
    evidence_file_id: str
    revision_id: str
    engine_job_id: str
    claim_type: str
    subject_id: str
    predicate: str
    object_value: dict[str, Any]
    quote: str
    source_location: dict[str, Any]
    confidence: float
    status: str = "grounded"


def _claim_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _claim(
    *,
    case_id: str,
    evidence_file_id: str,
    revision_id: str,
    engine_job_id: str,
    claim_type: str,
    subject_id: str,
    predicate: str,
    object_value: dict[str, Any],
    quote: str,
    source_location: dict[str, Any],
    confidence: float,
    status: str = "grounded",
) -> GroundedClaim:
    immutable_payload = {
        "case_id": case_id,
        "evidence_file_id": evidence_file_id,
        "revision_id": revision_id,
        "claim_type": claim_type,
        "subject_id": subject_id,
        "predicate": predicate,
        "object_value": object_value,
        "quote": quote,
        "source_location": source_location,
    }
    return GroundedClaim(
        id=_claim_id(immutable_payload),
        case_id=case_id,
        evidence_file_id=evidence_file_id,
        revision_id=revision_id,
        engine_job_id=engine_job_id,
        claim_type=claim_type,
        subject_id=subject_id,
        predicate=predicate,
        object_value=object_value,
        quote=quote,
        source_location=dict(source_location),
        confidence=confidence,
        status=status,
    )


def _ledger_status(verification_status: Any) -> str:
    return {
        "verified": "verified",
        "rejected": "rejected",
        "uncertain": "uncertain",
        "unreviewed": "unreviewed",
    }.get(str(verification_status or ""), "grounded")


def compile_grounded_claims(
    *,
    entities: list[RawEntity],
    relationships: list[RawRelationship],
    case_id: str,
    evidence_file_id: str,
    revision_id: str,
    engine_job_id: str,
) -> list[GroundedClaim]:
    """Compile grounded model observations into deterministic immutable claims."""
    claims: list[GroundedClaim] = []
    for entity in entities:
        if entity.source_location:
            claims.append(
                _claim(
                    case_id=case_id,
                    evidence_file_id=evidence_file_id,
                    revision_id=revision_id,
                    engine_job_id=engine_job_id,
                    claim_type="entity_mention",
                    subject_id=entity.temp_id,
                    predicate="mentioned_as",
                    object_value={
                        "name": entity.name,
                        "category": entity.category,
                        "specific_type": entity.specific_type,
                        "properties": entity.properties,
                    },
                    quote=entity.source_quote,
                    source_location=entity.source_location,
                    confidence=entity.confidence,
                )
            )

        for fact in entity.verified_facts:
            source_location = fact.get("source_location")
            quote = str(fact.get("quote", "")).strip()
            text = str(fact.get("text", "")).strip()
            if not isinstance(source_location, dict) or not quote or not text:
                continue
            claims.append(
                _claim(
                    case_id=case_id,
                    evidence_file_id=evidence_file_id,
                    revision_id=revision_id,
                    engine_job_id=engine_job_id,
                    claim_type="entity_fact",
                    subject_id=entity.temp_id,
                    predicate="verified_fact",
                    object_value={
                        "text": text,
                        "importance": fact.get("importance", 3),
                        "entity_name": entity.name,
                        "category": entity.category,
                        "specific_type": entity.specific_type,
                        "properties": entity.properties,
                        "verification_reason": fact.get("verification_reason", ""),
                    },
                    quote=quote,
                    source_location=source_location,
                    confidence=entity.confidence,
                    status=_ledger_status(fact.get("verification_status")),
                )
            )

    for relationship in relationships:
        if not relationship.source_location:
            continue
        claims.append(
            _claim(
                case_id=case_id,
                evidence_file_id=evidence_file_id,
                revision_id=revision_id,
                engine_job_id=engine_job_id,
                claim_type="relationship",
                subject_id=relationship.source_entity_id,
                predicate=relationship.type,
                object_value={
                    "target_entity_id": relationship.target_entity_id,
                    "detail": relationship.detail,
                    "properties": relationship.properties,
                    "verification_reason": relationship.verification_reason,
                },
                quote=relationship.source_quote,
                source_location=relationship.source_location,
                confidence=relationship.confidence,
                status=_ledger_status(relationship.verification_status),
            )
        )
    return claims


def rebuild_observations_from_claims(
    claims: list[GroundedClaim],
) -> tuple[list[RawEntity], list[RawRelationship]]:
    """Reconstruct projection inputs from the immutable grounded claim ledger."""
    projectable = [
        claim for claim in claims if claim.status in {"grounded", "verified"}
    ]
    entities: dict[tuple[str, str], RawEntity] = {}

    def rebuilt_id(claim: GroundedClaim, subject_id: str) -> str:
        return f"{claim.evidence_file_id}:{subject_id}"

    for claim in projectable:
        if claim.claim_type not in {"entity_mention", "entity_fact"}:
            continue
        key = (claim.evidence_file_id, claim.subject_id)
        obj = claim.object_value
        entity = entities.get(key)
        if entity is None:
            entity = RawEntity(
                temp_id=rebuilt_id(claim, claim.subject_id),
                category=str(obj.get("category") or "Other"),
                specific_type=str(obj.get("specific_type") or obj.get("category") or "Other"),
                name=str(obj.get("name") or obj.get("entity_name") or claim.subject_id),
                properties=dict(obj.get("properties") or {}),
                source_quote=claim.quote if claim.claim_type == "entity_mention" else "",
                confidence=claim.confidence,
                source_file=str(claim.source_location.get("source_file") or ""),
                source_location=(
                    dict(claim.source_location)
                    if claim.claim_type == "entity_mention"
                    else None
                ),
            )
            entities[key] = entity
        entity.confidence = max(entity.confidence, claim.confidence)
        if claim.id not in entity.source_claim_ids:
            entity.source_claim_ids.append(claim.id)
        if claim.claim_type == "entity_fact":
            entity.verified_facts.append(
                {
                    "text": str(obj.get("text") or ""),
                    "quote": claim.quote,
                    "page": claim.source_location.get("page_start"),
                    "importance": obj.get("importance", 3),
                    "source_doc": claim.source_location.get("source_file", ""),
                    "source_location": dict(claim.source_location),
                    "verification_status": (
                        "verified" if claim.status == "verified" else "not_reviewed"
                    ),
                }
            )

    relationships: list[RawRelationship] = []
    for claim in projectable:
        if claim.claim_type != "relationship":
            continue
        target_id = str(claim.object_value.get("target_entity_id") or "")
        relationships.append(
            RawRelationship(
                source_entity_id=rebuilt_id(claim, claim.subject_id),
                target_entity_id=rebuilt_id(claim, target_id),
                type=claim.predicate,
                detail=str(claim.object_value.get("detail") or ""),
                properties=dict(claim.object_value.get("properties") or {}),
                source_quote=claim.quote,
                confidence=claim.confidence,
                source_file=str(claim.source_location.get("source_file") or ""),
                source_location=dict(claim.source_location),
                verification_status=(
                    "verified" if claim.status == "verified" else "not_reviewed"
                ),
                verification_reason=str(
                    claim.object_value.get("verification_reason") or ""
                ),
                source_claim_ids=[claim.id],
            )
        )
    return list(entities.values()), relationships


def attach_claim_ids(
    entities: list[RawEntity],
    relationships: list[RawRelationship],
    claims: list[GroundedClaim],
) -> None:
    """Attach immutable ledger IDs to the observations they will project."""
    entity_claims: dict[str, list[str]] = {}
    relationship_claims: dict[tuple[str, str, str], list[str]] = {}
    for claim in claims:
        if claim.status not in {"grounded", "verified"}:
            continue
        if claim.claim_type in {"entity_mention", "entity_fact"}:
            entity_claims.setdefault(claim.subject_id, []).append(claim.id)
        elif claim.claim_type == "relationship":
            target_id = str(claim.object_value.get("target_entity_id", ""))
            relationship_claims.setdefault(
                (claim.subject_id, claim.predicate, target_id), []
            ).append(claim.id)

    for entity in entities:
        entity.source_claim_ids = list(entity_claims.get(entity.temp_id, []))
    for relationship in relationships:
        relationship.source_claim_ids = list(
            relationship_claims.get(
                (
                    relationship.source_entity_id,
                    relationship.type,
                    relationship.target_entity_id,
                ),
                [],
            )
        )


async def persist_grounded_claims(db: Any, claims: list[GroundedClaim]) -> int:
    """Append immutable claims, ignoring deterministic duplicates on retry."""
    if not claims:
        return 0

    from sqlalchemy.dialects.postgresql import insert

    statement = insert(EvidenceClaim).values(
        [
            {
                "id": claim.id,
                "case_id": uuid.UUID(claim.case_id),
                "evidence_file_id": uuid.UUID(claim.evidence_file_id),
                "revision_id": claim.revision_id,
                "engine_job_id": uuid.UUID(claim.engine_job_id),
                "claim_type": claim.claim_type,
                "subject_id": claim.subject_id,
                "predicate": claim.predicate,
                "object_value": claim.object_value,
                "quote": claim.quote,
                "source_location": claim.source_location,
                "confidence": claim.confidence,
                "status": claim.status,
            }
            for claim in claims
        ]
    )
    statement = statement.on_conflict_do_nothing(index_elements=[EvidenceClaim.id])
    await db.execute(statement)
    return len(claims)
