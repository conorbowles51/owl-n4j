"""Manual changes become lesson work: one call records a person changing, confirming or setting aside what the
system produced, and the lessons inbox gets one line for it once the save has committed.

``record_change`` / ``record_confirmation`` are the only calls a screen needs. A route can use the ``records``
decorator instead, which calls ``record_change`` after the route has returned (its save committed). Nothing here ever
fails or slows a save: a failed record or append is logged, and ``--check`` (run by the watchdog) adds any recorded
change missing from the inbox. The inbox is ``MANUAL-CHANGES.jsonl`` (one JSON object per line, each with its id);
grouping by ``pattern_key`` and delivery to the lesson job happen outside the app (``manual-change-lessons.py``).

A judgement correction keeps its own inbox (``JUDGEMENT-CORRECTIONS.md``, same line format as before): it is recorded
here too, with ``after_commit`` writing the judgement line, and is marked as delivered by the judgement feed.
"""
import fcntl
import functools
import inspect
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import event, inspect as sa_inspect, select

log = logging.getLogger(__name__)
INBOX = Path(os.environ.get('LOUPE_MANUAL_CHANGE_INBOX', '/mnt/owl-data/fin-wt/headless/MANUAL-CHANGES.jsonl'))
# The automated-checks login and its own case: their changes are recorded, marked test, and never delivered.
JOBS_EMAILS = {e.strip().lower() for e in os.environ.get('LOUPE_JOBS_EMAILS', 'jobs-verify@loupe.invalid,ui-walkthrough@loupe.invalid').split(',')
               if e.strip()}
VERIFICATION_CASE = os.environ.get('LOUPE_VERIFICATION_CASE', 'cded78d0-e659-44cc-940d-d8f8c8012760')
CHANGE_TYPES = ('change', 'confirm', 'set_aside')
# Kinds another feed already delivers (the judgement inbox): recorded and counted, not delivered twice.
DELIVERED_ELSEWHERE = {'judgement_correct': 'judgement-lessons'}
# Phone lines carry ids, kinds, counts and links only (CB-INDEX rule 3): no values, names or message text.
PHONE_SOURCES = {'phone'}
_CLIP = 600


def make_pattern_key(kind, field='', producer='', layout=''):
    """kind | field changed | the reader or rule that produced the value | layout fingerprint or bank."""
    return '|'.join(' '.join(str(part or '').split()).replace('|', '/') for part in (kind, field, producer, layout))


def is_test(case_id, actor_email, reason):
    if (actor_email or '').strip().lower() in JOBS_EMAILS:
        return True
    return str(case_id or '') == VERIFICATION_CASE and 'test' in (reason or '').lower()


def _actor_fields(actor):
    if actor is None:
        return '', '', ''
    if isinstance(actor, dict):
        get = actor.get
    else:
        def get(name, default=None):
            return getattr(actor, name, default)
    return (str(get('name') or get('username') or ''), str(get('email') or ''),
            str(get('user_id') or get('id') or ''))


def _subject(subject):
    if subject is None:
        return '', ''
    if isinstance(subject, (tuple, list)):
        return str(subject[0] or ''), str(subject[1] or '')
    if isinstance(subject, dict):
        return str(subject.get('type') or ''), str(subject.get('id') or '')
    text = str(subject)
    return tuple(text.split(':', 1)) if ':' in text else ('', text)


def _jsonable(value):
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


def _uuid(value):
    try:
        return uuid.UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


_READY = {}


def _ready(session):
    bind = session.get_bind()
    key = id(bind)
    if key not in _READY:
        try:
            _READY[key] = sa_inspect(bind).has_table('manual_changes')
        except Exception:  # noqa: BLE001
            return False
    return _READY[key]


