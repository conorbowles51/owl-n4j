"""The manual changes people saved before the feed existed, fed through ``record_change`` once, marked historic.

Each source below is where a route already keeps its person's decision (inventory: docs/manual-change-feed.md).
A record is a person's when it names a person and no model or system: an ``origin`` (a model acting for someone),
a model or system name ("Claude (for ...)", "Neil Byrne (via Claude)", "System", "Batch review") or a
``@system.local`` address is not a person. The automated-checks logins are recorded but marked test.
Every record carries ``source_ref`` (its table, row and position), so running this again adds nothing twice.
``python -m services.manual_changes --backfill`` is a dry run (counts per kind and patterns); ``--apply`` writes.
"""
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select, text

log = logging.getLogger(__name__)
_NOT_PERSON = re.compile(r'\b(claude|deepseek|system|batch review|model)\b|\(via ', re.I)
AUTOMATION_EMAILS = {'jobs-verify@loupe.invalid', 'ui-walkthrough@loupe.invalid'}


def is_person(name='', email='', origin=None):
    if origin:
        return False
    email = (email or '').lower()
    if email.endswith('@system.local') or 'reconciliation' in email:
        return False
    if _NOT_PERSON.search(name or ''):
        return False
    return bool((name or '').strip() or email)


def _rows(session, sql, **params):
    return session.execute(text(sql), params).mappings().all()


