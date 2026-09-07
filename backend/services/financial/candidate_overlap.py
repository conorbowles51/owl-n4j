"""Bounded, read-only source reuse checks across saved PDF mappings.

Findings concern source locations, not whether two economic transactions are the
same. No finding is an exclusion/admission decision or permission to write money.
"""
from itertools import combinations
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialExtractionCandidate
from services.financial.candidate_assessment import current_candidate_original
from services.financial.candidate_store import CandidateStoreError
from services.financial.pdf_candidates import _digest

_MAX_MAPPINGS = 100
_MAX_CANDIDATES = 1000
_MAX_PAIRS = 10000
_MAX_FINDINGS = 100


def _claim(mapping, row, typed):
    proposal = mapping['original']['proposal']
    result = dict(candidate_id=row['id'], mapping_id=mapping['id'], row_index=row['row_index'], status=row['status'])
    if proposal['schema_version'] == 'pdf-grid-mapping-v1':
        rects = [c.locator.rectangle for c in typed.cells]
        boxes = [(r.x0, r.y0, r.x1, r.y1, r.page_width, r.page_height) for r in rects if r is not None]
        return {**result, 'kind':'grid', 'page':proposal['page_number'], 'table':proposal['table_index'],
                'boxes':boxes, 'fully_located':len(boxes)==len(rects)}
    return {**result, 'kind':'text', 'spans':[(c.source.start_char,c.source.end_char) for c in typed.cells],
            'pages':{c.page_number for c in typed.cells}}


def _comparison(left, right):
    if left['kind'] == right['kind'] == 'grid':
        if left['page'] != right['page']:
            return None
        if (left['table'],left['row_index']) == (right['table'],right['row_index']):
            return 'same_stored_row'
        # Bounding rectangles keep pair work bounded. An overlap is a possible
        # reuse, not proof: sparse cell sets can include whitespace between them.
        if not left['fully_located'] or not right['fully_located']:
            return 'comparison_unavailable'
        def bounds(boxes):
            return min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)
        if len({b[4:] for b in left['boxes']+right['boxes']}) != 1:
            return 'comparison_unavailable'
        a,b=bounds(left['boxes']),bounds(right['boxes'])
        if a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]:
            return 'overlapping_source_area'
        return None
    if left['kind'] == right['kind'] == 'text':
        # At most 64 ordered spans per candidate, compared in a linear merge.
        a,b=sorted(left['spans']),sorted(right['spans'])
        i=j=0
        while i<len(a) and j<len(b):
            if a[i][0]<b[j][1] and b[j][0]<a[i][1]:return 'overlapping_source_text'
            if a[i][1]<=b[j][0]:i+=1
            else:j+=1
        return None
    grid,text = (left,right) if left['kind']=='grid' else (right,left)
    if None not in text['pages'] and grid['page'] not in text['pages']:
        return None
    return 'comparison_unavailable'


def check_candidate_source_reuse(session, *, case_id, evidence_file_id):
    if session.scalar(select(EvidenceFile.id).where(EvidenceFile.id==evidence_file_id, EvidenceFile.case_id==case_id).with_for_update(read=True)) is None:
        raise CandidateStoreError('Source file not found in this case.',404)
    mappings=list(session.scalars(select(FinancialCandidateMapping).where(
        FinancialCandidateMapping.case_id==case_id,FinancialCandidateMapping.evidence_file_id==evidence_file_id)
        .order_by(FinancialCandidateMapping.id).limit(_MAX_MAPPINGS+1)))
    if len(mappings)>_MAX_MAPPINGS or sum(m.candidate_count for m in mappings)>_MAX_CANDIDATES:
        raise CandidateStoreError('Source reuse check exceeds 100 mappings or 1,000 readings; no complete comparison was made.',422)
    counts={'pending':0,'resolved':0,'rejected':0}
    claims=[]; revisions=[]
    for mapping in mappings:
        candidate_id=session.scalar(select(FinancialExtractionCandidate.id).where(
            FinancialExtractionCandidate.mapping_id==mapping.id).order_by(FinancialExtractionCandidate.row_index).limit(1))
        if candidate_id is None:raise CandidateStoreError('Saved mapping has no original readings.')
        saved,_,bound=current_candidate_original(session,case_id=case_id,candidate_id=candidate_id)
        typed={row.candidate_key:row for row in bound.candidates}
        revisions.append(dict(mapping_id=saved['id'],mapping_revision=saved['mapping_revision'],
                              reviews=[(r['id'],r['review_revision']) for r in saved['candidates']]))
        for row in saved['candidates']:
            counts[row['status']]+=1
            if row['status']!='rejected':claims.append(_claim(saved,row,typed[row['candidate_key']]))
    examined=found=unavailable=0; findings=[]
    possible=len(claims)*(len(claims)-1)//2
    for left,right in combinations(claims,2):
        if examined>=_MAX_PAIRS:break
        examined+=1
        kind=_comparison(left,right)
        if kind is None:continue
        if kind=='comparison_unavailable':unavailable+=1
        else:found+=1
        if len(findings)<_MAX_FINDINGS:
            fields=('candidate_id','mapping_id','row_index','status')
            findings.append(dict(kind=kind,left={k:left[k] for k in fields},right={k:right[k] for k in fields}))
    return dict(case_id=str(case_id),evidence_file_id=str(evidence_file_id),counts=counts,
        active_readings=len(claims),pairs_examined=examined,total_pairs=possible,
        comparison_complete=examined==possible,source_reuse_pairs=found,unavailable_pairs=unavailable,
        findings=findings,findings_truncated=found+unavailable>len(findings),
        revision=_digest(revisions),applied=False,
        scope='Pending and resolved saved readings from this file; rejected readings are counted but not compared.',
        limitation='Source reuse only, not economic transaction duplication. A snapshot, not ledger admission; rerun after changing reviews.')
