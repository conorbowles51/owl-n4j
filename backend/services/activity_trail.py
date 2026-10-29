"""Who did what, from where: the append-only activity trail.

Every request carries its source (browser address, user agent, a fingerprint of
the sign-in, and the screen that sent it) in a context variable set by
``ActivityContextMiddleware``. ``record`` writes one ``activity_events`` row
with that source.

Source address: the frontend's Vite server proxies ``/api`` to this backend on
127.0.0.1 and sets ``X-Real-IP`` (overwritten, never appended) and
``X-Forwarded-For`` from the browser's socket. Those headers are believed only
when the connection comes from the loopback address; uvicorn's own proxy-header
handling (trusting 127.0.0.1 only) already replaces the client address with the
right-most X-Forwarded-For entry, so either way the address is the browser's.
A request that reaches the backend directly keeps its own socket address.

Recording never blocks the action (Rule 0): a failure is logged and swallowed.
Nothing here stores passwords, tokens or document contents; ``session_ref`` is
the first 16 hex characters of the token's sha256.
"""
import contextvars
import hashlib
import ipaddress
import logging
from datetime import datetime
from uuid import UUID

log = logging.getLogger(__name__)

LOOPBACK = frozenset({'127.0.0.1', '::1', 'localhost'})
SYSTEM_ADDRESS = 'system'
# Screens that can put files in Financial; the frontend names itself in X-Loupe-Origin.
ORIGINS = {
    'evidence_toolbar': 'Evidence toolbar (Send to Financial)',
    'financial_statement_files': 'Financial · statement files',
    'financial_upload': 'Financial · upload',
    'financial_review_queue': 'Financial · review queue',
    'evidence_upload': 'Evidence upload',
    'automatic': 'Automatic (statement detection)',
}
ACTIONS = {
    'login_success': 'Signed in',
    'login_failure': 'Sign-in failed',
    'logout': 'Signed out',
    'evidence_upload': 'Uploaded evidence',
    'financial_send': 'Added files to Financial',
    'financial_auto_add': 'Added to Financial automatically',
}

_context = contextvars.ContextVar('loupe_activity_context', default=None)


def _clean_ip(value):
    value = (value or '').strip()
    if value.startswith('::ffff:'):
        value = value[7:]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def client_address(socket_host, headers):
    """The browser's address. ``headers`` maps lower-case names to str values."""
    host = socket_host or ''
    if host in LOOPBACK:
        real = _clean_ip(headers.get('x-real-ip'))
        if real:
            return real
        forwarded = [_clean_ip(part) for part in (headers.get('x-forwarded-for') or '').split(',')]
        forwarded = [part for part in forwarded if part]
        if forwarded:
            return forwarded[-1]
    return _clean_ip(host) or host or None


def token_ref(token):
    return hashlib.sha256(token.encode()).hexdigest()[:16] if token else None


def session_ref(headers, cookies=None):
    token = None
    authorization = headers.get('authorization') or ''
    if authorization.lower().startswith('bearer '):
        token = authorization[7:].strip()
    if not token and cookies:
        token = cookies.get('access_token')
    return token_ref(token)


def _cookies(raw):
    jar = {}
    for part in (raw or '').split(';'):
        name, _, value = part.strip().partition('=')
        if name:
            jar[name] = value
    return jar


def context_from_scope(scope):
    headers = {k.decode('latin1').lower(): v.decode('latin1') for k, v in scope.get('headers') or []}
    client = scope.get('client')
    origin = (headers.get('x-loupe-origin') or '').strip()[:64] or None
    return dict(address=client_address(client[0] if client else None, headers),
                user_agent=(headers.get('user-agent') or '')[:1000] or None,
                session_ref=session_ref(headers, _cookies(headers.get('cookie'))),
                origin=origin, path=(scope.get('path') or '')[:255] or None)


