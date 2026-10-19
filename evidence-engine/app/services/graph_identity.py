"""Indexed, case-scoped identity lookup across supported entity categories."""
from app.ontology import load_ontology

ENTITY_LABELS = tuple(load_ontology().categories)
# Match all supported categories: an investigator may have changed a node's
# category since extraction. Label-specific property indexes remain usable.
ENTITY_LABEL_EXPRESSION = '|'.join('`' + label.replace('`', '``') + '`' for label in ENTITY_LABELS)


async def ensure_identity_indexes():
    from app.services.neo4j_client import execute_write
    await execute_write('CREATE CONSTRAINT ingestion_case_write_lock IF NOT EXISTS FOR (n:IngestionCaseWriteLock) REQUIRE n.case_id IS UNIQUE')
    for label in ENTITY_LABELS:
        escaped = '`' + label.replace('`', '``') + '`'
        await execute_write(f'CREATE INDEX IF NOT EXISTS FOR (n:{escaped}) ON (n.case_id, n.id)')
