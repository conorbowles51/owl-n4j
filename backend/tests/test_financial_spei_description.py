from services.financial.spei_description import kapital_spei
from services.financial.payment_inference import infer_payment_labels
from services.financial.account_mentions import mentions


def text(method='RECEPCION SPEI'):
    return (f'{method} | EXAMPLE BANK | EXAMPLE SERVICES DATO NO VERIFICADO POR ESTA INSTITUCION | '
        '001111111111111111 | TRACKING0000000123456 | 1710258 | TRASPASO ENTRE CUENTAS | '
        'KAPITAL | EXAMPLE SERVICES SA DE CV | 002222222222222222 |')


def test_incoming_and_outgoing_keep_banks_accounts_and_unverified_names_separate():
    for method,direction,remote_role in [('RECEPCION SPEI','credit','sender'),('ENVIO SPEI','debit','recipient')]:
        parsed=kapital_spei(text(method))
        assert parsed['direction']==direction
        assert parsed[remote_role]['party']['name']=='EXAMPLE SERVICES'
        assert parsed[remote_role]['party']['qualifier']=='DATO NO VERIFICADO POR ESTA INSTITUCION'
        assert parsed[remote_role]['bank']['text']=='EXAMPLE BANK'
        assert parsed[remote_role]['account']['text']=='001111111111111111'
        assert not parsed['ownership_established']
        label=infer_payment_labels(text(method),direction=direction,institution='Kapital')
        assert label['counterparty']['value']=='EXAMPLE SERVICES'
        assert label['counterparty']['rule']=='kapital-spei-party'
        assert 'unverified' in label['counterparty']['explanation']


def test_references_are_not_accounts_and_account_spans_quote_the_original():
    source=text()
    refs=mentions(source)
    assert len(refs)==2
    assert {r['value'] for r in refs}=={'001111111111111111','002222222222222222'}
    for ref in refs:
        assert source[ref['start']:ref['end']]==ref['value']
        assert ref['identifier_kind']=='clabe'


def test_wrong_direction_unknown_layout_or_short_account_does_not_guess_a_party():
    assert 'counterparty' not in infer_payment_labels(text(),direction='debit')
    for raw in [text().replace('KAPITAL','UNKNOWN BANK'),text().replace('001111111111111111','1234'),
        text().replace('|',' '),text().replace('RECEPCION SPEI','RETURN SPEI')]:
        assert kapital_spei(raw) is None
