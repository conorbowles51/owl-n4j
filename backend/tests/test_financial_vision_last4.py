"""The first statement of a card that prints only its last 4 digits (Neil, 2026-10-28, LAST4-APPROVED), and the plain
reason a statement held because its account cannot be confirmed gives (one per cause, saying what a person can do).

fdaf956c's 51 Capital One statements print only "ending in 8160" / "ending in 2602": rule 1 (the full number) can
never confirm them, and every one was held with the same "no saved statement" sentence whatever the cause."""
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select

from services.financial import vision_reader as vr
from services.financial.field_proposals import CaseKnowledge, KnownAccount, SavedStatement
from tests.test_financial_vision_reader import _page, _proposal, _row, _section

CARD = dict(account_number='****8160', holder='ERICA HOPPER', institution='Capital One', currency='USD',
            period_start='2023-06-10', period_end='2023-07-10', balance_convention='liability_owed')
IMAGE = dict(institution='Capital One', holder='ERICA HOPPER', account_number='8160', currency='',
             period_start='2023-06-10', period_end='2023-07-10')


def _card_pages(**header):
    """A card statement as the page images read it: owed 1000.00, a purchase of 100.00, payments of 30.50 and 69.50."""
    first = dict(IMAGE, **header)
    return [(1, _page([_section([_row('2023-06-12', '100.00', 'debit', '1100.00'),
                                 _row('2023-06-15', '30.50', 'credit', '1069.50')],
                                opening_balance='1000.00', total_debits='100.00', count_debits=1, **first)], 1, 2)),
            (2, _page([_section([_row('2023-07-01', '69.50', 'credit', '1000.00')],
                                closing_balance='1000.00', total_credits='100.00')], 2, 2))]


def _known(account='****8160', holder='ERICA MCCAULEY', institution='Capital One', currency='USD'):
    from services.financial.field_proposals import account_identity
    digits, masked = account_identity(account)
    saved = SavedStatement(currency=currency, period_start='2020-09-08', period_end='2020-10-07',
                           institution=institution, holder=holder, account_number=account)
    return KnownAccount(key=str(uuid4()), account=account, digits=digits, masked=masked, institution=institution,
                        currency=currency, statements=[saved])


def _prove(pages=None, knowledge=None, **text):
    proposal = _proposal(**dict(CARD, **text))
    pages = pages or _card_pages()
    vr.check_page_numbering(pages, proposal['page_numbers'])
    return vr.prove(proposal, vr.choose_section(vr.combine(pages), proposal), knowledge or CaseKnowledge(accounts=[]))


MASKED = (r'The bank prints only the last 4 digits of this card \(ending 8160\) and no statement of it is confirmed in '
          r'this case yet\. Confirm one statement of this card and the rest can follow\. It was not accepted as the '
          r'first statement of this card because ')


