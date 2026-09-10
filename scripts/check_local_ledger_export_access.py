"""Exercise real case:view authorization with temporary isolated local users.

Creates only synthetic users/membership and removes them in finally. No ledger or
evidence writes. Refuses any database target other than the fixed local sandbox.
"""
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4
import httpx
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from postgres.models.user import User
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import GlobalRole, CaseMembershipRole

fixture = json.loads((root / 'data/local-runtime/coverage-check.json').read_text())
case_id = UUID(fixture['case_id'])
engine = create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
user_id = uuid4()
email = f'local-export-access-{user_id}@example.invalid'
reports = {}
try:
    with Session(engine) as db:
        owner = db.scalar(select(User).where(User.email == 'loupe-local@example.com'))
        db.add(User(id=user_id, email=email, name='LOCAL TEST export authorization',
                    password_hash=owner.password_hash, global_role=GlobalRole.user, is_active=True))
        owner_id = owner.id
        db.commit()
    with httpx.Client(base_url='http://127.0.0.1:58002', timeout=60) as client:
        login = client.post('/api/auth/login', json={'username': email, 'password': 'Loupe-local-test-2026'})
        login.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
        def check(name, status):
            response = client.get('/api/financial/ledger-export', params={'case_id': str(case_id)})
            assert response.status_code == status, (name, response.status_code)
            assert ('application/zip' in response.headers.get('content-type', '')) == (status == 200)
            totals = client.get('/api/financial/ledger-working-summary', params={'case_id': str(case_id)})
            assert totals.status_code == status, (name, 'working totals', totals.status_code)
            if status == 200:
                assert totals.json()['population'] == 'working'
            reports[name] = status
            reports[name + '_working_totals'] = totals.status_code
        check('non_member', 403)
        with Session(engine) as db:
            db.add(CaseMembership(case_id=case_id, user_id=user_id, membership_role=CaseMembershipRole.collaborator,
                permissions={'case': {'view': False, 'edit': True}}, added_by_user_id=owner_id))
            db.commit()
        check('member_without_view', 403)
        with Session(engine) as db:
            membership = db.get(CaseMembership, (case_id, user_id))
            membership.permissions = {'case': {'view': True, 'edit': False}}
            db.commit()
        check('view_only_member', 200)
        with Session(engine) as db:
            db.delete(db.get(CaseMembership, (case_id, user_id)))
            db.commit()
        check('membership_revoked_same_token', 403)
finally:
    with Session(engine) as db:
        db.execute(delete(CaseMembership).where(CaseMembership.user_id == user_id))
        db.execute(delete(User).where(User.id == user_id))
        db.commit()
        assert db.get(User, user_id) is None
    engine.dispose()
reports['temporary_user_removed'] = True
(root / 'data/local-runtime/ledger-export-access-check.json').write_text(json.dumps(reports, indent=2))
print(json.dumps(reports))
