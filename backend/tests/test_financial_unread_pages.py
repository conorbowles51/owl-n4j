"""A page whose OCR timed out is kept unread; only the statements that could include it are held."""
from unittest import TestCase

from services.financial.unread_pages import unread_pages, unread_pages_message, unread_pages_of_statement


def page(number, status='success'):
    return dict(kind='page', page_number=number, ocr_status=status)


LOCATIONS = [page(1), page(2), page(3, 'timeout'), page(4), page(5), page(6, 'timeout'), page(7)]
A = dict(page_numbers=[1, 2])
B = dict(page_numbers=[4, 5])
C = dict(page_numbers=[6, 7])


class UnreadPagesTests(TestCase):
    def test_only_timed_out_pages_are_unread(self):
        self.assertEqual(unread_pages(LOCATIONS), [3, 6])
        self.assertEqual(unread_pages([page(1), page(2, 'no_text')]), [])

    def test_a_page_inside_a_statement_holds_only_that_statement(self):
        self.assertEqual(unread_pages_of_statement(LOCATIONS, C, [A, B, C]), [6])
        self.assertEqual(unread_pages_of_statement([page(6, 'timeout')], A, [A, B, C]), [])

    def test_a_page_between_statements_holds_both_neighbours(self):
        self.assertEqual(unread_pages_of_statement(LOCATIONS, A, [A, B, C]), [3])
        self.assertEqual(unread_pages_of_statement(LOCATIONS, B, [A, B, C]), [3])

    def test_without_a_known_statement_every_unread_page_holds(self):
        self.assertEqual(unread_pages_of_statement(LOCATIONS, None, []), [3, 6])
        self.assertEqual(unread_pages_of_statement(LOCATIONS, dict(page_numbers=[]), [A]), [3, 6])

    def test_after_the_last_statement_holds_the_last(self):
        locations = [page(1), page(2), page(3, 'timeout')]
        self.assertEqual(unread_pages_of_statement(locations, A, [A]), [3])

    def test_message_is_plain(self):
        self.assertTrue(unread_pages_message([3]).startswith('Page 3 of this PDF could not be read in time'))
        self.assertIn('Pages 3 and 6 of this PDF', unread_pages_message([3, 6]))
