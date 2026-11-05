"""The code-word glossary (agent-evidence-rest F; report scenario 4: "A code-word glossary is proposed as model readings
(term, meaning, speaker, citations) and confirmed term by term, so that once "breakfast" is decoded, every mention
joins to its ledger rows.").

A term enters only through a person: the agent's ``propose_glossary_term`` waits on Workspace as a model reading, and
a person's accept (with their own wording of the meaning, if they change it) writes ``case_glossary_terms``. The model's
reading stays beside it. From then on the term is a person's reading, shown as that, naming who confirmed it.

Every mention is found by the search itself (whole folded words) and joined by code, never by a model: for a message
between two people of the case, the ledger rows between them through reviewed identity (``link_edges.payments``), the
same rows ``money_between`` reads, within ``JOIN_DAYS`` of the message. The window is stated, rows outside it are
counted, a mention that cannot be joined says why, and nothing is summed.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text

log = logging.getLogger(__name__)

JOIN_DAYS = 7
PAGE = 200
PERSON_WORDS = 'A person\'s reading: confirmed by {name} on {day}.'
JOIN_WORDS = ('Ledger rows between the two people of the conversation, through reviewed identity, within %d days of '
              'the message.' % JOIN_DAYS)


class GlossaryError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status_code = status


def confirmed(session, case_id, term):
    from postgres.models.agent_evidence import CaseGlossaryTerm as G
    want = ' '.join(str(term or '').split()).lower()
    return next((r for r in session.scalars(select(G).where(G.case_id == uuid.UUID(str(case_id)),
                                                            G.status == 'confirmed'))
                 if r.term.lower() == want), None)


def confirm(session, item, content, reviewer, provenance, meaning=None):
    """A person confirms the meaning (their own words when they change it). Runs inside the proposal's accept."""
    from postgres.models.agent_evidence import CaseGlossaryTerm as G
    existing = confirmed(session, item.case_id, content['term'])
    if existing is not None and existing.proposal_id == item.id:
        return existing  # an accept that stopped after the confirmation was saved, tried again
    if existing is not None:
        from services.agent.proposals import ProposalError
        raise ProposalError(f'A person has already confirmed a meaning for "{content["term"]}".', 409)
    meaning = ' '.join(str(meaning or '').split()) or content['meaning']
    row = G(id=uuid.uuid4(), case_id=item.case_id, term=content['term'], meaning=meaning,
            model_meaning=content['meaning'], speaker=content.get('speaker'),
            citations=list(content.get('citations') or []), status='confirmed', confirmed_by_user_id=reviewer.id,
            confirmed_by_name=reviewer.name, confirmed_at=datetime.now(timezone.utc), proposal_id=item.id,
            origin=provenance)
    session.add(row)
    session.commit()
    _save_keyword_list(session, item.case_id, reviewer, row)
    return row


def _save_keyword_list(session, case_id, reviewer, row):
    """The term also runs as a saved keyword list, so every phone counts it and the typed-words and searches analyses
    compare it. A list that cannot be saved costs that, never the confirmation, and the term says so. ``K.create``
    commits on its own, so this runs after the confirmation is saved."""
    from services.search import keyword_lists as K
    try:
        saved = K.create(session, case_id, reviewer, name=f'Code word: {row.term}', terms=[row.term], exact=False,
                         note=f'Confirmed meaning: {row.meaning}')
        row.keyword_list_entry_id = uuid.UUID(saved['entry_id'])
    except K.KeywordListError as exc:
        session.rollback()
        row.keyword_list_note = f'Not counted as a keyword list: {exc}'
    except Exception:  # noqa: BLE001 - the person's confirmation stands
        log.exception('Keyword list for glossary term %s not saved', row.id)
        session.rollback()
        row.keyword_list_note = 'Not counted as a keyword list: the list could not be saved.'
    session.commit()


def withdraw(session, *, case_id, term_id, reviewer, reason):
    """A person takes the term back. It stays listed as withdrawn, with who and why."""
    from postgres.models.agent_evidence import CaseGlossaryTerm as G
    from services.financial.model_work import is_model
    if reviewer is None or is_model(reviewer):
        raise GlossaryError('A person withdraws a term.', 403)
    reason = ' '.join(str(reason or '').split())
    if not reason:
        raise GlossaryError('Say why the meaning is withdrawn.')
    row = session.get(G, uuid.UUID(str(term_id)))
    if row is None or row.case_id != uuid.UUID(str(case_id)):
        raise GlossaryError('Not in this case.', 404)
    if row.status != 'confirmed':
        raise GlossaryError('This term is already withdrawn.', 409)
    row.status, row.withdrawn_by_name, row.withdrawn_reason = 'withdrawn', reviewer.name, reason[:4000]
    row.withdrawn_at = datetime.now(timezone.utc)
    session.commit()
    _retire_keyword_list(session, case_id, reviewer, row)
    return term_out(row)