def _when(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def _users(session):
    return {str(r['id']): (r['name'] or '', r['email'] or '') for r in _rows(session, 'select id, name, email from users')}


def _actor(users, user_id='', name='', email=''):
    if user_id and str(user_id) in users and not email:
        known_name, known_email = users[str(user_id)]
        return dict(user_id=str(user_id), name=name or known_name, email=known_email)
    return dict(user_id=str(user_id or ''), name=name or '', email=email or '')


def adjudications(session, users):
    kinds = {'supersede_duplicate': ('duplicate_decision', 'set_aside'), 'restore_document': ('duplicate_decision', 'change'),
             'set_counterparty_party': ('counterparty_party', 'change'), 'set_account_party': ('account_party', 'change'),
             'admit_financial_document': ('file_admit', 'change'), 'set_account_identity': ('account_identity', 'change'),
             'correct_transaction': ('transaction_correction', 'change'), 'quarantine_row': ('quarantine', 'set_aside'),
             'release_row': ('release', 'change')}
    for r in _rows(session, "select id, case_id, decision::text as decision, subject_type::text as subject_type, "
                            "subject_id, actor_name, actor_email, actor_user_id, actor_origin, reason, before, after, "
                            "created_at from adjudications where actor_origin is null"):
        decision = r['decision'].lower()
        if decision not in kinds or not is_person(r['actor_name'], r['actor_email']):
            continue
        kind, change_type = kinds[decision]
        after = r['after'] or {}
        subject = {'source_document': 'source_document', 'transaction': 'transaction', 'account': 'account',
                   'evidence_file': 'evidence_file'}.get((r['subject_type'] or '').lower(), (r['subject_type'] or '').lower())
        yield dict(kind=kind, change_type=change_type, case_id=r['case_id'], subject=(subject, str(r['subject_id'])),
                   before=r['before'], after=after, actor=_actor(users, r['actor_user_id'], r['actor_name'], r['actor_email']),
                   reason=r['reason'] or '', field=(after.get('basis') or decision) if isinstance(after, dict) else decision,
                   at=r['created_at'], source_ref=f"adjudication:{r['id']}")


def judgements(session, users):
    for r in _rows(session, "select id, case_id, rule_id, target_key, status, resolved_by, resolved_by_email, "
                            "resolved_at, resolution_reason, source_document_id from financial_judgements "
                            "where status = 'confirmed'"):
        if not is_person(r['resolved_by'], r['resolved_by_email']):
            continue
        yield dict(kind='judgement_confirm', change_type='confirm', case_id=r['case_id'], subject=('judgement', str(r['id'])),
                   before=None, after=None, actor=dict(name=r['resolved_by'], email=r['resolved_by_email']),
                   reason=r['resolution_reason'] or '', field=r['target_key'] or '', producer=r['rule_id'],
                   at=r['resolved_at'], source_ref=f"judgement-confirm:{r['id']}",
                   link=f"/cases/{r['case_id']}/financial?document={r['source_document_id'] or ''}&judgement={r['id']}")


def payment_labels(session, users):
    for r in _rows(session, "select t.id, t.case_id, e.ordinality as n, e.value as e from financial_transactions t, "
                            "jsonb_array_elements(t.metadata->'investigation_label_history') with ordinality e"):
        e = r['e'] or {}
        if not is_person(e.get('actor_name'), e.get('actor_email'), e.get('origin')):
            continue
        if 'confirmed' in e:
            kind, change_type, fields = 'payment_label_confirm', 'confirm', e.get('confirmed') or []
        elif 'removed' in e:
            kind, change_type, fields = 'payment_label_remove', 'set_aside', e.get('removed') or []
        else:
            before, after = e.get('before') or {}, e.get('after') or {}
            kind, change_type = 'payment_label_change', 'change'
            fields = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        yield dict(kind=kind, change_type=change_type, case_id=r['case_id'], subject=('transaction', str(r['id'])),
                   before=e.get('before'), after=e.get('after') or e.get('values'), diff=change_type == 'change',
                   actor=_actor(users, e.get('actor_id'), e.get('actor_name'), e.get('actor_email')), reason=e.get('reason') or '',
                   field=','.join(map(str, fields)), at=_when(e.get('at')), source_ref=f"label:{r['id']}:{r['n']}")


def account_histories(session, users):
    for r in _rows(session, "select a.id, a.case_id, e.ordinality as n, e.value as e from financial_accounts a, "
                            "jsonb_array_elements(a.metadata->'account_details_history') with ordinality e"):
        e = r['e'] or {}
        confirmed = e.get('confirmed') or {}
        if confirmed and is_person(confirmed.get('by'), confirmed.get('by_email')):
            yield dict(kind='account_details_confirm', change_type='confirm', case_id=r['case_id'],
                       subject=('account', str(r['id'])), before=e.get('after'), after=e.get('after'),
                       actor=dict(name=confirmed.get('by'), email=confirmed.get('by_email'), user_id=confirmed.get('user_id')),
                       reason='', field=','.join(sorted((e.get('after') or {}).keys())), at=_when(confirmed.get('at')),
                       source_ref=f"account-details-confirm:{r['id']}:{r['n']}")
        if not is_person(e.get('actor_name'), e.get('actor_email'), e.get('origin')):
            continue
        before, after = e.get('before') or {}, e.get('after') or {}
        undo = e.get('kind') == 'undo'
        yield dict(kind='account_details_undo' if undo else 'account_details', change_type='set_aside' if undo else 'change',
                   case_id=r['case_id'], subject=('account', str(r['id'])), before=before, after=after, diff=not undo,
                   actor=_actor(users, e.get('actor_id'), e.get('actor_name'), e.get('actor_email')), reason=e.get('reason') or '',
                   field=','.join(sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))),
                   at=_when(e.get('at')), source_ref=f"account-details:{r['id']}:{r['n']}")
    for r in _rows(session, "select a.id, a.case_id, e.ordinality as n, e.value as e from financial_accounts a, "
                            "jsonb_array_elements(a.metadata->'account_type_history') with ordinality e"):
        e = r['e'] or {}
        if not is_person(e.get('actor_name'), e.get('actor_email'), e.get('origin')):
            continue
        yield dict(kind='account_type', change_type='change', case_id=r['case_id'], subject=('account', str(r['id'])),
                   before=e.get('before'), after=e.get('after'), actor=_actor(users, e.get('actor_id'), e.get('actor_name'),
                   e.get('actor_email')), reason=e.get('reason') or '', field='account_type', at=_when(e.get('at')),
                   source_ref=f"account-type:{r['id']}:{r['n']}")


