"""Rebuild the shared case graph from durable reviewed identity decisions.

The SQL audit chain is the retry source. A killed worker replays the same plan;
one short Neo4j transaction replaces only relationships owned by this projector.
Original graph entities, investigator notes and unrelated relationships survive.
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import contextmanager
from threading import Event, Lock
from uuid import UUID
from neo4j import Query
from sqlalchemy import or_, select, text
from postgres.models.case import Case
from postgres.models.financial import FinancialAccount, FinancialTransaction, AdjudicationEvent
from services.financial.account_identity import identity_state
from services.financial.projection import account_key

log = logging.getLogger(__name__)
RELATIONSHIPS = {'holder': 'HOLDS_ACCOUNT', 'controller': 'CONTROLS_ACCOUNT',
    'signatory': 'SIGNATORY_FOR', 'analysis_group': 'GROUPS_ACCOUNT'}
GRAPH_TRANSACTION_TIMEOUT = 20
GRAPH_CONNECTION_TIMEOUT = 20
# A case whose payment nodes are not in the graph yet, or whose sync failed, is
# deferred by the sweep with exponential backoff instead of being rewritten every
# round. The ledger projection wakes it early when it draws the payments.
SWEEP_RETRY_BASE_SECONDS = 60
SWEEP_RETRY_CAP_SECONDS = 1800
WAITING_FOR_PAYMENTS = 'waiting_for_payment_nodes'
_deferred = {}
_deferred_lock = Lock()


def sweep_retry_delay(attempts):
    return float(min(SWEEP_RETRY_BASE_SECONDS * (2 ** max(attempts - 1, 0)), SWEEP_RETRY_CAP_SECONDS))


def _defer(case_id, reason, *, missing=0, error=None):
    with _deferred_lock:
        state = _deferred.setdefault(str(case_id), dict(attempts=0, since=time.time()))
        state['attempts'] += 1
        delay = sweep_retry_delay(state['attempts'])
        state.update(reason=reason, missing=missing, error=error, next_due=time.monotonic() + delay)
        return state['attempts'], delay


def _clear_deferral(case_id):
    with _deferred_lock:
        _deferred.pop(str(case_id), None)


def _is_deferred(case_id):
    with _deferred_lock:
        state = _deferred.get(str(case_id))
        return state is not None and time.monotonic() < state['next_due']


def payment_nodes_changed(case_id):
    """Called after the ledger projection redraws a case: retry it on the next sweep."""
    with _deferred_lock:
        state = _deferred.get(str(case_id))
        if state is not None:
            state['next_due'] = 0.0


def sweep_deferral(case_id):
    with _deferred_lock:
        state = _deferred.get(str(case_id))
        if state is None:
            return None
        return dict(reason=state['reason'], attempts=state['attempts'], missing_payment_nodes=state['missing'],
            last_error=state['error'], retry_in_seconds=round(max(state['next_due'] - time.monotonic(), 0.0), 1))


PAYMENT_LINK_CHUNK = 1000


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
    from services.financial.payment_counterparty_link import resolved_link, stored_link
    out_of_case = []
    # Only the columns a payment's identity link is read from: loading every
    # admitted payment of the case whole (with its saved reading) made each
    # snapshot grow with the case, and the sweep takes one per case every 30 s.
    # Read 1,000 rows at a time: fetched in one go, d5b330d1's 27,673 rows held the interpreter lock for 489 ms in
    # the driver, and the sweep runs in a web worker's thread, so that worker's requests waited that long.
    for row_id, ref_id, direction, labels, reviewed in db.execute(select(FinancialTransaction.id,
            FinancialTransaction.ref_id, FinancialTransaction.direction,
            FinancialTransaction.metadata_['investigation_labels'],
            FinancialTransaction.provenance['reviewed_counterparty']).where(FinancialTransaction.case_id == case_id,
            FinancialTransaction.superseded_by_id.is_(None), FinancialTransaction.ledger_status == 'admitted',
            # Only rows that carry a link can give one (stored_link): d5b330d1 has 619 of 27,673.
            or_(FinancialTransaction.metadata_['investigation_labels']['counterparty_link'].isnot(None),
                FinancialTransaction.provenance['reviewed_counterparty'].isnot(None)))
            .order_by(FinancialTransaction.id).execution_options(yield_per=PAYMENT_LINK_CHUNK)):
        identity = resolved_link(db, case_id, stored_link(labels, reviewed))
        if not identity:
            continue
        if identity['kind'] != 'party' and identity['id'] not in indexed:
            # resolved_link returns a link to another case's account unchanged. It cannot be drawn in this
            # case's graph; it is reported (plan, status, log) and the rest of the case is still drawn.
            out_of_case.append(dict(payment_id=str(row_id), ref_id=ref_id, account_id=identity['id']))
            continue
        target = ('financial-party:' + identity['id']) if identity['kind'] == 'party' else account_key(indexed[identity['id']].identity_key)
        payment_links.append(dict(key='payment-identity:' + str(row_id), source=ref_id, target=target,
            direction=direction, recorded_identity=json.dumps(identity, sort_keys=True)))
    revision = hashlib.sha256(json.dumps([state['revision'], payment_links], sort_keys=True).encode()).hexdigest()
    if out_of_case:
        log.warning('Reviewed identity graph for case %s: %s payment link(s) name an account outside the case and '
            'are not drawn (first: payment %s -> account %s)', case_id, len(out_of_case),
            out_of_case[0]['payment_id'], out_of_case[0]['account_id'])
    return dict(case_id=str(case_id), revision=revision, accounts=accounts, parties=parties, links=links,
        entity_links=entity_links, account_links=account_links, payment_links=payment_links,
        out_of_case_links=out_of_case)


def _graph_target_matches(tx, plan):
    """Every case node carrying one of the plan's account, party or entity-link keys, with its labels."""
    targets = {link['target'] for link in plan['entity_links']}
    keys = targets | {row['key'] for row in plan['accounts'] + plan['parties']}
    if not keys:
        return {}
    # Keep the match label-independent: a non-financial entity with the same
    # key is a collision too. UNWIND + OPTIONAL MATCH performed a whole-graph
    # scan per key without a common indexed label. Read all requested keys in
    # one pass, preserving every match so duplicate nodes cannot be hidden.
    # A label-less MATCH is an AllNodesScan (81,290 nodes on live, 142-287 ms per case, every 30 s round).
    # One branch per label the database knows (each uses that label's key index), joined and de-duplicated
    # by node id, finds the same nodes (7 of 7 cases identical, 11-44 ms, measured 31 Oct): every node the
    # code creates carries a label ('Entity' at least) and live has none without. With no labels listed,
    # the single label-less read is used.
    labels = sorted(row['label'] for row in tx.run('CALL db.labels() YIELD label RETURN label').data())
    matches = {}
    if not labels:
        for row in tx.run('''MATCH (n {case_id:$case}) WHERE n.key IN $keys
            RETURN n.key AS key, labels(n) AS labels''',
            keys=sorted(keys), case=plan['case_id']).data():
            matches.setdefault(row['key'], []).append(row['labels'])
        return matches
    query = '\nUNION ALL\n'.join(
        'MATCH (n:`%s`) WHERE n.key IN $keys AND n.case_id = $case '
        'RETURN elementId(n) AS id, n.key AS key, labels(n) AS labels' % label.replace('`', '``') for label in labels)
    seen = set()
    for row in tx.run(query, keys=sorted(keys), case=plan['case_id']).data():
        if row['id'] not in seen:
            seen.add(row['id'])
            matches.setdefault(row['key'], []).append(row['labels'])
    return matches


