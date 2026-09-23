"""Rebuild the shared case graph from durable reviewed identity decisions.

The SQL audit chain is the retry source. A killed worker replays the same plan;
one short Neo4j transaction replaces only relationships owned by this projector.
Original graph entities, investigator notes and unrelated relationships survive.
"""
import asyncio
import hashlib
import json
import logging
from threading import Event
from uuid import UUID
from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.financial import FinancialAccount, FinancialTransaction, AdjudicationEvent
from services.financial.account_identity import identity_state
from services.financial.projection import account_key

log = logging.getLogger(__name__)
RELATIONSHIPS = {'holder': 'HOLDS_ACCOUNT', 'controller': 'CONTROLS_ACCOUNT',
    'signatory': 'SIGNATORY_FOR', 'analysis_group': 'GROUPS_ACCOUNT'}


def identity_graph_plan(db, case_id):
    state = identity_state(db, case_id)
    from services.financial.counterparty_parties import payment_party_choices
    state['parties'] = sorted(payment_party_choices(db, case_id=case_id, known_parties=state['parties']).values(), key=lambda p: p['id'])
    indexed = {str(a.id): a for a in db.scalars(select(FinancialAccount).where(FinancialAccount.case_id == case_id))}
    accounts, parties, links, entity_links, account_links, payment_links = [], [], [], [], [], []
    for account in state['accounts']:
        row = indexed[account['id']]
        key = account_key(row.identity_key)
        label = ' · '.join(str(v) for v in (account['holder_as_recorded'], account['institution'], account['identifier_as_printed'], account['currency']) if v) or 'Account reference'
        accounts.append(dict(key=key, name=label, ledger_account_id=account['id'], institution_name=account['institution'],
            canonical_account_id=account['canonical_id'],
            identifier_as_printed=account['identifier_as_printed'], currency=account['currency'],
            financial_identifiers=json.dumps(account['identity_review'].get('identifiers', []), ensure_ascii=False),
            financial_referenced_only=account['referenced_only'], financial_identity_url=f'/cases/{case_id}/financial?view=statements',
            summary='Referenced account — no statement imported.' if account['referenced_only'] else 'Account recorded in Financial. Review ownership and identifiers in Statements & accounts.'))
        if account['canonical_id'] != account['id']:
            account_links.append(dict(key='same-account:' + account['id'], source=key,
                target=account_key(indexed[account['canonical_id']].identity_key)))
        for link in account['relationships']:
            links.append(dict(key=link['id'], source='financial-party:' + link['party']['id'], target=key, type=RELATIONSHIPS[link['role']],
                role=link['role'], basis=link['basis'], source_references=json.dumps(link['sources']),
                effective_from=link['effective_from'], effective_to=link['effective_to']))
        if account['party']:
            links.append(dict(key='legacy:' + account['id'], source='financial-party:' + account['party']['id'], target=key,
                type='GROUPS_ACCOUNT', role='analysis_group', basis='legacy_group', source_references='[]', effective_from=None, effective_to=None))
        for link in account['identity_review'].get('entity_links', []):
            entity_links.append(dict(key='identity:' + link['party_id'] + ':' + link['entity_key'],
                source='financial-party:' + link['party_id'], target=link['entity_key'], basis=json.dumps(account['identity_review'].get('basis', {}))))
    for party in state['parties']:
        parties.append(dict(key='financial-party:' + party['id'], name=party['name'], financial_party_id=party['id'],
            financial_identity_url=f'/cases/{case_id}/financial?view=counterparties',
            summary='Reviewed financial identity. Account-holder, control, signatory and grouping relationships are distinct; inspect dates and evidence on each relationship.'))
    from services.financial.payment_counterparty_link import display_link
    for row in db.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == case_id,
            FinancialTransaction.superseded_by_id.is_(None), FinancialTransaction.ledger_status == 'admitted')
            .order_by(FinancialTransaction.id)):
        identity = display_link(row)
        if not identity:
            continue
        target = ('financial-party:' + identity['id']) if identity['kind'] == 'party' else account_key(indexed[identity['id']].identity_key)
        payment_links.append(dict(key='payment-identity:' + str(row.id), source=row.ref_id, target=target,
            direction=row.direction, recorded_identity=json.dumps(identity, sort_keys=True)))
    revision = hashlib.sha256(json.dumps([state['revision'], payment_links], sort_keys=True).encode()).hexdigest()
    return dict(case_id=str(case_id), revision=revision, accounts=accounts, parties=parties, links=links,
        entity_links=entity_links, account_links=account_links, payment_links=payment_links)