def statement_details(session, users):
    for r in _rows(session, "select d.id, d.case_id, e.ordinality as n, e.value as e from financial_source_documents d, "
                            "jsonb_array_elements(d.metadata->'statement_details_history') with ordinality e"):
        e = r['e'] or {}
        if not is_person(e.get('actor_name'), e.get('actor_email'), e.get('origin')):
            continue
        before, after = e.get('before') or {}, e.get('after') or {}
        fields = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)) if isinstance(before, dict) \
            and isinstance(after, dict) else []
        yield dict(kind='statement_details', change_type='change', case_id=r['case_id'],
                   subject=('source_document', str(r['id'])), before=before, after=after, diff=True,
                   actor=_actor(users, e.get('actor_id'), e.get('actor_name'), e.get('actor_email')), reason=e.get('reason') or '',
                   field=','.join(fields), at=_when(e.get('at') or e.get('saved_at')),
                   source_ref=f"statement-details:{r['id']}:{r['n']}")
    for r in _rows(session, "select d.id, d.case_id, e.ordinality as n, e.value as e from financial_source_documents d, "
                            "jsonb_array_elements(d.metadata->'statement_incomplete_records') with ordinality e"):
        e = r['e'] or {}
        original = e.get('original') or {}
        manual = original.get('kind') == 'manual_entry'
        who = e.get('corrected_by') or (original.get('actor') if manual else None)
        if not who and not manual:
            continue
        actor = _actor(users, who) if who else dict(name='', email='')
        if who and not is_person(*users.get(str(who), ('', ''))):
            continue
        correction = e.get('correction') or {}
        before_fields = original.get('fields') or {}
        yield dict(kind='manual_payment' if manual else 'record_completion', change_type='change', case_id=r['case_id'],
                   subject=('source_document', str(r['id'])), before=None if manual else before_fields,
                   after=correction or before_fields, actor=actor, reason=correction.get('reason') or '',
                   field='rows.added' if manual else ','.join(sorted(k for k in correction
                                                                     if before_fields.get(k) != correction.get(k))),
                   at=_when(e.get('corrected_at') or original.get('at')), source_ref=f"record:{r['id']}:{r['n']}")


def evidence_reviews(session, users):
    """Bulk account details, duplicate decisions, not-payment decisions, review comparisons and skips."""
    for r in _rows(session, "select f.id, f.case_id, e.ordinality as n, e.value as e from evidence_files f, "
                            "jsonb_array_elements(f.metadata->'financial_account_detail_history') with ordinality e"):
        e = r['e'] or {}
        actor = e.get('actor') or e.get('saved_by') or {}
        if not is_person(actor.get('name'), actor.get('email'), actor.get('origin')):
            continue
        before, after = e.get('before') or {}, e.get('after') or {}
        yield dict(kind='statement_account_details', change_type='change', case_id=r['case_id'],
                   subject=('evidence_file', f"{r['id']}#{e.get('statement_id') or ''}"), before=before, after=after, diff=True,
                   actor=_actor(users, actor.get('user_id'), actor.get('name'), actor.get('email')), reason=e.get('reason') or '',
                   field=','.join(sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)))
                   if isinstance(before, dict) and isinstance(after, dict) else '',
                   at=_when(e.get('at') or e.get('saved_at')), source_ref=f"bulk-details:{r['id']}:{r['n']}")
    for r in _rows(session, "select f.id, f.case_id, d.key, d.value as e from evidence_files f, "
                            "jsonb_each(f.metadata->'financial_duplicate_dispositions') d"):
        e = r['e'] or {}
        actor = e.get('actor') or {}
        if not isinstance(e, dict) or not is_person(actor.get('name'), actor.get('email'), actor.get('origin')):
            continue
        yield dict(kind='duplicate_disposition', change_type='set_aside' if e.get('status') == 'ignored' else 'change',
                   case_id=r['case_id'], subject=('evidence_file', f"{r['id']}#{r['key']}"), before=None,
                   after=dict(status=e.get('status'), retained=e.get('retained')),
                   actor=_actor(users, actor.get('user_id'), actor.get('name'), actor.get('email')), reason=e.get('reason') or '',
                   field=e.get('status') or '', at=_when(e.get('decided_at') or e.get('at')),
                   source_ref=f"duplicate-disposition:{r['id']}:{r['key']}")
    for r in _rows(session, "select f.id, f.case_id, d.key, d.value as e from evidence_files f, "
                            "jsonb_each(f.metadata->'statement_not_payment_decisions') d"):
        e = r['e'] or {}
        actor = e.get('actor') or {}
        if not isinstance(e, dict) or not is_person(actor.get('name'), actor.get('email'), actor.get('origin')):
            continue
        yield dict(kind='not_payment_statement', change_type='set_aside' if e.get('status') == 'set_aside' else 'change',
                   case_id=r['case_id'], subject=('evidence_file', f"{r['id']}#{r['key']}"), before=None,
                   after=dict(status=e.get('status')), actor=_actor(users, actor.get('user_id'), actor.get('name')),
                   reason=e.get('reason') or '', field=e.get('status') or '', at=_when(e.get('at')),
                   source_ref=f"not-payment:{r['id']}:{r['key']}")
    for r in _rows(session, "select f.id, f.case_id, e.ordinality as n, e.value as e from evidence_files f, "
                            "jsonb_array_elements(f.metadata->'financial_review_comparison_history') with ordinality e"):
        e = r['e'] or {}
        actor = e.get('saved_by') or {}
        if not is_person(actor.get('name'), actor.get('email'), actor.get('origin')):
            continue
        yield dict(kind='review_recovery_ack', change_type='confirm', case_id=r['case_id'],
                   subject=('evidence_file', str(r['id'])), before=None, after=None,
                   actor=_actor(users, actor.get('user_id'), actor.get('name')), reason='', field='previous_review',
                   at=_when(e.get('saved_at') or e.get('at')), source_ref=f"review-compare:{r['id']}:{r['n']}")
    for r in _rows(session, "select i.id, f.case_id, i.file_id, i.summary->'import_decision' as e "
                            "from financial_import_batch_items i join evidence_files f on f.id = i.file_id "
                            "where i.summary ? 'import_decision'"):
        e = r['e'] or {}
        actor = e.get('actor') or {}
        if not is_person(actor.get('name'), actor.get('email'), actor.get('origin')):
            continue
        yield dict(kind='batch_item_skip', change_type='set_aside' if e.get('action', 'skip') == 'skip' else 'change',
                   case_id=r['case_id'], subject=('batch_item', str(r['id'])), before=None, after=dict(action=e.get('action')),
                   actor=_actor(users, actor.get('user_id'), actor.get('name')), reason=e.get('reason') or '',
                   field=e.get('action') or 'skip', at=_when(e.get('at')), source_ref=f"batch-skip:{r['id']}")


