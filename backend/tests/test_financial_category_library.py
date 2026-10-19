import copy
import unittest
from uuid import uuid4
from pydantic import ValidationError
from postgres.models.financial_category import FinancialCategory
from services.financial.category_library import CreatePaymentCategoryRequest, ensure_category, category_library
from services.financial.payment_labels import PaymentLabelsRequest, PaymentLabelsError, update_payment_labels
from services.financial.transaction_query import to_view
from routers.financial_ledger import get_payment_category_library


class CategoryLibraryTests(unittest.TestCase):
    def setUp(self):
        from tests.test_financial_payment_labels import PaymentLabelsTests
        self.fixture = PaymentLabelsTests()
        self.fixture.setUp()
        self.f = self.fixture.f
        FinancialCategory.__table__.create(self.f.db.connection())
        self.rows = self.fixture.rows

    def tearDown(self):
        self.fixture.tearDown()

    def test_shared_category_exists_before_assignment_and_reloads_in_another_case(self):
        self.assertEqual(ensure_category(self.f.db, name='  Professional   fees ', color='#5571c8', actor=self.f.actor)['name'], 'Professional fees')
        self.f.db.commit()
        self.f.db.expire_all()
        other = get_payment_category_library(case_id=uuid4(), db=self.f.db)['categories']
        self.assertIn(dict(name='Professional fees', color='#5571c8', scope='shared'), other)
        duplicate = ensure_category(self.f.db, name='PROFESSIONAL FEES', color='#123456', actor=self.f.actor)
        self.assertEqual((duplicate['name'], duplicate['color']), ('Professional fees', '#5571c8'))
        self.assertEqual(len([item for item in category_library(self.f.db) if item['scope'] == 'shared']), 1)

    def test_unshared_case_labels_do_not_leak_to_other_cases(self):
        self.fixture.save(self.rows[:1], category='Private case label')
        self.assertIn('Private case label', [item['name'] for item in get_payment_category_library(case_id=self.f.case.id, db=self.f.db)['categories']])
        self.assertNotIn('Private case label', [item['name'] for item in get_payment_category_library(case_id=uuid4(), db=self.f.db)['categories']])

    def test_bulk_create_and_recategorize_preserves_readings_and_manual_choice(self):
        originals = [(r.amount_minor, r.description, copy.deepcopy(r.provenance)) for r in self.rows]
        self.fixture.save(self.rows[:1], category='Shopping')
        self.fixture.save(self.rows, category='Reviewed expenses', add_to_library=True)
        self.f.db.expire_all()
        for row, original in zip(self.rows, originals):
            view = to_view(row, account=row.account)
            self.assertEqual((view.category, view.label_sources['category']['source']), ('Reviewed expenses', 'investigator'))
            self.assertEqual((row.amount_minor, row.description, row.provenance), original)
        self.assertIn('Reviewed expenses', [item['name'] for item in category_library(self.f.db)])
        self.fixture.save(self.rows, category='Travel')
        self.fixture.save(self.rows, category='')
        self.assertTrue(all(to_view(row).category == '' for row in self.rows))
        self.assertIn('Reviewed expenses', [item['name'] for item in category_library(self.f.db)])

    def test_stale_bulk_edit_neither_creates_category_nor_partially_updates_payments(self):
        self.fixture.save(self.rows[:1], category='Reviewed')
        request = PaymentLabelsRequest(transactions=[dict(id=r.id, version=0) for r in self.rows], category='Should not exist', add_to_library=True)
        with self.assertRaises(PaymentLabelsError):
            update_payment_labels(self.f.db, case_id=self.f.case.id, request=request, actor=self.f.actor)
        self.assertNotIn('Should not exist', [item['name'] for item in category_library(self.f.db)])
        self.assertEqual(to_view(self.rows[0]).category, 'Reviewed')
        self.assertEqual(to_view(self.rows[1]).category, '')

    def test_invalid_category_names_and_colors_are_rejected(self):
        for body in [dict(name=' '), dict(name='one\ntwo'), dict(name='a'*121), dict(name='Name', color='red')]:
            with self.assertRaises(ValidationError):
                CreatePaymentCategoryRequest(**body)
