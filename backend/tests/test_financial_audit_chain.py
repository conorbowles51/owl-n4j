import copy
import hashlib
import json
import unittest
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from postgres.models.financial_audit import FinancialAuditEvent
from services.financial.audit_chain import capture_financial_audit_chain, verify_financial_audit_chain
from services.financial.ledger_summary import LedgerSummaryError


class FinancialAuditChainTests(unittest.TestCase):
    def setUp(self):
        self.case = uuid4()

    def entries(self):
        result = []
        previous = '0'*64
        for i in range(1,4):
            payload = json.dumps(dict(schema_version='loupe.financial.audit_event/1', case_id=str(self.case),
                sequence=i, source_table='adjudications', operation='INSERT',
                after={'reason':'Synthetic reason', 'amount_minor':9007199254740993}))
            digest = hashlib.sha256(bytes.fromhex(previous)+payload.encode()).hexdigest()
            result.append(dict(sequence=i,previous_sha256=previous,entry_sha256=digest,payload_text=payload))
            previous=digest
        return result

    def test_exact_bytes_and_separate_checkpoint(self):
        entries = self.entries()
        result = verify_financial_audit_chain(entries,case_id=self.case,expected_head_sha256=entries[-1]['entry_sha256'])
        self.assertEqual(result['event_count'],3)
        self.assertEqual(result['checkpoint_status'],'matches_supplied_head')
        self.assertEqual(json.loads(entries[0]['payload_text'])['after']['amount_minor'],9007199254740993)
        self.assertEqual(verify_financial_audit_chain([],case_id=self.case)['status'],'no_recorded_events')

    def test_edit_gap_wrong_case_and_tail_removal(self):
        originals = self.entries()
        for mutate in (
            lambda rows: rows[0].update(payload_text=rows[0]['payload_text']+' '),
            lambda rows: rows[1].update(sequence=3),
            lambda rows: rows[1].update(previous_sha256='a'*64),
            lambda rows: rows.pop(0),
        ):
            rows = copy.deepcopy(originals); mutate(rows)
            with self.assertRaises(LedgerSummaryError): verify_financial_audit_chain(rows,case_id=self.case)
        with self.assertRaises(LedgerSummaryError): verify_financial_audit_chain(originals,case_id=uuid4())
        with self.assertRaises(LedgerSummaryError): verify_financial_audit_chain(originals[:-1],case_id=self.case,expected_head_sha256=originals[-1]['entry_sha256'])
        # Without a separately kept checkpoint, a valid prefix remains internally valid.
        self.assertEqual(verify_financial_audit_chain(originals[:-1],case_id=self.case)['checkpoint_status'],'not_supplied')

    def test_ambiguous_json_and_scope_still_fail_after_rehash(self):
        for payload in ('{"sequence":1,"sequence":1}', '{"value":NaN}', '[]'):
            entry=dict(sequence=1,previous_sha256='0'*64,payload_text=payload,
                entry_sha256=hashlib.sha256(bytes(32)+payload.encode()).hexdigest())
            with self.assertRaises(LedgerSummaryError):verify_financial_audit_chain([entry],case_id=self.case)

    def test_capture_filters_case_preserves_bytes_and_checks_limits(self):
        engine=create_engine('sqlite://')
        FinancialAuditEvent.__table__.create(engine)
        with Session(engine) as db:
            for entry in self.entries(): db.add(FinancialAuditEvent(case_id=self.case,**entry))
            db.commit()
            self.assertEqual(capture_financial_audit_chain(db,case_id=uuid4())['entries'],[])
            captured=capture_financial_audit_chain(db,case_id=self.case)
            self.assertEqual(captured['entries'],self.entries())
            for setting in ('MAX_AUDIT_EVENTS','MAX_AUDIT_BYTES'):
                with patch('services.financial.audit_chain.'+setting,1):
                    with self.assertRaises(LedgerSummaryError):capture_financial_audit_chain(db,case_id=self.case)
        engine.dispose()