def review_saves(session, users):
    """Review-queue saves: each saved review (current and in history) against the review before it, or against the
    system's own reading on the first save when that reading is still the one the save was made on."""
    from services.financial.import_batches import initial_request
    from services.financial.manual_change_kinds import _normal, reading_producer, request_diff
    from services.financial.statement_import import read_statement_import
    readings, unread = {}, {}
    for r in _rows(session, "select f.id, f.case_id, f.metadata->'financial_review_progress' as progress, "
                            "f.metadata->'financial_review_history' as history from evidence_files f "
                            "where f.metadata ? 'financial_review_progress'"):
        saves = {}
        for entry in (r['history'] or []) + list((r['progress'] or {}).values()):
            if isinstance(entry, dict) and isinstance(entry.get('request'), dict):
                saves.setdefault(entry['request'].get('statement_id') or '', []).append(entry)
        for statement, entries in saves.items():
            entries.sort(key=lambda e: e.get('saved_at') or '')
            previous = None
            for n, entry in enumerate(entries):
                actor = entry.get('saved_by') or {}
                request = entry['request']
                if is_person(actor.get('name'), actor.get('email'), actor.get('origin')):
                    key = (str(r['id']), statement, request.get('expected_revision'), request.get('currency'))
                    baseline, producer, layout = previous, '', ''
                    if key not in readings:
                        try:
                            with session.begin_nested():
                                proposal = read_statement_import(session, case_id=r['case_id'], evidence_file_id=r['id'],
                                                                 currency=request.get('currency'),
                                                                 statement_id=statement or None,
                                                                 _include_period_checks=False)
                            readings[key] = proposal
                        except Exception as exc:  # noqa: BLE001 - the save is recorded without a reading to compare
                            log.info('Reading %s for the backfill failed: %s', key, exc)
                            readings[key] = None
                            unread[key] = (' '.join(str(exc).split()).split('.')[0][:80] or type(exc).__name__)
                    proposal = readings[key]
                    stored = False
                    if proposal is not None:
                        producer, layout = reading_producer(proposal)
                        if baseline is None and proposal.get('revision') == request.get('expected_revision'):
                            baseline = initial_request(proposal)
                    if baseline is None and previous is None:
                        # The file was removed or read again since: the reading this save was made on may still be
                        # the one stored with the statement it saved.
                        kept = stored_reading(session, r['id'], request.get('expected_revision'))
                        if kept is not None:
                            baseline, stored = kept['request'], True
                            producer, layout = reading_producer(kept['proposal'])
                    if baseline is not None:
                        fields, old, new = request_diff(_normal(baseline), _normal(request))
                    else:
                        why = unread.get(key)
                        fields, old, new = ([f'(not compared: {why})'] if why else
                                            ['(not compared: the reading this save was made on is not the current one)'],
                                            None, None)
                    ref = f"review-save:{r['id']}:{statement[:16]}:{entry.get('review_revision') or n}"
                    if not fields and stored:
                        # Compared at last and saved as read: a confirmation, which replaces its "(not compared)".
                        fields, change_type = ['(saved unchanged)'], 'confirm'
                    else:
                        change_type = 'change'
                    if fields:
                        yield dict(kind='statement_review_edit', change_type=change_type, case_id=r['case_id'],
                                   **({'replaces_ref': ref + ':'} if stored else {}),
                                   subject=('evidence_file', f"{r['id']}#{statement}"), before=old, after=new,
                                   per_field=(fields, old or {}, new or {}),
                                   actor=_actor(users, actor.get('user_id'), actor.get('name'), actor.get('email')),
                                   reason='', field=','.join(fields), producer=producer, layout=layout,
                                   at=_when(entry.get('saved_at')),
                                   link=f"/cases/{r['case_id']}/financial?file={r['id']}&statement={statement}",
                                   source_ref=ref)
                previous = request


