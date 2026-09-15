import unittest
from unittest.mock import patch
from pydantic import ValidationError
from routers import financial
from fastapi import HTTPException


class CategoryRequestTests(unittest.IsolatedAsyncioTestCase):
    def test_blank_names_invalid_colours_and_oversized_names_are_rejected(self):
        for body in [dict(name='n'*121,color='#b41624'),dict(name='Review',color='url(https://invalid.example)'),dict(name='Review',color='red')]:
            with self.assertRaises(ValidationError):
                financial.CreateCategoryRequest(case_id='case-a',**body)
        with self.assertRaises(ValidationError):
            financial.CategorizeRequest(case_id='case-a',category='   ')

    async def test_refused_creation_is_not_reported_as_saved(self):
        with patch.object(financial.neo4j_service,'create_financial_category',return_value=dict(success=False,error='Not saved')):
            with self.assertRaises(HTTPException) as failure:
                await financial.create_category(financial.CreateCategoryRequest(case_id='case-a',name='Review',color='#b41624'))
            self.assertEqual(failure.exception.status_code,500)

    async def test_assigning_a_category_to_a_missing_record_is_not_successful(self):
        with patch.object(financial.neo4j_service,'update_transaction_category',return_value=dict(success=False,error='Node not found')):
            with self.assertRaises(HTTPException) as failure:
                await financial.categorize_transaction('missing',financial.CategorizeRequest(case_id='case-a',category='Review'))
            self.assertEqual(failure.exception.status_code,404)
