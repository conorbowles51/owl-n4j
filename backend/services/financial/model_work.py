"""Work a model did for a person, recorded as the model's until a person confirms it.

A reading made by a model (a payee read off a cheque or a page image, a statement transcribed from the page, a
decision taken while working the import queue) is recorded and shown as the model's, with what it read from, until
a person confirms it. It is never saved under a person's name.

The origin is a field on the stored actor record, never parsed from a name:

    {"kind": "model", "model": "Claude", "model_id": "claude-opus-5-5", "for": {"name": ..., "user_id": ...},
     "at": "2026-10-29T05:40:00+00:00", "citation": {"page": 4, "source_document_id": ...}, "how": "..."}

The actor that carries it is named "Claude (for <person>)": the person's user id and address stay on it because the
work ran under their account and their case permissions, but the name it shows is the model's.

What the origin decides, and what it never decides:
- a person's entry or confirmation outranks it, and it outranks a rule's suggestion;
- it never changes a value, a sum, a flow, a search result or a proof class (proof class is computed from the
  document, never from who saved it).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

MODEL_KIND = 'model'
DEFAULT_MODEL = 'Claude'

# How records saved before the origin field existed named the model's work. Read only by the migration
# (services.financial.model_work_migration), which replaces the name with the model's and keeps this text in
# origin.recorded_as; nothing else may decide anything from an actor's name.
LEGACY_NAME_MARK = '(via Claude)'


class ModelWorkError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def model_origin(*, for_name: str, for_user_id: Any = None, model: str = DEFAULT_MODEL, model_id: str = '',
                 citation: Optional[Mapping[str, Any]] = None, how: str = '', at: Optional[str] = None) -> dict:
    """The origin of one piece of model work. ``citation``: what it was read from (page, image, file), when known."""
    if not str(for_name or '').strip():
        raise ModelWorkError('Model work is done for a person; say whom.')
    if not str(model or '').strip():
        raise ModelWorkError('Name the model that did the work.')
    origin = {'kind': MODEL_KIND, 'model': str(model).strip(),
              'for': {'name': str(for_name).strip(), 'user_id': str(for_user_id) if for_user_id else None},
              'at': at or datetime.now(timezone.utc).isoformat()}
    if model_id:
        origin['model_id'] = str(model_id)
    if citation:
        origin['citation'] = {str(k): v for k, v in dict(citation).items() if v not in (None, '')}
    if how:
        origin['how'] = ' '.join(str(how).split())
    return origin


def model_name(origin: Mapping[str, Any]) -> str:
    """The name the work is shown under: the model's, with the person it was done for."""
    return f"{origin.get('model') or DEFAULT_MODEL} (for {(origin.get('for') or {}).get('name') or 'a person'})"


def model_actor(*, for_name: str, for_email: str, for_user_id: Any = None, model: str = DEFAULT_MODEL,
                model_id: str = '', citation: Optional[Mapping[str, Any]] = None, how: str = ''):
    """The actor for work a model does through the product's own paths."""
    from services.financial.decisions import Actor
    import uuid
    origin = model_origin(for_name=for_name, for_user_id=for_user_id, model=model, model_id=model_id,
                          citation=citation, how=how)
    user_id = for_user_id if for_user_id is None or isinstance(for_user_id, uuid.UUID) else uuid.UUID(str(for_user_id))
    return Actor(name=model_name(origin), email=for_email, user_id=user_id, origin=origin)


def is_model(value: Any) -> bool:
    """True for a model origin, an actor carrying one, or a stored record carrying one."""
    if value is None:
        return False
    origin = getattr(value, 'origin', None) if not isinstance(value, Mapping) else (
        value if value.get('kind') == MODEL_KIND else value.get('origin'))
    return isinstance(origin, Mapping) and origin.get('kind') == MODEL_KIND


def origin_of(record: Any) -> Optional[dict]:
    """The model origin stored on a record (an actor dict, a history entry), or None for a person or a rule."""
    if isinstance(record, Mapping) and isinstance(record.get('origin'), Mapping) and \
            record['origin'].get('kind') == MODEL_KIND:
        return dict(record['origin'])
    return None


def origin_field(actor) -> dict:
    """``{'origin': ...}`` for a model actor and ``{}`` for anyone else, to spread into a stored actor record so a
    person's record stays exactly as it was."""
    origin = getattr(actor, 'origin', None)
    return {'origin': dict(origin)} if origin else {}


def actor_record(actor, **extra) -> dict:
    """An actor as stored on a record: user id, name, address, and the origin when a model did the work."""
    record = dict(user_id=str(actor.user_id) if actor.user_id else None, name=actor.name, **extra)
    if getattr(actor, 'email', None) and 'email' not in record:
        record['email'] = actor.email
    if getattr(actor, 'origin', None):
        record['origin'] = dict(actor.origin)
    return record


def actor_from_record(record: Mapping[str, Any]):
    """The Actor a stored actor record describes, origin included."""
    from services.financial.decisions import Actor
    import uuid
    user_id = record.get('user_id')
    return Actor(name=record['name'], email=record.get('email') or '',
                 user_id=uuid.UUID(str(user_id)) if user_id not in (None, '', 'None') else None,
                 origin=origin_of(record))


def require_person(actor, what: str = 'confirm work') -> None:
    """Only a person confirms or corrects model work; a model confirming its own reading confirms nothing."""
    if is_model(actor):
        raise ModelWorkError(f'Only a person can {what}. {actor.name} did this work; a person confirms it.', 403)


def citation_text(origin: Mapping[str, Any]) -> str:
    citation = (origin or {}).get('citation') or {}
    parts = []
    if citation.get('file'):
        parts.append(str(citation['file']))
    if citation.get('page'):
        parts.append(f"page {citation['page']}")
    if citation.get('image'):
        parts.append(f"image {citation['image']}")
    return ', '.join(parts)


def describe(origin: Mapping[str, Any], act: str = 'Read') -> str:
    """'Read by Claude · not confirmed', the words the investigator sees beside the value."""
    return f"{act} by {origin.get('model') or DEFAULT_MODEL} · not confirmed"


def explanation(origin: Mapping[str, Any], act: str = 'Read', reason: str = '') -> str:
    """The longer form shown on hover and in the export: who, for whom, when, from what, and why."""
    when = str(origin.get('at') or '')[:10]
    text = f"{act} by {origin.get('model') or DEFAULT_MODEL} for {(origin.get('for') or {}).get('name') or 'a person'}"
    text += (f' on {when}' if when else '') + '; not confirmed by a person.'
    cited = citation_text(origin)
    if cited:
        text += f' Read from {cited}.'
    if reason:
        text += ' ' + reason.strip()
    return text