def stored_reading(session, evidence_file_id, revision):
    """{'proposal', 'request'} of the reading a statement of this file was saved from, when its revision is
    ``revision`` (kept on the saved statement as ``statement_import_original``), or None."""
    from services.financial.import_batches import initial_request
    if not revision:
        return None
    for r in _rows(session, "select d.metadata->'statement_import_original' as original from financial_source_documents d "
                            "where d.evidence_file_id = :file and d.metadata->'statement_import_original'->>'revision' = :rev "
                            "order by d.created_at desc limit 1", file=str(evidence_file_id), rev=str(revision)):
        original = r['original']
        if isinstance(original, str):
            original = json.loads(original)
        try:
            return dict(proposal=original, request=initial_request(original))
        except Exception as exc:  # noqa: BLE001 - an older reading shape: not compared, as before
            log.info('Stored reading of %s could not be compared: %s', evidence_file_id, exc)
    return None


def graph_deletes(session, users):
    for r in _rows(session, "select id, case_id, item_type, original_key, original_type, deleted_by, deleted_at, "
                            "reason from graph_recycle_bin_items where item_type = 'entity_delete'"):
        email = r['deleted_by'] or ''
        name = next((n for n, e in users.values() if e == email), '')
        if not is_person(name, email):
            continue
        yield dict(kind='entity_delete', change_type='set_aside', case_id=r['case_id'], subject=('entity', r['original_key']),
                   before=None, after=None, actor=dict(name=name, email=email), reason=r['reason'] or '', field='entity',
                   producer=r['original_type'] or '', layout='', at=r['deleted_at'], source_ref=f"recycle:{r['id']}")


def workspace_ai(session, users):
    for r in _rows(session, "select id, case_id, review_status, reviewed_by_user_id, reviewed_at "
                            "from workspace_ai_outputs where review_status in ('accepted', 'rejected')"):
        name, email = users.get(str(r['reviewed_by_user_id']), ('', ''))
        if not is_person(name, email):
            continue
        accepted = r['review_status'] == 'accepted'
        yield dict(kind='workspace_ai_accept' if accepted else 'workspace_ai_reject',
                   change_type='confirm' if accepted else 'set_aside', case_id=r['case_id'],
                   subject=('workspace_ai_output', str(r['id'])), before=None, after=None,
                   actor=dict(name=name, email=email, user_id=str(r['reviewed_by_user_id'])), reason='', field='ai_output',
                   at=r['reviewed_at'], source_ref=f"workspace-ai:{r['id']}")


def merge_rejections(session, users):
    for r in _rows(session, "select id, case_id, entity_key_1, entity_key_2, rejected_by_user_id, created_at as rejected_at "
                            "from rejected_merge_pairs"):
        name, email = users.get(str(r['rejected_by_user_id']), ('', ''))
        if not is_person(name, email):
            continue
        yield dict(kind='merge_suggestion_reject', change_type='set_aside', case_id=r['case_id'],
                   subject=('entity_pair', f"{r['entity_key_1']},{r['entity_key_2']}"), before=None, after=None,
                   actor=dict(name=name, email=email), reason='', field='merge_suggestion', at=r['rejected_at'],
                   source_ref=f"rejected-merge:{r['id']}")