class LastFourProofTest(unittest.TestCase):
    def test_a_masked_card_first_statement_that_otherwise_proves_is_admitted(self):
        reading = _prove()
        self.assertEqual(reading['account_basis'], vr.LAST4_BASIS)
        self.assertEqual(reading['account_keys'], [])
        self.assertEqual((reading['opening'], reading['closing'], len(reading['rows'])), (100000, 100000, 3))
        self.assertEqual((reading['holder'], reading['institution'], reading['currency']), ('ERICA HOPPER', 'Capital One', 'USD'))
        self.assertEqual(vr.last4_card(reading), dict(digits='8160', institution='Capital One', holder='ERICA HOPPER',
                                                      period_start='2023-06-10'))
        # Detected as a credit card by the reader (account type) is a card too.
        proposal = _proposal(**dict(CARD, balance_convention='liability_owed', account_type='credit_card'))
        self.assertTrue(vr.is_card(proposal))

    def test_old_code_held_it(self):
        with mock.patch.object(vr, 'LAST4_FIRST_STATEMENT', False), \
                self.assertRaisesRegex(vr.NotProved, MASKED + 'accepting the first statement of such a card .* switched off'):
            _prove()

    def test_the_last_digits_must_be_read_by_both_and_agree(self):
        with self.assertRaisesRegex(vr.NotProved, 'no account section matching'):
            _prove(pages=_card_pages(account_number='8161'))
        with self.assertRaisesRegex(vr.NotProved, MASKED + 'its number is not read from both the page images and the text'):
            _prove(pages=_card_pages(account_number=''))
        with self.assertRaisesRegex(vr.NotProved, r'ending 160\) .*fewer than 4 digits'):
            _prove(pages=_card_pages(account_number='160'), account_number='***160')
        # Digits before the mask: they are not its last digits alone, so they do not name the card by them.
        with self.assertRaisesRegex(vr.NotProved, MASKED + 'its number shows digits before the masked part'):
            _prove(pages=_card_pages(account_number='517805******8160'), account_number='517805******8160')
        self.assertEqual(_prove(pages=_card_pages(account_number='XXXX XXXX XXXX 8160'))['account_basis'], vr.LAST4_BASIS)
        # The images read a longer number than the text: rule 1's route, both must read it in full.
        with self.assertRaisesRegex(vr.NotProved, MASKED + 'the page images reads a longer number'):
            _prove(pages=_card_pages(account_number='5178051234568160'))

    def test_holder_and_bank_must_be_read_by_both_and_agree(self):
        with self.assertRaisesRegex(vr.NotProved, 'account holder read from the page images differs'):
            _prove(pages=_card_pages(holder='ERICA MCCAULEY'))
        with self.assertRaisesRegex(vr.NotProved, MASKED + 'the account holder is not read from both'):
            _prove(pages=_card_pages(holder=''))
        with self.assertRaisesRegex(vr.NotProved, MASKED + 'the account holder is not read from both'):
            _prove(holder='')
        with self.assertRaisesRegex(vr.NotProved, 'bank read from the page images differs'):
            _prove(pages=_card_pages(institution='Chase'))
        with self.assertRaisesRegex(vr.NotProved, MASKED + 'the bank is not read from both'):
            _prove(pages=_card_pages(institution=''))

    def test_the_currency_must_be_printed(self):
        with self.assertRaisesRegex(vr.NotProved, MASKED + 'the currency is not printed'):
            _prove(currency='')

    def test_only_a_card_statement(self):
        with self.assertRaisesRegex(vr.NotProved, r'The bank prints only the last 4 digits of this account \(ending '
                                                  r'8160\).*not a card statement'):
            pages = _card_pages()
            for _, page in pages:  # the same money as an asset account: credit then debits
                for row in page['sections'][0]['rows']:
                    row['direction'] = 'credit' if row['direction'] == 'debit' else 'debit'
                    row['balance_after'] = None
            pages[0][1]['sections'][0].update(total_credits='100.00', count_credits=1, total_debits=None, count_debits=None)
            pages[1][1]['sections'][0].update(total_debits='100.00', total_credits=None)
            _prove(pages=pages, balance_convention='asset_balance')

    def test_a_saved_account_with_the_last_digits_at_that_bank(self):
        # Another holder saved on it: never merged; the person is asked.
        with self.assertRaisesRegex(vr.NotProved, r'^This card \(ending 8160\) is saved for ERICA MCCAULEY; this statement '
                                                  r'prints ERICA HOPPER\. Confirm whether they are the same account\.$'):
            _prove(knowledge=CaseKnowledge(accounts=[_known()]))
        # A full number ending the same way at that bank, another holder: the same.
        with self.assertRaisesRegex(vr.NotProved, r'saved for ERICA MCCAULEY; this statement prints ERICA HOPPER'):
            _prove(knowledge=CaseKnowledge(accounts=[_known(account='5178051234568160')]))
        # The same holder: the saved account confirms it (masked number, holder and bank), not this rule.
        reading = _prove(knowledge=CaseKnowledge(accounts=[_known(holder='ERICA HOPPER')]))
        self.assertNotIn('account_basis', reading)
        self.assertEqual(len(reading['account_keys']), 1)
        # Two saved accounts it could be: both named, the person chooses.
        two = CaseKnowledge(accounts=[_known(holder='ERICA HOPPER'), _known(account='5178051234568160', holder='ERICA HOPPER')])
        with self.assertRaisesRegex(vr.NotProved, r'^More than one account saved in this case could be this card \(ending '
                                                  r'8160\): \*\*\*\*8160 at Capital One; 5178051234568160 at Capital One\. '
                                                  r'Choose which account this statement belongs to\.$'):
            _prove(knowledge=two)

    def test_a_card_ending_the_same_at_another_bank_is_another_card(self):
        reading = _prove(knowledge=CaseKnowledge(accounts=[_known(institution='Chase', holder='SOMEONE')]))
        self.assertEqual(reading['account_basis'], vr.LAST4_BASIS)

    def test_every_other_proof_is_unchanged(self):
        pages = _card_pages()
        pages[1][1]['sections'][0]['closing_balance'] = '1000.01'
        with self.assertRaisesRegex(vr.NotProved, 'did not balance'):
            _prove(pages=pages)
        with self.assertRaisesRegex(vr.NotProved, 'period'):
            _prove(period_end='2023-07-09')
        pages = _card_pages()
        pages[0][1]['sections'][0]['rows'][0]['balance_after'] = '1100.10'
        with self.assertRaisesRegex(vr.NotProved, 'running balance'):
            _prove(pages=pages)
        pages = _card_pages()
        pages[0][1]['sections'][0]['total_debits'] = '100.01'
        with self.assertRaisesRegex(vr.NotProved, 'printed total'):
            _prove(pages=pages)
        pages = _card_pages()
        pages[0][1]['sections'][0]['rows'][1]['date'] = '2023-07-15'
        with self.assertRaisesRegex(vr.NotProved, 'outside the statement period'):
            _prove(pages=pages)
        pages = _card_pages()
        pages[0][1]['sections'][0]['rows'].reverse()
        pages[0][1]['sections'][0]['rows'][0]['balance_after'] = None
        pages[0][1]['sections'][0]['rows'][1]['balance_after'] = None
        with self.assertRaises(vr.NotProved):  # rows out of the printed date order
            _prove(pages=pages)
        gap = _card_pages()
        gap[1] = (2, dict(gap[1][1], printed_page_number=3, printed_page_total=3))
        with self.assertRaises(vr.NotProved):  # a missing page
            _prove(pages=gap)

    def test_a_saved_statement_never_creates_a_card(self):
        proposal = _proposal(**CARD)
        reading = dict(account_basis=vr.LAST4_BASIS, account_number='****8160')
        with mock.patch.object(vr, 'combine'), mock.patch.object(vr, 'choose_section'), \
                mock.patch.object(vr, 'check_page_numbering', return_value=False), \
                mock.patch.object(vr, 'document_pages', return_value=[]), \
                mock.patch.object(vr, 'prove', return_value=reading), \
                self.assertRaisesRegex(vr.NotProved, MASKED + 'a saved statement is never the first statement of a card'):
            vr.judge(None, 'c', proposal, {}, [1, 2], CaseKnowledge(accounts=[]), saved=True)

    def test_the_proof_version_counts_the_rule(self):
        self.assertTrue(vr.LAST4_FIRST_STATEMENT)
        self.assertEqual(vr.PROOF_VERSION, 22)


