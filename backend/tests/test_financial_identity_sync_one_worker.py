from unittest import TestCase, mock

from services.financial import identity_graph as ig


class OneWorkerPerCaseTests(TestCase):
    """Two API workers never synchronise one case's identity graph at once."""

    def test_a_case_another_worker_holds_is_skipped(self):
        calls = []
        claims = iter([False, True])

        class Claim:
            def __enter__(self):
                return next(claims)

            def __exit__(self, *exc):
                return False

        with mock.patch.object(ig, '_case_claim', lambda case_id: Claim()), \
             mock.patch.object(ig, 'synchronize_case', calls.append), \
             mock.patch.object(ig, '_is_deferred', lambda case_id: False), \
             mock.patch('postgres.session.get_background_session') as session:
            session.return_value.__enter__.return_value.scalars.return_value = ['held-by-other', 'free']
            ig.sync_saved_identities()
        self.assertEqual(calls, ['free'])

    def test_switched_off_every_case_is_claimed(self):
        with mock.patch.object(ig, 'ONE_WORKER_PER_CASE', False):
            with ig._case_claim('any') as claimed:
                self.assertTrue(claimed)