def record_change(session, kind, case_id, subject, before, after, actor, reason='', link='', pattern_key=None, *,
                  change_type='change', field='', producer='', layout='', source='app', committed=False,
                  historic=False, source_ref=None, after_commit=None, at=None):
    """Record one manual change. Returns the new row id, or None when nothing could be recorded (logged).

    ``committed=False`` (the default): the record joins the caller's transaction and the inbox line is written once
    that transaction commits; a rollback leaves neither. ``committed=True``: the caller's save has already committed
    (a route calling after its service), so the record is committed on its own and the line written at once.
    ``after_commit`` runs once the record is committed (the judgement inbox line uses it).
    """
    try:
        if change_type not in CHANGE_TYPES:
            raise ValueError(f'unknown change type {change_type!r}')
        from postgres.models.manual_change import ManualChange
        name, email, user_id = _actor_fields(actor)
        subject_type, subject_id = _subject(subject)
        key = pattern_key or make_pattern_key(kind, field, producer, layout)
        row = ManualChange(id=uuid.uuid4(), case_id=_uuid(case_id), kind=kind, change_type=change_type,
                           subject_type=subject_type[:40], subject_id=subject_id[:200], field=str(field or '')[:300],
                           producer=str(producer or '')[:300], layout=str(layout or '')[:300], pattern_key=key[:1000],
                           before=_jsonable(before), after=_jsonable(after), reason=str(reason or ''),
                           link=str(link or ''), actor_name=name[:300], actor_email=email[:300],
                           actor_user_id=user_id[:64], is_test=is_test(case_id, email, reason), historic=historic,
                           source=source, source_ref=source_ref,
                           created_at=at or datetime.now(timezone.utc))
        if not _ready(session):
            log.warning('manual_changes table missing: %s on %s not recorded', kind, subject_id)
            row = None
    except Exception:  # noqa: BLE001 - the person's save stands
        log.exception('Building the manual-change record %s failed', kind)
        row = None

    def deliver():
        if row is not None:
            try:
                append(as_line(row))
            except Exception:  # noqa: BLE001 - the watchdog's sync adds it
                log.exception('Appending manual change %s to the lessons inbox failed', row.id)
        # A step another feed owns (the judgement line) runs even when this record could not be made.
        if after_commit is not None:
            try:
                after_commit()
            except Exception:  # noqa: BLE001
                log.exception('After-commit step of manual change %s failed', kind)

    if committed:
        if row is not None:
            # A session of its own on the same database: committing the caller's session would expire the objects
            # its route is about to return, and roll back nothing of the caller's on a failure.
            from sqlalchemy.orm import Session
            try:
                with Session(bind=session.get_bind(), expire_on_commit=False) as own:
                    own.add(row)
                    own.commit()
            except Exception:  # noqa: BLE001
                log.exception('Recording manual change %s on %s failed', kind, row.subject_id)
                row = None
        deliver()
        return row.id if row is not None else None

    if row is not None:
        try:
            # A savepoint: a failed insert of the record never takes the person's save down with it.
            with session.begin_nested():
                session.add(row)
        except Exception:  # noqa: BLE001
            log.exception('Recording manual change %s on %s failed', kind, row.subject_id)
            row = None
    settled = []

    def on_commit(_session):
        if settled:
            return
        settled.append('committed')
        event.remove(session, 'after_soft_rollback', on_rollback)
        deliver()

    def on_rollback(_session, previous):
        if not previous.nested:  # a savepoint rolled back inside the save leaves the change standing
            settled.append('rolled back')

    event.listen(session, 'after_commit', on_commit, once=True)
    event.listen(session, 'after_soft_rollback', on_rollback)
    return row.id if row is not None else None


_CONSEQUENCE_KEYS = ('revision', 'case_id', 'pages', 'page_numbers')


