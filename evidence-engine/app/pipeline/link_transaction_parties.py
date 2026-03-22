"""
Link Transaction sender/receiver properties to resolved entity nodes.

After entity resolution, Transaction nodes have flat `sender` and `receiver`
string properties but no relationships connecting them to the actual
Person/Organization entities. This module creates SENT_PAYMENT and
RECEIVED_PAYMENT relationships by matching those strings against resolved
entity names and aliases.
"""

import logging
from typing import Any

from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship

logger = logging.getLogger(__name__)


def link_transaction_parties(
    entities: list[ResolvedEntity],
    relationships: list[ResolvedRelationship],
) -> list[ResolvedRelationship]:
    """
    For each Transaction entity with sender/receiver properties, find matching
    entities by name/alias and create SENT_PAYMENT/RECEIVED_PAYMENT relationships.

    Returns the augmented relationships list.
    """
    transactions = [e for e in entities if e.category == "Transaction"]
    if not transactions:
        return relationships

    # Build name → entity id lookup (non-Transaction entities)
    name_to_id: dict[str, str] = {}
    for e in entities:
        if e.category == "Transaction":
            continue
        norm = e.name.strip().lower()
        if norm:
            name_to_id[norm] = e.id
        for alias in e.aliases:
            norm_alias = alias.strip().lower()
            if norm_alias:
                name_to_id.setdefault(norm_alias, e.id)

    # Index existing relationships to avoid duplicates
    existing: set[tuple[str, str, str]] = set()
    for r in relationships:
        existing.add((r.source_entity_id, r.target_entity_id, r.type))

    new_rels: list[ResolvedRelationship] = []

    for tx in transactions:
        sender = tx.properties.get("sender", "")
        receiver = tx.properties.get("receiver", "")

        if sender:
            sender_norm = sender.strip().lower()
            matched_id = name_to_id.get(sender_norm)
            if matched_id:
                key = (matched_id, tx.id, "SENT_PAYMENT")
                if key not in existing:
                    new_rels.append(ResolvedRelationship(
                        source_entity_id=matched_id,
                        target_entity_id=tx.id,
                        type="SENT_PAYMENT",
                        detail=f"{sender} sent payment",
                        confidence=0.85,
                        source_files=tx.source_files,
                    ))
                    existing.add(key)

        if receiver:
            receiver_norm = receiver.strip().lower()
            matched_id = name_to_id.get(receiver_norm)
            if matched_id:
                key = (tx.id, matched_id, "RECEIVED_PAYMENT")
                if key not in existing:
                    new_rels.append(ResolvedRelationship(
                        source_entity_id=tx.id,
                        target_entity_id=matched_id,
                        type="RECEIVED_PAYMENT",
                        detail=f"{receiver} received payment",
                        confidence=0.85,
                        source_files=tx.source_files,
                    ))
                    existing.add(key)

    if new_rels:
        logger.info(
            "Linked %d transaction sender/receiver relationships", len(new_rels)
        )

    return relationships + new_rels