def validate_graph_targets(tx, plan):
    missing = tx.run('''UNWIND $keys AS key OPTIONAL MATCH (n {case_id:$case,key:key})
        WITH key, count(n) AS matches WHERE matches <> 1 RETURN key''',
        keys=list({link['target'] for link in plan['entity_links']}), case=plan['case_id']).data()
    if missing:
        raise ValueError('A connected case entity is missing or ambiguous. Review its financial identity connection.')
    for label, rows in [('FinancialAccount', plan['accounts']), ('FinancialParty', plan['parties'])]:
        collisions = tx.run('''UNWIND $keys AS key OPTIONAL MATCH (n {case_id:$case,key:key})
            WITH key, collect(n) AS nodes WHERE size(nodes)>1 OR any(n IN nodes WHERE NOT $label IN labels(n)) RETURN key''',
            keys=[row['key'] for row in rows], case=plan['case_id'], label=label).data()
        if collisions:
            raise ValueError('An account identity key conflicts with an existing case entity. No graph connections were changed.')


def apply_identity_graph(graph_session, plan):
    case_id, revision = plan['case_id'], plan['revision']
    with graph_session.begin_transaction(timeout=20) as tx:
        validate_graph_targets(tx, plan)
        marker = tx.run('MATCH (m:FinancialIdentitySync {case_id:$case}) RETURN m.revision AS revision', case=case_id).single()
        if marker and marker['revision'] == revision:
            return False
        for label, rows in [('FinancialAccount', plan['accounts']), ('FinancialParty', plan['parties'])]:
            # All labels and relation types come from this module, never user text.
            tx.run(f'''UNWIND $rows AS row
                MERGE (n:{label} {{case_id:$case, key:row.key}})
                ON CREATE SET n.name=row.name
                SET n.name=CASE WHEN n.name IS NULL OR n.name=n.financial_identity_label THEN row.name ELSE n.name END,
                    n.id=coalesce(n.id, row.ledger_account_id, row.financial_party_id),
                    n.financial_identity_label=row.name,
                    n.ledger_account_id=row.ledger_account_id,
                    n.canonical_account_id=row.canonical_account_id,
                    n.financial_party_id=row.financial_party_id,
                    n.institution_name=row.institution_name, n.identifier_as_printed=row.identifier_as_printed,
                    n.currency=row.currency, n.financial_identifiers=row.financial_identifiers,
                    n.financial_referenced_only=row.financial_referenced_only,
                    n.financial_identity_url=row.financial_identity_url,
                    n.financial_identity_summary=row.summary,
                    n.financial_identity_managed=true''', rows=rows, case=case_id).consume()
        for kind in RELATIONSHIPS.values():
            tx.run(f'''MATCH (a {{case_id:$case}})-[r:{kind}]->(b {{case_id:$case}})
                WHERE r.financial_identity_managed=true DELETE r''', case=case_id).consume()
            tx.run(f'''UNWIND $rows AS row
                MATCH (a:FinancialParty {{case_id:$case, key:row.source}}), (b:FinancialAccount {{case_id:$case, key:row.target}})
                MERGE (a)-[r:{kind} {{financial_identity_key:row.key}}]->(b)
                SET r.financial_identity_managed=true, r.case_id=$case, r.reviewed=true, r.role=row.role,
                    r.basis=row.basis, r.source_references=row.source_references,
                    r.effective_from=row.effective_from, r.effective_to=row.effective_to''', rows=[r for r in plan['links'] if r['type'] == kind], case=case_id).consume()
        tx.run('''MATCH (a {case_id:$case})-[r:REVIEWED_SAME_IDENTITY]->(b {case_id:$case})
            WHERE r.financial_identity_managed=true DELETE r''', case=case_id).consume()
        tx.run('''UNWIND $rows AS row MATCH (a:FinancialParty {case_id:$case,key:row.source}), (b {case_id:$case,key:row.target})
            MERGE (a)-[r:REVIEWED_SAME_IDENTITY {financial_identity_key:row.key}]->(b)
            SET r.financial_identity_managed=true, r.case_id=$case, r.basis=row.basis, r.reviewed=true''', rows=plan['entity_links'], case=case_id).consume()
        tx.run('''MATCH ({case_id:$case})-[r:REVIEWED_SAME_ACCOUNT]->({case_id:$case})
            WHERE r.financial_identity_managed=true DELETE r''', case=case_id).consume()
        tx.run('''UNWIND $rows AS row
            MATCH (a:FinancialAccount {case_id:$case,key:row.source}), (b:FinancialAccount {case_id:$case,key:row.target})
            MERGE (a)-[r:REVIEWED_SAME_ACCOUNT {financial_identity_key:row.key}]->(b)
            SET r.financial_identity_managed=true,r.case_id=$case,r.reviewed=true''', rows=plan.get('account_links', []), case=case_id).consume()
        for kind, direction in [('REVIEWED_PAID_BY', 'credit'), ('REVIEWED_PAID_TO', 'debit')]:
            tx.run(f'''MATCH (a {{case_id:$case}})-[r:{kind}]->(b {{case_id:$case}})
                WHERE r.financial_identity_managed=true DELETE r''', case=case_id).consume()
            tx.run(f'''UNWIND $rows AS row
                MATCH (a:FinancialTransaction {{case_id:$case,key:row.source}}), (b {{case_id:$case,key:row.target}})
                MERGE (a)-[r:{kind} {{financial_identity_key:row.key}}]->(b)
                SET r.financial_identity_managed=true,r.case_id=$case,r.reviewed=true,r.recorded_identity=row.recorded_identity''',
                rows=[r for r in plan.get('payment_links', []) if r['direction'] == direction], case=case_id).consume()
        # A source projection may still be catching up. Leave this identity
        # revision pending until its payment nodes exist, so the next sweep retries.
        missing = tx.run('''UNWIND $keys AS key OPTIONAL MATCH (n:FinancialTransaction {case_id:$case,key:key})
            WITH key, count(n) AS matches WHERE matches=0 RETURN key''',
            keys=[r['source'] for r in plan.get('payment_links', [])], case=case_id).data()
        if missing:
            tx.commit()
            return True
        # The marker is hidden from ordinary entity lists by the standard system flag.
        tx.run('''MERGE (m:FinancialIdentitySync {case_id:$case})
            SET m.system_node=true, m.revision=$revision, m.completed_at=datetime()''', case=case_id, revision=revision).consume()
        tx.commit()
        return True


