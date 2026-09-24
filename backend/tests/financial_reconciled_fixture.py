"""Explicit, fully reconciled synthetic source for admission workflow tests."""
from copy import deepcopy
from hashlib import sha256
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
from tests.test_financial_pdf_geometry_candidates import rectangle


def install_reconciled_source(fixture, *, quiet=False):
    text = fixture.db.get(EvidenceDocumentText, fixture.file.id)
    text.content = 'Account Name: Synthetic Company\nAccount Number: TEST123\nCurrency: EUR\nBank: Synthetic Bank\nStatement Period: January 1, 2023 - December 31, 2023\n'
    text.content_sha256 = sha256(text.content.encode()).hexdigest()
    text.character_count = len(text.content)
    geometry = fixture.db.get(EvidenceTableGeometry, (fixture.file.id,1))
    payload = deepcopy(geometry.payload)
    values = payload[0]['table']['values']
    closing_rows={v['row'] for v in values if v['text']=='Closing Balance'}
    values[:]=[v for v in values if v['row'] not in closing_rows]
    if quiet: values[:] = [v for v in values if v['row'] <= 1]
    index = max(v['row'] for v in values)+1
    for column, value in ((0,'2023-12-31'), (1,'Closing Balance'), (4,'€12,450' if quiet else '€47,450')):
        values.append(dict(row=index,column=column,text=value,locator=rectangle(400,x=20+column*100,width=90,height=15)))
    geometry.payload = payload
    fixture.db.commit()
