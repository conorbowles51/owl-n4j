"""The batch page names unsaved statements and unread files by the review queue's lists (d5b330d1 batch 30231f0a)."""
from types import SimpleNamespace
from unittest import TestCase, mock
from uuid import uuid4

from services.financial import import_batches


def item(status, file_id, key=''):
    return SimpleNamespace(id=uuid4(), status=status, file_id=file_id, statement_key=key, summary={})


class BatchQueueListTests(TestCase):
    def run_with(self, view, items, files, rechecked=None):
        def recheck(session, case_id, entries):
            for entry in entries:
                if rechecked and entry['id'] in rechecked:
                    entry['bucket'] = 'rechecking'
            return entries
        with mock.patch('services.financial.review_queue.current_view', return_value=view), \
                mock.patch('services.financial.review_queue._rechecked_by_recovery', side_effect=recheck):
            return import_batches._as_the_queue_lists(SimpleNamespace(rollback=lambda: None), uuid4(), items, files)

    def test_unsaved_statements_are_named_by_their_queue_list(self):
        copy, fund, reader, unread, waiting, unknown = (str(uuid4()) for _ in range(6))
        view = dict(entries=[
            dict(id='a', bucket='copies', file_ids=[copy], statement_id='s1'),
            dict(id='b', bucket='not_payment', file_ids=[fund], statement_id=None),
            dict(id='c', bucket='reader_fix', file_ids=[reader], statement_id='s3'),
            dict(id='d', bucket='unreadable', file_ids=[unread], statement_id='s4'),
            dict(id='e', bucket='waiting', file_ids=[waiting], statement_id='s5'),
        ], copy_files=[])
        items = [item('attention', copy, 's1'), item('attention', fund), item('attention', reader, 's3'),
                 item('attention', unread, 's4'), item('ready', waiting, 's5'), item('attention', unknown, 's6'),
                 item('imported', copy, 's1')]
        result = self.run_with(view, items, [])
        self.assertEqual((result['copies'], result['not_payment'], result['reader_fix'], result['unreadable']), (1, 1, 1, 1))
        # Waiting in the queue, and a statement the queue does not list, stay work.
        self.assertEqual(result['still_to_finish'], 2)

    def test_a_reader_campaign_moves_a_held_statement_to_being_checked_again(self):
        reader = str(uuid4())
        view = dict(entries=[dict(id='c', bucket='reader_fix', file_ids=[reader], statement_id='s')], copy_files=[])
        result = self.run_with(view, [item('attention', reader, 's')], [], rechecked={'c'})
        self.assertEqual((result['rechecking'], result['reader_fix']), (1, 0))

    def test_failed_files_read_in_another_batch_or_copied_are_not_unread(self):
        read, copied, failed, removed = (str(uuid4()) for _ in range(4))
        view = dict(entries=[dict(id='x', bucket='imported', file_ids=[read], statement_id='s')],
                    copy_files=[dict(file_id=copied, source_id=copied)])
        files = [dict(file_id=read, source_id=read, status='error'), dict(file_id=copied, source_id=copied, status='error'),
                 dict(file_id=failed, source_id=failed, status='error'),
                 dict(file_id=removed, source_id=removed, status='error', set_aside='removed')]
        self.run_with(view, [], files)
        self.assertEqual([f.get('set_aside') for f in files], ['read_elsewhere', 'copy', None, 'removed'])

    def test_no_queue_built_yet_leaves_the_page_its_own_words(self):
        files = [dict(file_id='f', source_id='f', status='error')]
        self.assertIsNone(self.run_with(None, [item('attention', 'f')], files))
        self.assertIsNone(files[0].get('set_aside'))
