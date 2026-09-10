"""Transaction-local audit attribution after successful case authorization."""
import json
from uuid import UUID
from sqlalchemy import event, text
from sqlalchemy.orm import Session

_KEY='loupe.authorized_audit_context'


def _apply(connection, value):
    if connection.dialect.name=='postgresql':
        connection.execute(text("SELECT set_config('loupe.audit_context', :context, true)"),
            {'context':json.dumps(value,separators=(',',':'))})


@event.listens_for(Session,'after_begin')
def _restore_audit_context(session, transaction, connection):
    # Transactions begun after an explicit commit in the same authorized request
    # must keep attribution. SET LOCAL cannot leak to a pooled connection.
    value=session.info.get(_KEY)
    if value is not None:_apply(connection,value)


def set_authorized_audit_context(session, *, case_id, user):
    if not isinstance(session,Session) or session.get_bind().dialect.name!='postgresql':
        return
    value={'case_id':str(UUID(str(case_id))),
        'actor':{'user_id':str(UUID(str(user.id))),'name':user.name,'email':user.email}}
    session.info[_KEY]=value
    _apply(session.connection(),value)