def _retire_keyword_list(session, case_id, reviewer, row):
    """A withdrawn meaning stops running: its list and the note stating the meaning leave with it."""
    from postgres.models.workspace_entry import WorkspaceEntry
    from services.workspace_entry_service import soft_delete_entry
    entry = session.get(WorkspaceEntry, row.keyword_list_entry_id) if row.keyword_list_entry_id else None
    if entry is None or entry.deleted_at is not None:
        return
    try:
        soft_delete_entry(session, case_id=uuid.UUID(str(case_id)), entry_id=entry.id, current_user=reviewer,
                          expected_version=entry.version)
    except Exception:  # noqa: BLE001 - the withdrawal stands, and says what is left
        log.exception('Keyword list of withdrawn glossary term %s not removed', row.id)
        session.rollback()
        row.keyword_list_note = 'The keyword list of this term could not be removed and still runs.'
        session.commit()


def term_out(row) -> dict:
    day = row.confirmed_at.date().isoformat() if row.confirmed_at else ''
    return dict(id=str(row.id), term=row.term, meaning=row.meaning, model_meaning=row.model_meaning,
                meaning_changed=(row.model_meaning or '') != row.meaning, speaker=row.speaker,
                citations=list(row.citations or []), status=row.status, confirmed_by=row.confirmed_by_name,
                confirmed_at=row.confirmed_at.isoformat() if row.confirmed_at else None,
                reading_words=PERSON_WORDS.format(name=row.confirmed_by_name, day=day),
                keyword_list_note=row.keyword_list_note,
                withdrawn_by=row.withdrawn_by_name, withdrawn_reason=row.withdrawn_reason,
                withdrawn_at=row.withdrawn_at.isoformat() if row.withdrawn_at else None)


def _hits(conn, case_id, term) -> tuple[list[str], list[str]]:
    """Every message and email holding the term, by the search itself: record ids and any stated limit of the search."""
    from services.search import search as S
    if len(S.F.fold(term, exact=False).replace(' ', '')) < S.MIN_TEXT:
        return [], [f'"{term}" is shorter than the {S.MIN_TEXT} letters or digits the search needs, so its mentions '
                    'were not searched. No mention is listed; that is not the same as none.']
    uids, limits = [], []
    for group in ('messages', 'emails'):
        cursor = '0'
        while cursor is not None:
            page = S.group_page(conn, case_id, term, group, cursor=cursor, limit=PAGE, exact=False)
            uids += [str(i['record_uid']) for i in page['items'] if i.get('record_uid')]
            limits += [x.get('message') or x.get('words') or str(x) for x in page.get('limits') or []]
            cursor = page.get('next_cursor')
    return list(dict.fromkeys(uids)), list(dict.fromkeys(limits))


def _events(conn, case_id, uids) -> list[dict]:
    """Each mention with its time, phone and the people of its message, through reviewed identity links."""
    if not uids:
        return []
    events = {}
    for r in conn.execute(text(
            "SELECT ev.event_uid, ev.record_uid, ev.extraction_id, ev.sort_instant, ev.kind FROM pv_comm_event ev WHERE "
            "ev.case_id = :c AND ev.record_uid = ANY(CAST(:u AS uuid[]))"), {"c": str(case_id), "u": uids}):
        events.setdefault(str(r.record_uid), dict(event_uid=str(r.event_uid), record_uid=str(r.record_uid),
                                                  extraction_id=str(r.extraction_id), instant=r.sort_instant,
                                                  kind=r.kind, people=set()))
    for r in conn.execute(text(
            "SELECT DISTINCT ev.record_uid, d.id::text AS dossier, d.display_name, d.canonical_entity_key FROM "
            "pv_comm_event ev JOIN pv_comm_party p ON p.event_uid = ev.event_uid JOIN pv_identity i ON i.case_id = "
            "ev.case_id AND i.identity_key = p.identity_key JOIN case_profiles d ON d.id = i.person_id AND d.case_id = "
            "ev.case_id AND d.archived_at IS NULL WHERE ev.case_id = :c AND ev.record_uid = ANY(CAST(:u AS uuid[]))"),
            {"c": str(case_id), "u": uids}):
        e = events.get(str(r.record_uid))
        if e is not None:
            e['people'].add((r.dossier, r.display_name, r.canonical_entity_key))
    return sorted(events.values(), key=lambda e: (e['instant'] is None, e['instant'] or datetime.min, e['record_uid']))