class ActivityContextMiddleware:
    """Pure ASGI: sets the request's source for ``record``; changes nothing else."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        token = _context.set(context_from_scope(scope))
        try:
            return await self.app(scope, receive, send)
        finally:
            _context.reset(token)


def current_context():
    return _context.get()


def _person(user):
    if user is None:
        return None, None, None
    if isinstance(user, dict):
        identifier = user.get('user_id') or user.get('id')
        return identifier, user.get('name'), user.get('email')
    return (getattr(user, 'user_id', None) or getattr(user, 'id', None), getattr(user, 'name', None),
            getattr(user, 'email', None))


def _uuid(value):
    if value in (None, ''):
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def build(action, *, user=None, case_id=None, details=None, origin=None, system=False, user_email=None,
          session=None):
    from postgres.models.activity_event import ActivityEvent
    context = {} if system else (current_context() or {})
    user_id, name, email = _person(user)
    return ActivityEvent(action=action, user_id=_uuid(user_id), user_name=name, user_email=email or user_email,
        case_id=_uuid(case_id), source_address=SYSTEM_ADDRESS if system else context.get('address'),
        user_agent=None if system else context.get('user_agent'),
        session_ref=None if system else (session or context.get('session_ref')),
        origin=origin or ('automatic' if system else context.get('origin')),
        request_path=None if system else context.get('path'), details=details or {})


def record(action, *, db=None, commit=False, **kwargs):
    """Append one event. With ``db``, inside its transaction (savepoint; ``commit`` commits it,
    for an action that has already committed its own work); else in a session of its own.

    Never raises: the action this records must keep working even if recording fails.
    """
    try:
        event = build(action, **kwargs)
        if db is not None:
            with db.begin_nested():
                db.add(event)
                db.flush()
            if commit:
                db.commit()
        else:
            from postgres.session import _get_session_local
            with _get_session_local()() as own:
                own.add(event)
                own.commit()
        log.info('activity %s user=%s address=%s case=%s', action, event.user_email or '-',
                 event.source_address or '-', event.case_id or '-')
        return True
    except Exception:
        log.exception('Activity trail: could not record %s (the action itself is unaffected)', action)
        return False


def file_entries(files):
    """The file facts kept for an event: id, name, sha256, size. Never contents."""
    out = []
    for file in files:
        get = file.get if isinstance(file, dict) else (lambda key, f=file: getattr(f, key, None))
        out.append(dict(id=str(get('id')) if get('id') else None,
                        filename=get('original_filename') or get('filename'),
                        sha256=get('sha256'), size=get('size')))
    return out


# --- reading --------------------------------------------------------------------

def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def event_dict(event):
    return dict(id=event.id, at=_iso(event.at), action=event.action, action_label=ACTIONS.get(event.action, event.action),
        user_id=str(event.user_id) if event.user_id else None, user_name=event.user_name, user_email=event.user_email,
        case_id=str(event.case_id) if event.case_id else None, source_address=event.source_address,
        user_agent=event.user_agent, session_ref=event.session_ref, origin=event.origin,
        origin_label=ORIGINS.get(event.origin or '', event.origin), request_path=event.request_path,
        details=event.details or {})


def list_events(db, *, case_id=None, user=None, action=None, since=None, until=None, limit=200, offset=0):
    """Newest first. ``user`` matches email (case-insensitive), name, or user id."""
    from sqlalchemy import func, or_, select
    from postgres.models.activity_event import ActivityEvent as E
    query = select(E)
    if case_id:
        query = query.where(E.case_id == _uuid(case_id))
    if user:
        conditions = [func.lower(E.user_email) == user.lower(), func.lower(E.user_name) == user.lower()]
        if _uuid(user):
            conditions.append(E.user_id == _uuid(user))
        query = query.where(or_(*conditions))
    if action:
        query = query.where(E.action.in_(action if isinstance(action, (list, tuple)) else [action]))
    if since:
        query = query.where(E.at >= since)
    if until:
        query = query.where(E.at < until)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(E.at.desc(), E.id.desc()).limit(limit).offset(offset))
    return dict(events=[event_dict(e) for e in rows], total=total, limit=limit, offset=offset)


# --- provenance shown in Evidence and Financial -----------------------------------

AUTO_REASONS = {
    'detected': 'statement detection',
    'evidence_backfill': 'statement detection of earlier uploads',
    'automatic': 'statement detection',
}


def _event_files(event):
    return {f.get('id') for f in (event.details or {}).get('files') or [] if f.get('id')}


def file_provenance(db, *, case_id, file_ids):
    """Per file: who uploaded it, and (when it is in Financial) who added it, when and from where.

    Only what was recorded: the activity trail first (it has the address and
    screen), then the batch that holds the file (its recorded actor and time),
    then the Financial selection mark. Nothing is filled in when none of them
    names a person: ``added_by`` stays null.
    """
    from sqlalchemy import select
    from postgres.models.activity_event import ActivityEvent as E
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch
    from postgres.models.user import User
    from services.financial.file_scope import financial_file_ids
    from services.financial.file_visibility import financial_file_visibility
    case_id = _uuid(case_id)
    wanted = [i for i in (_uuid(f) for f in file_ids) if i]
    files = list(db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id, EvidenceFile.id.in_(wanted)))) if wanted else []
    if not files:
        return {}
    people = {u.id: u.name or u.email for u in db.scalars(select(User).where(
        User.id.in_({f.created_by_id for f in files if f.created_by_id})))} if any(f.created_by_id for f in files) else {}
    in_financial = financial_file_ids(db, case_id=case_id)
    events = list(db.scalars(select(E).where(E.case_id == case_id, E.action.in_(('financial_send', 'financial_auto_add', 'evidence_upload')))
                             .order_by(E.at, E.id)))
    batches = list(db.scalars(select(Batch).where(Batch.case_id == case_id).order_by(Batch.created_at, Batch.id)))
    out = {}
    for file in files:
        key = str(file.id)
        upload = next((e for e in events if e.action == 'evidence_upload' and key in _event_files(e)), None)
        entry = dict(file_id=key, uploaded_by=people.get(file.created_by_id), uploaded_at=_iso(file.created_at),
                     uploaded_from=upload.source_address if upload else None,
                     in_financial=file.id in in_financial and not financial_file_visibility(file)['financial_removed'],
                     added_by=None, added_at=None, added_automatically=False, auto_reason=None,
                     added_from=None, added_via=None, batch_id=None, recorded_by='none')
        if entry['in_financial']:
            sent = next((e for e in events if e.action in ('financial_send', 'financial_auto_add') and key in _event_files(e)), None)
            if sent is not None:
                automatic = sent.action == 'financial_auto_add'
                reason = (sent.details or {}).get('reason')
                entry.update(added_by=None if automatic else (sent.user_name or sent.user_email), added_at=_iso(sent.at),
                    added_automatically=automatic, auto_reason=AUTO_REASONS.get(reason, reason) if automatic else None,
                    added_from=None if automatic else sent.source_address, added_via=ORIGINS.get(sent.origin or '', sent.origin),
                    batch_id=(sent.details or {}).get('batch_id'), recorded_by='activity_trail')
            else:
                holder = next(((b, f) for b in batches for f in (b.files or [])
                               if key in (f.get('source_id'), f.get('file_id'))), None)
                if holder is not None:
                    batch, item = holder
                    auto = (item.get('auto_read') or {}) if (batch.actor or {}).get('auto_read') else {}
                    reason = auto.get('reason')
                    # A file a person put in Financial ("financial_upload", "unread_action") joined the automatic
                    # batch on their request; only detection is "automatic". Its requester is not named in the batch.
                    detected = reason in AUTO_REASONS
                    entry.update(added_at=auto.get('at') or _iso(batch.created_at), batch_id=str(batch.id),
                        added_automatically=detected, auto_reason=AUTO_REASONS.get(reason) if detected else None,
                        added_by=None if detected else ((auto.get('requested_by') or {}).get('name') if auto
                                                        else (batch.actor or {}).get('name')),
                        recorded_by='batch')
                else:
                    mark = (file.metadata_ or {}).get('financial_workspace') or {}
                    if mark.get('selected_at'):
                        person = db.get(User, _uuid(mark.get('selected_by'))) if _uuid(mark.get('selected_by')) else None
                        entry.update(added_at=mark.get('selected_at'), added_by=(person.name or person.email) if person else None,
                                     recorded_by='selection_mark')
        out[key] = entry
    return out


def batch_sources(db, *, case_id, batch_ids):
    """For each batch: the address and screen it was sent from, when the trail has it."""
    from sqlalchemy import select
    from postgres.models.activity_event import ActivityEvent as E
    wanted = {str(b) for b in batch_ids}
    out = {}
    for event in db.scalars(select(E).where(E.case_id == _uuid(case_id), E.action.in_(('financial_send', 'financial_auto_add')))
                            .order_by(E.at, E.id)):
        batch = (event.details or {}).get('batch_id')
        if batch in wanted and batch not in out:
            out[batch] = dict(source_address=event.source_address, origin=event.origin,
                              origin_label=ORIGINS.get(event.origin or '', event.origin),
                              user_name=event.user_name, at=_iso(event.at))
    return out