def validate_graph_targets(tx, plan):
    targets = {link['target'] for link in plan['entity_links']}
    matches = _graph_target_matches(tx, plan)
    if any(len(matches.get(key, [])) != 1 for key in targets):
        raise ValueError('A connected case entity is missing or ambiguous. Review its financial identity connection.')
    for label, rows in [('FinancialAccount', plan['accounts']), ('FinancialParty', plan['parties'])]:
        if any(len(matches.get(row['key'], [])) > 1 or
               any(label not in labels for labels in matches.get(row['key'], [])) for row in rows):
            raise ValueError('An account identity key conflicts with an existing case entity. No graph connections were changed.')


def apply_identity_graph(graph_session, plan, *, is_current=None):
    case_id, revision = plan['case_id'], plan['revision']
    # A unique marker supplies the graph-side mutex even on a case's first
    # projection. Existing conflicting markers fail closed; no nodes are
    # deleted to install this constraint.
    graph_session.run(Query('''CREATE CONSTRAINT financial_identity_sync_case IF NOT EXISTS
        FOR (m:FinancialIdentitySync) REQUIRE m.case_id IS UNIQUE''',
        timeout=GRAPH_TRANSACTION_TIMEOUT)).consume()
    with graph_session.begin_transaction(timeout=GRAPH_TRANSACTION_TIMEOUT) as tx:
        marker = tx.run('''MERGE (m:FinancialIdentitySync {case_id:$case})
            SET m.system_node=true, m.projection_lock=coalesce(m.projection_lock,0)+1
            RETURN m.revision AS revision''', case=case_id).single()
        # The ledger projection MERGEs the same FinancialAccount keys under its
        # own marker, and (case_id, key) is indexed, not unique. Two writers
        # creating one account at once committed two nodes, every later
        # projection drew each payment onto both, and validate_graph_targets
        # then refused the case for good. Take the projection's lock too, after
        # this one; the projection never takes this marker, so the order holds.
        from services.financial.graph_followup import _LOCK_MARKER
        tx.run(_LOCK_MARKER, case_id=case_id).consume()
        # A graph already at this revision gets no write, so no newer writer can be overwritten and the plan need
        # not be built again: the sweep finds most cases unchanged, and d5b330d1's plan took 1.24 s of a web
        # worker's interpreter (31 Oct).
        if marker and marker['revision'] == revision:
            # Where this branch's answer depends on the plan still being current (a refusal to report, or a backoff
            # to clear), it is rebuilt as before, so a plan that went stale while waiting changes neither.
            with _deferred_lock:
                deferred = str(case_id) in _deferred
            try:
                validate_graph_targets(tx, plan)
            except Exception:
                if is_current is not None and not is_current():
                    tx.rollback()
                    return False
                raise
            if deferred and is_current is not None and not is_current():
                tx.rollback()
                return False
            tx.rollback()
            _clear_deferral(case_id)
            return False
        # Revalidate only after acquiring the graph marker lock. Otherwise an
        # older snapshot could wait behind a newer writer and overwrite it.
        # The callback closes its short SQL snapshot before graph work resumes.
        if is_current is not None and not is_current():
            tx.rollback()
            return False
        validate_graph_targets(tx, plan)
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
            # Bounded, visible waiting: the marker says what is missing, and the
            # sweep defers this case with backoff rather than rewriting it every
            # round. Links whose payments exist are already committed above.
            attempts, delay = _defer(case_id, WAITING_FOR_PAYMENTS, missing=len(missing))
            tx.run('''MATCH (m:FinancialIdentitySync {case_id:$case})
                SET m.status=$status, m.missing_payment_nodes=$missing, m.waiting_revision=$revision,
                    m.waiting_since=coalesce(m.waiting_since, datetime()), m.waiting_attempts=$attempts,
                    m.next_attempt_at=datetime() + duration({seconds:$delay})''',
                case=case_id, status=WAITING_FOR_PAYMENTS, missing=len(missing), revision=revision,
                attempts=attempts, delay=int(delay)).consume()
            tx.commit()
            if attempts == 1 or attempts % 10 == 0:
                log.info('Reviewed identity graph for case %s is waiting for %s payment nodes (attempt %s, next in %ss)',
                    case_id, len(missing), attempts, int(delay))
            return True
        # The marker is hidden from ordinary entity lists by the standard system flag.
        tx.run('''MERGE (m:FinancialIdentitySync {case_id:$case})
            SET m.system_node=true, m.revision=$revision, m.completed_at=datetime(), m.status='current'
            REMOVE m.missing_payment_nodes, m.waiting_revision, m.waiting_since, m.waiting_attempts, m.next_attempt_at''',
            case=case_id, revision=revision).consume()
        tx.commit()
        _clear_deferral(case_id)
        return True