def synchronize_case(case_id):
    from postgres.session import get_background_session
    from services.neo4j_service import neo4j_service
    with get_background_session() as db:
        if db.scalar(select(Case.id).where(Case.id == case_id).with_for_update(skip_locked=True)) is None:
            return False
        plan = identity_graph_plan(db, case_id)
        with neo4j_service.session() as graph:
            return apply_identity_graph(graph, plan)


def identity_graph_status(db, case_id):
    from services.neo4j_service import neo4j_service
    plan = identity_graph_plan(db, case_id)
    expected = plan['revision']
    try:
        with neo4j_service.session() as graph:
            validate_graph_targets(graph, plan)
            row = graph.run('MATCH (m:FinancialIdentitySync {case_id:$case}) RETURN m.revision AS revision, toString(m.completed_at) AS completed_at', case=str(case_id)).single()
        return dict(case_id=str(case_id), status='current' if row and row['revision'] == expected else 'pending', completed_at=row['completed_at'] if row else None)
    except Exception:
        return dict(case_id=str(case_id), status='unavailable', completed_at=None)


def sync_saved_identities(stop=None):
    from postgres.session import get_background_session
    with get_background_session() as db:
        cases = list(db.scalars(select(AdjudicationEvent.case_id).where(AdjudicationEvent.decision.in_(['set_account_party', 'set_account_identity', 'set_counterparty_party'])).distinct()))
    for case_id in cases:
        if stop is not None and stop.is_set():
            break
        try:
            synchronize_case(case_id)
        except Exception:
            log.exception('Reviewed account identity graph will retry for case %s', case_id)


async def run_identity_graph_forever():
    while True:
        stop = Event()
        work = asyncio.create_task(asyncio.to_thread(sync_saved_identities, stop))
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            stop.set()
            await work
            raise
        except Exception:
            log.exception('Reviewed identity graph sweep will retry')
        await asyncio.sleep(30)
