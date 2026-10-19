from collections import defaultdict
from importlib import import_module
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from routers import financial
from services.financial_record_amounts import recorded_amount
from services.financial_export_service import render_financial_export
from services.neo4j.financial_service import FinancialService

@pytest.mark.parametrize('raw,expected', [(0,0),('0.00',0),('€1,234.50',1234.5),('-$1,234.50',-1234.5),('$-123.50',-123.5),('125.50 USD',125.5),('EUR 100.000',100),('.50',.5),('(100.50)',-100.5)])
def test_supported_recorded_amounts_keep_their_sign_and_cents(raw,expected):
    assert recorded_amount(raw)==expected

@pytest.mark.parametrize('raw',[None,True,'','not stated','approx 500','100 to 200','1,23','1.234,56','100.001','1.2.3',float('inf'),float('nan'),'9007199254740993','(-100)','--20'])
def test_unusable_amounts_do_not_become_zero_or_lose_characters(raw):
    assert recorded_amount(raw) is None

def test_record_retains_unreadable_current_and_original_text():
    record=defaultdict(lambda:None,key='r',name='Amount to check',raw_amount='not stated',amount=None,original_amount='approx 500',financial_view_mode='intelligence')
    answer=FinancialService()._record_to_transaction(record,uses_legacy=False,mode='intelligence')
    assert answer['amount'] is None and answer['raw_amount']=='not stated'
    assert answer['original_amount'] is None and answer['original_amount_raw']=='approx 500'

@pytest.mark.parametrize('current,refused',[('not stated',False),('now unreadable',True),(120,True)])
def test_unknown_amount_correction_checks_exact_source_under_the_write_lock(current,refused):
    module=import_module('services.neo4j.financial_service')
    driver=MagicMock();tx=MagicMock()
    tx.run.return_value.single.side_effect=[{'amount':current},{'key':'r','amount':125.5,'original_amount':current}]
    driver.session.return_value.__enter__.return_value.execute_write.side_effect=lambda callback:callback(tx)
    with patch.object(module,'driver',driver):
        if refused:
            with pytest.raises(ValueError):module.FinancialService().update_transaction_amount('r','case',125.5,'Checked PDF',expected_raw_amount='not stated')
            assert tx.run.call_count==1
        else:
            answer=module.FinancialService().update_transaction_amount('r','case',125.5,'Checked PDF',expected_raw_amount='not stated')
            assert answer['original_amount']=='not stated' and answer['amount']==125.5

def test_correction_request_does_not_accept_two_conflicting_expected_values():
    with pytest.raises(ValueError):financial.UpdateAmountRequest(case_id='case',new_amount=125.5,correction_reason='Checked',expected_amount=0,expected_raw_amount='not stated')
    with pytest.raises(ValueError):financial.UpdateAmountRequest(case_id='case',new_amount=9007199254740993,correction_reason='Checked')

def test_nonfinite_original_is_safe_to_return_after_a_confirmed_correction():
    module=import_module('services.neo4j.financial_service')
    driver=MagicMock();tx=MagicMock()
    tx.run.return_value.single.side_effect=[{'amount':float('nan')},{'key':'r','amount':125.5,'original_amount':float('nan')}]
    driver.session.return_value.__enter__.return_value.execute_write.side_effect=lambda callback:callback(tx)
    with patch.object(module,'driver',driver):
        answer=module.FinancialService().update_transaction_amount('r','case',125.5,'Checked PDF',expected_raw_amount='nan')
    assert answer['success'] and answer['original_amount'] is None and answer['original_amount_raw']=='nan'