def _identity_snapshot(case_id):
    from postgres.session import get_background_session
    with get_background_session() as db:
        if db.scalar(select(Case.id).where(Case.id == case_id).with_for_update(skip_locked=True)) is None:
            return None
        return identity_graph_plan(db, case_id)


# The sweep visits every case every 30 s. Building a plan reads the case's accounts, decisions and admitted
# payments (d5b330d1 0.77 s measured), and the sync built it twice (once more under the graph lock) before
# finding the graph already current. A case whose plan inputs and graph reads are unchanged since its last
# completed sync is skipped: today's code would have reached the same "already current" answer. Any change on
# either side, and at least every FULL_SYNC_SECONDS regardless, takes the full path.
# Switch LOUPE_IDENTITY_GRAPH_SKIP_UNCHANGED (default on; '0' rebuilds every case every round as before).
SKIP_UNCHANGED = os.environ.get('LOUPE_IDENTITY_GRAPH_SKIP_UNCHANGED', '1') != '0'
FULL_SYNC_SECONDS = 600
_INPUT_TABLES = (FinancialAccount, AdjudicationEvent, FinancialTransaction)
_unchanged = {}
_unchanged_lock = Lock()


def identity_inputs_fingerprint(db, case_id):
    """A change detector for every table identity_graph_plan reads: per table, the case's row count and a
    per-row version sum. On PostgreSQL the version is xmin, which every UPDATE (ORM, Core or raw SQL) renews;
    elsewhere it is updated_at (the append-only decision table has created_at). Inserts and deletes move the
    count. A false 'changed' costs one extra build; nothing here decides what is drawn."""
    from sqlalchemy import func, literal_column
    postgres = db.get_bind().dialect.name == 'postgresql'
    parts = []
    for model in _INPUT_TABLES:
        table = model.__table__
        if postgres:
            version = func.sum(literal_column(f'{table.name}.xmin::text::bigint'))
        else:
            column = table.c.updated_at if 'updated_at' in table.c else table.c.created_at
            version = func.max(column)
        count, value = db.execute(select(func.count(), version).select_from(table)
            .where(table.c.case_id == case_id)).one()
        parts.append([table.name, int(count or 0), str(value)])
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _graph_reads(graph, plan):
    """What the sync reads from the graph before deciding to write: the target matches and the marker."""
    marker = graph.run('MATCH (m:FinancialIdentitySync {case_id:$case}) RETURN m.revision AS revision',
        case=plan['case_id']).data()
    matches = _graph_target_matches(graph, plan)
    digest = hashlib.sha256(json.dumps([marker, {k: sorted(map(sorted, v)) for k, v in matches.items()}],
        sort_keys=True).encode()).hexdigest()
    return digest, (marker[0]['revision'] if marker else None)