def _parts(item):
    """One item per changed field, so each field's pattern counts the change."""
    import hashlib
    from services.manual_changes import changed_paths

    def part(name, old, new):
        ref = f"{item['source_ref']}:{name}"
        if len(ref) > 200:
            ref = item['source_ref'][:150] + ':' + hashlib.sha1(name.encode()).hexdigest()[:16]
        return {**item, 'field': name, 'before': old, 'after': new, 'source_ref': ref}
    if item.get('per_field'):
        fields, old, new = item['per_field']
        for name in fields:
            yield part(name, old.get(name), new.get(name))
        return
    if item.get('diff') and isinstance(item.get('after'), dict):
        paths = changed_paths(item.get('before'), item['after'])
        if paths:
            for name, (old, new) in sorted(paths.items()):
                yield part(name, old, new)
            return
        # Saved with nothing changed: the person confirmed what was there.
        yield {**item, 'change_type': 'confirm', 'field': '(saved unchanged)'}
        return
    yield item


SOURCES = (adjudications, judgements, payment_labels, account_histories, statement_details, evidence_reviews,
           review_saves, graph_deletes, workspace_ai, merge_rejections)


def tests_here(item, actor):
    from services.manual_changes import is_test
    return is_test(item['case_id'], actor.get('email'), item.get('reason'))


def backfill(session, apply=False, sources=SOURCES):
    from postgres.models.manual_change import ManualChange
    from services.manual_changes import make_pattern_key, producer_for, record_change
    users = _users(session)
    from services.manual_changes import _ready
    done = ({ref for ref in session.scalars(select(ManualChange.source_ref).where(ManualChange.source_ref.is_not(None)))}
            if _ready(session) else set())
    if apply and not _ready(session):
        return dict(applied=False, error='the manual_changes table does not exist yet')
    kinds, patterns, tests, skipped, errors = Counter(), Counter(), Counter(), 0, []
    replaced = set()
    pending = 0
    for source in sources:
        try:
            for whole in source(session, users):
                for item in _parts(whole):
                    if item['source_ref'] in done:
                        skipped += 1
                        continue
                    done.add(item['source_ref'])
                    producer, layout = item.get('producer'), item.get('layout')
                    if producer is None and layout is None:
                        producer, layout = producer_for(session, *item['subject'])
                    key = make_pattern_key(item['kind'], item.get('field', ''), producer or '', layout or '')
                    actor = item['actor'] or {}
                    if tests_here(item, actor):
                        tests[item['kind']] += 1
                    kinds[item['kind']] += 1
                    if item['change_type'] != 'confirm' and not tests_here(item, actor):
                        patterns[key] += 1
                    replaces = None
                    if item.get('replaces_ref') and _ready(session):
                        # The record this save got when it could not be compared ("(not compared: ...)").
                        replaces = session.scalar(select(ManualChange.id).where(
                            ManualChange.source_ref.startswith(item['replaces_ref'], autoescape=True),
                            ManualChange.field.startswith('(not compared', autoescape=True)).limit(1))
                    if replaces is not None:
                        replaced.add(replaces)
                    if apply:
                        record_change(session, item['kind'], item['case_id'], item['subject'], item.get('before'),
                                      item.get('after'), actor, item.get('reason', ''), item.get('link', '') or '',
                                      change_type=item['change_type'], field=item.get('field', ''), producer=producer or '',
                                      layout=layout or '', source='backfill', historic=True, source_ref=item['source_ref'],
                                      at=item.get('at') or datetime.now(timezone.utc), replaces=replaces)
                        pending += 1
                        if pending >= 200:
                            session.commit()
                            pending = 0
        except Exception as exc:  # noqa: BLE001 - one source failing is reported, the rest still run
            log.exception('Backfill source %s failed', source.__name__)
            session.rollback()
            pending = 0  # the records of this source not yet committed are added by the next run (source_ref)
            errors.append(f'{source.__name__}: {type(exc).__name__}: {exc}'[:300])
    if apply:
        session.commit()
    return dict(applied=apply, kinds=dict(kinds), tests=dict(tests), patterns=len(patterns),
                changes=sum(patterns.values()), skipped_already_recorded=skipped, errors=errors,
                replaced_records=len(replaced),
                pattern_counts=dict(patterns.most_common()))