def _rows_between(session, case_id, a, b, cache):
    """Every ledger row between two people, once per pair; ``None`` when one has no reviewed financial side."""
    from services.phone import link_edges
    pair = tuple(sorted((a, b)))
    if pair not in cache:
        keys = [p[2] for p in pair if p[2]]
        sides = link_edges.financial_sides(session, case_id, keys) if len(keys) == 2 else {}
        sa, sb = sides.get(pair[0][2]), sides.get(pair[1][2])
        if not sa or not sb or not (sa['accounts'] or sb['accounts']):
            cache[pair] = None
        else:
            cache[pair] = dict(rows=link_edges.payments(session, case_id, sa, sb)['rows'], a=pair[0], b=pair[1])
    return cache[pair]


def _row_out(r, day, got):
    from services.phone import link_edges
    a, b = (got['a'], got['b']) if r['direction'] == 'ab' else (got['b'], got['a'])
    when = date.fromisoformat(r['ordering_date'])
    return dict(txn=f"txn://{r['id']}", ref=r.get('ref_id'), payment=r['id'],
                amount=link_edges.format_minor(r['amount_minor'], r['currency']), date=r['ordering_date'],
                proof_class=r['proof_class'], paid_by=a[1], paid_to=b[1], days_from_mention=(when - day).days)


def mentions(conn, session, case_id, term) -> dict:
    """Every mention of the term, each with the ledger rows it joins to, or the reason it joins none."""
    uids, limits = _hits(conn, case_id, term)
    cache, items = {}, []
    joined = no_join = 0
    for e in _events(conn, case_id, uids):
        item = dict(rec=f"rec://{e['record_uid']}", kind=e['kind'], at=e['instant'].isoformat() if e['instant'] else None,
                    people=sorted(p[1] for p in e['people']), rows=[], rows_outside_window=0, join_reason=None)
        people = sorted(e['people'])
        if e['instant'] is None:
            item['join_reason'] = 'The message has no time, so no window can be set.'
        elif len(people) < 2:
            item['join_reason'] = ('The people of this message are not both linked to a person of the case through a '
                                   'reviewed identity.')
        else:
            day = e['instant'].astimezone(timezone.utc).date()
            usable = False
            for i, a in enumerate(people):
                for b in people[i + 1:]:
                    got = _rows_between(session, case_id, a, b, cache)
                    if got is None:
                        continue
                    usable = True
                    for r in got['rows']:
                        out = _row_out(r, day, got)
                        if abs(out['days_from_mention']) <= JOIN_DAYS:
                            item['rows'].append(out)
                        else:
                            item['rows_outside_window'] += 1
            item['rows'].sort(key=lambda r: (abs(r['days_from_mention']), r['date'], r['payment']))
            if not usable:
                item['join_reason'] = ('No account of these people is linked through a reviewed identity, so the '
                                       'ledger cannot be joined.')
            elif not item['rows']:
                item['join_reason'] = 'No ledger row between them within %d days.' % JOIN_DAYS
        joined += bool(item['rows'])
        no_join += not item['rows']
        items.append(item)
    return dict(total=len(items), with_rows=joined, without_rows=no_join, items=items, join_rule=JOIN_WORDS,
                search_limits=limits)


def read(conn, session, case_id, *, with_mentions=True) -> dict:
    """Every term of the case, newest first, confirmed ones with their mentions."""
    from postgres.models.agent_evidence import CaseGlossaryTerm as G
    rows = session.scalars(select(G).where(G.case_id == uuid.UUID(str(case_id)))
                           .order_by(G.status, G.confirmed_at.desc())).all()
    items = []
    for row in rows:
        out = term_out(row)
        if with_mentions and row.status == 'confirmed':
            out['mentions'] = mentions(conn, session, case_id, row.term)
        items.append(out)
    return dict(total=len(items), confirmed=sum(1 for x in items if x['status'] == 'confirmed'), items=items,
                limitation='A meaning here is a person\'s reading, not a fact; each mention is a word in a message and '
                           'each joined row sits inside the stated window. Amounts are listed, never added.')