class FullNumberReasonTest(unittest.TestCase):
    """Rule 1's refusals now say which of number, holder and bank was not read alike."""
    TEXT = dict(account_number='0123456789', holder='ACME SA DE CV', institution='BBVA MEXICO', currency='MXN',
                period_start='2025-12-01', period_end='2025-12-31')

    def test_each_cause_its_reason(self):
        from tests.test_financial_vision_reader import _balanced_pages, _proved
        start = r'^No statement of account 0123456789 is confirmed in this case yet, and this one was not accepted as its first because '
        end = r'\. Confirm one statement of this account and the rest can follow\.$'
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['holder'] = ''
        with self.assertRaisesRegex(vr.NotProved, start + 'the account holder is not read from both the page images and the text' + end):
            _proved(_proposal(**self.TEXT), CaseKnowledge(accounts=[]), pages)
        with self.assertRaisesRegex(vr.NotProved, start + 'the bank is not read from both the page images and the text' + end):
            _proved(_proposal(**dict(self.TEXT, institution='')), CaseKnowledge(accounts=[]))
        with self.assertRaisesRegex(vr.NotProved, start + 'the full number is not read from both the page images and the text' + end):
            _proved(_proposal(**dict(self.TEXT, account_number='')), CaseKnowledge(accounts=[]))