def changed_paths(before, after, prefix=''):
    """{dotted path: (before, after)} for every leaf the after side sets that differs from before. Ids and revisions
    that change as a consequence of a save (``*_id``, ``revision``) are not fields a person changed."""
    out = {}
    if not isinstance(after, dict):
        return {prefix or 'value': (before, after)} if before != after else {}
    before = before if isinstance(before, dict) else {}
    for key, value in after.items():
        if key in _CONSEQUENCE_KEYS or str(key).endswith('_id') or str(key).endswith('_sha256'):
            continue
        path = f'{prefix}.{key}' if prefix else str(key)
        if isinstance(value, dict):
            out.update(changed_paths(before.get(key), value, path))
        elif before.get(key) != value:
            out[path] = (before.get(key), value)
    return out


def record_confirmation(session, kind, case_id, subject, value, actor, reason='', link='', pattern_key=None, **kw):
    """A person confirmed what the system did: recorded and counted per pattern, never delivered as a lesson."""
    kw.setdefault('change_type', 'confirm')
    return record_change(session, kind, case_id, subject, value, value, actor, reason, link, pattern_key, **kw)


def record_judgement_correction(session, item, statement=None, *, committed, actor=None):
    """A corrected judgement call: recorded here (counted, marked delivered by the judgement feed) and its line in
    ``JUDGEMENT-CORRECTIONS.md`` written after commit, in the judgement inbox's own unchanged format."""
    from services.financial import judgement_inbox
    ev = item.get('evidence') or {}
    corr = ev.get('correction') or {}

    def judgement_line():
        judgement_inbox.append_correction(session, item, statement=statement)

    return record_change(
        session, 'judgement_correct', item.get('case_id'), ('judgement', item.get('id')),
        ev.get('before') if ev.get('before') is not None else (corr.get('before') or ev.get('chosen')),
        corr.get('after'), actor or dict(name=item.get('resolved_by'), email=item.get('resolved_by_email')),
        item.get('resolution_reason') or '',
        f"/cases/{item.get('case_id')}/financial?document={item.get('source_document_id') or ''}"
        f"&judgement={item.get('id')}",
        field=item.get('target_key') or '', producer=item.get('rule_id') or '', committed=committed,
        source_ref=f"judgement:{item.get('id')}", after_commit=judgement_line)


def _clip(value):
    if value is None:
        return None
    text = json.dumps(value, default=str, ensure_ascii=False)
    return value if len(text) <= _CLIP else text[:_CLIP] + '…'


def as_line(row):
    phone = row.source in PHONE_SOURCES
    out = dict(id=str(row.id), at=(row.created_at or datetime.now(timezone.utc)).isoformat(timespec='seconds'),
               kind=row.kind, type=row.change_type, case=str(row.case_id or ''), subject_type=row.subject_type,
               subject_id=row.subject_id, field=row.field, producer=row.producer, layout=row.layout,
               pattern_key=row.pattern_key, link=row.link, test=bool(row.is_test), historic=bool(row.historic),
               source=row.source, actor='jobs' if (row.actor_email or '').lower() in JOBS_EMAILS else 'person')
    if not phone:
        out.update(before=_clip(row.before), after=_clip(row.after), reason=' '.join((row.reason or '').split())[:400])
    if row.kind in DELIVERED_ELSEWHERE:
        out['delivered_by'] = DELIVERED_ELSEWHERE[row.kind]
    return json.dumps(out, ensure_ascii=False, sort_keys=True) + '\n'


def _ids(text):
    ids = set()
    for raw in text.splitlines():
        try:
            ids.add(json.loads(raw)['id'])
        except (ValueError, KeyError, TypeError):
            continue
    return ids


def _known():
    try:
        return INBOX.read_text() if INBOX.exists() else ''
    except OSError:
        return ''


def append(text):
    """Append one inbox line once (the id decides), under an exclusive lock. Returns True when written."""
    ident = json.loads(text)['id']
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    with INBOX.open('a') as out:
        fcntl.flock(out.fileno(), fcntl.LOCK_EX)
        try:
            if f'"id": "{ident}"' in _known():
                return False
            out.write(text)
            out.flush()
        finally:
            fcntl.flock(out.fileno(), fcntl.LOCK_UN)
    return True


