import unittest
from unittest.mock import patch

from services.agent.concurrency import (
    AgentConcurrencyLimitExceeded,
    _reset_for_tests,
    acquire_run_slot,
    release_run_slot,
)
from services.agent.service import AgentService, AgentSpendLimitExceeded


class AgentRunBoundsTests(unittest.TestCase):
    def setUp(self):
        _reset_for_tests()

    def tearDown(self):
        _reset_for_tests()

    def test_per_user_concurrency_cap_rejects_second_run(self):
        acquire_run_slot("user-1", max_per_user=1, max_global=8)

        with self.assertRaises(AgentConcurrencyLimitExceeded):
            acquire_run_slot("user-1", max_per_user=1, max_global=8)

        release_run_slot("user-1")
        acquire_run_slot("user-1", max_per_user=1, max_global=8)

    def test_global_concurrency_cap_rejects_other_users(self):
        acquire_run_slot("user-1", max_per_user=2, max_global=1)

        with self.assertRaises(AgentConcurrencyLimitExceeded):
            acquire_run_slot("user-2", max_per_user=2, max_global=1)

    def test_stream_slot_wrapper_releases_when_stream_fails_before_run_start(self):
        def broken_stream():
            raise RuntimeError("pre-run failure")
            yield {}

        acquire_run_slot("user-1", max_per_user=1, max_global=1)
        wrapped = AgentService._stream_with_slot_release(broken_stream(), "user-1")

        with self.assertRaises(RuntimeError):
            next(wrapped)

        acquire_run_slot("user-1", max_per_user=1, max_global=1)

    def test_daily_spend_cap_rejects_at_cap(self):
        class User:
            id = "user-1"

        with patch.object(AgentService, "_daily_agent_spend_usd", return_value=20.0):
            with self.assertRaises(AgentSpendLimitExceeded):
                AgentService._enforce_daily_spend_cap(object(), User(), cap_usd=20.0)

    def test_daily_spend_cap_allows_below_cap(self):
        class User:
            id = "user-1"

        with patch.object(AgentService, "_daily_agent_spend_usd", return_value=19.99):
            AgentService._enforce_daily_spend_cap(object(), User(), cap_usd=20.0)


if __name__ == "__main__":
    unittest.main()