def _snapshot(case_id, known=None):
    """(inputs fingerprint, plan) under the case row lock; plan is None when the inputs equal `known`."""
    from postgres.session import get_background_session
    with get_background_session() as db:
        if db.scalar(select(Case.id).where(Case.id == case_id).with_for_update(skip_locked=True)) is None:
            return None
        inputs = identity_inputs_fingerprint(db, case_id) if SKIP_UNCHANGED else None
        if known is not None and inputs == known:
            return inputs, None
        return inputs, identity_graph_plan(db, case_id)


def forget_unchanged(case_id=None):
    with _unchanged_lock:
        if case_id is None:
            _unchanged.clear()
        else:
            _unchanged.pop(str(case_id), None)


def synchronize_case(case_id):
    from services.neo4j_service import neo4j_service
    with _unchanged_lock:
        known = _unchanged.get(str(case_id))
    if known and time.monotonic() - known['at'] >= FULL_SYNC_SECONDS:
        known = None
    snapshot = _snapshot(case_id, known['inputs'] if known else None)
    if snapshot is None:
        return False
    inputs, plan = snapshot
    if plan is None:
        with neo4j_service.session(connection_acquisition_timeout=GRAPH_CONNECTION_TIMEOUT) as graph:
            if _graph_reads(graph, known['plan'])[0] == known['graph']:
                # The old code cleared any retry state when it found the graph current.
                _clear_deferral(case_id)
                return False
        snapshot = _snapshot(case_id)
        if snapshot is None:
            return False
        inputs, plan = snapshot
    forget_unchanged(case_id)
    # No SQL transaction or Case lock may span connection acquisition, graph
    # validation or projection. An unavailable graph must not block edits or
    # recovery controls in Financial.
    def is_current():
        current = _identity_snapshot(case_id)
        return current is not None and current['revision'] == plan['revision']
    with neo4j_service.session(connection_acquisition_timeout=GRAPH_CONNECTION_TIMEOUT) as graph:
        before = _graph_reads(graph, plan) if inputs is not None else None
        applied = apply_identity_graph(graph, plan, is_current=is_current)
        # Remember a case only after a round that found the graph already current and wrote nothing: the graph
        # reads before and after the sync are equal, and it is not deferred (waiting for payment nodes or
        # refused). A graph write landing after those reads changes the next round's reads. The inputs were
        # read before the plan in the same transaction, so a later commit only causes one more build.
        if inputs is not None and not applied and sweep_deferral(case_id) is None:
            # apply also returns False when the revalidation found the source changed or the case row busy
            # (skip_locked): only a marker already at this plan's revision means the graph is current.
            after = _graph_reads(graph, plan)
            if after == before and after[1] == plan['revision']:
                keys = dict(case_id=plan['case_id'], accounts=[dict(key=r['key']) for r in plan['accounts']],
                    parties=[dict(key=r['key']) for r in plan['parties']],
                    entity_links=[dict(target=r['target']) for r in plan['entity_links']])
                with _unchanged_lock:
                    _unchanged[str(case_id)] = dict(inputs=inputs, graph=after[0], plan=keys, at=time.monotonic())
        return applied