def missing(session):
    from postgres.models.manual_change import ManualChange as M
    known = _ids(_known())
    return [str(i) for i in session.scalars(select(M.id).order_by(M.created_at)) if str(i) not in known]


def sync(session):
    """Append every recorded change missing from the inbox (an append that failed). Returns the number appended."""
    from postgres.models.manual_change import ManualChange as M
    known = _ids(_known())
    added = 0
    for row in session.scalars(select(M).order_by(M.created_at).execution_options(yield_per=500)):
        if str(row.id) not in known:
            added += append(as_line(row))
    return added


def check(session):
    out = dict(inbox=str(INBOX), appended=0, error='')
    try:
        if not _ready(session):
            out['error'] = 'the manual_changes table does not exist yet'
            out['missing'] = []
            return out
        out['appended'] = sync(session)
    except Exception as exc:  # noqa: BLE001 - shown on the status board
        out['error'] = f'{type(exc).__name__}: {exc}'
    try:
        out['missing'] = missing(session)
    except Exception as exc:  # noqa: BLE001
        out['missing'] = []
        out['error'] = out['error'] or f'{type(exc).__name__}: {exc}'
    return out


# ---- the route decorator ---------------------------------------------------------------------------------------

_NOT_FIELDS = {'reason', 'case_id', 'expected_revision', 'revision', 'expected_version', 'version', 'note'}


def _body(kwargs):
    from pydantic import BaseModel
    for value in kwargs.values():
        if isinstance(value, BaseModel):
            return value.model_dump(mode='json', exclude_unset=True)
    for value in kwargs.values():
        if isinstance(value, dict):
            return value
    return {}


def _actor_from(kwargs):
    for name in ('current_user', 'current_db_user', 'user', 'db_user'):
        if kwargs.get(name) is not None:
            return kwargs[name]
    for value in kwargs.values():
        if hasattr(value, 'email') and hasattr(value, 'id'):
            return value
    return None


def _session_from(kwargs):
    """A session of the decorator's own (closed by it): on the route's database when the route has one, so the
    route's session and the objects it returns are never touched."""
    from sqlalchemy.orm import Session
    for value in kwargs.values():
        if isinstance(value, Session):
            return Session(bind=value.get_bind(), expire_on_commit=False), True
    return _own_session(), True


def _own_session():
    """A session of its own, for a route that has none (its store is the graph)."""
    from postgres.session import _get_session_local
    return _get_session_local()()


# The subject of a route's change, from its path arguments or its body: the first id it names.
_SUBJECT_KEYS = (('transaction_id', 'transaction'), ('child_key', 'node'), ('parent_key', 'node'),
                 ('node_key', 'node'), ('judgement_id', 'judgement'), ('source_document_id', 'source_document'),
                 ('document_id', 'source_document'), ('source_id', 'source_document'), ('account_id', 'account'),
                 ('evidence_file_id', 'evidence_file'), ('file_id', 'evidence_file'), ('candidate_id', 'candidate'),
                 ('nomination_id', 'model_nomination'), ('rule_id', 'category_rule'), ('item_id', 'batch_item'),
                 ('confirmation_id', 'layout_memory'), ('trail_id', 'money_trail'))


def _infer_subject(kwargs, body):
    for source in (kwargs, body or {}):
        for key, kind in _SUBJECT_KEYS:
            if source.get(key) is not None:
                return kind, str(source[key])
    for key, kind in _SUBJECT_KEYS:
        many = (body or {}).get(key + 's') or (body or {}).get(key.replace('_id', '_ids'))
        if isinstance(many, list) and many:
            return kind, str(many[0]) + (f' (+{len(many) - 1})' if len(many) > 1 else '')
    return '', ''


def _plain(kwargs):
    """The route's simple arguments (a reason sent as a lone body field, an action, an id)."""
    out = {}
    for key, value in kwargs.items():
        if key == 'case_id' or value is None:
            continue
        if isinstance(value, (str, int, float, bool, uuid.UUID)):
            out[key] = str(value) if isinstance(value, uuid.UUID) else value
    return out