class TextLayerAndTurnTest(unittest.TestCase):
    READING = dict(account_number='****8160', institution='Capital One', holder='ERICA HOPPER', period_start='2023-06-10')

    def test_a_longer_number_printed_in_the_file_holds_it(self):
        for printed in ({'5178051234568160'}, {'1234568160'}):
            with self.subTest(printed=printed), mock.patch.object(vr, 'card_turn') as turn, \
                    self.assertRaisesRegex(vr.NotProved, r'The statement prints only the last 4 digits of this card '
                                           r'\(ending 8160\) as its account, and no statement of it is confirmed in this '
                                           r'case yet\. The file also prints a longer number ending in the same digits '
                                           r'\(%s\), which the page images do not read as this card\'s number, so this '
                                           r'statement is not accepted as the first of this card\. Confirm one statement '
                                           r'of this card and the rest can follow\.$' % next(iter(printed))) as raised:
                vr.last4_turn(None, 'c', 'i', self.READING, 'x.pdf', numbers_of=lambda path: printed)
            turn.assert_not_called()
            self.assertEqual(raised.exception.card, vr.card_key('Capital One', '8160'))
        with mock.patch.object(vr, 'card_turn') as turn:
            vr.last4_turn(None, 'c', 'i', self.READING, 'x.pdf', numbers_of=lambda path: {'20230610', '123456'})
        turn.assert_called_once()
        with self.assertRaisesRegex(vr.NotProved, 'the text of its file could not be checked'):
            vr.last4_turn(None, 'c', 'i', self.READING, 'x.pdf', numbers_of=lambda path: 1 / 0)

    def test_a_reading_stored_under_earlier_instructions_is_judged_again(self):
        # A prompt change reads anew only what is read anew: a stored page reading is still judged under new rules.
        record = dict(version=vr.VERSION, proof=vr.PROOF_VERSION - 1, status='not_proved', raw={}, revision='r',
                      reader='deepseek/deepseek-v4-flash (statement-pages-v3)', pages=[1, 2])
        model = 'deepseek/deepseek-v4-flash (%s)' % vr.PROMPT_VERSION
        self.assertTrue(vr.rejudgeable(record, 'r', model, [1, 2]))
        self.assertFalse(vr.rejudgeable(record, 'r', 'openai/gpt-x (%s)' % vr.PROMPT_VERSION, [1, 2]))
        self.assertFalse(vr.rejudgeable(record, 'r', model, [1, 2, 3]))

    def test_full_number_confirmed_needs_the_one_longer_number_digit_for_digit(self):
        reading = dict(self.READING, full_account_number='5178 0599 8442 8160')
        self.assertEqual(vr.full_number_confirmed(reading, ['5178059984428160']), '5178059984428160')
        self.assertIsNone(vr.full_number_confirmed(reading, ['5178059984428160', '5178000000048160']))
        self.assertIsNone(vr.full_number_confirmed(reading, ['5178059984420000']))
        self.assertIsNone(vr.full_number_confirmed(dict(self.READING, full_account_number=''), ['5178059984428160']))
        # Not a card number: too short, or its check digit fails.
        self.assertIsNone(vr.full_number_confirmed(dict(self.READING, full_account_number='998160'), ['998160']))
        self.assertIsNone(vr.full_number_confirmed(dict(self.READING, full_account_number='5178051234568160'),
                                                   ['5178051234568160']))
        with mock.patch.object(vr, 'card_turn') as turn:
            self.assertEqual(vr.last4_turn(None, 'c', 'i', reading, 'x.pdf', numbers_of=lambda path: {'5178059984428160'}),
                             '5178059984428160')
        turn.assert_called_once()

    def test_printed_numbers_reads_the_text_layer(self):
        import fitz
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'card.pdf'
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), 'Platinum Mastercard ending in 8160  Page 1 of 4')
            page.insert_text((72, 100), 'Card 5178 0512 3456 8160   Ref 12-3456-8160   Phone 1-800-227-4825')
            page.insert_text((72, 128), 'Amount 1,238,160.00  Date 06/10/2023  Zip 28160')
            page.insert_text((72, 156), 'A 4000  1111  2222  8161  B 4000.1111.2222.8162  C 3782 822463 18163')
            page.insert_text((72, 184), 'D 4000\u00a01111\u00a02222\u00a08164  E 5178 05XX XXXX 8165  F 10 2023 8166')
            page.insert_text((72, 212), 'Ref 1234 4000 1111 2222 8167')
            document.save(str(path))
            document.close()
            numbers = vr.printed_numbers(path)
        self.assertIn('5178051234568160', numbers)
        self.assertIn('1234568160', numbers)
        self.assertNotIn('8160', numbers)
        self.assertNotIn('28160', numbers)  # 5 digits: not a full number
        self.assertFalse(any(n.endswith('238160') for n in numbers))  # an amount is not a number of the card
        for full in ('4000111122228161', '4000111122228162', '378282246318163', '4000111122228164', '4000111122228167'):
            self.assertIn(full, numbers)
        self.assertFalse(any(n.endswith('8165') or n.endswith('8166') for n in numbers), numbers)  # masked; a date's parts