def identity_graph_status(db, case_id):
    from services.neo4j_service import neo4j_service
    plan = identity_graph_plan(db, case_id)
    expected = plan['revision']
    try:
        with neo4j_service.session() as graph:
            validate_graph_targets(graph, plan)
            row = graph.run('''MATCH (m:FinancialIdentitySync {case_id:$case}) RETURN m.revision AS revision,
                toString(m.completed_at) AS completed_at, m.status AS status, m.waiting_revision AS waiting_revision,
                m.missing_payment_nodes AS missing_payment_nodes, toString(m.waiting_since) AS waiting_since,
                m.waiting_attempts AS waiting_attempts, toString(m.next_attempt_at) AS next_attempt_at''', case=str(case_id)).single()
    except Exception:
        return dict(case_id=str(case_id), status='unavailable', completed_at=None)
    result = dict(case_id=str(case_id), status='current' if row and row['revision'] == expected else 'pending',
        completed_at=row['completed_at'] if row else None)
    if plan.get('out_of_case_links'):
        result['out_of_case_links'] = len(plan['out_of_case_links'])
    if result['status'] == 'pending' and row and row['status'] == WAITING_FOR_PAYMENTS and row['waiting_revision'] == expected:
        # Saved decisions are linked, except those whose payments are not yet
        # in the graph; the ledger graph follow-up draws them.
        local = sweep_deferral(case_id) or {}
        result.update(status='waiting_for_payments', missing_payment_nodes=row['missing_payment_nodes'],
            waiting_since=row['waiting_since'], attempts=row['waiting_attempts'],
            next_attempt_at=row['next_attempt_at'], retry_in_seconds=local.get('retry_in_seconds'))
    return result


# Switch LOUPE_FINANCIAL_IDENTITY_SYNC_ONE_WORKER (default on; '0' turns it off): every API worker runs this
# sweep; two syncing one case at once deadlock in Neo4j and one is terminated (LockClientStopped). A case is
# synchronised by whichever worker holds its advisory lock; the other skips it until its next round.
ONE_WORKER_PER_CASE = os.environ.get('LOUPE_FINANCIAL_IDENTITY_SYNC_ONE_WORKER', '1') != '0'


@contextmanager
def _case_claim(case_id):
    """True while this worker holds the case's identity-sync lock (always True off Postgres or switched off).

    A session-level advisory lock on one dedicated connection, held for the whole sync and released on that
    same connection (closing it releases it too, if this worker dies mid-sync)."""
    from postgres.session import _get_background_engine
    if not ONE_WORKER_PER_CASE:
        yield True
        return
    engine = _get_background_engine()
    if engine.dialect.name != 'postgresql':
        yield True
        return
    key = "hashtextextended('loupe.financial.identity_graph:' || CAST(:case_id AS text), 0)"
    with engine.connect() as conn:
        held = False
        try:
            held = bool(conn.execute(text(f'SELECT pg_try_advisory_lock({key})'), dict(case_id=str(case_id))).scalar())
            conn.commit()
            yield held
        finally:
            if held:
                try:
                    conn.execute(text(f'SELECT pg_advisory_unlock({key})'), dict(case_id=str(case_id)))
                    conn.commit()
                except Exception:
                    # Never return a connection to the pool still holding the lock: drop it (Postgres
                    # releases a session lock when its connection closes).
                    conn.invalidate()
                    raise


def sync_saved_identities(stop=None):
    from postgres.session import get_background_session
    with get_background_session() as db:
        cases = list(db.scalars(select(AdjudicationEvent.case_id).where(AdjudicationEvent.decision.in_(['set_account_party', 'set_account_identity', 'set_counterparty_party'])).distinct()))
    for case_id in cases:
        if stop is not None and stop.is_set():
            break
        if _is_deferred(case_id):
            continue
        try:
            with _case_claim(case_id) as claimed:
                if not claimed:
                    continue
                synchronize_case(case_id)
        except Exception as error:
            attempts, delay = _defer(case_id, 'failed', error=str(error)[:500])
            if attempts == 1:
                log.exception('Reviewed account identity graph will retry for case %s in %ss', case_id, int(delay))
            else:
                log.warning('Reviewed account identity graph failed again for case %s (attempt %s); next in %ss: %s',
                    case_id, attempts, int(delay), error)


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
