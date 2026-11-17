"""A long model call must not leave the run's database session idle in a transaction (the background connection
is ended by Postgres after 10 minutes of that, and the run fails: deep run 458cf3b2, 81 min)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.agent.service import AgentService


def test_steering_read_ends_its_transaction():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.execute.return_value.scalar.return_value = [{"kind": "note"}]
    out = AgentService._steering_requests(db, "r1")
    assert out == [{"kind": "note"}]
    db.commit.assert_called()


def test_access_check_ends_its_transaction():
    db = MagicMock()
    user = SimpleNamespace(id="u1", is_active=True)
    request = SimpleNamespace(case_id="c1", all_cases=False)
    with patch("services.agent.service.check_case_access"):
        AgentService._checkpoint_access(db, user, request, [])
    db.commit.assert_called()