def _call(spec, ctx, default=None):
    if spec is None:
        return default
    return spec(ctx) if callable(spec) else spec


def records(kind, change_type='change', *, subject_type='', subject=None, field=None, before=None, after=None,
            reason=None, link=None, producer=None, case=None, when=None):
    """Record a route's successful call as a manual change (see module docstring).

    Every option may be a value or a function of ``ctx`` (a dict: the route's keyword arguments as ``kw``, the
    request body as ``body``, the route's result as ``result``, the database session as ``db``). ``subject``
    defaults to the first path argument ending ``_id`` or ``_key``; ``after`` to the request body; ``before`` to
    the result's ``before`` when it has one; ``field`` to the body's keys; ``producer`` to the reader and layout of
    the subject (``producer_for``). ``when`` returning False skips the record (an action that changed nothing).
    """
    def decorate(fn):
        def note(kwargs, result):
            try:
                ctx = dict(kw=kwargs, body=_body(kwargs) or {}, result=result)
                if (getattr(result, 'status_code', 200) or 200) >= 400:
                    return  # a refusal returned as a response rather than raised: nothing was saved
                if when is not None and not when(ctx):
                    return
                db, own = _session_from(kwargs)
                ctx['db'] = db
                try:
                    name = _call(kind, ctx)
                    body = ctx['body']
                    if subject is not None:
                        stype, sid = _call(subject_type, ctx) or '', str(_call(subject, ctx) or '')
                    else:
                        stype, sid = _infer_subject(kwargs, body)
                        stype = _call(subject_type, ctx) or stype
                    res = result if isinstance(result, dict) else {}
                    case_id = _call(case, ctx) if case is not None else (
                        kwargs.get('case_id') or body.get('case_id') or res.get('case_id'))
                    fld = _call(field, ctx) if field is not None else ','.join(
                        sorted(k for k in (body or _plain(kwargs)) if k not in _NOT_FIELDS))
                    prod, lay = (_call(producer, ctx) if producer is not None
                                 else producer_for(db, stype, sid))
                    why = _call(reason, ctx) if reason is not None else (body.get('reason') or kwargs.get('reason'))
                    if field is None and before is None and after is None and isinstance(res.get('before'), dict) \
                            and isinstance(res.get('after'), dict):
                        # The service says what it changed: one record per changed field, so each field's pattern
                        # counts it.
                        paths = changed_paths(res['before'], res['after'])
                        if paths:
                            for path, (old, new) in sorted(paths.items()):
                                record_change(db, name, case_id, (stype, sid), old, new, _actor_from(kwargs),
                                              why if isinstance(why, str) else '',
                                              _call(link, ctx) if link is not None else _default_link(case_id, stype, sid),
                                              change_type=_call(change_type, ctx), field=path, producer=prod,
                                              layout=lay, committed=True)
                            return
                    record_change(
                        db, name, case_id, (stype, sid),
                        _call(before, ctx) if before is not None else res.get('before'),
                        _call(after, ctx) if after is not None else (body or _plain(kwargs)),
                        _actor_from(kwargs), why if isinstance(why, str) else '',
                        _call(link, ctx) if link is not None else _default_link(case_id, stype, sid),
                        change_type=_call(change_type, ctx), field=fld, producer=prod, layout=lay,
                        committed=True)
                finally:
                    if own:
                        db.close()
            except Exception:  # noqa: BLE001 - the person's save stands
                log.exception('Recording the manual change for %s failed', getattr(fn, '__name__', fn))

        config = dict(kind=kind, change_type=change_type, subject_type=subject_type, subject=subject, field=field,
                      before=before, after=after, reason=reason, link=link, producer=producer, case=case, when=when)
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapped(*args, **kwargs):
                result = await fn(*args, **kwargs)
                from starlette.concurrency import run_in_threadpool
                await run_in_threadpool(note, kwargs, result)
                return result
        else:
            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                result = fn(*args, **kwargs)
                note(kwargs, result)
                return result
        wrapped.manual_change = config  # read by the per-kind tests and the inventory
        return wrapped
    return decorate


