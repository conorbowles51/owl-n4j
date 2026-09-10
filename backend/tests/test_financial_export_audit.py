import unittest
from unittest.mock import MagicMock,patch
from uuid import uuid4
from services.financial.export_audit import record_prepared_export


class PreparedExportValidationTests(unittest.TestCase):
    def test_invalid_preparation_never_opens_a_transaction(self):
        valid=dict(case_id=uuid4(),kind='ledger_exports',content=b'synthetic',scope={},
            actor=dict(id=str(uuid4()),name='Synthetic',email='test@example.invalid'))
        for changed in (dict(kind='arbitrary'),dict(content=b''),dict(content='not bytes'),dict(scope={'bad':float('nan')}),dict(actor=None),dict(actor={'id':str(uuid4()),'name':'Synthetic','email':'x','token':'do not accept'})):
            with patch('services.financial.export_audit.Session') as session:
                with self.assertRaises((ValueError,TypeError)):record_prepared_export(MagicMock(),**{**valid,**changed})
                session.assert_not_called()