class SweepPassTest(unittest.TestCase):
    """A statement waiting for an earlier statement of its card is tried again in the same round once that is decided."""

    class Factory:
        def __call__(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def test_waiting_statements_follow_in_the_next_pass(self):
        decided, calls = set(), []

        def read(factory, item_id, resolve_path):
            calls.append(item_id)
            earlier = {'b': 'a', 'c': 'b'}.get(item_id)
            if earlier and earlier not in decided:
                return dict(status='not_proved', reason='waits_for_card')
            decided.add(item_id)
            return dict(status='not_proved', message='x', rejudged=True)
        vr._skip_until.clear()
        with mock.patch.object(vr, 'ENABLED', True), mock.patch.object(vr, 'pending', return_value=['c', 'b', 'a']), \
                mock.patch.object(vr, 'read_item', side_effect=read):
            report = vr.sweep(self.Factory(), None, concurrency=1)
        vr._skip_until.clear()
        self.assertEqual(calls, ['c', 'b', 'a', 'c', 'b', 'c'])
        self.assertEqual(report['not_proved'], 3)

    def test_no_progress_ends_the_round(self):
        calls = []

        def read(factory, item_id, resolve_path):
            calls.append(item_id)
            return dict(status='not_proved', reason='waits_for_card')
        vr._skip_until.clear()
        with mock.patch.object(vr, 'ENABLED', True), mock.patch.object(vr, 'pending', return_value=['a', 'b']), \
                mock.patch.object(vr, 'read_item', side_effect=read):
            vr.sweep(self.Factory(), None, concurrency=1)
        # Still waiting at the round's end: looked at again in a while, not every round.
        self.assertEqual(set(vr._skip_until), {'a', 'b'})
        vr._skip_until.clear()
        self.assertEqual(calls, ['a', 'b'])
        # A wait whose re-judging failed is marked judged without it: final, not due every round.
        self.assertNotIn('waiting', vr._judged(dict(status='not_proved', waiting=True)))


class LastFourFlowTest(unittest.TestCase):
    """Through read_item on the batch fixture: the card's first statement is saved with its basis; its turn, the
    case's accounts, and the statements that waited on it judged again."""

    def setUp(self):
        from tests import test_financial_reader_release as release
        self.release = release
        self.r = release.ReaderReleaseTests('test_no_mark_with_the_page_image_reader_off')
        self.r.setUp()
        self.addCleanup(self.r.tearDown)
        self.f = self.r.f
        for p in (patch.dict(vr._spend, {}, clear=True),
                  patch('services.ai_model_policy.deepseek_only', return_value=False)):
            p.start()
            self.addCleanup(p.stop)
        with patch.object(vr, 'ENABLED', True):
            self.batch = self.r.prepare_with_old_reader()
        self.held = self.r.item(self.batch)
        document, _ = self.r._image_reading(self.held)
        account = document['accounts'][0]
        account.update(account_number='0123', holder='ERICA HOPPER', currency='')
        self.document = document

    def card_reader(self, db, **kw):
        proposal = self.release.old_reader(db, **kw)
        proposal['metadata'].update(account_number='****0123', holder='ERICA HOPPER', account_type='credit_card')
        return proposal

    def read(self, knowledge=None, numbers=frozenset(), apply=True, model='deepseek-flash', calls=None):
        from services.financial import import_batches as batches
        document = self.document
        calls = calls if calls is not None else []
        chain = [vr.PageReader(provider='deepseek', model=model, read=lambda images: calls.append(model) or (document, {}),
                               unavailable='', strips=1, max_output_tokens=1000)]
        with patch.object(vr, 'render_pages', lambda path, pages, width=None, strips=None: [(p, [b'png']) for p in pages]), \
                patch.object(batches, 'read_statement_import', self.card_reader), \
                patch('services.financial.statement_import.read_statement_import', self.card_reader), \
                patch.object(vr, 'check_neighbours', lambda *a: None):
            return vr.read_item(self.f.SessionLocal, self.held.id, Path, page_reader=lambda db, case_id: chain,
                                knowledge_for=lambda db, case_id: knowledge or CaseKnowledge(accounts=[]),
                                numbers_of=lambda path: set(numbers), apply=apply)

    def stored(self, item=None):
        from postgres.models.evidence import EvidenceFile
        item = item or self.held
        with self.f.SessionLocal() as db:
            return (db.get(EvidenceFile, item.file_id).metadata_.get(vr.METADATA_KEY) or {}).get(item.statement_key or '')

    def sibling(self, status='attention', period_start='2023-01-01', account='****0123', record=None):
        """Another statement of the same card in the case (a copy of the held item's row)."""
        from postgres.models.evidence import EvidenceFile
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        key = uuid4().hex
        with self.f.SessionLocal() as db:
            item = Item(id=uuid4(), batch_id=self.held.batch_id, file_id=self.held.file_id, statement_key=key,
                        status=status, summary=dict(self.held.summary, account=account, institution='Synthetic Bank',
                                                     period_start=period_start), review_request=None)
            db.add(item)
            if record is not None:
                file = db.get(EvidenceFile, self.held.file_id)
                metadata = dict(file.metadata_ or {})
                metadata[vr.METADATA_KEY] = dict(metadata.get(vr.METADATA_KEY) or {}, **{key: record})
                file.metadata_ = metadata
            db.commit()
            return item.id, key

    def test_the_first_statement_of_the_card_is_saved_with_its_basis(self):
        outcome = self.read()
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        stored = self.stored()
        self.assertEqual(stored['account_basis'], vr.LAST4_BASIS)
        self.assertIn('first statement of this card', stored['message'])
        self.assertEqual(stored['card']['digits'], '0123')
        self.assertEqual(self.r.item(self.batch).status, 'ready')
        self.assertEqual(self.r.item(self.batch).review_request['account_number'], '****0123')

    def test_the_full_number_printed_in_the_file_holds_it(self):
        outcome = self.read(numbers={'99990123'})
        self.assertEqual(outcome['status'], 'not_proved')
        self.assertIn('The file also prints a longer number ending in the same digits (99990123)', outcome['message'])
        self.assertEqual(self.stored()['account_wait'], vr.card_key('Synthetic Bank', '0123'))
        self.assertEqual(self.r.item(self.batch).status, 'attention')
        self.assertIn('the statement prints only the last 4 digits of this card (ending 0123)',
                      self.r.item(self.batch).summary['vision_reading']['line'])

    def test_the_full_number_read_alike_from_the_page_images_and_the_text_admits_it(self):
        # Capital One: page 1's payment coupon line prints the complete card number; the page images read it.
        self.document['accounts'][0]['full_account_number'] = '4000000000040123'
        outcome = self.read(numbers={'4000000000040123'})
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        stored = self.stored()
        self.assertEqual(stored['account_basis'], vr.LAST4_BASIS)
        self.assertEqual(stored['card']['full_number'], '4000000000040123')
        self.assertIn('its full number (4000000000040123), printed on its payment coupon, is read alike from the page images and the text', stored['message'])
        self.assertEqual(self.r.item(self.batch).status, 'ready')

    def test_a_full_number_the_text_does_not_print_alike_still_holds_it(self):
        for read, printed in (('4000000000040123', {'4000000000050123'}), ('400000000040123', {'4000000000040123'}),
                              ('4000000000040123', {'4000000000040123', '77770123'}),
                              ('4000000000040124', {'4000000000040124', '4000000000040123'}),
                              ('99990123', {'99990123'})):  # not a card number (8 digits, no Luhn check)
            with self.subTest(read=read, printed=printed):
                self.document['accounts'][0]['full_account_number'] = read
                outcome = self.read(numbers=printed)
                self.assertEqual(outcome['status'], 'not_proved')
                self.assertIn('The file also prints a longer number ending in the same digits', outcome['message'])
        with patch.object(vr, 'FULL_NUMBER_FROM_IMAGES', False):
            self.document['accounts'][0]['full_account_number'] = '4000000000040123'
            self.assertEqual(self.read(numbers={'4000000000040123'})['status'], 'not_proved')

    def test_an_earlier_held_statement_still_to_be_judged_goes_first(self):
        old = dict(version=vr.VERSION, proof=vr.PROOF_VERSION - 1, status='not_proved', raw={}, message='x')
        self.sibling(period_start='2022-12-01', record=old)
        outcome = self.read()
        self.assertEqual((outcome['status'], outcome['reason']), ('not_proved', 'waits_for_card'))
        self.assertIn('An earlier statement of this card (ending 0123, 2022-12-01', outcome['message'])
        stored = self.stored()
        # Never final: judged again later from the stored reading, whatever the proof version.
        self.assertEqual((stored['proof'], stored['waiting']), (vr.PROOF_VERSION, True))
        self.assertTrue(vr.due_again(stored, lambda: CaseKnowledge(accounts=[])))
        self.assertTrue(vr.rejudgeable(stored, due=True))
        self.assertEqual(self.r.item(self.batch).status, 'attention')
        self.assertIn('is checked first', self.r.item(self.batch).summary['vision_reading']['line'])

    def test_an_earlier_statement_listed_to_be_read_anew_goes_first(self):
        # Marked to be read anew with its summary page (SUMMARY_PAGES), not read yet: it is still to be judged.
        from datetime import datetime, timezone
        record = dict(version=vr.VERSION, proof=vr.PROOF_VERSION, status='not_proved', raw={},
                      read_anew_at=datetime.now(timezone.utc).isoformat())
        _, key = self.sibling(period_start='2022-12-01', record=record)
        outcome = self.read()
        self.assertEqual((outcome['status'], outcome['reason']), ('not_proved', 'waits_for_card'))
        self.assertTrue(vr._to_read_anew(record))
        # Read since (its pages rule recorded), or marked long ago and never read: it does not hold this one.
        self.assertFalse(vr._to_read_anew(dict(record, pages_rule=vr.PAGES_RULE)))
        self.assertFalse(vr._to_read_anew(dict(record, read_anew_at='2026-01-01T00:00:00+00:00')))
        # A backlog takes hours to read: a mark 3 hours old still holds the later statement.
        from datetime import timedelta
        self.assertTrue(vr._to_read_anew(dict(record, read_anew_at=(datetime.now(timezone.utc) - timedelta(hours=3)).isoformat())))

    def test_a_later_or_decided_statement_does_not_hold_it(self):
        self.sibling(period_start='2030-01-01', record=dict(version=vr.VERSION, proof=vr.PROOF_VERSION - 1,
                                                            status='not_proved', raw={}))
        self.sibling(period_start='2020-01-01', record=dict(version=vr.VERSION, proof=vr.PROOF_VERSION,
                                                            status='not_proved', raw={}))
        self.sibling(period_start='2019-01-01', account='****9999')  # another card
        self.sibling(status='imported', period_start='2019-01-01')   # in its account already (checked through it)
        # Accepted, but its save or import refused and held again: decided, waiting for a person, not for this one.
        # The same holder: the same account, so it does not hold this one.
        self.sibling(period_start='2018-01-01', record=dict(version=vr.VERSION, proof=vr.PROOF_VERSION, status='proved', raw={},
                                                            card=dict(digits='0123', holder='ERICA HOPPER')))
        # A wait not refreshed for hours (its statement no longer looked at) does not hold the others back.
        self.sibling(period_start='2017-01-01', record=dict(version=vr.VERSION, proof=vr.PROOF_VERSION, status='not_proved',
                                                            raw={}, waiting=True, at='2026-01-01T00:00:00+00:00'))
        self.assertEqual(self.read()['status'], 'proved')

    def test_an_accepted_statement_held_again_for_another_holder_holds_it_with_the_question(self):
        # Its import can still happen later and would join this card's account by bank and last digits alone.
        self.sibling(period_start='2030-01-01', record=dict(version=vr.VERSION, proof=vr.PROOF_VERSION, status='proved', raw={},
                                                            card=dict(digits='0123', holder='ERICA MCCAULEY')))
        outcome = self.read()
        self.assertEqual(outcome['status'], 'not_proved')
        self.assertNotEqual(outcome.get('reason'), 'waits_for_card')
        self.assertIn('was accepted for ERICA MCCAULEY and waits for a person; this statement prints ERICA HOPPER. '
                      'Confirm whether they are the same account.', outcome['message'])
        self.assertEqual(self.r.item(self.batch).status, 'attention')

    def test_an_earlier_statement_that_is_itself_waiting_holds_it(self):
        from datetime import datetime, timezone
        self.sibling(period_start='2022-12-01', record=dict(version=vr.VERSION, proof=vr.PROOF_VERSION, status='not_proved',
                                                            raw={}, waiting=True, at=datetime.now(timezone.utc).isoformat()))
        self.assertEqual(self.read()['reason'], 'waits_for_card')

    def test_a_wait_is_never_made_final(self):
        old = dict(version=vr.VERSION, proof=vr.PROOF_VERSION - 1, status='not_proved', raw={}, message='x')
        self.sibling(period_start='2022-12-01', record=old)
        calls = []
        self.assertEqual(self.read(calls=calls)['reason'], 'waits_for_card')
        self.assertEqual(self.read(calls=calls)['reason'], 'waits_for_card')  # judged again from the stored reading
        self.assertEqual(calls, ['deepseek-flash'])
        # Another reader in use now: the wait is read again by it, not marked judged as it stands.
        self.assertEqual(self.read(model='deepseek-pro', calls=calls)['reason'], 'waits_for_card')
        self.assertEqual(calls, ['deepseek-flash', 'deepseek-pro'])
        self.assertTrue(self.stored()['waiting'])

    def test_a_statement_of_the_card_waiting_to_be_imported_holds_it(self):
        self.sibling(status='ready', period_start='2030-01-01')
        outcome = self.read()
        self.assertEqual(outcome['reason'], 'waits_for_card')
        self.assertIn('is accepted and waits to be imported', outcome['message'])

    def test_an_account_recorded_with_those_digits_at_that_bank_holds_it(self):
        from postgres.models.financial import FinancialAccount
        with self.f.SessionLocal() as db:
            db.add(FinancialAccount(id=uuid4(), case_id=self.f.case.id, identity_key='x-0123', institution_name='Synthetic Bank',
                                    identifier_as_printed='****0123', identifier_normalised='0123', holder_name='ERICA MCCAULEY',
                                    metadata_={}))
            db.commit()
        outcome = self.read()
        self.assertEqual(outcome['status'], 'not_proved')
        self.assertIn('this card (ending 0123) is saved for ERICA MCCAULEY; this statement prints ERICA HOPPER. Confirm '
                      'whether they are the same account.', outcome['message'])
        self.assertNotEqual(outcome.get('reason'), 'waits_for_card')

    def test_differently_printed_holders_are_never_merged(self):
        # The same holder follows through the saved account.
        same = CaseKnowledge(accounts=[_known(account='****0123', holder='ERICA HOPPER', institution='Synthetic Bank',
                                              currency='EUR')])
        measured = self.read(knowledge=same, apply=False)
        self.assertEqual(measured['status'], 'proved', measured.get('message'))
        self.assertNotIn('account_basis', measured)
        # Once the card is saved for one holder, a statement printing another is held with the question, never saved.
        saved = CaseKnowledge(accounts=[_known(account='****0123', holder='ERICA MCCAULEY', institution='Synthetic Bank',
                                               currency='EUR')])
        outcome = self.read(knowledge=saved)
        self.assertEqual(outcome['status'], 'not_proved')
        self.assertIn('saved for ERICA MCCAULEY; this statement prints ERICA HOPPER', outcome['message'])
        self.assertEqual(self.r.item(self.batch).status, 'attention')

    def test_a_refusal_that_waited_on_the_card_is_judged_again_once_the_case_holds_it(self):
        refused = self.read(numbers={'99990123'})
        self.assertEqual(refused['status'], 'not_proved')
        wait = self.stored()['account_wait']
        self.assertEqual(wait, vr.card_key('Synthetic Bank', '0123'))
        # Nothing saved for the card yet: not judged again.
        self.assertEqual(self.read()['reason'], 'already_read')
        # The card's account is saved (by this rule or confirmed by a person; only admitted statements count): its
        # stored reading is judged again, now through the saved account.
        same = CaseKnowledge(accounts=[_known(account='****0123', holder='ERICA HOPPER', institution='Synthetic Bank',
                                              currency='EUR')])
        self.assertTrue(vr.card_known(same, wait))
        self.assertFalse(vr.card_known(CaseKnowledge(accounts=[_known(account='****0123', institution='Chase')]), wait))
        outcome = self.read(knowledge=same)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        self.assertTrue(outcome.get('rejudged'))
        self.assertNotIn('account_basis', self.stored())
        self.assertEqual(self.r.item(self.batch).status, 'ready')

    def test_pending_lists_the_statements_due_again(self):
        from postgres.models.evidence import EvidenceFile
        with self.f.SessionLocal() as db:
            listed = vr.pending(db)
        self.assertIn(self.held.id, listed)
        self.read(numbers={'99990123'})
        with self.f.SessionLocal() as db:
            self.assertNotIn(self.held.id, vr.pending(db))
        same = CaseKnowledge(accounts=[_known(account='****0123', holder='ERICA HOPPER', institution='Synthetic Bank',
                                              currency='EUR')])
        with self.f.SessionLocal() as db, patch('services.financial.field_proposals.case_knowledge', lambda *a, **k: same):
            self.assertIn(self.held.id, vr.pending(db))

    def test_statements_due_again_are_listed_before_the_rest(self):
        # A round has a time budget; statements re-judged from their stored reading (nothing requested) go first, so
        # the ones a person's decision released are never left behind statements listed ahead of them every round.
        from datetime import datetime, timezone
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        self.read(numbers={'99990123'})
        other, _ = self.sibling(period_start='2020-01-01')
        with self.f.SessionLocal() as db:
            db.get(Item, other).updated_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
            db.get(Item, self.held.id).updated_at = datetime.now(timezone.utc)
            db.commit()
        same = CaseKnowledge(accounts=[_known(account='****0123', holder='ERICA HOPPER', institution='Synthetic Bank',
                                              currency='EUR')])
        with self.f.SessionLocal() as db, patch('services.financial.field_proposals.case_knowledge', lambda *a, **k: same):
            self.assertEqual(vr.pending(db)[:2], [self.held.id, other])
            self.assertEqual(vr.pending(db, limit=1), [self.held.id])
        with self.f.SessionLocal() as db:
            self.assertEqual(vr.pending(db), [other])  # not due: listed in its turn only

if __name__ == '__main__':
    unittest.main()
