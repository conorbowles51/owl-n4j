"""Record successful export preparation before handing bytes to the HTTP response."""
import hashlib
import json
import re
from uuid import UUID, uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session


def record_prepared_export(engine, *, case_id, kind, content, scope, actor):
    # Call only after case authorization and successful archive construction.
    case_id=UUID(str(case_id))
    if kind not in ('ledger_exports','trace_support_exports') or not isinstance(content,bytes) or not content:
        raise ValueError('Invalid prepared export.')
    if not isinstance(scope,dict) or len(json.dumps(scope,allow_nan=False).encode())>65536:
        raise ValueError('Invalid prepared export scope.')
    if (not isinstance(actor,dict) or set(actor)!={'id','name','email'}
        or any(not isinstance(actor[key],str) for key in actor)
        or not actor['id'].strip() or not actor['email'].strip()):
        raise ValueError('Prepared export needs its authenticated actor.')
    actor_id=str(UUID(actor['id']))
    identity=str(uuid4())
    body=dict(capture_policy='20260910_audit_source_exports',source_table=kind,
        source_id=identity,operation='EXPORT_PREPARED',actor_basis='authorized_request',
        actor={'user_id':actor_id,'name':actor['name'],'email':actor['email']},reason=None,before=None,
        after=dict(artifact_sha256=hashlib.sha256(content).hexdigest(),byte_count=len(content),scope=scope,
            delivery_status='prepared_not_delivery_confirmed'))
    # Separate transaction: never commit other pending state in the request's DB
    # session. The captured archive necessarily predates this preparation event.
    with Session(engine) as session:
        with session.begin():
            receipt=session.scalar(text('SELECT append_financial_audit_event(:case_id,CAST(:body AS jsonb))'),
                {'case_id':case_id,'body':json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)})
            if (not isinstance(receipt,dict) or type(receipt.get('sequence')) is not int or receipt['sequence']<1
                or not isinstance(receipt.get('entry_sha256'),str) or re.fullmatch(r'[a-f0-9]{64}',receipt['entry_sha256']) is None):
                raise RuntimeError('Prepared export audit receipt is inconsistent.')
    return dict(export_id=identity,**receipt)