def _default_link(case_id, subject_type, subject_id):
    if not case_id:
        return ''
    if subject_type in ('transaction', 'source_document', 'evidence_file', 'account', 'judgement'):
        return f'/cases/{case_id}/financial?{subject_type}={subject_id}'
    return f'/cases/{case_id}'


def _choice_producer(choices, statement_id):
    if not isinstance(choices, list):
        return '', ''
    choice = next((c for c in choices if isinstance(c, dict) and c.get('id') == statement_id), None)
    if choice is None and len(choices) == 1 and isinstance(choices[0], dict):
        choice = choices[0]
    if not choice:
        return '', ''
    return (str(choice.get('layout_id') or choice.get('document_kind') or ''),
            str(choice.get('layout_fingerprint') or choice.get('institution') or ''))


def producer_for(session, subject_type, subject_id):
    """(reader or rule that produced the value, layout fingerprint or bank) for a subject, or ('', '')."""
    try:
        from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialTransaction
        ident = _uuid(str(subject_id or '').split('#', 1)[0].split(' ', 1)[0])
        if ident is None or session is None:
            return '', ''
        D = FinancialSourceDocument
        where = None
        if subject_type == 'batch_item':
            from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
            file_id = session.scalar(select(Item.file_id).where(Item.id == ident))
            if file_id is None:
                return '', ''
            subject_type, ident = 'evidence_file', file_id
        if subject_type == 'transaction':
            document = session.scalar(select(FinancialTransaction.source_document_id)
                                      .where(FinancialTransaction.id == ident))
            where = D.id == document if document is not None else None
        elif subject_type == 'source_document':
            where = D.id == ident
        elif subject_type == 'evidence_file':
            where = D.evidence_file_id == ident
        elif subject_type == 'account':
            return '', session.scalar(select(FinancialAccount.institution_name)
                                      .where(FinancialAccount.id == ident)) or ''
        elif subject_type == 'judgement':
            from postgres.models.financial_judgements import FinancialJudgement as J
            return session.scalar(select(J.rule_id).where(J.id == ident)) or '', ''
        if where is None:
            return '', ''
        # Only the columns needed: a statement's metadata holds its whole reading (up to megabytes).
        original = D.metadata_['statement_import_original']
        row = session.execute(select(D.parser_name, D.parser_version, D.institution_name,
                                     original['statement_choices'], original['statement_id'])
                              .where(where).order_by(D.created_at.desc()).limit(1)).first()
        if row is None:
            if subject_type == 'evidence_file':
                # Not saved yet: the batch that prepared the file names the bank it read.
                from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
                statement = str(subject_id or '').partition('#')[2]
                query = select(Item.summary['institution']).where(Item.file_id == ident)
                if statement:
                    query = query.where(Item.statement_key == statement)
                bank = session.scalar(query.limit(1))
                return '', str(bank or '')
            return '', ''
        parser_name, parser_version, institution, choices, statement_id = row
        # A statement saved from a review was read by a layout reader: that reader is the producer, not the
        # review's own format version.
        layout_reader, layout = _choice_producer(choices, statement_id)
        if layout_reader:
            return layout_reader, layout or institution or ''
        return f'{parser_name}@{parser_version}', institution or ''
    except Exception:  # noqa: BLE001
        log.exception('Finding the producer of %s %s failed', subject_type, subject_id)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return '', ''


if __name__ == '__main__':
    from postgres.session import _get_session_local
    with _get_session_local()() as db:
        if '--backfill' in sys.argv:
            from services.manual_changes_backfill import backfill
            print(json.dumps(backfill(db, apply='--apply' in sys.argv)))
        elif '--check' in sys.argv:
            print(json.dumps(check(db)))
        else:
            print('appended', sync(db))
