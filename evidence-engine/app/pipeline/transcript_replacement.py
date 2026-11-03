"""Retire only ledger-backed contributions of superseded audio revisions.

Immutable claims remain available as history. Unprovenanced legacy/manual
material is never inferred to belong to a recording from its filename alone.
"""
from copy import deepcopy
import json
import uuid
from sqlalchemy import select, or_
from app.dependencies import async_session
from app.models.job import EvidenceClaim


def _list(value):
    if isinstance(value, list): return value
    try: return json.loads(value or '[]')
    except (ValueError, TypeError): return []


def _location_key(value):
    return (str(value.get('source_document_id', '')), str(value.get('revision_id', '')))


def prune_properties(properties, retired, retained):
    result = deepcopy(properties)
    ids = set(result.get('source_claim_ids') or [])
    removed = [claim for claim in retired if claim['id'] in ids]
    if not removed: return result
    removed_ids = {claim['id'] for claim in removed}
    remaining_ids = ids - removed_ids
    kept = [claim for claim in retained if claim['id'] in remaining_ids]
    manual = set(result.get('manual_fields') or [])
    old_locations = {_location_key(claim['source_location']) for claim in removed}
    old_quotes = {claim['quote'] for claim in removed}
    retained_quotes = {claim['quote'] for claim in kept}
    old_files = {claim['source_location'].get('source_file') for claim in removed}
    kept_files = {claim['source_location'].get('source_file') for claim in kept}
    locations = [loc for loc in _list(result.get('source_locations')) if _location_key(loc) not in old_locations]
    facts = [fact for fact in _list(result.get('verified_facts')) if
             _location_key(fact.get('source_location') or {}) not in old_locations and
             (fact.get('quote') not in old_quotes or fact.get('quote') in retained_quotes)]
    updates = {'source_claim_ids': sorted(remaining_ids), 'source_locations': json.dumps(locations),
        'source_quotes': [quote for quote in result.get('source_quotes', []) if quote not in old_quotes or quote in retained_quotes],
        'source_files': [name for name in result.get('source_files', []) if name not in old_files or name in kept_files],
        'verified_facts': json.dumps(facts),
        'ai_insights': json.dumps([insight for insight in _list(result.get('ai_insights'))
            if insight.get('source_doc') not in old_files or insight.get('source_doc') in kept_files])}
    # Retire scalar values only when the old ledger explicitly records that
    # value and all remaining contributions are known. Manual fields win.
    if remaining_ids <= {claim['id'] for claim in kept}:
        for claim in removed:
            obj = claim['object_value'] or {}
            for key, value in (obj.get('properties') or {}).items():
                if key.startswith('_') or key in ('id', 'key', 'case_id', 'name', 'aliases') or key in manual:
                    continue
                if result.get(key) == value:
                    alternatives = [(item['object_value'].get('properties') or {}).get(key) for item in kept]
                    updates[key] = next((candidate for candidate in alternatives if candidate is not None), None)
        updates['summary'] = '\n'.join(dict.fromkeys(fact.get('text', '') for fact in facts if fact.get('text')))
        if 'description' not in updates:
            updates['description'] = next((item['object_value'].get('properties', {}).get('description') for item in kept
                if item['object_value'].get('properties', {}).get('description')), '')
        if 'detail' in result:
            updates['detail'] = next((item['object_value'].get('detail') for item in kept if item['object_value'].get('detail')), '')
    result.update({key: value for key, value in updates.items() if key not in manual})
    return result


def _claim(row):
    return {'id': row.id, 'quote': row.quote, 'source_location': row.source_location, 'object_value': row.object_value}


async def load_retired_claims(case_id, audio_revisions):
    if not audio_revisions: return []
    async with async_session() as db:
        rows = await db.scalars(select(EvidenceClaim).where(EvidenceClaim.case_id == uuid.UUID(case_id), or_(
            *( (EvidenceClaim.evidence_file_id == uuid.UUID(evidence_id)) & (EvidenceClaim.revision_id != revision)
                for evidence_id, revision in audio_revisions.items()))))
        return [_claim(row) for row in rows]


async def prune_existing(properties, retired):
    remaining_ids = set(properties.get('source_claim_ids') or []) - {claim['id'] for claim in retired}
    if not remaining_ids: return prune_properties(properties, retired, [])
    async with async_session() as db:
        rows = await db.scalars(select(EvidenceClaim).where(EvidenceClaim.id.in_(remaining_ids)))
        retained = [_claim(row) for row in rows]
    return prune_properties(properties, retired, retained)


async def retire_graph_contributions(tx, case_id, retired):
    """Called under the graph case lock in the replacement write transaction."""
    if not retired: return
    params = {'case_id': case_id, 'claim_ids': [claim['id'] for claim in retired]}
    nodes = await tx.run('''MATCH (n {case_id: $case_id})
        WHERE any(id IN coalesce(n.source_claim_ids, []) WHERE id IN $claim_ids)
        WITH n ORDER BY n.id SET n._audio_projection_sequence=coalesce(n._audio_projection_sequence,0)+1
        RETURN n.id AS id, properties(n) AS props''', params)
    for row in await nodes.data():
        clean = await prune_existing(row['props'], retired)
        await (await tx.run('MATCH (n {case_id:$case_id, id:$id}) SET n = $props',
            {'case_id': case_id, 'id': row['id'], 'props': clean})).consume()
    rels = await tx.run('''MATCH (a {case_id:$case_id})-[r]->(b {case_id:$case_id})
        WHERE any(id IN coalesce(r.source_claim_ids, []) WHERE id IN $claim_ids)
        WITH r ORDER BY elementId(r) SET r._audio_projection_sequence=coalesce(r._audio_projection_sequence,0)+1
        RETURN elementId(r) AS id, properties(r) AS props''', params)
    for row in await rels.data():
        clean = await prune_existing(row['props'], retired)
        if not clean.get('source_claim_ids') and not clean.get('manual_fields'):
            await (await tx.run('MATCH ()-[r]->() WHERE elementId(r)=$id DELETE r', {'id': row['id']})).consume()
        else:
            await (await tx.run('MATCH ()-[r]->() WHERE elementId(r)=$id SET r = $props', {'id': row['id'], 'props': clean})).consume()
